"""c2s7.sim: операторы, типы и стандартные блоки за пределами основных тестов (значения посчитаны вручную)."""

from __future__ import annotations

from pathlib import Path

import pytest
from c2s7.ingest.layout import load_single_st
from c2s7.sim.interp import Clock, Sim, SimError

SRC = """
TYPE E_Mode :
(
    Off := 0,
    Run := 5,
    Fault
) INT;
END_TYPE

TYPE ST_Pair :
STRUCT
    a : INT := 3;
    b : REAL := 1.5;
END_STRUCT
END_TYPE

TYPE T_Pct : INT(0..100);
END_TYPE

FUNCTION F_Add3 : DINT
VAR_INPUT
    x : DINT;
END_VAR
F_Add3 := x + 3;
END_FUNCTION

FUNCTION_BLOCK FB_All
VAR_INPUT
    iSel : INT;
    sIn : STRING(40);
    xGo : BOOL;
END_VAR
VAR_OUTPUT
    iCase, iFor, iWhile, iRepeat, iExit : INT;
    sLeft, sRight, sMid, sIns, sDel, sRep, sCat : STRING(40);
    iLen, iFind : INT;
    rAbs, rSqrt, rExpt, rMax, rMin : REAL;
    iSel2, iMux : INT;
    eMode : E_Mode;
    iEnum : INT;
    aArr : ARRAY[1..5] OF INT;
    stP : ST_Pair;
    pct : T_Pct;
    xTof, xTp : BOOL;
    wCv : WORD;
    xQu, xQd : BOOL;
    diF : DINT;
    wShl, wRor : WORD;
    bAnd : BYTE;
    xNot : BOOL;
    iMod : INT;
    rDiv : REAL;
    diConv : DINT;
    rConv : REAL;
END_VAR
VAR
    i : INT;
    fbTof : TOF;
    fbTp : TP;
    fbCtud : CTUD;
END_VAR
CASE iSel OF
    1, 2: iCase := 10;
    3..5: iCase := 20;
ELSE
    iCase := 30;
END_CASE
iFor := 0;
FOR i := 10 TO 1 BY -3 DO
    iFor := iFor + i;
END_FOR
iWhile := 0;
WHILE iWhile < 7 DO
    iWhile := iWhile + 2;
END_WHILE
iRepeat := 0;
REPEAT
    iRepeat := iRepeat + 1;
UNTIL iRepeat >= 3
END_REPEAT
iExit := 0;
FOR i := 1 TO 10 DO
    IF i = 2 THEN
        CONTINUE;
    END_IF
    IF i > 4 THEN
        EXIT;
    END_IF
    iExit := iExit + i;
END_FOR
sLeft := LEFT(sIn, 3);
sRight := RIGHT(sIn, 2);
sMid := MID(sIn, 2, 2);
sIns := INSERT(sIn, 'XY', 1);
sDel := DELETE(sIn, 2, 1);
sRep := REPLACE(sIn, 'Z', 1, 3);
sCat := CONCAT(sIn, '!');
iLen := LEN(sIn);
iFind := FIND(sIn, 'CD');
rAbs := ABS(-2.5);
rSqrt := SQRT(16.0);
rExpt := EXPT(2.0, 3.0);
rMax := MAX(1.0, 7.5, 3.0);
rMin := MIN(4.0, -1.0);
iSel2 := SEL(xGo, 1, 2);
iMux := MUX(2, 5, 6, 7);
eMode := E_Mode.Fault;
iEnum := E_Mode.Run;
FOR i := 1 TO 5 DO
    aArr[i] := i * i;
END_FOR
stP.a := stP.a + 1;
pct := 50;
fbTof(IN := xGo, PT := T#200MS);
xTof := fbTof.Q;
fbTp(IN := xGo, PT := T#300MS);
xTp := fbTp.Q;
fbCtud(CU := xGo, CD := FALSE, RESET := FALSE, LOAD := FALSE, PV := 2);
wCv := fbCtud.CV;
xQu := fbCtud.QU;
xQd := fbCtud.QD;
diF := F_Add3(x := 4);
wShl := SHL(WORD#16#00F0, 4);
wRor := ROR(WORD#16#0001, 1);
bAnd := BYTE#16#F0 AND BYTE#16#3C;
xNot := NOT xGo;
iMod := -7 MOD 3;
rDiv := 1.0 / 4.0;
diConv := INT_TO_DINT(iSel) * 100000;
rConv := DINT_TO_REAL(diConv);
END_FUNCTION_BLOCK
"""


@pytest.fixture()
def sim(tmp_path: Path) -> Sim:
    f = tmp_path / "all.st"
    f.write_text(SRC, encoding="utf-8")
    return Sim(load_single_st(f), Clock())


def test_statements_types_and_functions(sim: Sim) -> None:
    inst = sim.new_instance(sim.pous["FB_ALL"])
    sim.call_fb(inst, {"iSel": 4, "sIn": "ABCDEF", "xGo": True})
    g = inst.get
    assert (g("iCase"), g("iFor"), g("iWhile"), g("iRepeat"), g("iExit")) == (20, 22, 8, 3, 8)
    assert (g("sLeft"), g("sRight"), g("sMid"), g("sCat"), g("iLen"), g("iFind")) == (
        "ABC",
        "EF",
        "BC",
        "ABCDEF!",
        6,
        3,
    )
    # INSERT после позиции 1; DELETE 2 символа с позиции 1; REPLACE 1 символ с позиции 3
    assert (g("sIns"), g("sDel"), g("sRep")) == ("AXYBCDEF", "CDEF", "ABZDEF")
    assert (g("rAbs"), g("rSqrt"), g("rExpt"), g("rMax"), g("rMin")) == (2.5, 4.0, 8.0, 7.5, -1.0)
    assert (g("iSel2"), g("iMux"), g("iEnum")) == (2, 7, 5)
    assert g("eMode") == 6
    assert [g("aArr")[i] for i in range(1, 6)] == [1, 4, 9, 16, 25]
    assert g("pct") == 50 and g("diF") == 7
    assert (g("wShl"), g("wRor"), g("bAnd"), g("xNot")) == (0x0F00, 0x8000, 0x30, False)
    assert g("iMod") == -1 and g("rDiv") == 0.25
    assert (g("diConv"), g("rConv")) == (400000, 400000.0)
    assert g("wCv") == 1 and g("xQu") is False and g("xQd") is False  # CV = 1: ни QU (CV >= 2), ни QD (CV <= 0)


def test_timers_tof_tp(sim: Sim) -> None:
    inst = sim.new_instance(sim.pous["FB_ALL"])
    seq = [(0, True), (100, True), (200, False), (350, False), (450, False)]
    got = []
    for t, go in seq:
        sim.clock.now_ms = t
        sim.call_fb(inst, {"iSel": 0, "sIn": "", "xGo": go})
        got.append((inst.get("xTof"), inst.get("xTp")))
    # TOF: Q держится 200 мс после спада (спад в 200 → до 400); TP: импульс 300 мс с фронта в 0
    assert got == [(True, True), (True, True), (True, True), (True, False), (False, False)]


def test_errors(tmp_path: Path) -> None:
    f = tmp_path / "e.st"
    f.write_text(
        "FUNCTION_BLOCK FB_E\nVAR\n    p : POINTER TO INT;\n    x : INT;\nEND_VAR\nx := p^;\nEND_FUNCTION_BLOCK\n",
        encoding="utf-8",
    )
    sim = Sim(load_single_st(f))
    with pytest.raises(SimError):
        sim.call_fb(sim.new_instance(sim.pous["FB_E"]))
