"""Понижения в ST AST: IL, jumps.py, сети LD/FBD/CFC, автомат SFC (ТЗ M2, M3, M5)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from c2s7.emit.printer import Printer
from c2s7.ingest.plcopen import load_plcopen
from c2s7.lower import lower_pou
from c2s7.lower.il import IlError, il_to_st, parse_il
from c2s7.lower.jumps import remove_jumps
from c2s7.model import Origin, Pou
from c2s7.st import nodes as A
from c2s7.st import parser as P

REPO = Path(__file__).resolve().parents[2]
SP17 = REPO / "tests" / "fixtures" / "sp17"
sys.path[:0] = [str(REPO / "tools" / "corpus"), str(REPO / "tools" / "probes")]


def text(stmts: list[A.Stmt]) -> str:
    return "\n".join(Printer("st").stmts(stmts, 0))


def il_pou() -> Pou:
    return Pou(
        "FB_X", "FUNCTION_BLOCK", "IL", A.PouText(A.PouHeader("FUNCTION_BLOCK", "FB_X"), [], []), Origin("x.xml", 1)
    )


def test_il_probe_backward_jump_becomes_repeat() -> None:
    import probe_specs as PS

    out = text(il_to_st(PS.IL_POU.body.text, il_pou()))
    assert out.splitlines()[0] == "i := 0;"
    assert "REPEAT" in out and "UNTIL NOT (i < iN)" in out
    assert "fbEdge(CLK := xIn);" in out and out.endswith("xRise := fbEdge.Q;")


@pytest.mark.parametrize(
    ("il", "st"),
    [
        ("LD a\nST b\nAND c\nST d\n", "b := a;\nd := b AND c;"),
        ("LDN a\nOR( b\nAND c\n)\nST q\n", "q := NOT a OR b AND c;"),
        (
            "LD a\nANDN b\nS q\nR r\n",
            "IF a AND NOT b THEN\n    q := TRUE;\nEND_IF\nIF a AND NOT b THEN\n    r := FALSE;\nEND_IF",
        ),
        ("LD x\nADD 1\nMUL 2\nST y\n", "y := (x + 1) * 2;"),
        ("LD x\nLIMIT 0, 100\nST y\n", "y := LIMIT(x, 0, 100);"),
        ("LD a\nRETC\nLD 1\nST i\n", "IF a THEN\n    RETURN;\nEND_IF\ni := 1;"),
        ("LD a\nCALC fb(IN := b)\n", "IF a THEN\n    fb(IN := b);\nEND_IF"),
        ("LD a\nJMPC skip\nLD 1\nST i\nskip: LD 2\nST j\n", "IF NOT a THEN\n    i := 1;\nEND_IF\nj := 2;"),
    ],
)
def test_il_forms(il: str, st: str) -> None:
    assert text(il_to_st(il, il_pou())) == st


def test_il_cr_survives_store_and_protects_stn() -> None:
    out = text(il_to_st("LD a\nSTN a\nST b\n", il_pou()))
    assert out.startswith("_c2s7_cr := a;\na := NOT _c2s7_cr;\nb := _c2s7_cr;")


def test_il_errors() -> None:
    with pytest.raises(IlError):
        il_to_st("ST x\n", il_pou())
    with pytest.raises(IlError):
        il_to_st("LD a\n)\n", il_pou())
    assert parse_il("(* комментарий *)\nlbl:\n  LD a (* ещё *)\n")[0].label == "lbl"


def _stmts(src: str) -> list[A.Stmt]:
    body, _ = P.parse_body(src, "t.st")
    return body


def test_jumps_forward_backward_and_irreducible() -> None:
    fwd = remove_jumps(
        [*_stmts("IF a THEN\n;\nEND_IF\nx := 1;\n"), A.Jump("L", A.Name("c")), *_stmts("y := 1;\n"), A.Label("L")]
    )
    assert fwd.remaining == [] and "IF NOT c THEN\n    y := 1;\nEND_IF" in text(fwd.stmts)
    back = remove_jumps([A.Label("L"), *_stmts("i := i + 1;\n"), A.Jump("L", A.Name("c"))])
    assert text(back.stmts) == "REPEAT\n    i := i + 1;\nUNTIL NOT c\nEND_REPEAT"
    # переплетённые переходы: L1 ведёт внутрь участка L2
    cross = [
        A.Jump("L1", A.Name("a")),
        A.Label("L2"),
        *_stmts("x := 1;\n"),
        A.Label("L1"),
        *_stmts("y := 2;\n"),
        A.Jump("L2", A.Name("b")),
    ]
    res = remove_jumps(cross)
    assert res.remaining  # неприводимое остаётся GOTO
    dead = remove_jumps([A.Jump("E", None), *_stmts("x := 1;\n"), A.Label("E"), *_stmts("y := 1;\n")])
    assert text(dead.stmts) == "y := 1;"


def lowered(name: str) -> tuple[Pou, str]:
    pou = load_plcopen(SP17 / name).pous[0]
    st = lower_pou(pou, None)
    assert st is not None
    return pou, text(st)


def test_ld_probe() -> None:
    pou, out = lowered("FB_ProbeLd.xml")
    assert "_c2s7_xStart_e := xStart AND NOT _c2s7_xStart_P;" in out
    assert "_c2s7_xStop_e := NOT xStop AND _c2s7_xStop_N;" in out
    assert "IF _c2s7_xStop_e OR NOT xPermit THEN\n    xRun := FALSE;" in out
    assert "xRunInv := NOT xRun;" in out
    statics = [d.name for b, d in pou.decls() if b.kind == "VAR"]
    assert statics == ["_c2s7_xStart_P", "_c2s7_xStop_N"]
    assert pou.net is not None and pou.net.meta.edge_bits


def test_fbd_probe_jump_folds() -> None:
    _, out = lowered("FB_ProbeFbd.xml")
    assert out.splitlines()[0] == "xHigh := rLevel > rHigh;"
    assert "IF xEnable THEN" in out and "xAlarm := (xHigh OR xAlarm) AND NOT xAck;" in out
    assert out.endswith("xOut := xAlarm;")


def test_cfc_feedback_is_static() -> None:
    pou, out = lowered("FB_ProbeCfc.xml")
    assert out.splitlines() == [
        "_c2s7_add_1 := rIn + _c2s7_limit_2;",
        "_c2s7_limit_2 := LIMIT(rLo, _c2s7_add_1, rHi);",
        "rOut := _c2s7_limit_2;",
    ]
    kinds = {d.name: b.kind for b, d in pou.decls()}
    assert kinds["_c2s7_limit_2"] == "VAR" and kinds["_c2s7_add_1"] == "VAR_TEMP"
    _, out2 = lowered("FB_ProbePcfc.xml")
    assert out2.splitlines()[0] == "rEarly := _c2s7_mul_2;"  # порядок 1 читает выход шага 2 — прошлый цикл


def test_sfc_probe_automaton_shape() -> None:
    pou, out = lowered("PRG_ProbeSfc.xml")
    lines = out.splitlines()
    assert lines.index("IF _c2s7_ActN_qp AND NOT _c2s7_ActN_q THEN") < lines.index("IF _c2s7_ActN_q THEN")
    assert "_c2s7_ActS_s := (_c2s7_ActS_s OR StepA_x) AND NOT StepB_x;" in out
    assert "_c2s7_ActP_q := StepA_x AND NOT StepA_xp;" in out
    assert "IF _c2s7_Par1_a AND _c2s7_Par2_a AND Par1_t >= T#100MS THEN" in out
    init = next(d for _, d in pou.decls() if d.name == "Init_x")
    assert isinstance(init.init, A.Literal) and init.init.value is True
