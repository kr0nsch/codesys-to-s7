"""Элементарные типы CODESYS и S7: разрядность, знак, категория, имя в SCL."""

from __future__ import annotations

from dataclasses import dataclass

from c2s7.st import nodes as A


@dataclass(frozen=True)
class Elem:
    cds: str  # имя в CODESYS (каноническое)
    s7: str  # имя в SCL
    cat: str  # bool int bits real time ltime date tod dt ldt ltod
    bits: int = 0
    signed: bool = False
    is64: bool = False


ELEMS: dict[str, Elem] = {
    e.cds: e
    for e in (
        Elem("BOOL", "Bool", "bool", 1),
        Elem("BIT", "Bool", "bool", 1),
        Elem("BYTE", "Byte", "bits", 8),
        Elem("WORD", "Word", "bits", 16),
        Elem("DWORD", "DWord", "bits", 32),
        Elem("LWORD", "LWord", "bits", 64, is64=True),
        Elem("SINT", "SInt", "int", 8, True),
        Elem("USINT", "USInt", "int", 8),
        Elem("INT", "Int", "int", 16, True),
        Elem("UINT", "UInt", "int", 16),
        Elem("DINT", "DInt", "int", 32, True),
        Elem("UDINT", "UDInt", "int", 32),
        Elem("LINT", "LInt", "int", 64, True, is64=True),
        Elem("ULINT", "ULInt", "int", 64, is64=True),
        Elem("REAL", "Real", "real", 32, True),
        Elem("LREAL", "LReal", "real", 64, True),
        Elem("TIME", "Time", "time", 32),
        Elem("LTIME", "LTime", "ltime", 64, is64=True),
        Elem("DATE", "Date", "date", 32),
        Elem("TOD", "Time_Of_Day", "tod", 32),
        Elem("TIME_OF_DAY", "Time_Of_Day", "tod", 32),
        Elem("DT", "Date_And_Time", "dt", 32),
        Elem("DATE_AND_TIME", "Date_And_Time", "dt", 32),
        Elem("LDT", "LDT", "ldt", 64, is64=True),
        Elem("LTOD", "LTOD", "ltod", 64, is64=True),
        Elem("__XWORD", "DWord", "bits", 32),
        Elem("__UXINT", "UDInt", "int", 32),
        Elem("__XINT", "DInt", "int", 32, True),
    )
}

INT_ORDER = ["SINT", "USINT", "INT", "UINT", "DINT", "UDINT", "LINT", "ULINT"]
STD_FB = {"TON", "TOF", "TP", "LTON", "LTOF", "LTP", "CTU", "CTD", "CTUD", "R_TRIG", "F_TRIG", "SR", "RS", "RTC"}
UTIL_FB = {
    "BLINK",
    "HYSTERESIS",
    "LIMITALARM",
    "RAMP_INT",
    "RAMP_REAL",
    "PID",
    "PID_FIXCYCLE",
    "PD",
    "INTEGRAL",
    "DERIVATIVE",
    "LIN_TRAFO",
    "STATISTICS_INT",
    "STATISTICS_REAL",
    "VARIANCE",
    "FREQ_MEASURE",
    "GEN",
    "CHARCURVE",
    "BCD_TO_INT",
    "INT_TO_BCD",
}


def elem(name: str) -> Elem | None:
    up = name.upper()
    if up.startswith("STANDARD."):
        up = up[len("STANDARD.") :]
    return ELEMS.get(up)


def type_name(tr: A.TypeRef | None) -> str | None:
    """Имя для именованных типов (без пространства имён библиотеки Standard)."""
    if isinstance(tr, A.NamedType):
        n = tr.name
        return n[len("Standard.") :] if n.lower().startswith("standard.") else n
    return None


def is_string(tr: A.TypeRef | None) -> bool:
    return isinstance(tr, A.StringType)


def category(tr: A.TypeRef | None) -> str | None:
    if tr is None:
        return None
    if isinstance(tr, A.StringType):
        return "wstring" if tr.wide else "string"
    if isinstance(tr, A.SubrangeType):
        e = elem(tr.base)
        return e.cat if e else None
    name = type_name(tr)
    if name:
        e = elem(name)
        return e.cat if e else None
    return None


def bits(tr: A.TypeRef | None) -> int:
    name = type_name(tr)
    if name:
        e = elem(name)
        return e.bits if e else 0
    if isinstance(tr, A.SubrangeType):
        e = elem(tr.base)
        return e.bits if e else 0
    return 0


def is_signed_int(tr: A.TypeRef | None) -> bool:
    name = type_name(tr)
    e = elem(name) if name else None
    return bool(e and e.cat == "int" and e.signed)


def int_range(name: str) -> tuple[int, int] | None:
    e = elem(name)
    if not e or e.cat not in ("int", "bits"):
        return None
    if e.cat == "bits" or not e.signed:
        return 0, 2**e.bits - 1
    return -(2 ** (e.bits - 1)), 2 ** (e.bits - 1) - 1
