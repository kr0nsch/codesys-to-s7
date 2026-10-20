"""Модель PRG_PumpInterlock (описание — corpus/ld/PRG_PumpInterlock/spec.py)."""

from __future__ import annotations

from typing import Any

from refcommon import ModelSpec, Row, Scenario


class Model:
    def __init__(self) -> None:
        self.p1 = self.p2 = False

    def call(self, i: dict[str, Any], t: int) -> dict[str, Any]:
        self.p1 = (i["xP1Ready"] and not self.p2) or i["xP1Force"]
        self.p2 = (i["xP2Ready"] and not self.p1) or i["xP2Force"]
        alarm = self.p1 and self.p2
        alarm = i["xEmergency"]  # двойная катушка: последняя сеть побеждает
        return {"xP1Run": self.p1, "xP2Run": self.p2, "xAnyRun": self.p1 or self.p2, "xAlarm": alarm}


Z = {"xP1Ready": False, "xP2Ready": False, "xP1Force": False, "xP2Force": False, "xEmergency": False}

SPEC = ModelSpec(
    "PRG_PumpInterlock",
    [(n, "BOOL") for n in Z],
    [("xP1Run", "BOOL"), ("xP2Run", "BOOL"), ("xAnyRun", "BOOL"), ("xAlarm", "BOOL")],
    Model,
    [
        Scenario(
            "Alternation",
            "блокировка: первый готовый держит",
            [
                Row(0, {**Z, "xP1Ready": True}, "готов насос 1"),
                Row(100, {"xP2Ready": True}, "готов и 2 — заблокирован"),
                Row(200, {"xP1Ready": False}, "1 не готов: 2 подхватывает в том же цикле (сеть 2 после сети 1)"),
                Row(300, {"xP1Ready": True}, "1 снова готов — заблокирован работающим 2"),
            ],
        ),
        Scenario(
            "BothAtOnce",
            "оба готовы на первом вызове: побеждает 1",
            [Row(0, {**Z, "xP1Ready": True, "xP2Ready": True}, "первый вызов")],
        ),
        Scenario(
            "DoubleCoil",
            "принудительный пуск обоих: сеть 4 ставит тревогу, сеть 5 её перезаписывает",
            [
                Row(0, {**Z, "xP1Force": True, "xP2Force": True}, "оба в работе — тревога сети 4 перезаписана"),
                Row(100, {"xEmergency": True}, "аварийная кнопка"),
                Row(200, {"xP1Force": False, "xP2Force": False, "xEmergency": False}, "сброс"),
            ],
        ),
    ],
)
