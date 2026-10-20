"""Значения c2s7.sim: семантика CODESYS 3.5 для элементарных типов.

Целые хранятся как int Python и приводятся к разрядности типа при записи (перенос, как у CODESYS —
проба M0: INT 32767 + 1 = −32768); промежуточные результаты — без ограничения (CODESYS считает их не
меньше чем в 32 битах, проба M0). REAL — float32 (округление при записи и в операциях REAL×REAL),
LREAL — float64. TIME — миллисекунды, 32 бита без знака; LTIME — наносекунды, 64 бита без знака.
"""

from __future__ import annotations

import math
import struct
from typing import Any

from c2s7.st import types as T

INT_BITS = {
    "SINT": (8, True),
    "USINT": (8, False),
    "INT": (16, True),
    "UINT": (16, False),
    "DINT": (32, True),
    "UDINT": (32, False),
    "LINT": (64, True),
    "ULINT": (64, False),
}
BITS = {"BYTE": 8, "WORD": 16, "DWORD": 32, "LWORD": 64}


def f32(x: float) -> float:
    if math.isnan(x) or math.isinf(x):
        return x
    try:
        return float(struct.unpack("<f", struct.pack("<f", x))[0])
    except OverflowError:
        return math.copysign(math.inf, x)


def wrap(value: int, bits: int, signed: bool) -> int:
    mask = (1 << bits) - 1
    v = value & mask
    if signed and v >= 1 << (bits - 1):
        v -= 1 << bits
    return v


def round_half_away(x: float) -> int:
    """REAL_TO_INT CODESYS: половина от нуля (проба M0: 2.5 → 3, −2.5 → −3)."""
    if math.isnan(x) or math.isinf(x):
        return 0
    return math.floor(abs(x) + 0.5) * (1 if x >= 0 else -1)


def coerce(value: Any, tname: str | None) -> Any:
    """Значение → тип переменной при записи."""
    if tname is None:
        return value
    up = tname.upper()
    if up.startswith("STANDARD."):
        up = up[9:]
    if up in ("BOOL", "BIT"):
        return bool(value)
    if up in INT_BITS:
        bits, signed = INT_BITS[up]
        if isinstance(value, float):
            value = int(value)  # неявного REAL → INT в CODESYS нет; на всякий случай — отбрасывание
        return wrap(int(value), bits, signed)
    if up in BITS:
        return wrap(int(value), BITS[up], False)
    if up == "REAL":
        return f32(float(value))
    if up == "LREAL":
        return float(value)
    if up == "TIME":
        return wrap(int(value), 32, False)
    if up == "LTIME":
        return wrap(int(value), 64, False)
    if up in ("DATE", "TOD", "TIME_OF_DAY", "DT", "DATE_AND_TIME"):
        return wrap(int(value), 32, False)
    return value


def default(tname: str) -> Any:
    up = tname.upper()
    el = T.elem(up)
    if el is None:
        return None
    if el.cat == "bool":
        return False
    if el.cat == "real":
        return 0.0
    return 0


def result_type(a: str | None, b: str | None) -> str | None:
    """Тип результата бинарной операции (неявное расширение МЭК)."""
    if a is None:
        return b
    if b is None:
        return a
    ua, ub = a.upper(), b.upper()
    if "LREAL" in (ua, ub):
        return "LREAL"
    if "REAL" in (ua, ub):
        return "REAL"
    if ua in ("TIME", "LTIME") or ub in ("TIME", "LTIME"):
        return "LTIME" if "LTIME" in (ua, ub) else "TIME"
    ea, eb = T.elem(ua), T.elem(ub)
    if ea and eb and ea.bits != eb.bits:
        return ua if ea.bits > eb.bits else ub
    return ua
