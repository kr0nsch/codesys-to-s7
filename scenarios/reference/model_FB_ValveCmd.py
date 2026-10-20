"""Модель FB_ValveCmd (описание — corpus/fbd/FB_ValveCmd/spec.py)."""

from __future__ import annotations

from typing import Any

from refcommon import ModelSpec, Row, Scenario


class Model:
    def call(self, i: dict[str, Any], t: int) -> dict[str, Any]:
        cmd = i["iOpenPos"] if i["xOpen"] else i["iClosedPos"]
        pos = min(max(cmd, i["iMin"]), i["iMax"])
        return {"iOut": pos, "xAtLimit": pos in (i["iMin"], i["iMax"])}


SPEC = ModelSpec(
    "FB_ValveCmd",
    [("xOpen", "BOOL"), ("iClosedPos", "INT"), ("iOpenPos", "INT"), ("iMin", "INT"), ("iMax", "INT")],
    [("iOut", "INT"), ("xAtLimit", "BOOL")],
    Model,
    [
        Scenario(
            "Select",
            "SEL, LIMIT и признак упора",
            [
                Row(
                    0,
                    {"xOpen": False, "iClosedPos": 0, "iOpenPos": 80, "iMin": 5, "iMax": 95},
                    "закрыта: 0 → 5, на упоре",
                ),
                Row(100, {"xOpen": True}, "открыта: 80"),
                Row(200, {"iOpenPos": 120}, "120 → 95, на упоре"),
                Row(300, {"xOpen": False, "iClosedPos": 50}, "закрытое положение 50"),
            ],
        ),
    ],
)
