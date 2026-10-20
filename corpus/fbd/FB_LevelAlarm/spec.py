"""FB_LevelAlarm — сигнализация уровня в фильтре (FBD, 4 сети, Jump/Label).

Поведение (модель scenarios/reference/model_FB_LevelAlarm.py):
1. xHigh := rLevel > rHigh;
2. если NOT xEnable — переход на lblOut (сеть 3 пропускается, тревога держит прошлое значение);
3. xAlarm := (xHigh OR xAlarm) AND NOT xAck — защёлка с квитированием;
4. (метка lblOut) xLamp := xAlarm AND xEnable.
"""

from builder import Box, Fbd, FbdJump, In, Network, Out, Pou, V

POU = Pou(
    "FB_LevelAlarm",
    "functionBlock",
    Fbd(
        [
            Network(
                [Out("xHigh", Box("GT", inputs={"In1": In("rLevel"), "In2": In("rHigh")}))],
                title="Уровень выше уставки",
            ),
            Network(
                [FbdJump("lblOut", Box("NOT", inputs={"In1": In("xEnable")}))], title="Пропуск при выводе из работы"
            ),
            Network(
                [
                    Out(
                        "xAlarm",
                        Box(
                            "AND",
                            inputs={
                                "In1": Box("OR", inputs={"In1": In("xHigh"), "In2": In("xAlarm")}),
                                "In2": In("xAck"),
                            },
                            negated=("In2",),
                        ),
                    )
                ],
                title="Защёлка тревоги",
            ),
            Network(
                [Out("xLamp", Box("AND", inputs={"In1": In("xAlarm"), "In2": In("xEnable")}))],
                title="Лампа",
                label="lblOut",
            ),
        ]
    ),
    [
        V("rLevel", "REAL", "VAR_INPUT"),
        V("rHigh", "REAL", "VAR_INPUT"),
        V("xEnable", "BOOL", "VAR_INPUT"),
        V("xAck", "BOOL", "VAR_INPUT"),
        V("xAlarm", "BOOL", "VAR_OUTPUT"),
        V("xLamp", "BOOL", "VAR_OUTPUT"),
        V("xHigh", "BOOL"),
    ],
    doc=__doc__ or "",
)
