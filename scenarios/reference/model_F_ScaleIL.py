"""Модель F_ScaleIL (описание — corpus/il/F_ScaleIL/spec.py), float32."""

from __future__ import annotations

from typing import Any

from refcommon import ModelSpec, Row, Scenario, f32


class Model:
    def call(self, x: dict[str, Any], t: int) -> dict[str, Any]:
        r = f32(f32(f32(x["rRaw"]) - f32(x["rLo"])) * f32(x["rK"]))
        return {"F_ScaleIL": r, "xGateEdge": bool(x["xGate"])}


SPEC = ModelSpec(
    "F_ScaleIL",
    [("rRaw", "REAL"), ("rLo", "REAL"), ("rK", "REAL"), ("xGate", "BOOL")],
    [("F_ScaleIL", "REAL"), ("xGateEdge", "BOOL")],
    Model,
    [
        Scenario(
            "Scale",
            "линейное масштабирование; R_TRIG в функции даёт фронт при каждом вызове",
            [
                Row(0, {"rRaw": 10.0, "rLo": 2.0, "rK": 0.5, "xGate": True}, "(10 − 2) · 0.5 = 4"),
                Row(100, {}, "снова фронт: экземпляр инициализирован заново"),
                Row(200, {"rRaw": 2.0, "xGate": False}, "0"),
            ],
        ),
    ],
)
