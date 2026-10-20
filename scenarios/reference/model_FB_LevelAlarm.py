"""Модель FB_LevelAlarm (описание — corpus/fbd/FB_LevelAlarm/spec.py)."""

from __future__ import annotations

from typing import Any

from refcommon import ModelSpec, Row, Scenario, f32


class Model:
    def __init__(self) -> None:
        self.high = False
        self.alarm = False

    def call(self, i: dict[str, Any], t: int) -> dict[str, Any]:
        self.high = f32(i["rLevel"]) > f32(i["rHigh"])
        if i["xEnable"]:
            self.alarm = (self.high or self.alarm) and not i["xAck"]
        return {"xAlarm": self.alarm, "xLamp": self.alarm and i["xEnable"]}


SPEC = ModelSpec(
    "FB_LevelAlarm",
    [("rLevel", "REAL"), ("rHigh", "REAL"), ("xEnable", "BOOL"), ("xAck", "BOOL")],
    [("xAlarm", "BOOL"), ("xLamp", "BOOL")],
    Model,
    [
        Scenario(
            "AlarmLatch",
            "защёлка тревоги и квитирование",
            [
                Row(0, {"rLevel": 1.0, "rHigh": 2.0, "xEnable": True, "xAck": False}, "уровень в норме"),
                Row(100, {"rLevel": 3.0}, "выше уставки: тревога"),
                Row(200, {"rLevel": 1.0}, "уровень вернулся — тревога держится"),
                Row(300, {"xAck": True}, "квитирование"),
                Row(400, {"xAck": False}, "покой"),
            ],
        ),
        Scenario(
            "DisabledHolds",
            "вывод из работы: сеть 3 пропущена прыжком",
            [
                Row(0, {"rLevel": 3.0, "rHigh": 2.0, "xEnable": True, "xAck": False}, "тревога"),
                Row(100, {"xEnable": False, "xAck": True}, "выведен: квитирование не действует, лампа гаснет"),
                Row(200, {"xEnable": True}, "введён: квитирование срабатывает"),
                Row(300, {"xEnable": False, "xAck": False, "rLevel": 5.0}, "выведен: новая тревога не ставится"),
            ],
        ),
    ],
)
