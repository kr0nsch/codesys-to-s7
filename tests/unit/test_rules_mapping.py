"""Реестр правил, корпус, документы (RULES.md, MAPPING.md), обратные правила к «авто» s7conv, модель трудозатрат."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest
from c2s7 import mapping, rules
from c2s7.api import migrate
from c2s7.convert.core import Options
from c2s7.ingest.layout import load_layout, load_single_st
from c2s7.model import Origin
from c2s7.rules import Finding, effort, registry

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "tests" / "corpus"
TMP = Path(tempfile.mkdtemp(prefix="c2s7-rev-"))
GRAPHIC_OR_PROJECT = {
    "C2S7-GFX-",
    "C2S7-IL",
    "C2S7-PROF-LANG",
    "C2S7-IO-NOMAP",
    "C2S7-ACT",
    "C2S7-OOP",
    "C2S7-TASK-",
    "C2S7-RING-",
}


def test_registry_complete() -> None:
    reg = registry()
    assert len(reg) >= 50
    for rid, r in reg.items():
        assert re.match(r"^C2S7-[A-Z0-9-]+$", rid)
        assert r.outcome in rules.OUTCOMES
        assert r.source and r.why and r.fix
        mn, mode, mx = r.effort
        assert 0 <= mn <= mode <= mx


PENDING_STAGE_B = {
    "C2S7-GFX-ENO",
    "C2S7-GFX-GOTO",
    "C2S7-GFX-DOUBLECOIL",
    "C2S7-GFX-CFCFB",
    "C2S7-GFX-EDGE",
    "C2S7-GFX-SFCQ",
    "C2S7-GFX-SFC",
    "C2S7-GFX-SCL",
    "C2S7-GFX-ORDER",
    "C2S7-IL",
    "C2S7-PROF-LANG",
}


def test_every_rule_has_corpus() -> None:
    for rid in registry():
        if rid in PENDING_STAGE_B:
            continue
        d = CORPUS / rid
        assert (d / "expected.json").exists(), f"нет корпуса {rid}"
        assert any((d / "pos" / n).exists() for n in ("input.st", "input.xml", "input")), rid
        assert any((d / "neg" / n).exists() for n in ("input.st", "input.xml", "input")), rid


def test_docs_are_generated() -> None:
    assert (REPO / "docs" / "RULES.md").read_text(encoding="utf-8") == rules.render_md()
    assert (REPO / "docs" / "MAPPING.md").read_text(encoding="utf-8") == mapping.render_md()


def test_effort_deterministic() -> None:
    fs = [
        Finding("C2S7-TYPE-TIME", "review", "P", "ST", Origin("x")),
        Finding("C2S7-OOP", "manual", "P", "ST", Origin("x")),
    ]
    a, b = effort(fs), effort(fs)
    assert a == b and a["model"] == "triangular-mc" and a["runs"] == 10_000 and a["seed"] == 20261019
    assert 0 < a["p50_h"] < a["p90_h"]
    assert effort([])["p50_h"] == 0.0


def _load(path: Path):  # type: ignore[no-untyped-def]
    if path.is_dir():
        return load_layout(path)
    if path.suffix == ".xml":
        from c2s7.ingest.plcopen import load_plcopen

        return load_plcopen(path)
    return load_single_st(path)


def _corpus_ids() -> list[str]:
    return sorted(p.name for p in CORPUS.iterdir() if (p / "expected.json").exists()) if CORPUS.exists() else []


@pytest.mark.parametrize("rid", _corpus_ids())
def test_corpus(rid: str) -> None:
    d = CORPUS / rid
    exp = json.loads((d / "expected.json").read_text(encoding="utf-8"))
    for kind in ("pos", "neg"):
        inp = next(d / kind / n for n in ("input.st", "input.xml", "input") if (d / kind / n).exists())
        opts = dict(exp.get("options", {}))
        opts.update(exp.get(f"options_{kind}", {}))
        io_map = opts.pop("io_map", None)
        o = Options(**opts)
        if io_map:
            from c2s7.ingest.iomap import load_io_map

            o.io_map = load_io_map(d / kind / io_map)
        res = migrate(_load(inp), o)
        hits = [f for f in res.collector.findings if f.rule == exp["rule"] or exp["rule"] in f.related]
        if kind == "pos":
            assert len(hits) >= exp["pos_min"], (rid, [f.rule for f in res.collector.findings])
        else:
            assert len(hits) == exp["neg"], (rid, [(f.rule, f.fragment) for f in hits])


# ---- обратные правила к строкам «авто» s7conv
def _fb_scl(decl: str, body: str, kind: str = "FUNCTION_BLOCK", ret: str = "") -> str:
    from c2s7.emit.scl import block_text

    head = f"{kind} FB_X" + (f" : {ret}" if ret else "")
    text = f"{head}\n{decl}\n{body}\nEND_{kind}\n"
    src = TMP / "_rev.st"
    src.write_text(text, encoding="utf-8")
    res = migrate(load_single_st(src), Options())
    return "\n".join(block_text(b) for b in res.blocks)


VARS = (
    "VAR_INPUT\n    a : BOOL;\nEND_VAR\nVAR\n    x : REAL;\n    r : INT;\n    i : INT;\n    b : BOOL;\n    w : WORD;\n    s : STRING(80);\n"
    "    ws : WSTRING(80);\n    t : TIME;\n    lt : LTIME;\n    d : DATE;\nEND_VAR"
)


@pytest.mark.parametrize(
    "row",
    [
        r
        for r in mapping.reverse_rules()
        if r["kind"] in ("body", "type", "decl", "fc", "gvl", "gvlconst", "gvlretain", "addr", "layout")
    ],
    ids=lambda r: str(r["line"]),
)
def test_reverse_rule(row: dict[str, object]) -> None:
    kind, cds, expect = row["kind"], str(row["cds"]), str(row["expect"])
    if kind == "body":
        out = _fb_scl(VARS, cds)
    elif kind == "type":
        out = _fb_scl(f"VAR\n    v : {cds};\nEND_VAR", "")
    elif kind == "decl":
        out = _fb_scl(cds, "")
    elif kind == "fc":
        decl = cds if cds.startswith("VAR") else "VAR_INPUT\n    a : BOOL;\nEND_VAR"
        body = "" if cds.startswith("VAR") else cds.replace("FC_X", "FB_X")
        out = (
            _fb_scl(decl, body + ("\nFB_X := 0;" if cds.startswith("VAR") else ""), "FUNCTION", "INT")
            .replace('"FB_X"', '"FC_X"')
            .replace("#FB_X", "#FC_X")
        )
    elif kind in ("gvl", "gvlconst", "gvlretain"):
        src = TMP / "_rev_gvl.st"
        gvl_text = cds if cds.startswith("VAR_GLOBAL") else "VAR_GLOBAL\n    a : INT;\nEND_VAR"
        src.write_text(
            gvl_text
            + "\n"
            + (
                "FUNCTION_BLOCK FB_U\n" + cds.replace("GVL_X", "_rev_gvl") + "\nEND_FUNCTION_BLOCK\n"
                if "GVL_X" in cds
                else ""
            ),
            encoding="utf-8",
        )
        res = migrate(load_single_st(src), Options())
        from c2s7.emit import tags as TG
        from c2s7.emit.scl import block_text

        out = "\n".join(block_text(b) for b in res.blocks).replace("_rev_gvl", "GVL_X")
        if kind == "gvlconst":
            out += "\n" + ("User constants" if res.constants else "")
            assert TG.build_xlsx(res)
    elif kind == "addr":
        from c2s7.convert import addr as AD

        out = str(AD.to_s7(cds)[0])
    else:  # layout
        if cds.startswith("TYPE"):
            src = TMP / "_rev_t.st"
            src.write_text(cds + "\n", encoding="utf-8")
            from c2s7.emit.scl import block_text

            out = "\n".join(block_text(b) for b in migrate(load_single_st(src), Options()).blocks)
        elif cds.startswith("FUNCTION "):
            out = _fb_scl("VAR_INPUT\n    a : BOOL;\nEND_VAR", "FB_X := 1.0;", "FUNCTION", "REAL").replace(
                '"FB_X"', '"FC_X"'
            )
        elif cds.startswith("FUNCTION_BLOCK"):
            out = _fb_scl("VAR\n    a : INT;\nEND_VAR", "a := 1;")
        elif "GVL_InstanceDBs" in cds or "IEC_TIMER" in expect:
            src = TMP / "_rev_i" / "src" / "GVLs"
            src.mkdir(parents=True, exist_ok=True)
            (src / "GVL_InstanceDBs.gvl.st").write_text(
                "{attribute 'qualified_only'}\nVAR_GLOBAL\n    T_DB : TON;\nEND_VAR\n", encoding="utf-8"
            )
            from c2s7.emit.scl import block_text

            out = "\n".join(block_text(b) for b in migrate(load_layout(src.parent.parent), Options()).blocks)
        else:
            src = TMP / "_rev_g.st"
            src.write_text("{attribute 'qualified_only'}\nVAR_GLOBAL\n    a : INT;\nEND_VAR\n", encoding="utf-8")
            from c2s7.emit.scl import block_text

            out = "\n".join(block_text(b) for b in migrate(load_single_st(src), Options()).blocks).replace(
                "_rev_g", "GVL_X"
            )
    assert expect in out, f"стр. {row['line']}: нет «{expect}» в\n{out}"


def test_reverse_covers_all_auto_rows() -> None:
    """Каждая строка «авто» MAPPING.md s7conv @ 2285760c есть в reverse.yaml (по номеру строки)."""
    clone = REPO / ".cache" / "s7-to-codesys@2285760c" / "docs" / "MAPPING.md"
    if not clone.exists():
        pytest.skip("нет клона s7-to-codesys @ 2285760c в .cache/")
    auto = [
        i + 1 for i, line in enumerate(clone.read_text(encoding="utf-8").splitlines()) if re.search(r"\|\s*авто", line)
    ]
    have = {int(str(r["line"])) for r in mapping.reverse_rules()}
    missing = [n for n in auto if n not in have]
    assert not missing, f"нет обратных правил для строк {missing}"
    assert not any(r["line"] == 93 for r in mapping.reverse_rules())  # SR/RS 1.0.0 не зеркалируется
