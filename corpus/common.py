"""Корпус «все языки» (ТЗ M9): объект вымышленный — фильтровальная станция ВОС «Заречная».

13 POU P0 по языкам (`corpus/<язык>/<кейс>/spec.py`, DSL tools/corpus/builder.py), общие объекты —
здесь: GVL_IO (AT %IX/%IW/%MD, наложение %MW/%MX), GVL_Retain (RETAIN/PERSISTENT), DUT (alias,
диапазон, ENUM, UNION), задачи 10/50/500 мс + freewheeling и программа-обвязка PRG_Corpus (вызывает ФБ
и функции, чтобы CODESYS их собрал: `app.build()` компилирует только достижимое из задач; в 13 не входит).

IL в CODESYS 3.5.17 из PLCopen не импортируется (M0: N): кейсы `il/*` — текстовый корпус для c2s7.sim,
в проект CODESYS они не попадают (11 POU + обвязка).
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
if str(REPO / "tools" / "corpus") not in sys.path:
    sys.path.insert(0, str(REPO / "tools" / "corpus"))

import builder as B  # noqa: E402

LANG_DIRS = ("st", "fbd", "ld", "cfc", "sfc", "il")


@dataclass
class CaseSpec:
    name: str
    lang: str  # каталог: st fbd ld cfc sfc il
    path: Path
    pou: B.Pou

    @property
    def in_codesys(self) -> bool:
        return self.lang != "il"


def load_specs() -> dict[str, CaseSpec]:
    out: dict[str, CaseSpec] = {}
    for lang in LANG_DIRS:
        for d in sorted((ROOT / lang).iterdir()):
            spec_file = d / "spec.py"
            if not spec_file.exists():
                continue
            mod_name = f"c2s7_corpus_{lang}_{d.name}"
            spec = importlib.util.spec_from_file_location(mod_name, spec_file)
            assert spec is not None and spec.loader is not None
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            pou = mod.POU
            out[pou.name] = CaseSpec(pou.name, lang, d, pou)
    return out


GVL_IO = B.Gvl(
    "GVL_IO",
    [
        B.V("xStartPb", "BOOL", address="%IX0.0", comment="кнопка «Пуск промывки»"),
        B.V("xStopPb", "BOOL", address="%IX0.1", comment="кнопка «Стоп»"),
        B.V("iLevelRaw", "INT", address="%IW2", comment="уровень в фильтре, сырое"),
        B.V("diFlowTotal", "DINT", address="%MD4", comment="накопленный расход"),
        B.V("wStatus", "WORD", address="%MW10", comment="слово состояния"),
        B.V("xStatusBit3", "BOOL", address="%MX20.3", comment="бит 3 байта 20 — внутри %MW10 (наложение)"),
        B.V("rLevel", "REAL", comment="уровень, м"),
    ],
)

GVL_RETAIN = B.Gvl(
    "GVL_Retain",
    [
        B.V("diBackwashCount", "DINT", qualifiers=("RETAIN",), comment="число промывок"),
        B.V("rFilterHours", "REAL", qualifiers=("PERSISTENT", "RETAIN"), comment="наработка фильтра, ч"),
    ],
)

DUTS = [
    B.Dut("T_Level", "TYPE T_Level : REAL;\nEND_TYPE\n"),
    B.Dut("T_Pct", "TYPE T_Pct : INT(0..100);\nEND_TYPE\n"),
    B.Dut(
        "E_FilterMode", "TYPE E_FilterMode :\n(\n    Off := 0,\n    Filter := 1,\n    Backwash := 2\n) INT;\nEND_TYPE\n"
    ),
    B.Dut("U_Status", "TYPE U_Status :\nUNION\n    w : WORD;\n    b : ARRAY[0..1] OF BYTE;\nEND_UNION\nEND_TYPE\n"),
]

PRG_CORPUS = B.Pou(
    "PRG_Corpus",
    "program",
    B.St(
        "iConv := F_Convert(rIn := GVL_IO.rLevel, iA := 1, iB := 2, iSel := 0, iMn := 0, iMx := 100);\n"
        "fbLatch(xSet := GVL_IO.xStartPb, xReset := GVL_IO.xStopPb);\n"
        "fbTime(xIn := GVL_IO.xStartPb, tIn := T#1S);\n"
        "fbLevel(rLevel := GVL_IO.rLevel, rHigh := 2.5, xEnable := TRUE, xAck := GVL_IO.xStopPb);\n"
        "fbValve(xOpen := GVL_IO.xStartPb, iClosedPos := 0, iOpenPos := 80, iMin := 5, iMax := 95);\n"
        "fbPi(rSp := 1.0, rPv := GVL_IO.rLevel, rKp := 2.0, rKi := 0.1, rMin := 0.0, rMax := 100.0);\n"
        "fbRatio(rFlow := GVL_IO.rLevel, rK := 0.5, rBias := 1.0);\n"
        "eMode := E_FilterMode.Filter;\n"
        "uStatus.w := GVL_IO.wStatus;\n"
        "rLvl := GVL_IO.rLevel;\n"
        "pct := 50;\n"
        "IF GVL_IO.xStartPb THEN\n    GVL_Retain.diBackwashCount := GVL_Retain.diBackwashCount + 1;\nEND_IF\n"
    ),
    [
        B.V("iConv", "INT"),
        B.V("fbLatch", "FB_Latch"),
        B.V("fbTime", "FB_TimeIdioms"),
        B.V("fbLevel", "FB_LevelAlarm"),
        B.V("fbValve", "FB_ValveCmd"),
        B.V("fbPi", "FB_PiCfc"),
        B.V("fbRatio", "FB_RatioCfc"),
        B.V("eMode", "E_FilterMode"),
        B.V("uStatus", "U_Status"),
        B.V("rLvl", "T_Level"),
        B.V("pct", "T_Pct"),
    ],
    doc="Программа-обвязка корпуса: вызывает ФБ и функции, чтобы CODESYS их собрал (в 13 POU не входит).",
)

TASKS = [
    B.TaskSpec("Task_10ms", 10, 1, ["PRG_Corpus", "PRG_Permissives"]),
    B.TaskSpec("Task_50ms", 50, 2, ["PRG_PumpInterlock"]),
    B.TaskSpec("Task_500ms", 500, 3, ["PRG_Backwash"]),
    B.TaskSpec("Task_Free", None, 10, ["PRG_FilterAlt"], kind="freewheeling"),
]


def case(include_il: bool = False) -> B.Case:
    specs = load_specs()
    pous = [s.pou for s in specs.values() if include_il or s.in_codesys]
    return B.Case("Zarechnaya", pous=[*pous, PRG_CORPUS], gvls=[GVL_IO, GVL_RETAIN], duts=DUTS, tasks=TASKS)
