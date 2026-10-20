"""Выход migrate (BOM/CRLF, порядок, шапка, теги, детерминизм zip) и разбор PLCopen CODESYS 3.5.17."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import jsonschema
import pytest

from c2s7.api import load_input, run_migrate
from c2s7.convert.core import Options
from c2s7.ingest.plcopen import load_plcopen
from c2s7.pathsort import sorted_paths

REPO = Path(__file__).resolve().parents[2]
SP17 = REPO / "tests" / "fixtures" / "sp17"
RING = REPO / "tests" / "fixtures" / "s7-to-codesys"


@pytest.fixture(scope="module")
def ring_out(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("ring") / "out"
    run_migrate(RING, out, Options(), zip_path=out.parent / "ring.zip")
    return out


def test_tia_files_bom_crlf_and_header(ring_out: Path) -> None:
    srcs = sorted((ring_out / "tia" / "sources").glob("*"))
    assert srcs and srcs[0].name.startswith("001_")
    for f in srcs:
        data = f.read_bytes()
        assert data.startswith(b"\xef\xbb\xbf"), f
        assert b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b""), f
        text = data.decode("utf-8-sig")
        assert text.startswith("// создано c2s7 0.1.0 · источник ")
        assert "сгенерир" not in text.lower()
    kinds = [f.suffix for f in srcs]
    assert kinds.index(".db") > kinds.index(".udt")  # типы раньше DB
    assert not (ring_out / "tia" / "sources" / "001_Main.scl").exists()  # OB в исходник не пишутся


def test_roundtrip_files(ring_out: Path) -> None:
    tags = (ring_out / "roundtrip" / "PlcTags.csv").read_text(encoding="utf-8").splitlines()
    assert tags[0] == "Name,Path,Data Type,Logical Address,Comment,Value"
    assert any(line.startswith("PT101_Raw,IO,Int,%IW64,") for line in tags)  # %IW32 CODESYS → %IW64 S7
    obc = json.loads((ring_out / "roundtrip" / "ob_config.json").read_text(encoding="utf-8"))
    assert obc["Main"]["number"] == 1 and obc["Cyclic interrupt"]["number"] == 30
    assert (ring_out / "tia" / "tags" / "PLCTags.xlsx").exists()
    for name in ("TASKS.md", "IO_MAP.csv", "MANUAL_STEPS.md", "BlockProperties.csv"):
        assert (ring_out / "roundtrip" / name).exists()


def test_report_validates_against_schemas(ring_out: Path) -> None:
    data = json.loads((ring_out / "MIGRATION_REPORT.json").read_text(encoding="utf-8"))
    core = json.loads((REPO / "schemas" / "report-core.schema.json").read_text(encoding="utf-8"))
    ext = json.loads((REPO / "schemas" / "report.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(data, core)
    jsonschema.validate(data, ext)
    assert data["effort"]["calibration"] == "модель, не калибрована"
    assert data["findings"] == sorted(
        data["findings"],
        key=lambda f: (f["origin"]["file"], f["origin"].get("line", 0), f["origin"].get("column", 0), f["rule"]),
    )
    assert (ring_out / "trace.json").exists() and (ring_out / "MIGRATION_REPORT.html").read_text(
        encoding="utf-8"
    ).startswith("<!doctype html>")


def test_zip_deterministic(ring_out: Path, tmp_path: Path) -> None:
    out2 = tmp_path / "again"
    run_migrate(RING, out2, Options(), zip_path=tmp_path / "again.zip")
    a = hashlib.sha256((ring_out.parent / "ring.zip").read_bytes()).hexdigest()
    b = hashlib.sha256((tmp_path / "again.zip").read_bytes()).hexdigest()
    assert a == b
    with zipfile.ZipFile(tmp_path / "again.zip") as z:
        infos = z.infolist()
        assert [i.filename for i in infos] == sorted(i.filename for i in infos)
        assert all(i.compress_type == zipfile.ZIP_STORED and i.date_time == (1980, 1, 1, 0, 0, 0) for i in infos)


def test_plcopen_languages_from_codesys_exports() -> None:
    ld = load_plcopen(SP17 / "FB_ProbeLd.xml").pous[0]
    assert ld.language == "LD" and ld.net is not None and len(ld.net.networks) == 4
    first = ld.net.networks[0]
    assert first.title == "Пуск по фронту"
    assert any(e.kind == "contact" and e.edge == "rising" for e in first.elements)
    fbd = load_plcopen(SP17 / "FB_ProbeFbd.xml").pous[0]
    assert fbd.net is not None and [n.title for n in fbd.net.networks][1] == "Пропуск при отключении"
    assert fbd.net.networks[3].label == "lblEnd"
    cfc = load_plcopen(SP17 / "FB_ProbeCfc.xml").pous[0]
    assert cfc.language == "CFC" and cfc.net is not None
    assert sorted(e.order for e in cfc.net.networks[0].elements if e.order) == [1, 2, 3]
    sfc = load_plcopen(SP17 / "PRG_ProbeSfc.xml").pous[0]
    assert sfc.sfc is not None and [s.name for s in sfc.sfc.initial] == ["Init"]
    assert sfc.sfc.step("Init").step_action == "ActInit"
    assert {a.qualifier for a in sfc.sfc.step("StepA").actions} == {"N", "S", "P"}
    alt = [t for t in sfc.sfc.transitions if t.source == ["Init"]]
    assert [t.target for t in alt] == [["StepA"], ["StepB"]]
    par = [t for t in sfc.sfc.transitions if set(t.source) == {"Par1", "Par2"}]
    assert par and par[0].target == ["Init"]


def test_application_export_tasks_and_gvl() -> None:
    proj = load_input(SP17 / "form_Application.xml")
    assert [(t.name, t.kind, t.interval_ms) for t in proj.tasks] == [
        ("Task_Fast", "cyclic", 10.0),
        ("Task_Free", "freewheeling", None),
    ]
    g = proj.gvls[0]
    kinds = {(tuple(b.qualifiers), d.name) for b, d in g.decls()}
    assert (("RETAIN", "PERSISTENT"), "diHours") in kinds or (("PERSISTENT", "RETAIN"), "diHours") in kinds
    oop = proj.pou("FB_ProbeOop")
    assert oop is not None and oop.methods and oop.properties and oop.actions


def test_path_order_same_on_windows_and_linux() -> None:
    """Порядок путей не зависит от ОС: как в Windows (без учёта регистра), иначе отчёт и zip расходятся."""
    from pathlib import PurePosixPath, PureWindowsPath

    names = ["FB_Latch", "F_Convert", "b/x", "A/y", "a b/z"]
    want = ["A/y", "a b/z", "b/x", "F_Convert", "FB_Latch"]
    assert [p.as_posix() for p in sorted_paths(PurePosixPath(n) for n in names)] == want
    assert [p.as_posix() for p in sorted_paths(PureWindowsPath(n) for n in names)] == want
    assert [p.as_posix() for p in sorted(PureWindowsPath(n) for n in names)] == want
