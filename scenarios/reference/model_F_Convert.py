"""Модель F_Convert (описание — corpus/st/F_Convert/spec.py)."""

from __future__ import annotations

from typing import Any

from refcommon import ModelSpec, Row, Scenario, div_trunc, real_to_int, wrap


class Model:
    def call(self, i: dict[str, Any], t: int) -> dict[str, Any]:
        r = real_to_int(i["rIn"])
        mn, mx = i["iMn"], i["iMx"]
        return {
            "F_Convert": r,
            "iSum": wrap(i["iA"] + i["iB"]),
            "iQuot": wrap(div_trunc(i["iA"], i["iB"])) if i["iB"] != 0 else 0,
            "iMux": (10, 20, 30)[i["iSel"]],
            "iLim": min(max(r, mn), mx),
        }


BASE = {"rIn": 0.0, "iA": 0, "iB": 1, "iSel": 0, "iMn": 0, "iMx": 100}


def rows(*changes: tuple[dict[str, Any], str]) -> list[Row]:
    return [Row(100 * k, {**BASE, **ch}, c) for k, (ch, c) in enumerate(changes)]


SPEC = ModelSpec(
    "F_Convert",
    [("rIn", "REAL"), ("iA", "INT"), ("iB", "INT"), ("iSel", "INT"), ("iMn", "INT"), ("iMx", "INT")],
    [("F_Convert", "INT"), ("iSum", "INT"), ("iQuot", "INT"), ("iMux", "INT"), ("iLim", "INT")],
    Model,
    [
        Scenario(
            "Rounding",
            "REAL_TO_INT: половина от нуля",
            rows(
                ({"rIn": 2.5}, "2.5 → 3"),
                ({"rIn": -2.5}, "−2.5 → −3"),
                ({"rIn": 3.5}, "3.5 → 4"),
                ({"rIn": 0.4}, "0.4 → 0"),
                ({"rIn": -0.6}, "−0.6 → −1"),
            ),
        ),
        Scenario(
            "Overflow",
            "сумма INT с переносом",
            rows(({"iA": 32767, "iB": 1}, "32767 + 1 → −32768"), ({"iA": -32768, "iB": -1}, "−32768 − 1 → 32767")),
        ),
        Scenario(
            "Division",
            "деление к нулю и защита от 0",
            rows(
                ({"iA": 7, "iB": 2}, "7 / 2 → 3"),
                ({"iA": -7, "iB": 2}, "−7 / 2 → −3"),
                ({"iA": 5, "iB": 0}, "делитель 0 → 0"),
            ),
        ),
        Scenario("Mux", "MUX по индексу", rows(({"iSel": 0}, "K=0"), ({"iSel": 1}, "K=1"), ({"iSel": 2}, "K=2"))),
        Scenario(
            "Limit",
            "LIMIT в норме и при MN > MX",
            rows(
                ({"rIn": 150.0}, "150 → MX = 100"),
                ({"rIn": 5.0, "iMn": 10, "iMx": 0}, "MN 10 > MX 0 → MX = 0"),
                ({"rIn": -5.0, "iMn": 0, "iMx": 100}, "−5 → MN = 0"),
            ),
        ),
    ],
)
