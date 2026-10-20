"""c2s7.sim: семантика CODESYS (проба M0) — перенос целых, REAL float32, таймеры, SR/RS, счётчики, функции."""

from __future__ import annotations

from pathlib import Path

import pytest
from c2s7.ingest.layout import load_single_st
from c2s7.sim import values as V
from c2s7.sim.interp import Clock, Sim, SimError
from c2s7.sim.stdlib import call_function, convert

SRC = """
FUNCTION_BLOCK FB_T
VAR_INPUT
    xIn : BOOL;
    xSet : BOOL;
    xReset : BOOL;
    xCu : BOOL;
END_VAR
VAR_OUTPUT
    xTon : BOOL;
    tEt : TIME;
    xSr : BOOL;
    xRs : BOOL;
    wCv : WORD;
    iWrap : INT;
    rHalf : REAL;
END_VAR
VAR
    fbTon : TON;
    fbSr : SR;
    fbRs : RS;
    fbCtu : CTU;
    iCnt : INT := 32767;
END_VAR
fbTon(IN := xIn, PT := T#1S, Q => xTon, ET => tEt);
fbSr(SET1 := xSet, RESET := xReset, Q1 => xSr);
fbRs(SET := xSet, RESET1 := xReset, Q1 => xRs);
fbCtu(CU := xCu, PV := 3);
wCv := fbCtu.CV;
iWrap := iCnt + 1;
rHalf := 1.0 / 3.0;
END_FUNCTION_BLOCK

FUNCTION F_Out : INT
VAR_INPUT
    x : BOOL;
END_VAR
VAR_OUTPUT
    o : INT := 7;
END_VAR
IF x THEN
    o := 99;
END_IF
F_Out := o;
END_FUNCTION
"""


@pytest.fixture()
def sim(tmp_path: Path) -> Sim:
    f = tmp_path / "s.st"
    f.write_text(SRC, encoding="utf-8")
    return Sim(load_single_st(f), Clock())


def test_fb_semantics(sim: Sim) -> None:
    inst = sim.new_instance(sim.pous["FB_T"])
    sim.call_fb(inst, {"xIn": True, "xSet": True, "xReset": True, "xCu": True})
    assert inst.get("xSr") is True and inst.get("xRs") is False  # SR — установка доминирует, RS — сброс
    assert inst.get("iWrap") == -32768
    assert inst.get("rHalf") == V.f32(1 / 3) and inst.get("wCv") == 1
    sim.clock.now_ms = 999
    sim.call_fb(inst, {"xCu": False})
    assert inst.get("xTon") is False and inst.get("tEt") == 999
    sim.clock.now_ms = 1000
    sim.call_fb(inst, {})
    assert inst.get("xTon") is True and inst.get("tEt") == 1000


def test_function_outputs_reinitialised(sim: Sim) -> None:
    from c2s7.st import nodes as A

    frame = sim.new_instance(sim.pous["FB_T"])
    frame.vars["O1"] = 0
    frame.types["O1"] = A.NamedType("INT")
    r1, _ = sim.call_function(
        sim.pous["F_OUT"], [A.Arg(A.Literal("bool", "TRUE", True), "x"), A.Arg(A.Name("O1"), "o", output=True)], frame
    )
    assert (r1, frame.get("O1")) == (99, 99)
    r2, _ = sim.call_function(
        sim.pous["F_OUT"], [A.Arg(A.Literal("bool", "FALSE", False), "x"), A.Arg(A.Name("O1"), "o", output=True)], frame
    )
    assert (r2, frame.get("O1")) == (7, 7)


def test_conversions_and_functions() -> None:
    assert [convert("REAL_TO_INT", x)[0] for x in (2.5, 3.5, -2.5, -3.5, 0.5, 1.5)] == [3, 4, -3, -4, 1, 2]
    assert convert("DINT_TO_INT", 40000)[0] == -25536
    assert convert("INT_TO_WORD", -1)[0] == 65535
    assert call_function("LIMIT", [(None, (10, "INT")), (None, (5, "INT")), (None, (0, "INT"))])[0] == 0  # MN > MX → MX
    assert call_function("MID", [(None, ("ABCDEF", "STRING")), (None, (2, "INT")), (None, (3, "INT"))])[0] == "CD"
    assert call_function("CONCAT", [("STR1", ("ab", "STRING")), ("STR2", ("c", "STRING"))])[0] == "abc"
    assert call_function("SHR", [(None, (0xABCD, "WORD")), (None, (8, "INT"))])[0] == 0xAB
    assert call_function("ROL", [(None, (0x8001, "WORD")), (None, (1, "INT"))])[0] == 0x0003


def test_time_wraps_unsigned() -> None:
    assert V.coerce(-1, "TIME") == 2**32 - 1
    assert V.coerce(70000, "WORD") == 70000 - 65536


def test_counter_saturates() -> None:
    from c2s7.sim.stdlib import CTD, CTU

    c = CTU(Clock())
    for _ in range(70000):
        c.set("CU", True)
        c.run()
        c.set("CU", False)
        c.run()
    assert c.get("CV") == 65535
    d = CTD(Clock())
    d.set("LOAD", True)
    d.set("PV", 2)
    d.run()
    d.set("LOAD", False)
    for _ in range(5):
        d.set("CD", True)
        d.run()
        d.set("CD", False)
        d.run()
    assert d.get("CV") == 0 and d.get("Q") is True


def test_division_by_zero_is_error(tmp_path: Path) -> None:
    f = tmp_path / "d.st"
    f.write_text(
        "FUNCTION_BLOCK FB_D\nVAR\n    a : INT;\n    b : INT;\nEND_VAR\na := a / b;\nEND_FUNCTION_BLOCK\n",
        encoding="utf-8",
    )
    sim = Sim(load_single_st(f))
    with pytest.raises(SimError):
        sim.call_fb(sim.new_instance(sim.pous["FB_D"]))
