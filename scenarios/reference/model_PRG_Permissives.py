"""Модель PRG_Permissives (описание — corpus/ld/PRG_Permissives/spec.py)."""

from __future__ import annotations

from typing import Any

from refcommon import FTrig, ModelSpec, Row, RTrig, Scenario


class Model:
    def __init__(self) -> None:
        self.run = False
        self.start, self.stop = RTrig(), FTrig()

    def call(self, i: dict[str, Any], t: int) -> dict[str, Any]:
        if self.start(i["xStartBtn"]) and i["xPermit"]:
            self.run = True
        if self.stop(i["xStopBtn"]) or not i["xPermit"]:
            self.run = False
        return {"xRun": self.run, "xMotor": self.run and not i["xFault"], "xIdle": not self.run}


Z = {"xStartBtn": False, "xStopBtn": False, "xPermit": True, "xFault": False}

SPEC = ModelSpec(
    "PRG_Permissives",
    [(n, "BOOL") for n in Z],
    [("xRun", "BOOL"), ("xMotor", "BOOL"), ("xIdle", "BOOL")],
    Model,
    [
        Scenario(
            "StartStop",
            "пуск по фронту, стоп по спаду",
            [
                Row(0, dict(Z), "покой"),
                Row(100, {"xStartBtn": True}, "фронт пуска"),
                Row(200, {}, "кнопка держится"),
                Row(300, {"xStartBtn": False, "xStopBtn": True}, "стоп нажат — ещё работает"),
                Row(400, {"xStopBtn": False}, "спад стопа: останов"),
            ],
        ),
        Scenario(
            "FirstCallEdge",
            "кнопка нажата уже на первом вызове: фронт есть (память фронта FALSE)",
            [Row(0, {**Z, "xStartBtn": True}, "первый вызов"), Row(100, {}, "")],
        ),
        Scenario(
            "NoPermit",
            "нет разрешения: сброс побеждает",
            [
                Row(0, {**Z, "xPermit": False}, "без разрешения"),
                Row(100, {"xStartBtn": True}, "пуск без разрешения"),
                Row(200, {"xStartBtn": False, "xPermit": True}, "разрешение дали"),
                Row(300, {"xStartBtn": True, "xFault": True}, "пуск при неисправности: работает, двигатель стоит"),
            ],
        ),
    ],
)
