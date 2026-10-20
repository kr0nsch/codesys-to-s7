"""PRG_PumpInterlock — взаимная блокировка насосов II подъёма (LD, PROGRAM: параллели, двойная катушка).

Поведение (модель scenarios/reference/model_PRG_PumpInterlock.py), сети по порядку:
1. xP1Run := (xP1Ready AND NOT xP2Run) OR xP1Force;
2. xP2Run := (xP2Ready AND NOT xP1Run) OR xP2Force — читает уже новое xP1Run этого цикла;
3. xAnyRun := xP1Run OR xP2Run;
4. xAlarm := xP1Run AND xP2Run;
5. xAlarm := xEmergency — двойная катушка: последняя сеть побеждает (C2S7-GFX-DOUBLECOIL).
"""

from builder import Coil, Contact, Ld, Parallel, Pou, Rung, Series, V

POU = Pou(
    "PRG_PumpInterlock",
    "program",
    Ld(
        [
            Rung(
                Series(
                    Parallel(Series(Contact("xP1Ready"), Contact("xP2Run", neg=True)), Contact("xP1Force")),
                    Coil("xP1Run"),
                ),
                title="Насос 1",
            ),
            Rung(
                Series(
                    Parallel(Series(Contact("xP2Ready"), Contact("xP1Run", neg=True)), Contact("xP2Force")),
                    Coil("xP2Run"),
                ),
                title="Насос 2",
            ),
            Rung(Series(Parallel(Contact("xP1Run"), Contact("xP2Run")), Coil("xAnyRun")), title="Любой в работе"),
            Rung(Series(Contact("xP1Run"), Contact("xP2Run"), Coil("xAlarm")), title="Оба в работе"),
            Rung(Series(Contact("xEmergency"), Coil("xAlarm")), title="Аварийная кнопка"),
        ]
    ),
    [
        V("xP1Ready", "BOOL", "VAR_INPUT"),
        V("xP2Ready", "BOOL", "VAR_INPUT"),
        V("xP1Force", "BOOL", "VAR_INPUT"),
        V("xP2Force", "BOOL", "VAR_INPUT"),
        V("xEmergency", "BOOL", "VAR_INPUT"),
        V("xP1Run", "BOOL", "VAR_OUTPUT"),
        V("xP2Run", "BOOL", "VAR_OUTPUT"),
        V("xAnyRun", "BOOL", "VAR_OUTPUT"),
        V("xAlarm", "BOOL", "VAR_OUTPUT"),
    ],
    doc=__doc__ or "",
)
