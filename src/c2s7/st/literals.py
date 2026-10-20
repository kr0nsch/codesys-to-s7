"""Литералы ST/SCL: время, дата, целые с основанием, строки с экранированием `$`."""

from __future__ import annotations

import re

_TIME_UNITS_NS = {
    "d": 86_400_000_000_000,
    "h": 3_600_000_000_000,
    "m": 60_000_000_000,
    "s": 1_000_000_000,
    "ms": 1_000_000,
    "us": 1_000,
    "ns": 1,
}
_TIME_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|us|ns|d|h|m|s)", re.IGNORECASE)

TIME_MAX_CDS_MS = 2**32 - 1  # 49d17h2m47s295ms, TIME CODESYS без знака
TIME_MAX_S7_MS = 2**31 - 1  # 24d20h31m23s647ms, Time S7 со знаком


class LiteralError(ValueError):
    pass


def split_prefix(text: str) -> tuple[str, str]:
    """`T#5s` → ('T', '5s')."""
    head, _, body = text.partition("#")
    return head, body


def parse_duration_ns(body: str) -> int:
    """Тело литерала времени (`1h30m`, `1.5s`, `-5s`, `500`) → наносекунды."""
    text = body.replace("_", "").strip()
    sign = 1
    if text.startswith(("-", "+")):
        sign = -1 if text[0] == "-" else 1
        text = text[1:]
    if text.isdigit():
        return sign * int(text) * _TIME_UNITS_NS["ms"]
    pos = 0
    total = 0.0
    for m in _TIME_PART.finditer(text):
        if m.start() != pos:
            raise LiteralError(f"литерал времени: {body!r}")
        total += float(m.group(1)) * _TIME_UNITS_NS[m.group(2).lower()]
        pos = m.end()
    if pos != len(text) or pos == 0:
        raise LiteralError(f"литерал времени: {body!r}")
    return sign * round(total)


def parse_time_ms(text: str) -> int:
    """`T#1h30m` → миллисекунды (целые; доли мс отбрасываются)."""
    _, body = split_prefix(text)
    ns = parse_duration_ns(body)
    return ns // 1_000_000 if ns >= 0 else -((-ns) // 1_000_000)


def format_duration(ms: int, prefix: str = "T#") -> str:
    """Миллисекунды → канонический литерал `T#1D2H3M4S5MS` (как пишет TIA)."""
    if ms == 0:
        return f"{prefix}0MS"
    sign = "-" if ms < 0 else ""
    rest = abs(ms)
    parts = []
    for unit, size in (("D", 86_400_000), ("H", 3_600_000), ("M", 60_000), ("S", 1000), ("MS", 1)):
        q, rest = divmod(rest, size)
        if q:
            parts.append(f"{q}{unit}")
    return f"{prefix}{sign}{''.join(parts)}"


def format_duration_ns(ns: int, prefix: str = "LT#") -> str:
    if ns == 0:
        return f"{prefix}0NS"
    sign = "-" if ns < 0 else ""
    rest = abs(ns)
    parts = []
    for unit, size in (
        ("D", 86_400_000_000_000),
        ("H", 3_600_000_000_000),
        ("M", 60_000_000_000),
        ("S", 1_000_000_000),
        ("MS", 1_000_000),
        ("US", 1_000),
        ("NS", 1),
    ):
        q, rest = divmod(rest, size)
        if q:
            parts.append(f"{q}{unit}")
    return f"{prefix}{sign}{''.join(parts)}"


def parse_int(text: str) -> int:
    """Целое: `1_000`, `16#FF`, `2#1010`, `8#17`, с типом `INT#5` и знаком."""
    t = text.replace("_", "")
    if "#" in t:
        head, _, body = t.partition("#")
        if head.isdigit():
            return int(body, int(head))
        return parse_int(body)
    return int(t, 10)


def parse_typed(text: str) -> tuple[str, str]:
    """`INT#5` → ('INT', '5'); `DWORD#16#FF` → ('DWORD', '16#FF')."""
    head, _, body = text.partition("#")
    return head.upper(), body


_ESC = {"$": "$", "'": "'", '"': '"', "L": "\n", "N": "\n", "P": "\f", "R": "\r", "T": "\t"}


def unescape(body: str) -> str:
    """Тело строки без кавычек: `$'`, `$$`, `$N`, `$41` → символы."""
    out = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "$" and i + 1 < len(body):
            nxt = body[i + 1]
            if nxt.upper() in _ESC:
                out.append(_ESC[nxt.upper()])
                i += 2
                continue
            hexpart = body[i + 1 : i + 3]
            if len(hexpart) == 2 and all(c in "0123456789abcdefABCDEF" for c in hexpart):
                out.append(chr(int(hexpart, 16)))
                i += 3
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def escape(value: str, quote: str = "'") -> str:
    """Строка → тело литерала с экранированием `$` (для ST и SCL одинаково)."""
    out = []
    for ch in value:
        if ch == "$":
            out.append("$$")
        elif ch == quote:
            out.append("$" + quote)
        elif ch == "\n":
            out.append("$N")
        elif ch == "\r":
            out.append("$R")
        elif ch == "\t":
            out.append("$T")
        elif ord(ch) < 32:
            out.append(f"${ord(ch):02X}")
        else:
            out.append(ch)
    return "".join(out)


def parse_date_days(text: str) -> int:
    """`D#2024-01-31` → дни от 1970-01-01."""
    import datetime as dt

    _, body = split_prefix(text)
    y, m, d = (int(p) for p in body.split("-"))
    return (dt.date(y, m, d) - dt.date(1970, 1, 1)).days


def parse_tod_ms(text: str) -> int:
    _, body = split_prefix(text)
    parts = body.split(":")
    h, mi = int(parts[0]), int(parts[1])
    sec = float(parts[2]) if len(parts) > 2 else 0.0
    return round(((h * 60 + mi) * 60 + sec) * 1000)


def parse_dt_s(text: str) -> float:
    import datetime as dt

    _, body = split_prefix(text)
    date_part, _, time_part = body.rpartition("-") if body.count("-") == 3 else (body, "", "")
    y, m, d = (int(p) for p in date_part.split("-"))
    parts = time_part.split(":") if time_part else ["0", "0"]
    h, mi = int(parts[0]), int(parts[1])
    sec = float(parts[2]) if len(parts) > 2 else 0.0
    base = dt.datetime(y, m, d) - dt.datetime(1970, 1, 1)
    return base.total_seconds() + h * 3600 + mi * 60 + sec
