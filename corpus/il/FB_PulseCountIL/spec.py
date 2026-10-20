"""FB_PulseCountIL — накопитель импульсов дозатора (IL, JMPC назад).

IL в CODESYS 3.5.17 из PLCopen не импортируется (M0: N), поэтому кейс — только текстовый корпус для c2s7.sim.
Поведение (модель scenarios/reference/model_FB_PulseCountIL.py): за вызов iAcc увеличивается на iStep
ровно iN раз (цикл do-while: тело выполняется хотя бы раз, даже при iN ≤ 0); xOver := iAcc > iMax.
INT с переносом.
"""

from builder import Il, Pou, V

POU = Pou(
    "FB_PulseCountIL",
    "functionBlock",
    Il(
        "    LD 0\n    ST i\n"
        "loop: LD iAcc\n    ADD iStep\n    ST iAcc\n"
        "    LD i\n    ADD 1\n    ST i\n    LT iN\n    JMPC loop\n"
        "    LD iAcc\n    GT iMax\n    ST xOver\n"
    ),
    [
        V("iN", "INT", "VAR_INPUT"),
        V("iStep", "INT", "VAR_INPUT"),
        V("iMax", "INT", "VAR_INPUT"),
        V("iAcc", "INT", "VAR_OUTPUT"),
        V("xOver", "BOOL", "VAR_OUTPUT"),
        V("i", "INT"),
    ],
    doc=__doc__ or "",
)
