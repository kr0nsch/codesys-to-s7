"""Модель FB_PiCfc (описание — corpus/cfc/FB_PiCfc/spec.py), арифметика float32."""

from __future__ import annotations

from typing import Any

from refcommon import ModelSpec, Row, Scenario, f32


class Model:
    def __init__(self) -> None:
        self.i = 0.0

    def call(self, x: dict[str, Any], t: int) -> dict[str, Any]:
        e = f32(f32(x["rSp"]) - f32(x["rPv"]))
        p = f32(f32(x["rKp"]) * e)
        k = f32(f32(x["rKi"]) * e)
        self.i = f32(k + self.i)
        u = f32(p + self.i)
        return {"rOut": min(max(u, f32(x["rMin"])), f32(x["rMax"]))}


SPEC = ModelSpec(
    "FB_PiCfc",
    [("rSp", "REAL"), ("rPv", "REAL"), ("rKp", "REAL"), ("rKi", "REAL"), ("rMin", "REAL"), ("rMax", "REAL")],
    [("rOut", "REAL")],
    Model,
    [
        Scenario(
            "Integrate",
            "интегратор через обратную связь CFC",
            [
                Row(0, {"rSp": 1.0, "rPv": 0.0, "rKp": 2.0, "rKi": 0.5, "rMin": 0.0, "rMax": 10.0}, "i = 0.5, u = 2.5"),
                Row(100, {}, "i = 1.0"),
                Row(200, {}, "i = 1.5"),
                Row(300, {"rPv": 1.0}, "ошибка 0: интеграл держится"),
            ],
        ),
        Scenario(
            "Clamp",
            "ограничение выхода без антинасыщения",
            [
                Row(0, {"rSp": 5.0, "rPv": 0.0, "rKp": 1.0, "rKi": 1.0, "rMin": 0.0, "rMax": 8.0}, "u = 10 → 8"),
                Row(100, {}, "u = 15 → 8, интеграл растёт"),
                Row(200, {"rPv": 20.0}, "ошибка −15: u = −15 + (10 − 15) → 0"),
            ],
        ),
    ],
)
