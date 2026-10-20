"""Модель FB_Latch (описание — corpus/st/FB_Latch/spec.py)."""

from __future__ import annotations

from typing import Any

from refcommon import FTrig, ModelSpec, Row, RTrig, Scenario


class Model:
    def __init__(self) -> None:
        self.sr = self.rs = False
        self.cu = self.cd = 0
        self.cu_edge, self.cd_edge = RTrig(), RTrig()
        self.rise, self.fall = RTrig(), FTrig()

    def call(self, i: dict[str, Any], t: int) -> dict[str, Any]:
        self.sr = i["xSet"] or (self.sr and not i["xReset"])
        self.rs = (i["xSet"] or self.rs) and not i["xReset"]
        e = self.cu_edge(i["xCu"])
        if i["xReset"]:
            self.cu = 0
        elif e and self.cu < 65535:
            self.cu += 1
        d = self.cd_edge(i["xCd"])
        if i["xLoad"]:
            self.cd = 2
        elif d and self.cd > 0:
            self.cd -= 1
        return {
            "xSr": self.sr,
            "xRs": self.rs,
            "xCuQ": self.cu >= 3,
            "xCdQ": self.cd == 0,
            "wCu": self.cu,
            "wCd": self.cd,
            "xRise": self.rise(i["xClk"]),
            "xFall": self.fall(i["xClk"]),
        }


Z = {"xSet": False, "xReset": False, "xCu": False, "xCd": False, "xLoad": False, "xClk": False}


def seq(*changes: tuple[dict[str, Any], str]) -> list[Row]:
    out = []
    cur = dict(Z)
    for k, (ch, c) in enumerate(changes):
        cur = {**cur, **ch}
        out.append(Row(100 * k, dict(cur), c))
    return out


SPEC = ModelSpec(
    "FB_Latch",
    [(n, "BOOL") for n in Z],
    [
        ("xSr", "BOOL"),
        ("xRs", "BOOL"),
        ("xCuQ", "BOOL"),
        ("xCdQ", "BOOL"),
        ("wCu", "WORD"),
        ("wCd", "WORD"),
        ("xRise", "BOOL"),
        ("xFall", "BOOL"),
    ],
    Model,
    [
        Scenario(
            "SetResetBoth",
            "SR — установка доминирует, RS — сброс",
            seq(
                ({"xSet": True, "xReset": True}, "SET = RESET = 1: SR → 1, RS → 0"),
                ({"xReset": False}, "только SET"),
                ({"xSet": False}, "память"),
                ({"xReset": True}, "только RESET"),
                ({"xSet": True}, "снова оба"),
            ),
        ),
        Scenario(
            "CountUp",
            "CTU до PV и сброс",
            seq(
                ({"xCu": True}, "фронт 1"),
                ({"xCu": False}, ""),
                ({"xCu": True}, "фронт 2"),
                ({"xCu": False}, ""),
                ({"xCu": True}, "фронт 3: Q"),
                ({"xReset": True}, "RESET"),
            ),
        ),
        Scenario(
            "CountDown",
            "CTD от PV до нуля и не ниже",
            seq(
                ({}, "CV = 0 → Q до загрузки"),
                ({"xLoad": True}, "LOAD: CV = 2"),
                ({"xLoad": False, "xCd": True}, "фронт: 1"),
                ({"xCd": False}, ""),
                ({"xCd": True}, "фронт: 0, Q"),
                ({"xCd": False}, ""),
                ({"xCd": True}, "фронт на нуле: остаётся 0"),
            ),
        ),
        Scenario(
            "Edges",
            "R_TRIG и F_TRIG, первый вызов",
            seq(
                ({}, "первый вызов CLK = 0: спада нет"),
                ({"xClk": True}, "фронт"),
                ({}, ""),
                ({"xClk": False}, "спад"),
                ({}, ""),
            ),
        ),
    ],
)
