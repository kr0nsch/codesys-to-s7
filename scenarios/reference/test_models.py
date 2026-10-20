"""Вторая проверка моделей: контрольные точки, посчитанные вручную по описаниям в spec.py (HAND_CHECKS).

Каждая точка: модель, последовательность (t_ms, входы) от нового экземпляра и ожидаемые выходы
последнего вызова. Если модель расходится с точкой — сначала сверяют описание поведения в spec.py.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

HAND_CHECKS: list[tuple[str, list[tuple[int, dict[str, Any]]], dict[str, Any]]] = [
    ("F_Convert", [(0, {"rIn": 2.5, "iA": 0, "iB": 1, "iSel": 0, "iMn": 0, "iMx": 100})], {"F_Convert": 3}),
    ("F_Convert", [(0, {"rIn": -2.5, "iA": 0, "iB": 1, "iSel": 0, "iMn": 0, "iMx": 100})], {"F_Convert": -3}),
    (
        "F_Convert",
        [(0, {"rIn": 0.0, "iA": 32767, "iB": 1, "iSel": 2, "iMn": 0, "iMx": 100})],
        {"iSum": -32768, "iMux": 30},
    ),
    ("F_Convert", [(0, {"rIn": 5.0, "iA": -7, "iB": 2, "iSel": 0, "iMn": 10, "iMx": 0})], {"iQuot": -3, "iLim": 0}),
    (
        "FB_Latch",
        [(0, {"xSet": True, "xReset": True, "xCu": False, "xCd": False, "xLoad": False, "xClk": False})],
        {"xSr": True, "xRs": False, "xFall": False, "xCdQ": True},
    ),
    (
        "FB_TimeIdioms",
        [(0, {"xIn": False, "tIn": 0}), (300, {}), (600, {})],
        {"xPulse": True},
    ),
    ("FB_TimeIdioms", [(0, {"xIn": False, "tIn": 31 * 86_400_000})], {"xLong": True}),
    (
        "FB_LevelAlarm",
        [(0, {"rLevel": 3.0, "rHigh": 2.0, "xEnable": False, "xAck": False})],
        {"xAlarm": False, "xLamp": False},
    ),
    (
        "FB_ValveCmd",
        [(0, {"xOpen": True, "iClosedPos": 0, "iOpenPos": 120, "iMin": 5, "iMax": 95})],
        {"iOut": 95, "xAtLimit": True},
    ),
    (
        "PRG_Permissives",
        [(0, {"xStartBtn": True, "xStopBtn": False, "xPermit": True, "xFault": False})],
        {"xRun": True, "xIdle": False},
    ),
    (
        "PRG_PumpInterlock",
        [(0, {"xP1Ready": True, "xP2Ready": True, "xP1Force": False, "xP2Force": False, "xEmergency": False})],
        {"xP1Run": True, "xP2Run": False},
    ),
    (
        "PRG_PumpInterlock",
        [(0, {"xP1Ready": False, "xP2Ready": False, "xP1Force": True, "xP2Force": True, "xEmergency": False})],
        {"xAlarm": False},
    ),
    ("FB_PiCfc", [(0, {"rSp": 1.0, "rPv": 0.0, "rKp": 2.0, "rKi": 0.5, "rMin": 0.0, "rMax": 10.0})], {"rOut": 2.5}),
    (
        "FB_RatioCfc",
        [(0, {"rFlow": 10.0, "rK": 0.5, "rBias": 1.0}), (100, {"rFlow": 20.0})],
        {"rPrev": 5.0, "rNow": 10.0},
    ),
    # Idle → Drain на цикле 100; Drain → Wash на цикле 2100 (2000 мс от цикла перехода); P исполняется
    # при активации и ещё раз последним вызовом
    (
        "PRG_Backwash",
        [(0, {"xStart": True, "xAbort": False}), (100, {"xStart": False}), (2100, {}), (2200, {}), (2300, {})],
        {"iCycles": 2, "iWashTicks": 2},
    ),
    ("PRG_FilterAlt", [(0, {"xHigh": True, "xLow": True, "xReset": False}), (100, {})], {"iFast": 1, "iSlow": 0}),
    ("FB_PulseCountIL", [(0, {"iN": 0, "iStep": 2, "iMax": 10})], {"iAcc": 2, "xOver": False}),
    ("F_ScaleIL", [(0, {"rRaw": 10.0, "rLo": 2.0, "rK": 0.5, "xGate": True})], {"F_ScaleIL": 4.0, "xGateEdge": True}),
]


@pytest.mark.parametrize(
    ("block", "seq", "expected"), HAND_CHECKS, ids=[f"{b}-{i}" for i, (b, _, _) in enumerate(HAND_CHECKS)]
)
def test_hand_checks(block: str, seq: list[tuple[int, dict[str, Any]]], expected: dict[str, Any]) -> None:
    spec = importlib.import_module(f"model_{block}").SPEC
    inst = spec.factory()
    cur: dict[str, Any] = {}
    out: dict[str, Any] = {}
    for t, inputs in seq:
        cur.update(inputs)
        out = inst.call(dict(cur), t)
    for k, v in expected.items():
        assert out[k] == pytest.approx(v), (block, k, out[k], v)
