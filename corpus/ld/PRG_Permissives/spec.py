"""PRG_Permissives — разрешения пуска насоса промывки (LD, PROGRAM: P/N, S/R).

Поведение (модель scenarios/reference/model_PRG_Permissives.py):
1. фронт xStartBtn И xPermit → xRun := TRUE (S);
2. спад xStopBtn ИЛИ NOT xPermit → xRun := FALSE (R) — сеть 2 после сети 1, сброс побеждает в одном цикле;
3. xMotor := xRun AND NOT xFault;
4. xIdle := NOT xRun (инверсная катушка).
Фронты — R_TRIG/F_TRIG CODESYS по переменной; первый вызов: память фронта FALSE.
"""

from builder import Coil, Contact, Ld, Parallel, Pou, Rung, Series, V

POU = Pou(
    "PRG_Permissives",
    "program",
    Ld(
        [
            Rung(
                Series(Contact("xStartBtn", edge="rising"), Contact("xPermit"), Coil("xRun", storage="set")),
                title="Пуск по фронту",
            ),
            Rung(
                Series(
                    Parallel(Contact("xStopBtn", edge="falling"), Contact("xPermit", neg=True)),
                    Coil("xRun", storage="reset"),
                ),
                title="Стоп по спаду или без разрешения",
            ),
            Rung(Series(Contact("xRun"), Contact("xFault", neg=True), Coil("xMotor")), title="Двигатель"),
            Rung(Series(Contact("xRun"), Coil("xIdle", neg=True)), title="Простой"),
        ]
    ),
    [
        V("xStartBtn", "BOOL", "VAR_INPUT"),
        V("xStopBtn", "BOOL", "VAR_INPUT"),
        V("xPermit", "BOOL", "VAR_INPUT"),
        V("xFault", "BOOL", "VAR_INPUT"),
        V("xRun", "BOOL", "VAR_OUTPUT"),
        V("xMotor", "BOOL", "VAR_OUTPUT"),
        V("xIdle", "BOOL", "VAR_OUTPUT"),
    ],
    doc=__doc__ or "",
)
