"""Стандартные блоки и функции CODESYS для c2s7.sim (Standard 3.5.17).

Семантика — по описанию МЭК 61131-3 и справке CODESYS; спорные места сверены пробой M0 в Control Win
(docs/PROBES.md): SR — установка доминирует, RS — сброс; CTU/CTD насыщаются на 65535/0; LIMIT при
MN > MX возвращает MX; REAL_TO_INT округляет половину от нуля; F_TRIG на первом вызове с CLK = FALSE
спада не даёт.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, ClassVar

from c2s7.sim import values as V
from c2s7.st import types as T


class Arr:
    """Массив с нижней границей lo."""

    def __init__(self, lo: int, items: list[Any], elem: str | None = None) -> None:
        self.lo = lo
        self.items = items
        self.elem = elem

    def __getitem__(self, i: int) -> Any:
        k = i - self.lo
        if not 0 <= k < len(self.items):
            raise IndexError(f"индекс {i} вне [{self.lo}..{self.lo + len(self.items) - 1}]")
        return self.items[k]

    def __setitem__(self, i: int, v: Any) -> None:
        k = i - self.lo
        if not 0 <= k < len(self.items):
            raise IndexError(f"индекс {i} вне [{self.lo}..{self.lo + len(self.items) - 1}]")
        self.items[k] = V.coerce(v, self.elem) if self.elem else v


class Builtin:
    """Стандартный ФБ: переменные — словарь, run() — один вызов."""

    names: tuple[str, ...] = ()
    types: ClassVar[dict[str, str]] = {}

    def __init__(self, clock: Any) -> None:
        self.clock = clock
        self.v: dict[str, Any] = {}
        for n in self.names:
            t = self.types.get(n, "BOOL")
            self.v[n] = V.default(t)

    def get(self, name: str) -> Any:
        return self.v[name.upper()]

    def set(self, name: str, value: Any) -> None:
        up = name.upper()
        if up not in self.v:
            raise KeyError(f"{type(self).__name__}.{name}")
        self.v[up] = V.coerce(value, self.types.get(up, "BOOL"))

    def has(self, name: str) -> bool:
        return name.upper() in self.v

    def type_of(self, name: str) -> str:
        return self.types.get(name.upper(), "BOOL")

    def run(self) -> None:
        raise NotImplementedError


class _Timer(Builtin):
    names = ("IN", "PT", "Q", "ET")
    types: ClassVar[dict[str, str]] = {"IN": "BOOL", "PT": "TIME", "Q": "BOOL", "ET": "TIME"}

    def __init__(self, clock: Any) -> None:
        super().__init__(clock)
        self.m = False
        self.start = 0
        self.running = False

    def now(self) -> int:
        return int(self.clock.now_ms)


class TON(_Timer):
    def run(self) -> None:
        inp = self.v["IN"]
        if inp:
            if not self.m:
                self.start = self.now()
            el = self.now() - self.start
            pt = self.v["PT"]
            self.v["Q"] = el >= pt
            self.v["ET"] = min(el, pt)
        else:
            self.v["Q"] = False
            self.v["ET"] = 0
        self.m = inp


class TOF(_Timer):
    def run(self) -> None:
        inp = self.v["IN"]
        if inp:
            self.v["Q"] = True
            self.v["ET"] = 0
            self.running = False
        else:
            if self.m:
                self.start = self.now()
                self.running = True
            if self.running:
                el = self.now() - self.start
                pt = self.v["PT"]
                self.v["ET"] = min(el, pt)
                if el >= pt:
                    self.v["Q"] = False
                    self.running = False
        self.m = inp


class TP(_Timer):
    def run(self) -> None:
        inp = self.v["IN"]
        pt = self.v["PT"]
        if inp and not self.m and not self.running:
            self.start = self.now()
            self.running = True
        if self.running:
            el = self.now() - self.start
            if el >= pt:
                self.running = False
                self.v["Q"] = False
                self.v["ET"] = pt
            else:
                self.v["Q"] = True
                self.v["ET"] = el
        if not self.running and not inp:
            self.v["ET"] = 0
            self.v["Q"] = False
        self.m = inp


class R_TRIG(Builtin):
    names = ("CLK", "Q")

    def __init__(self, clock: Any) -> None:
        super().__init__(clock)
        self.m = False

    def run(self) -> None:
        clk = self.v["CLK"]
        self.v["Q"] = clk and not self.m
        self.m = clk


class F_TRIG(Builtin):
    names = ("CLK", "Q")

    def __init__(self, clock: Any) -> None:
        super().__init__(clock)
        self.m = False

    def run(self) -> None:
        clk = self.v["CLK"]
        self.v["Q"] = (not clk) and self.m
        self.m = clk


class SR(Builtin):
    names = ("SET1", "RESET", "Q1")

    def run(self) -> None:
        self.v["Q1"] = self.v["SET1"] or (not self.v["RESET"] and self.v["Q1"])


class RS(Builtin):
    names = ("SET", "RESET1", "Q1")

    def run(self) -> None:
        self.v["Q1"] = (not self.v["RESET1"]) and (self.v["SET"] or self.v["Q1"])


class CTU(Builtin):
    names = ("CU", "RESET", "PV", "Q", "CV")
    types: ClassVar[dict[str, str]] = {"PV": "WORD", "CV": "WORD"}

    def __init__(self, clock: Any) -> None:
        super().__init__(clock)
        self.m = False

    def run(self) -> None:
        cu = self.v["CU"]
        if self.v["RESET"]:
            self.v["CV"] = 0
        elif cu and not self.m and self.v["CV"] < 65535:
            self.v["CV"] += 1
        self.m = cu
        self.v["Q"] = self.v["CV"] >= self.v["PV"]


class CTD(Builtin):
    names = ("CD", "LOAD", "PV", "Q", "CV")
    types: ClassVar[dict[str, str]] = {"PV": "WORD", "CV": "WORD"}

    def __init__(self, clock: Any) -> None:
        super().__init__(clock)
        self.m = False

    def run(self) -> None:
        cd = self.v["CD"]
        if self.v["LOAD"]:
            self.v["CV"] = self.v["PV"]
        elif cd and not self.m and self.v["CV"] > 0:
            self.v["CV"] -= 1
        self.m = cd
        self.v["Q"] = self.v["CV"] <= 0


class CTUD(Builtin):
    names = ("CU", "CD", "RESET", "LOAD", "PV", "QU", "QD", "CV")
    types: ClassVar[dict[str, str]] = {"PV": "WORD", "CV": "WORD"}

    def __init__(self, clock: Any) -> None:
        super().__init__(clock)
        self.mu = False
        self.md = False

    def run(self) -> None:
        cu, cd = self.v["CU"], self.v["CD"]
        if self.v["RESET"]:
            self.v["CV"] = 0
        elif self.v["LOAD"]:
            self.v["CV"] = self.v["PV"]
        else:
            if cu and not self.mu and self.v["CV"] < 65535:
                self.v["CV"] += 1
            if cd and not self.md and self.v["CV"] > 0:
                self.v["CV"] -= 1
        self.mu, self.md = cu, cd
        self.v["QU"] = self.v["CV"] >= self.v["PV"]
        self.v["QD"] = self.v["CV"] <= 0


BUILTINS: dict[str, type[Builtin]] = {
    "TON": TON,
    "TOF": TOF,
    "TP": TP,
    "R_TRIG": R_TRIG,
    "F_TRIG": F_TRIG,
    "SR": SR,
    "RS": RS,
    "CTU": CTU,
    "CTD": CTD,
    "CTUD": CTUD,
}


# ---------------------------------------------------------------------------
# Функции
# ---------------------------------------------------------------------------

Val = tuple[Any, str | None]


def _pos(args: list[tuple[str | None, Val]], names: list[str]) -> list[Val]:
    """Аргументы по позициям; именованные — по списку имён CODESYS (и S7 для совместимости)."""
    out: list[Val | None] = [None] * len(names)
    i = 0
    for name, val in args:
        if name is None:
            out[i] = val
            i += 1
        else:
            up = name.upper()
            alias = {"MN": 0, "MX": 2}.get(up)
            if up in names:
                out[names.index(up)] = val
            elif alias is not None and len(names) == 3:
                out[alias] = val
            else:
                raise KeyError(name)
    return [x if x is not None else (0, None) for x in out]


def _num_type(*vals: Val) -> str | None:
    t: str | None = None
    for _, vt in vals:
        t = V.result_type(t, vt)
    return t


def _limit(args: list[tuple[str | None, Val]]) -> Val:
    mn, x, mx = _pos(args, ["MN", "IN", "MX"])
    return min(max(x[0], mn[0]), mx[0]), _num_type(mn, x, mx)


def _sel(args: list[tuple[str | None, Val]]) -> Val:
    g, a, b = _pos(args, ["G", "IN0", "IN1"])
    return b if g[0] else a


def _mux(args: list[tuple[str | None, Val]]) -> Val:
    vals = [v for _, v in args]
    k = int(vals[0][0])
    if not 0 <= k < len(vals) - 1:
        k = len(vals) - 2  # вне диапазона — последний вход (поведение CODESYS сверить, C2S7-SEM-MUX)
    return vals[k + 1]


def _minmax(f: Callable[..., Any]) -> Callable[[list[tuple[str | None, Val]]], Val]:
    def run(args: list[tuple[str | None, Val]]) -> Val:
        vals = [v for _, v in args]
        return f(v[0] for v in vals), _num_type(*vals)

    return run


def _real1(f: Callable[[float], float]) -> Callable[[list[tuple[str | None, Val]]], Val]:
    def run(args: list[tuple[str | None, Val]]) -> Val:
        (x, t) = args[0][1]
        r = f(float(x))
        return (V.f32(r) if (t or "REAL").upper() != "LREAL" else r), (t if (t or "").upper() == "LREAL" else "REAL")

    return run


def _abs(args: list[tuple[str | None, Val]]) -> Val:
    x, t = args[0][1]
    return abs(x), t


def _expt(args: list[tuple[str | None, Val]]) -> Val:
    (a, ta), (b, _) = args[0][1], args[1][1]
    r = float(a) ** float(b)
    return (r if (ta or "").upper() == "LREAL" else V.f32(r)), ta or "REAL"


def _shift(kind: str) -> Callable[[list[tuple[str | None, Val]]], Val]:
    def run(args: list[tuple[str | None, Val]]) -> Val:
        (x, t), (n, _) = _pos(args, ["IN", "N"])
        bits = V.BITS.get((t or "DWORD").upper(), 32)
        mask = (1 << bits) - 1
        x, n = int(x) & mask, int(n)
        if kind == "SHL":
            r = (x << n) & mask
        elif kind == "SHR":
            r = x >> n
        elif kind == "ROL":
            n %= bits
            r = ((x << n) | (x >> (bits - n))) & mask
        else:
            n %= bits
            r = ((x >> n) | (x << (bits - n))) & mask
        return r, t

    return run


def _str_args(args: list[tuple[str | None, Val]], names: list[str], s7: list[str]) -> list[Any]:
    out: list[Any] = [None] * len(names)
    i = 0
    for name, (v, _) in args:
        if name is None:
            out[i] = v
            i += 1
        else:
            up = name.upper()
            idx = names.index(up) if up in names else s7.index(up)
            out[idx] = v
    return out


def _len(args: list[tuple[str | None, Val]]) -> Val:
    (s,) = _str_args(args, ["STR"], ["IN"])
    return len(s), "INT"


def _left(args: list[tuple[str | None, Val]]) -> Val:
    s, n = _str_args(args, ["STR", "SIZE"], ["IN", "L"])
    return s[: max(0, int(n))], "STRING"


def _right(args: list[tuple[str | None, Val]]) -> Val:
    s, n = _str_args(args, ["STR", "SIZE"], ["IN", "L"])
    n = max(0, int(n))
    return (s[-n:] if n else ""), "STRING"


def _mid(args: list[tuple[str | None, Val]]) -> Val:
    s, n, p = _str_args(args, ["STR", "LEN", "POS"], ["IN", "L", "P"])
    p, n = int(p), int(n)
    return s[p - 1 : p - 1 + n] if p >= 1 else "", "STRING"


def _concat(args: list[tuple[str | None, Val]]) -> Val:
    a, b = _str_args(args, ["STR1", "STR2"], ["IN1", "IN2"])
    return a + b, "STRING"


def _find(args: list[tuple[str | None, Val]]) -> Val:
    a, b = _str_args(args, ["STR1", "STR2"], ["IN1", "IN2"])
    return a.find(b) + 1, "INT"


def _insert(args: list[tuple[str | None, Val]]) -> Val:
    a, b, p = _str_args(args, ["STR1", "STR2", "POS"], ["IN1", "IN2", "P"])
    p = int(p)
    return a[:p] + b + a[p:], "STRING"


def _delete(args: list[tuple[str | None, Val]]) -> Val:
    s, n, p = _str_args(args, ["STR", "LEN", "POS"], ["IN", "L", "P"])
    p, n = int(p), int(n)
    return s[: p - 1] + s[p - 1 + n :], "STRING"


def _replace(args: list[tuple[str | None, Val]]) -> Val:
    a, b, n, p = _str_args(args, ["STR1", "STR2", "L", "P"], ["IN1", "IN2", "L", "P"])
    p, n = int(p), int(n)
    return a[: p - 1] + b + a[p - 1 + n :], "STRING"


FUNCS: dict[str, Callable[[list[tuple[str | None, Val]]], Val]] = {
    "LIMIT": _limit,
    "SEL": _sel,
    "MUX": _mux,
    "MIN": _minmax(min),
    "MAX": _minmax(max),
    "ABS": _abs,
    "SQRT": _real1(math.sqrt),
    "LN": _real1(math.log),
    "LOG": _real1(math.log10),
    "EXP": _real1(math.exp),
    "SIN": _real1(math.sin),
    "COS": _real1(math.cos),
    "TAN": _real1(math.tan),
    "ASIN": _real1(math.asin),
    "ACOS": _real1(math.acos),
    "ATAN": _real1(math.atan),
    "EXPT": _expt,
    "MOVE": lambda a: a[0][1],
    "SHL": _shift("SHL"),
    "SHR": _shift("SHR"),
    "ROL": _shift("ROL"),
    "ROR": _shift("ROR"),
    "LEN": _len,
    "LEFT": _left,
    "RIGHT": _right,
    "MID": _mid,
    "CONCAT": _concat,
    "FIND": _find,
    "INSERT": _insert,
    "DELETE": _delete,
    "REPLACE": _replace,
}


def convert(name: str, x: Any) -> Val:
    """X_TO_Y CODESYS: REAL → целое округляет половину от нуля; целые — перенос по разрядности."""
    src, _, dst = name.upper().partition("_TO_")
    el = T.elem(dst)
    if dst == "STRING":
        return str(x), "STRING"
    if el is None:
        raise KeyError(name)
    if src in ("REAL", "LREAL") and el.cat in ("int", "bits", "time"):
        return V.coerce(V.round_half_away(float(x)), dst), dst
    if el.cat == "bool":
        return bool(x), "BOOL"
    if el.cat == "real":
        return V.coerce(float(x), dst), dst
    if isinstance(x, bool):
        x = int(x)
    return V.coerce(int(x), dst), dst


def call_function(name: str, args: list[tuple[str | None, Val]]) -> Val:
    up = name.upper()
    if up in FUNCS:
        return FUNCS[up](args)
    if up == "TRUNC":
        return int(float(args[0][1][0])), "DINT"
    if "_TO_" in up:
        return convert(up, args[0][1][0])
    if up.startswith("TO_"):
        return convert("X_TO_" + up[3:], args[0][1][0])
    raise KeyError(f"функция {name} вне подмножества c2s7.sim")
