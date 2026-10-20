"""Модель PRG_FilterAlt (описание — corpus/sfc/PRG_FilterAlt/spec.py)."""

from __future__ import annotations

from typing import Any

from refcommon import ModelSpec, Row, Scenario
from sfcmodel import SfcDef, SfcRun

OUTS = ("iFast", "iSlow", "iDone")


def _inc(name: str) -> Any:
    def body(o: dict[str, Any]) -> None:
        o[name] += 1

    return body


DEF = SfcDef(
    steps=["Wait", "Fast", "Slow", "Done"],
    initial="Wait",
    actions={"Fast": [("N", "ActFast")], "Slow": [("N", "ActSlow")], "Done": [("N", "ActDone")]},
    transitions=[
        (["Wait"], lambda i, t: bool(i["xHigh"]), ["Fast"]),
        (["Fast"], lambda i, t: not i["xHigh"], ["Wait"]),
        (["Wait"], lambda i, t: bool(i["xLow"]), ["Slow"]),
        (["Slow"], lambda i, t: not i["xLow"], ["Done"]),
        (["Done"], lambda i, t: bool(i["xReset"]), ["Wait"]),
    ],
    bodies={"ActFast": _inc("iFast"), "ActSlow": _inc("iSlow"), "ActDone": _inc("iDone")},
)


class Model:
    def __init__(self) -> None:
        self.run = SfcRun(DEF, dict.fromkeys(OUTS, 0))

    def call(self, i: dict[str, Any], t: int) -> dict[str, Any]:
        return self.run.call(i, t)


SPEC = ModelSpec(
    "PRG_FilterAlt",
    [("xHigh", "BOOL"), ("xLow", "BOOL"), ("xReset", "BOOL")],
    [(n, "INT") for n in OUTS],
    Model,
    [
        Scenario(
            "Priority",
            "оба условия альтернативы: побеждает левое",
            [
                Row(0, {"xHigh": True, "xLow": True, "xReset": False}, "Wait → Fast"),
                Row(100, {}, "Fast"),
                Row(200, {"xHigh": False}, "Fast → Wait (прыжок)"),
                Row(300, {}, "Wait → Slow (xLow)"),
                Row(400, {"xLow": False}, "Slow → Done"),
                Row(500, {}, "Done"),
                Row(600, {"xReset": True}, "Done → Wait"),
                Row(700, {"xReset": False}, "Wait"),
            ],
        ),
    ],
)
