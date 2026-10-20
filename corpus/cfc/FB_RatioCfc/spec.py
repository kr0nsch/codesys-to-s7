"""FB_RatioCfc — соотношение реагента к расходу (CFC, две страницы, порядок не по схеме).

Поведение (модель scenarios/reference/model_FB_RatioCfc.py), шаги executionOrderId:
1. rPrev := m — выход MUL читается раньше его шага: значение прошлого вызова (начально 0);
2. m := rFlow · rK;  3. rNow := m;  4. s := m + rBias;  5. rSum := s.
Страница 1 — входы и MUL, страница 2 — сумматор и выходы. REAL (float32).
"""

from builder import Cfc, CfcBlock, CfcIn, CfcOut, Pou, V

POU = Pou(
    "FB_RatioCfc",
    "functionBlock",
    Cfc(
        [
            CfcIn("flow", "rFlow"),
            CfcIn("k", "rK"),
            CfcIn("bias", "rBias"),
            CfcBlock("mul", "MUL", 2, {"In1": "flow", "In2": "k"}, page=0),
            CfcOut("prev", "rPrev", ("mul", "Out1"), 1, page=0),
            CfcOut("now", "rNow", ("mul", "Out1"), 3, page=1),
            CfcBlock("add", "ADD", 4, {"In1": ("mul", "Out1"), "In2": "bias"}, page=1),
            CfcOut("sum", "rSum", ("add", "Out1"), 5, page=1),
        ],
        pages=2,
    ),
    [
        V("rFlow", "REAL", "VAR_INPUT"),
        V("rK", "REAL", "VAR_INPUT"),
        V("rBias", "REAL", "VAR_INPUT"),
        V("rPrev", "REAL", "VAR_OUTPUT"),
        V("rNow", "REAL", "VAR_OUTPUT"),
        V("rSum", "REAL", "VAR_OUTPUT"),
    ],
    doc=__doc__ or "",
)
