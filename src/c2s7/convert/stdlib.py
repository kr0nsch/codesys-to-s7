"""Стандартные блоки и функции CODESYS → инструкции S7 (имена, параметры, класс)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FbMap:
    s7: str  # тип экземпляра в S7
    instruction: str | None  # InstructionName (системный ФБ) или None — блок CodesysCompat
    params: dict[str, str] = field(default_factory=dict)  # параметр CODESYS → S7
    rule: str | None = None  # правило C2S7, которое ставится на объявление
    compat: str | None = None


STD_FB: dict[str, FbMap] = {
    "TON": FbMap("TON_TIME", "TON_TIME"),
    "TOF": FbMap("TOF_TIME", "TOF_TIME"),
    "TP": FbMap("TP_TIME", "TP_TIME"),
    "LTON": FbMap("TON_LTIME", "TON_LTIME"),
    "LTOF": FbMap("TOF_LTIME", "TOF_LTIME"),
    "LTP": FbMap("TP_LTIME", "TP_LTIME"),
    "R_TRIG": FbMap("R_TRIG", "R_TRIG"),
    "F_TRIG": FbMap("F_TRIG", "F_TRIG"),
    "CTU": FbMap("CTU_UINT", "CTU_UINT", {"RESET": "R"}, rule="C2S7-SEM-CTR"),
    "CTD": FbMap("CTD_UINT", "CTD_UINT", {"LOAD": "LD"}, rule="C2S7-SEM-CTR"),
    "CTUD": FbMap("CTUD_UINT", "CTUD_UINT", {"RESET": "R", "LOAD": "LD"}, rule="C2S7-SEM-CTR"),
    "SR": FbMap("CDS_SR", None, rule="C2S7-SEM-SRRS", compat="CDS_SR"),
    "RS": FbMap("CDS_RS", None, rule="C2S7-SEM-SRRS", compat="CDS_RS"),
}
TIMERS = {"TON", "TOF", "TP", "LTON", "LTOF", "LTP"}
COUNTERS = {"CTU", "CTD", "CTUD"}

# Блоки S7Compat s7-to-codesys (MAPPING.md @ 2285760c): обратное распознавание в кольце
S7COMPAT_FB = {"FB_S7TON": "TON", "FB_S7TOF": "TOF", "FB_S7TP": "TP", "FB_S7FTRIG": "F_TRIG"}
S7COMPAT_OBJECTS = {"F_NORMX", "F_SCALEX", "F_S7NOW", "FB_S7TON", "FB_S7TOF", "FB_S7TP", "FB_S7FTRIG", "GVL_S7CLOCK"}

# Функции: формальные параметры S7 по позициям CODESYS
FUNC_FORMAL: dict[str, list[str]] = {
    "LIMIT": ["MN", "IN", "MX"],
    "SEL": ["G", "IN0", "IN1"],
    "MOVE": ["IN"],
}
VARIADIC_IN = {"MIN", "MAX"}  # IN1, IN2, ...
MUX = "MUX"  # K, IN0, IN1, ...

# Строковые функции: параметры CODESYS → S7 (R§4.3)
STRING_FUNCS: dict[str, list[str]] = {
    "CONCAT": ["IN1", "IN2"],
    "LEFT": ["IN", "L"],
    "RIGHT": ["IN", "L"],
    "MID": ["IN", "L", "P"],
    "FIND": ["IN1", "IN2"],
    "INSERT": ["IN1", "IN2", "P"],
    "DELETE": ["IN", "L", "P"],
    "REPLACE": ["IN1", "IN2", "L", "P"],
    "LEN": ["IN"],
}
STRING_PARAM_CDS: dict[str, dict[str, str]] = {
    "CONCAT": {"STR1": "IN1", "STR2": "IN2"},
    "LEFT": {"STR": "IN", "SIZE": "L"},
    "RIGHT": {"STR": "IN", "SIZE": "L"},
    "MID": {"STR": "IN", "LEN": "L", "POS": "P"},
    "FIND": {"STR1": "IN1", "STR2": "IN2"},
    "INSERT": {"STR1": "IN1", "STR2": "IN2", "POS": "P"},
    "DELETE": {"STR": "IN", "LEN": "L", "POS": "P"},
    "REPLACE": {"STR1": "IN1", "STR2": "IN2", "L": "L", "P": "P"},
    "LEN": {"STR": "IN"},
}

# Функции с одним аргументом и тем же именем в SCL
UNARY_SAME = {"ABS", "SQRT", "LN", "LOG", "EXP", "SIN", "COS", "TAN", "ASIN", "ACOS", "ATAN", "TRUNC", "NOT"}
SHIFT = {"SHL", "SHR", "ROL", "ROR"}  # (IN, N)

# Библиотеки и функции без аналога в P0
LIB_FUNCS = {
    "ADR": "C2S7-TYPE-PTR",
    "__NEW": "C2S7-TYPE-PTR",
    "__DELETE": "C2S7-TYPE-PTR",
    "__ISVALIDREF": "C2S7-TYPE-PTR",
    "SIZEOF": "C2S7-LIB",
    "BITADR": "C2S7-LIB",
    "MEMCPY": "C2S7-LIB",
    "MEMSET": "C2S7-LIB",
}
LIB_NAMESPACES = {
    "MEMUTILS",
    "SYSMEM",
    "SYSTIME",
    "SYSTIMERTC",
    "SYSFILE",
    "SYSSOCKET",
    "CAA",
    "NBS",
    "FILE",
    "OSCAT",
    "OSCAT_BASIC",
    "OWEN",
    "MODBUS",
    "IODRVMODBUS",
    "CMPAPP",
    "SYSLIBTIME",
    "UTIL",
    "DTU",
}
