"""Модель FB_RatioCfc (описание — corpus/cfc/FB_RatioCfc/spec.py), float32."""

from __future__ import annotations

from typing import Any

from refcommon import ModelSpec, Row, Scenario, f32


class Model:
    def __init__(self) -> None:
        self.m = 0.0

    def call(self, x: dict[str, Any], t: int) -> dict[str, Any]:
        prev = self.m
        self.m = f32(f32(x["rFlow"]) * f32(x["rK"]))
        return {"rPrev": prev, "rNow": self.m, "rSum": f32(self.m + f32(x["rBias"]))}


SPEC = ModelSpec(
    "FB_RatioCfc",
    [("rFlow", "REAL"), ("rK", "REAL"), ("rBias", "REAL")],
    [("rPrev", "REAL"), ("rNow", "REAL"), ("rSum", "REAL")],
    Model,
    [
        Scenario(
            "Order",
            "выход, прочитанный раньше шага MUL, отстаёт на цикл",
            [
                Row(0, {"rFlow": 10.0, "rK": 0.5, "rBias": 1.0}, "первый вызов: rPrev = 0"),
                Row(100, {"rFlow": 20.0}, "rPrev — прошлый m"),
                Row(200, {"rK": 0.25}, ""),
            ],
        ),
    ],
)
