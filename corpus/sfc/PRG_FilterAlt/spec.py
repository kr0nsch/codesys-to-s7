"""PRG_FilterAlt — выбор режима фильтрации (SFC, PROGRAM: альтернатива, прыжок, приоритет переходов).

Шаги: Wait (начальный) → альтернатива слева направо: [xHigh] → Fast, [xLow] → Slow (оба TRUE —
побеждает левый, Fast); Fast → [NOT xHigh] и Slow → [NOT xLow] → Done → [xReset] сходятся и прыжком
возвращаются на Wait. (Первый вариант — ветви, оканчивающиеся прыжком без схождения, в форме
tools/corpus/builder.py — CODESYS 3.5.17 при import_xml молча пропустил, 20.10.2026; кейс перестроен.)
Действия (IEC, N): Fast — ActFast (iFast += 1), Slow — ActSlow (iSlow += 1), Done — ActDone (iDone += 1).
"""

from builder import Act, Action, Alt, JumpTo, Pou, Sfc, St, Step, Trans, V

POU = Pou(
    "PRG_FilterAlt",
    "program",
    Sfc(
        [
            Step("Wait", initial=True),
            Alt(
                [
                    [Trans("xHigh"), Step("Fast", actions=[Act("N", "ActFast")]), Trans("NOT xHigh")],
                    [
                        Trans("xLow"),
                        Step("Slow", actions=[Act("N", "ActSlow")]),
                        Trans("NOT xLow"),
                        Step("Done", actions=[Act("N", "ActDone")]),
                        Trans("xReset"),
                    ],
                ]
            ),
            JumpTo("Wait"),
        ]
    ),
    [
        V("xHigh", "BOOL", "VAR_INPUT"),
        V("xLow", "BOOL", "VAR_INPUT"),
        V("xReset", "BOOL", "VAR_INPUT"),
        V("iFast", "INT", "VAR_OUTPUT"),
        V("iSlow", "INT", "VAR_OUTPUT"),
        V("iDone", "INT", "VAR_OUTPUT"),
    ],
    actions=[
        Action("ActFast", St("iFast := iFast + 1;\n")),
        Action("ActSlow", St("iSlow := iSlow + 1;\n")),
        Action("ActDone", St("iDone := iDone + 1;\n")),
    ],
    doc=__doc__ or "",
)
