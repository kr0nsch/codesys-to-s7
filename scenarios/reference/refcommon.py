"""Общее для эталонных моделей корпуса «Заречная»: типы CODESYS, таймеры и фронты, формат CSV.

Модели пишутся по описанию поведения в шапке `corpus/<язык>/<кейс>/spec.py`, а не по тексту POU и не
по выходу c2s7. Формат CSV — как у s7-to-codesys (`tests/fixtures/s7-to-codesys/scenarios/README.md`).
Семантика стандартных блоков — по пробе M0 в CODESYS Control Win (docs/PROBES.md).
"""

from __future__ import annotations

import csv
import io
import math
import struct
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


def f32(x: float) -> float:
    return float(struct.unpack("<f", struct.pack("<f", float(x)))[0])


def wrap(v: int, bits: int = 16, signed: bool = True) -> int:
    v &= (1 << bits) - 1
    if signed and v >= 1 << (bits - 1):
        v -= 1 << bits
    return v


def real_to_int(x: float) -> int:
    """CODESYS REAL_TO_INT: половина от нуля (проба M0)."""
    return wrap(math.floor(abs(x) + 0.5) * (1 if x >= 0 else -1))


def div_trunc(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


class Ton:
    def __init__(self) -> None:
        self.start: int | None = None
        self.q = False
        self.et = 0

    def __call__(self, inp: bool, pt: int, now: int) -> bool:
        if inp:
            if self.start is None:
                self.start = now
            self.et = min(now - self.start, pt)
            self.q = self.et >= pt
        else:
            self.start, self.et, self.q = None, 0, False
        return self.q


class RTrig:
    def __init__(self) -> None:
        self.m = False

    def __call__(self, clk: bool) -> bool:
        q = clk and not self.m
        self.m = clk
        return q


class FTrig:
    """F_TRIG Standard 3.5.17: Q := NOT CLK AND M, M := CLK (первый вызов с CLK = FALSE — спада нет, M0)."""

    def __init__(self) -> None:
        self.m = False

    def __call__(self, clk: bool) -> bool:
        q = (not clk) and self.m
        self.m = clk
        return q


@dataclass
class Row:
    t: int
    inputs: dict[str, Any]
    comment: str = ""
    boundary: bool = False


@dataclass
class Scenario:
    name: str
    description: str
    rows: list[Row] = field(default_factory=list)


@dataclass
class ModelSpec:
    block: str
    inputs: list[tuple[str, str]]  # (имя, тип CSV)
    outputs: list[tuple[str, str]]
    factory: Callable[[], Any]  # новый экземпляр модели: obj.call(inputs: dict, t: int) -> dict выходов
    scenarios: list[Scenario]
    tolerance: float = 1e-4


def fmt(value: Any, typ: str) -> str:
    if typ == "BOOL":
        return "TRUE" if value else "FALSE"
    if typ == "TIME":
        return f"T#{int(value)}MS"
    if typ in ("REAL", "LREAL"):
        r = repr(float(value))
        return r[:-2] if r.endswith(".0") else r
    if typ.upper().startswith("STRING"):
        return str(value)
    if typ.upper() in ("WORD", "DWORD", "BYTE", "LWORD") and isinstance(value, int):
        return str(value)
    return str(int(value))


def render_csv(spec: ModelSpec) -> str:
    head = ["scenario", "cycle", "t_ms"]
    head += [f"in.{n}:{t}" for n, t in spec.inputs]
    for n, t in spec.outputs:
        head.append(f"out.{n}:{t}")
        if t in ("REAL", "LREAL"):
            head.append(f"tol.{n}")
    head += ["boundary", "comment"]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(head)
    for sc in spec.scenarios:
        inst = spec.factory()
        current: dict[str, Any] = {}
        for k, row in enumerate(sc.rows, start=1):
            current.update(row.inputs)
            missing = [n for n, _ in spec.inputs if n not in current]
            if missing:
                raise ValueError(f"{spec.block}/{sc.name}: нет входов {missing}")
            outs = inst.call(dict(current), row.t)
            line = [sc.name, str(k), str(row.t)]
            line += [fmt(current[n], t) for n, t in spec.inputs]
            for n, t in spec.outputs:
                line.append(fmt(outs[n], t))
                if t in ("REAL", "LREAL"):
                    line.append(repr(spec.tolerance))
            line += ["TRUE" if row.boundary else "FALSE", row.comment]
            w.writerow(line)
    return buf.getvalue()
