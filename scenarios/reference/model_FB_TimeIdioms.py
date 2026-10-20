"""Модель FB_TimeIdioms (описание — corpus/st/FB_TimeIdioms/spec.py)."""

from __future__ import annotations

from typing import Any

from refcommon import ModelSpec, Row, Scenario, Ton

DAY = 86_400_000


class Model:
    def __init__(self) -> None:
        self.pulse, self.delay = Ton(), Ton()

    def call(self, i: dict[str, Any], t: int) -> dict[str, Any]:
        self.pulse(not self.pulse.q, 500, t)
        early = self.delay.q
        self.delay(i["xIn"], 1000, t)
        return {"xPulse": self.pulse.q, "xEarly": early, "xLate": self.delay.q, "xLong": i["tIn"] > 30 * DAY}


SPEC = ModelSpec(
    "FB_TimeIdioms",
    [("xIn", "BOOL"), ("tIn", "TIME")],
    [("xPulse", "BOOL"), ("xEarly", "BOOL"), ("xLate", "BOOL"), ("xLong", "BOOL")],
    Model,
    [
        Scenario(
            "PulseTrain",
            "самосбрасывающийся таймер: импульс на один вызов",
            [
                Row(0, {"xIn": False, "tIn": 0}, "запуск импульсного таймера"),
                Row(300, {}, "ET 300"),
                Row(600, {}, "ET ≥ 500: импульс"),
                Row(700, {}, "IN = NOT Q: сброс"),
                Row(800, {}, "новый запуск"),
                Row(1400, {}, "второй импульс"),
            ],
        ),
        Scenario(
            "DelayRead",
            "чтение Q до и после вызова TON",
            [
                Row(0, {"xIn": True, "tIn": 0}, "вход держится"),
                Row(500, {}, "ещё нет"),
                Row(1200, {}, "после вызова Q, до вызова — прошлое"),
                Row(1300, {}, "оба"),
                Row(1400, {"xIn": False}, "вход снят: до вызова — прошлое"),
                Row(1500, {}, "покой"),
            ],
        ),
        Scenario(
            "LongTime",
            "TIME больше 24 суток (беззнаковый 32-битный)",
            [Row(0, {"xIn": False, "tIn": 31 * DAY}, "31 сутки > 30"), Row(100, {"tIn": 29 * DAY}, "29 суток")],
        ),
    ],
)
