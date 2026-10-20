"""Модель PRG_Backwash (описание — corpus/sfc/PRG_Backwash/spec.py)."""

from __future__ import annotations

from typing import Any

from refcommon import ModelSpec, Row, Scenario
from sfcmodel import SfcDef, SfcRun

OUTS = ("iDrainTicks", "iValveTicks", "iWashTicks", "iCycles", "iRinseTicks")


def _inc(name: str) -> Any:
    def body(o: dict[str, Any]) -> None:
        o[name] += 1

    return body


DEF = SfcDef(
    steps=["Idle", "Drain", "Wash", "Rinse"],
    initial="Idle",
    actions={
        "Drain": [("N", "ActDrain"), ("S", "ActValve")],
        "Wash": [("N", "ActWash"), ("P", "ActCount")],
        "Rinse": [("R", "ActValve"), ("N", "ActRinse")],
    },
    transitions=[
        (["Idle"], lambda i, t: bool(i["xStart"]), ["Drain"]),
        (["Drain"], lambda i, t: t["Drain"] >= 2000, ["Wash"]),
        (["Wash"], lambda i, t: t["Wash"] >= 3000, ["Rinse"]),
        (["Rinse"], lambda i, t: t["Rinse"] >= 1000 or bool(i["xAbort"]), ["Idle"]),
    ],
    bodies={
        "ActDrain": _inc("iDrainTicks"),
        "ActValve": _inc("iValveTicks"),
        "ActWash": _inc("iWashTicks"),
        "ActCount": _inc("iCycles"),
        "ActRinse": _inc("iRinseTicks"),
    },
)


class Model:
    def __init__(self) -> None:
        self.run = SfcRun(DEF, dict.fromkeys(OUTS, 0))

    def call(self, i: dict[str, Any], t: int) -> dict[str, Any]:
        return self.run.call(i, t)


SPEC = ModelSpec(
    "PRG_Backwash",
    [("xStart", "BOOL"), ("xAbort", "BOOL")],
    [(n, "INT") for n in OUTS],
    Model,
    [
        Scenario(
            "FullCycle",
            "полный цикл промывки по таймаутам шагов",
            [
                Row(0, {"xStart": False, "xAbort": False}, "Idle"),
                Row(100, {"xStart": True}, "пуск: переход в конце цикла"),
                Row(200, {"xStart": False}, "Drain: N и S"),
                Row(1200, {}, "Drain 1 с"),
                Row(2300, {}, "Drain ≥ 2 с: переход"),
                Row(2400, {}, "Wash: последний вызов ActDrain, импульс ActCount"),
                Row(2500, {}, "последний вызов ActCount"),
                Row(5500, {}, "Wash ≥ 3 с: переход"),
                Row(5600, {}, "Rinse: R сбрасывает ActValve"),
                Row(5700, {}, ""),
                Row(6700, {}, "Rinse ≥ 1 с: переход"),
                Row(6800, {}, "Idle"),
            ],
        ),
        Scenario(
            "Abort",
            "прерывание полоскания",
            [
                Row(0, {"xStart": True, "xAbort": False}, "пуск"),
                Row(100, {"xStart": False}, "Drain"),
                Row(2200, {}, "в Wash"),
                Row(5300, {}, "в Rinse"),
                Row(5400, {"xAbort": True}, "прерывание: в Idle"),
                Row(5500, {"xAbort": False}, "Idle"),
            ],
        ),
    ],
)
