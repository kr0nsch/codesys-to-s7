"""CLI (коды выхода и форматы), SVG-схемы и сборка сайта."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from c2s7.cli import main
from c2s7.render.cli import render_pou
from c2s7.render.tree import Box, Par, Series, from_flgnet, from_netir

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "corpus" / "zarechnaya.xml"
RING = REPO / "tests" / "fixtures" / "s7-to-codesys"


def test_inventory_and_analyze_formats(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["inventory", str(CORPUS)]) == 0
    out = capsys.readouterr().out
    assert "PRG_Backwash" in out and "SFC" in out
    assert main(["inventory", str(CORPUS), "--format", "json"]) == 0
    inv = json.loads(capsys.readouterr().out)
    assert inv["pous"]
    assert main(["analyze", str(CORPUS), "--format", "json", "--fail-on", "never"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["totals"]["by_outcome"]["manual"] > 0
    assert main(["analyze", str(CORPUS), "--fail-on", "manual"]) == 1  # есть manual (IO-NOMAP, ФБ в функции)
    capsys.readouterr()
    for fmt in ("md", "html", "text"):
        assert (
            main(["analyze", str(CORPUS), "--format", fmt, "--fail-on", "never", "--cpu", "s7-1200", "--tia", "V19"])
            == 0
        )
        assert capsys.readouterr().out.strip()


def test_input_and_profile_errors(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert main(["analyze", str(tmp_path / "нет.xml")]) == 2
    assert main(["analyze", str(CORPUS), "--tia", "V20"]) == 2  # V20 исключён: аномалия схем
    bad = tmp_path / "bad.st"
    bad.write_text("FUNCTION_BLOCK X\nVAR\n a : INT\nEND_VAR\nEND_FUNCTION_BLOCK\n", encoding="utf-8")
    assert main(["analyze", str(bad)]) == 2
    assert main(["explain", "C2S7-НЕТ"]) == 2
    capsys.readouterr()


def test_migrate_zip_bundle_probe_explain(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    out = tmp_path / "zar"
    z = tmp_path / "zar.zip"
    code = main(["migrate", str(CORPUS), "--out", str(out), "--zip", str(z), "--bundle", "--fail-on", "verify"])
    assert code == 1  # verify и manual есть
    assert (out / "tia" / "sources" / "all.scl").exists()
    assert (out / "tia" / "simaticml" / "FB_LevelAlarm.xml").exists()
    assert (out / "probe" / "RESULTS.csv").exists()
    with zipfile.ZipFile(z) as f:
        assert "MIGRATION_REPORT.json" in f.namelist()
    assert main(["probe", str(out)]) == 0
    assert main(["explain", "C2S7-SEM-SRRS"]) == 0
    text = capsys.readouterr().out
    assert "крест-накрест" in text.lower() or "SR" in text
    assert (
        main(
            [
                "migrate",
                str(CORPUS),
                "--out",
                str(tmp_path / "scl"),
                "--graphics",
                "scl",
                "--sfc",
                "graph",
                "--cpu",
                "s7-1200",
                "--tia",
                "V19",
            ]
        )
        == 0
    )
    assert not (tmp_path / "scl" / "tia" / "simaticml").exists()


def test_render_pou_both_sides(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    svgs = render_pou(CORPUS, "PRG_PumpInterlock")
    assert set(svgs) == {"source", "target"}
    assert svgs["target"].startswith("<svg") and "схема построена c2s7, не снимок TIA" in svgs["target"]
    assert main(["render", str(CORPUS), "--pou", "FB_PiCfc", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "FB_PiCfc.source.svg").exists() and not (tmp_path / "FB_PiCfc.target.svg").exists()
    capsys.readouterr()
    with pytest.raises(ValueError):
        render_pou(CORPUS, "F_Convert")


def test_trees() -> None:
    from c2s7.api import load_input, migrate
    from c2s7.convert.core import Options

    proj = load_input(CORPUS)
    ld = next(p for p in proj.pous if p.name == "PRG_PumpInterlock")
    assert ld.net is not None
    views = from_netir(ld.net)
    assert len(views) == 5 and isinstance(views[0].rungs[0].flow, Par)
    res = migrate(load_input(CORPUS), Options())
    lad = from_flgnet(res.simaticml["tia/simaticml/PRG_PumpInterlock.xml"])
    assert [len(v.rungs) for v in lad] == [1, 1, 1, 1, 1]
    assert isinstance(lad[3].rungs[0].flow, Series)
    fbd = from_flgnet(res.simaticml["tia/simaticml/FB_LevelAlarm.xml"])
    assert isinstance(fbd[0].sinks[0].node, Box) and fbd[0].sinks[0].node.type == "Gt"
    assert fbd[3].label == "lblOut"


def test_site_build(tmp_path: Path) -> None:
    from c2s7.site.build import build_site

    out = tmp_path / "site"
    assert build_site(out, root=REPO) == 0
    index = json.loads((out / "data" / "index.json").read_text(encoding="utf-8"))
    assert [c["id"] for c in index["cases"]] == ["ring", "corpus", "process-lib"]
    assert len(index["traps"]) == 6
    srrs = next(t for t in index["traps"] if t["id"] == "srrs")
    assert '"CDS_SR"' in srrs["scl"]
    iw = next(t for t in index["traps"] if t["id"] == "iw5")
    assert "C2S7-ADDR-MAP" in iw["rules"]
    data = json.loads((out / "data" / "corpus.s7-1500.json").read_text(encoding="utf-8"))
    pumps = next(p for p in data["pous"] if p["name"] == "PRG_PumpInterlock")
    assert (out / pumps["svg_source"]).exists() and (out / pumps["svg_target"]).exists()
    assert (out / data["zip"]).exists()
    assert (out / "index.html").exists() and (out / "assets" / "app.js").exists()
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "http://" not in html and "https://" not in html  # чужих доменов нет
