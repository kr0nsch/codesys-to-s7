"""Модель FB_PulseCountIL (описание — corpus/il/FB_PulseCountIL/spec.py)."""

from __future__ import annotations

from typing import Any

from refcommon import ModelSpec, Row, Scenario, wrap


class Model:
    def __init__(self) -> None:
        self.acc = 0

    def call(self, x: dict[str, Any], t: int) -> dict[str, Any]:
        i = 0
        while True:  # do-while: IL прыгает назад после тела
            self.acc = wrap(self.acc + x["iStep"])
            i = wrap(i + 1)
            if not i < x["iN"]:
                break
        return {"iAcc": self.acc, "xOver": self.acc > x["iMax"]}


SPEC = ModelSpec(
    "FB_PulseCountIL",
    [("iN", "INT"), ("iStep", "INT"), ("iMax", "INT")],
    [("iAcc", "INT"), ("xOver", "BOOL")],
    Model,
    [
        Scenario(
            "Accumulate",
            "iN раз по iStep за вызов, тело хотя бы раз",
            [
                Row(0, {"iN": 3, "iStep": 2, "iMax": 10}, "+6"),
                Row(100, {}, "+6 → 12 > 10"),
                Row(200, {"iN": 0}, "iN = 0: тело один раз, +2"),
            ],
        ),
    ],
)
