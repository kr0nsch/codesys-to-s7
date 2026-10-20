"""FB_ValveCmd — команда регулирующей задвижки (FBD, MOVE/SEL/LIMIT; EN/ENO не используется — M0: N).

Поведение (модель scenarios/reference/model_FB_ValveCmd.py):
1. iCmd := SEL(xOpen, iClosedPos, iOpenPos) — xOpen = FALSE → iClosedPos, TRUE → iOpenPos;
2. iPos := LIMIT(iMin, iCmd, iMax);
3. iOut := MOVE(iPos);
4. xAtLimit := (iPos = iMin) OR (iPos = iMax).
SEL и LIMIT вне подмножества FlgNet P0 → блок целиком в SCL (C2S7-GFX-SCL).
"""

from builder import Box, Fbd, In, Network, Out, Pou, V

POU = Pou(
    "FB_ValveCmd",
    "functionBlock",
    Fbd(
        [
            Network(
                [Out("iCmd", Box("SEL", inputs={"In1": In("xOpen"), "In2": In("iClosedPos"), "In3": In("iOpenPos")}))],
                title="Выбор положения",
            ),
            Network(
                [Out("iPos", Box("LIMIT", inputs={"In1": In("iMin"), "In2": In("iCmd"), "In3": In("iMax")}))],
                title="Ограничение",
            ),
            Network([Out("iOut", Box("MOVE", inputs={"In1": In("iPos")}))], title="Выход"),
            Network(
                [
                    Out(
                        "xAtLimit",
                        Box(
                            "OR",
                            inputs={
                                "In1": Box("EQ", inputs={"In1": In("iPos"), "In2": In("iMin")}),
                                "In2": Box("EQ", inputs={"In1": In("iPos"), "In2": In("iMax")}),
                            },
                        ),
                    )
                ],
                title="На упоре",
            ),
        ]
    ),
    [
        V("xOpen", "BOOL", "VAR_INPUT"),
        V("iClosedPos", "INT", "VAR_INPUT"),
        V("iOpenPos", "INT", "VAR_INPUT"),
        V("iMin", "INT", "VAR_INPUT"),
        V("iMax", "INT", "VAR_INPUT"),
        V("iOut", "INT", "VAR_OUTPUT"),
        V("xAtLimit", "BOOL", "VAR_OUTPUT"),
        V("iCmd", "INT"),
        V("iPos", "INT"),
    ],
    doc=__doc__ or "",
)
