"""FB_PiCfc — ПИ-регулятор расхода промывочной воды (CFC, обратная связь).

Поведение (модель scenarios/reference/model_FB_PiCfc.py), шаги executionOrderId:
1. e := rSp − rPv;  2. p := rKp · e;  3. k := rKi · e;
4. i := k + i (вход In2 блока ADD — его собственный выход: значение прошлого цикла, начально 0; C2S7-GFX-CFCFB);
5. u := p + i;  6. o := LIMIT(rMin, u, rMax);  7. rOut := o.
Все операции — REAL (float32).
"""

from builder import Cfc, CfcBlock, CfcIn, CfcOut, Pou, V

POU = Pou(
    "FB_PiCfc",
    "functionBlock",
    Cfc(
        [
            CfcIn("sp", "rSp"),
            CfcIn("pv", "rPv"),
            CfcIn("kp", "rKp"),
            CfcIn("ki", "rKi"),
            CfcIn("mn", "rMin"),
            CfcIn("mx", "rMax"),
            CfcBlock("err", "SUB", 1, {"In1": "sp", "In2": "pv"}),
            CfcBlock("prop", "MUL", 2, {"In1": "kp", "In2": ("err", "Out1")}),
            CfcBlock("kint", "MUL", 3, {"In1": "ki", "In2": ("err", "Out1")}),
            CfcBlock("integ", "ADD", 4, {"In1": ("kint", "Out1"), "In2": ("integ", "Out1")}),
            CfcBlock("sum", "ADD", 5, {"In1": ("prop", "Out1"), "In2": ("integ", "Out1")}),
            CfcBlock("lim", "LIMIT", 6, {"In1": "mn", "In2": ("sum", "Out1"), "In3": "mx"}),
            CfcOut("out", "rOut", ("lim", "Out1"), 7),
        ]
    ),
    [
        V("rSp", "REAL", "VAR_INPUT"),
        V("rPv", "REAL", "VAR_INPUT"),
        V("rKp", "REAL", "VAR_INPUT"),
        V("rKi", "REAL", "VAR_INPUT"),
        V("rMin", "REAL", "VAR_INPUT"),
        V("rMax", "REAL", "VAR_INPUT"),
        V("rOut", "REAL", "VAR_OUTPUT"),
    ],
    doc=__doc__ or "",
)
