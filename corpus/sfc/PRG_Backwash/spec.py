"""PRG_Backwash — промывка фильтра (SFC, PROGRAM: таймауты, N/S/R/P).

Шаги: Idle (начальный) → [xStart] → Drain → [Drain.t >= T#2S] → Wash → [Wash.t >= T#3S] → Rinse →
[Rinse.t >= T#1S OR xAbort] → Idle.
Действия (IEC): Drain — N ActDrain (iDrainTicks += 1), S ActValve (iValveTicks += 1);
Wash — N ActWash (iWashTicks += 1), P ActCount (iCycles += 1); Rinse — R ActValve, N ActRinse (iRinseTicks += 1).
Порядок цикла — справка CODESYS (lower/sfc.py); IEC-действие исполняется ещё раз после деактивации
(последний вызов с Q = FALSE). entry/exit-действия в CODESYS 3.5.17 не импортируются из PLCopen
(M0: N), поэтому в кейсе их нет — автомат c2s7 их поддерживает (unit-тесты).
"""

from builder import Act, Action, JumpTo, Pou, Sfc, St, Step, Trans, V

POU = Pou(
    "PRG_Backwash",
    "program",
    Sfc(
        [
            Step("Idle", initial=True),
            Trans("xStart"),
            Step("Drain", actions=[Act("N", "ActDrain"), Act("S", "ActValve")]),
            Trans("Drain.t >= T#2S"),
            Step("Wash", actions=[Act("N", "ActWash"), Act("P", "ActCount")]),
            Trans("Wash.t >= T#3S"),
            Step("Rinse", actions=[Act("R", "ActValve"), Act("N", "ActRinse")]),
            Trans("Rinse.t >= T#1S OR xAbort"),
            JumpTo("Idle"),
        ]
    ),
    [
        V("xStart", "BOOL", "VAR_INPUT"),
        V("xAbort", "BOOL", "VAR_INPUT"),
        V("iDrainTicks", "INT", "VAR_OUTPUT"),
        V("iValveTicks", "INT", "VAR_OUTPUT"),
        V("iWashTicks", "INT", "VAR_OUTPUT"),
        V("iCycles", "INT", "VAR_OUTPUT"),
        V("iRinseTicks", "INT", "VAR_OUTPUT"),
    ],
    actions=[
        Action("ActDrain", St("iDrainTicks := iDrainTicks + 1;\n")),
        Action("ActValve", St("iValveTicks := iValveTicks + 1;\n")),
        Action("ActWash", St("iWashTicks := iWashTicks + 1;\n")),
        Action("ActCount", St("iCycles := iCycles + 1;\n")),
        Action("ActRinse", St("iRinseTicks := iRinseTicks + 1;\n")),
    ],
    doc=__doc__ or "",
)
