"""F_ScaleIL — масштабирование сырого значения датчика мутности (IL, FUNCTION: CAL, CR через ST).

IL в CODESYS 3.5.17 из PLCopen не импортируется (M0: N) — только текстовый корпус для c2s7.sim.
Поведение (модель scenarios/reference/model_F_ScaleIL.py):
- результат := (rRaw − rLo) · rK; rTmp := тот же результат (CR переживает ST: «ST rTmp; ST F_ScaleIL»);
- CAL fbGate(CLK := xGate): R_TRIG внутри FUNCTION инициализируется при каждом вызове, поэтому
  xGateEdge = xGate (C2S7-POU-FBINFC — ФБ в функции, manual).
"""

from builder import Il, Pou, V

POU = Pou(
    "F_ScaleIL",
    "function",
    Il(
        "    LD rRaw\n    SUB rLo\n    MUL rK\n    ST rTmp\n    ST F_ScaleIL\n"
        "    CAL fbGate(CLK := xGate)\n    LD fbGate.Q\n    ST xGateEdge\n"
    ),
    [
        V("rRaw", "REAL", "VAR_INPUT"),
        V("rLo", "REAL", "VAR_INPUT"),
        V("rK", "REAL", "VAR_INPUT"),
        V("xGate", "BOOL", "VAR_INPUT"),
        V("xGateEdge", "BOOL", "VAR_OUTPUT"),
        V("rTmp", "REAL"),
        V("fbGate", "R_TRIG"),
    ],
    return_type="REAL",
    doc=__doc__ or "",
)
