"""POU пробы M0: по одной на язык и форму (FORMAT-CODESYS.md, критерий G/N)."""

from __future__ import annotations

from builder import (
    Act,
    Action,
    Alt,
    Box,
    Case,
    Cfc,
    CfcBlock,
    CfcIn,
    CfcOut,
    Coil,
    Contact,
    Dut,
    Fbd,
    FbdJump,
    Gvl,
    Il,
    In,
    JumpTo,
    Ld,
    Method,
    Network,
    Out,
    Par,
    Parallel,
    Pou,
    Property,
    Rung,
    Series,
    Sfc,
    St,
    Step,
    TaskSpec,
    Trans,
    V,
)

ST_POU = Pou(
    "FB_ProbeSt",
    "functionBlock",
    St(
        "fbTon(IN := xIn, PT := T#1S);\nxQ := fbTon.Q;\nfbEdge(CLK := xIn);\nIF fbEdge.Q THEN\n    iCount := iCount + 1;\nEND_IF\n"
    ),
    [
        V("xIn", "BOOL", "VAR_INPUT"),
        V("xQ", "BOOL", "VAR_OUTPUT"),
        V("iCount", "INT", "VAR_OUTPUT"),
        V("fbTon", "TON"),
        V("fbEdge", "R_TRIG"),
    ],
)

FBD_POU = Pou(
    "FB_ProbeFbd",
    "functionBlock",
    Fbd(
        [
            Network(
                [Out("xHigh", Box("GT", inputs={"In1": In("rLevel"), "In2": In("rHigh")}))],
                title="Уровень выше уставки",
            ),
            Network([FbdJump("lblEnd", In("xEnable"), negated=True)], title="Пропуск при отключении"),
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
            Network([Out("xOut", In("xAlarm"))], title="Выход", label="lblEnd"),
        ]
    ),
    [
        V("rLevel", "REAL", "VAR_INPUT"),
        V("rHigh", "REAL", "VAR_INPUT"),
        V("xEnable", "BOOL", "VAR_INPUT"),
        V("xAck", "BOOL", "VAR_INPUT"),
        V("xOut", "BOOL", "VAR_OUTPUT"),
        V("xHigh", "BOOL"),
        V("xAlarm", "BOOL"),
    ],
)

LD_POU = Pou(
    "FB_ProbeLd",
    "functionBlock",
    Ld(
        [
            Rung(Series(Contact("xStart", edge="rising"), Coil("xRun", storage="set")), title="Пуск по фронту"),
            Rung(
                Series(
                    Parallel(Contact("xStop", edge="falling"), Contact("xPermit", neg=True)),
                    Coil("xRun", storage="reset"),
                ),
                title="Стоп по спаду или без разрешения",
            ),
            Rung(Series(Contact("xRun"), Contact("xStop", neg=True), Coil("xMoved")), title="Последовательная цепь"),
            Rung(Series(Contact("xRun"), Coil("xRunInv", neg=True)), title="Инверсная катушка"),
        ]
    ),
    [
        V("xStart", "BOOL", "VAR_INPUT"),
        V("xStop", "BOOL", "VAR_INPUT"),
        V("xPermit", "BOOL", "VAR_INPUT"),
        V("iSp", "INT", "VAR_INPUT"),
        V("xRun", "BOOL", "VAR_OUTPUT"),
        V("iOut", "INT", "VAR_OUTPUT"),
        V("xMoved", "BOOL", "VAR_OUTPUT"),
        V("xRunInv", "BOOL", "VAR_OUTPUT"),
    ],
)

FBD_ENO_POU = Pou(
    "FB_ProbeFbdEno",
    "functionBlock",
    Fbd(
        [
            Network(
                [Out("iOut", Box("MOVE", inputs={"In1": In("iSp")}, en=True, eno="xMoved"))], title="MOVE с EN/ENO"
            ),
        ]
    ),
    [
        V("xEn", "BOOL", "VAR_INPUT"),
        V("iSp", "INT", "VAR_INPUT"),
        V("iOut", "INT", "VAR_OUTPUT"),
        V("xMoved", "BOOL", "VAR_OUTPUT"),
    ],
)

CFC_POU = Pou(
    "FB_ProbeCfc",
    "functionBlock",
    Cfc(
        [
            CfcIn("a", "rIn"),
            CfcIn("lo", "rLo"),
            CfcIn("hi", "rHi"),
            CfcBlock("add", "ADD", 1, {"In1": "a", "In2": ("lim", "Out1")}),
            CfcBlock("lim", "LIMIT", 2, {"In1": "lo", "In2": "add", "In3": "hi"}),
            CfcOut("out", "rOut", ("lim", "Out1"), 3),
        ]
    ),
    [
        V("rIn", "REAL", "VAR_INPUT"),
        V("rLo", "REAL", "VAR_INPUT"),
        V("rHi", "REAL", "VAR_INPUT"),
        V("rOut", "REAL", "VAR_OUTPUT"),
    ],
)

PCFC_POU = Pou(
    "FB_ProbePcfc",
    "functionBlock",
    Cfc(
        [
            CfcIn("a", "rA"),
            CfcIn("k", "rK"),
            CfcBlock("mul", "MUL", 2, {"In1": "a", "In2": "k"}, page=0),
            CfcOut("o1", "rEarly", ("mul", "Out1"), 1, page=1),
            CfcOut("o2", "rLate", ("mul", "Out1"), 3, page=1),
        ],
        pages=2,
    ),
    [
        V("rA", "REAL", "VAR_INPUT"),
        V("rK", "REAL", "VAR_INPUT"),
        V("rEarly", "REAL", "VAR_OUTPUT"),
        V("rLate", "REAL", "VAR_OUTPUT"),
    ],
)

SFC_POU = Pou(
    "PRG_ProbeSfc",
    "program",
    Sfc(
        [
            Step("Init", initial=True, step_action="ActInit"),
            Alt(
                [
                    [
                        Trans("xA"),
                        Step("StepA", actions=[Act("N", "ActN"), Act("S", "ActS"), Act("P", "ActP")]),
                        Trans("xNext"),
                    ],
                    [Trans("xB"), Step("StepB", actions=[Act("R", "ActS")]), Trans("xNext")],
                ]
            ),
            Par([[Step("Par1", actions=[Act("N", "ActN")])], [Step("Par2")]]),
            Trans("Par1.t >= T#100MS"),
            JumpTo("Init"),
        ]
    ),
    [
        V("xA", "BOOL", "VAR_INPUT"),
        V("xB", "BOOL", "VAR_INPUT"),
        V("xNext", "BOOL", "VAR_INPUT"),
        V("iN", "INT", "VAR_OUTPUT"),
        V("xS", "BOOL", "VAR_OUTPUT"),
        V("iP", "INT", "VAR_OUTPUT"),
        V("iInit", "INT", "VAR_OUTPUT"),
    ],
    actions=[
        Action("ActInit", St("iInit := iInit + 1;\n")),
        Action("ActN", St("iN := iN + 1;\n")),
        Action("ActS", St("xS := TRUE;\n")),
        Action("ActP", St("iP := iP + 1;\n")),
    ],
)

IL_POU = Pou(
    "FB_ProbeIl",
    "functionBlock",
    Il(
        "    LD 0\n    ST i\nlbl: LD iCount\n    ADD 1\n    ST iCount\n    LD i\n    ADD 1\n    ST i\n    LT iN\n    JMPC lbl\n"
        "    CAL fbEdge(CLK := xIn)\n    LD fbEdge.Q\n    ST xRise\n"
    ),
    [
        V("xIn", "BOOL", "VAR_INPUT"),
        V("iN", "INT", "VAR_INPUT"),
        V("iCount", "INT", "VAR_OUTPUT"),
        V("xRise", "BOOL", "VAR_OUTPUT"),
        V("i", "INT"),
        V("fbEdge", "R_TRIG"),
    ],
)

OOP_POU = Pou(
    "FB_ProbeOop2",
    "functionBlock",
    St("iState := iState + 1;\n"),
    [V("xIn", "BOOL", "VAR_INPUT"), V("iState", "INT")],
    methods=[Method("Reset", "BOOL", [V("iTo", "INT", "VAR_INPUT")], St("iState := iTo;\nReset := TRUE;\n"))],
    properties=[Property("State", "INT", get=St("State := iState;\n"), set=St("iState := State;\n"))],
    actions=[Action("ActClear", St("iState := 0;\n"))],
)

MAIN_POU = Pou(
    "PRG_ProbeMain",
    "program",
    St(
        "fbSt(xIn := GVL_ProbeP.xFlag);\nfbFbd(rLevel := 1.0, rHigh := 0.5, xEnable := TRUE);\nfbLd(xStart := GVL_ProbeP.xFlag);\n"
        "fbFbdEno(xEn := TRUE, iSp := 5);\nfbCfc(rIn := 1.0, rLo := 0.0, rHi := 10.0);\nfbPcfc(rA := 2.0, rK := 3.0);\nfbOop(xIn := TRUE);\nfbIl(xIn := TRUE, iN := 3);\n"
        "GVL_ProbeP.diHours := GVL_ProbeP.diHours + 1;\nstVal.eMode := E_ProbeMode.Auto;\n"
    ),
    [
        V("fbSt", "FB_ProbeSt"),
        V("fbFbd", "FB_ProbeFbd"),
        V("fbLd", "FB_ProbeLd"),
        V("fbFbdEno", "FB_ProbeFbdEno"),
        V("fbCfc", "FB_ProbeCfc"),
        V("fbPcfc", "FB_ProbePcfc"),
        V("fbOop", "FB_ProbeOop2"),
        V("fbIl", "FB_ProbeIl"),
        V("stVal", "ST_ProbeVal"),
    ],
)

GVL = Gvl(
    "GVL_ProbeP",
    [
        V("xFlag", "BOOL"),
        V("rTotal", "REAL", qualifiers=("RETAIN",)),
        V("diHours", "DINT", qualifiers=("PERSISTENT", "RETAIN")),
    ],
)

DUTS = [
    Dut("E_ProbeMode", "TYPE E_ProbeMode :\n(\n    Off := 0,\n    Manual := 1,\n    Auto := 2\n) INT;\nEND_TYPE\n"),
    Dut(
        "ST_ProbeVal",
        "TYPE ST_ProbeVal :\nSTRUCT\n    eMode : E_ProbeMode;\n    rValue : REAL := 1.5;\nEND_STRUCT\nEND_TYPE\n",
    ),
]

LANG_POUS = {
    "ST": ST_POU,
    "FBD": FBD_POU,
    "FBD_ENO": FBD_ENO_POU,
    "LD": LD_POU,
    "CFC": CFC_POU,
    "CFC_PAGES": PCFC_POU,
    "SFC": SFC_POU,
    "IL": IL_POU,
    "OOP": OOP_POU,
}


def probe_case() -> Case:
    return Case(
        "probe",
        pous=[*LANG_POUS.values(), MAIN_POU],
        gvls=[GVL],
        duts=DUTS,
        tasks=[
            TaskSpec("Task_Main", 10, 1, ["PRG_ProbeMain"]),
            TaskSpec("Task_Sfc", 50, 2, ["PRG_ProbeSfc"]),
        ],
    )
