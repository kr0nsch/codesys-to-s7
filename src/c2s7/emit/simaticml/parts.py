"""Реестр частей FlgNet (Part@Name, пины, шаблоны), которые пишет c2s7, с источником каждой строки.

Уровни: [H] — есть в эталонном наборе bulaofen0036-coder/TIA_Portal_Openness_MCP @ e131b257 (MIT,
`Engineering version="V21"`, происхождение [M]: круглая метка времени, проверка M0); [M] — по аналогии
с частью из набора и по реестру инструкций s7-lint-vscode @ 0735f8ff (имена FBD A/O/X); [L] — по
схеме LADFBD_v5 без эталона. Валидатор (`validate.py`) проверяет выход по этой таблице.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PartSpec:
    name: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    templates: tuple[str, ...] = ()
    version: str | None = None
    instance: bool = False
    card_inputs: str | None = None  # префикс входов по Card: in1..inN
    operand: bool = False  # вход-операнд (переменная) у контакта/катушки
    level: str = "H"
    source: str = "bulaofen e131b257"
    langs: tuple[str, ...] = ("LAD", "FBD")
    extra: dict[str, str] = field(default_factory=dict)


REF = "bulaofen0036-coder/TIA_Portal_Openness_MCP @ e131b257, MCPVerify_*.xml"
_CMP_SRC = REF + " (Eq/Ne/Gt/Ge/Lt/Le)"

PARTS: dict[str, PartSpec] = {
    "Contact": PartSpec("Contact", ("in", "operand"), ("out",), operand=True, langs=("LAD",), source=REF),
    "Coil": PartSpec("Coil", ("in", "operand"), ("out",), operand=True, source=REF),
    "SCoil": PartSpec("SCoil", ("in", "operand"), ("out",), operand=True, source=REF),
    "RCoil": PartSpec("RCoil", ("in", "operand"), ("out",), operand=True, source=REF),
    "Not": PartSpec("Not", ("in",), ("out",), langs=("LAD",), source=REF),
    "PBox": PartSpec("PBox", ("in", "bit"), ("out",), source=REF),
    "NBox": PartSpec("NBox", ("in", "bit"), ("out",), level="M", source="по аналогии с PBox (" + REF + ")"),
    "O": PartSpec("O", (), ("out",), templates=("Card",), card_inputs="in", source=REF),
    "A": PartSpec(
        "A",
        (),
        ("out",),
        templates=("Card",),
        card_inputs="in",
        level="M",
        langs=("FBD",),
        source="s7-lint-vscode @ 0735f8ff FBD-bit-logic.yaml (A/O/X); форма — по O из " + REF,
    ),
    "X": PartSpec(
        "X",
        (),
        ("out",),
        templates=("Card",),
        card_inputs="in",
        level="M",
        langs=("FBD",),
        source="s7-lint-vscode @ 0735f8ff FBD-bit-logic.yaml (A/O/X); форма — по O из " + REF,
    ),
    "TON": PartSpec(
        "TON", ("IN", "PT"), ("Q", "ET"), templates=("time_type",), version="1.0", instance=True, source=REF
    ),
    "TOF": PartSpec(
        "TOF",
        ("IN", "PT"),
        ("Q", "ET"),
        templates=("time_type",),
        version="1.0",
        instance=True,
        level="M",
        source="по аналогии с TON (" + REF + ")",
    ),
    "TP": PartSpec(
        "TP",
        ("IN", "PT"),
        ("Q", "ET"),
        templates=("time_type",),
        version="1.0",
        instance=True,
        level="M",
        source="по аналогии с TON (" + REF + ")",
    ),
    "Move": PartSpec("Move", ("en", "in"), ("out1", "eno"), templates=("Card",), source=REF),
    "Jump": PartSpec(
        "Jump",
        ("in", "operand"),
        (),
        operand=True,
        level="L",
        source="схема LADFBD_v5 (Access Scope=Label); эталона нет",
    ),
}
for _n in ("Eq", "Ne", "Gt", "Ge", "Lt", "Le"):
    PARTS[_n] = PartSpec(_n, ("pre", "in1", "in2"), ("out",), templates=("SrcType",), source=_CMP_SRC)
for _n in ("Add", "Mul"):
    PARTS[_n] = PartSpec(_n, ("en",), ("out", "eno"), templates=("SrcType", "Card"), card_inputs="in", source=REF)
for _n in ("Sub", "Div", "Mod"):
    PARTS[_n] = PartSpec(_n, ("en", "in1", "in2"), ("out", "eno"), templates=("SrcType",), source=REF)

CMP_PART = {">": "Gt", ">=": "Ge", "<": "Lt", "<=": "Le", "=": "Eq", "<>": "Ne"}
ARITH_PART = {"ADD": "Add", "SUB": "Sub", "MUL": "Mul", "DIV": "Div", "MOD": "Mod"}
TIMER_PART = {"TON": "TON", "TOF": "TOF", "TP": "TP"}

# Типы S7 для TemplateValue SrcType (элементарные)
S7_ELEM = {
    "BOOL": "Bool",
    "BYTE": "Byte",
    "WORD": "Word",
    "DWORD": "DWord",
    "LWORD": "LWord",
    "SINT": "SInt",
    "USINT": "USInt",
    "INT": "Int",
    "UINT": "UInt",
    "DINT": "DInt",
    "UDINT": "UDInt",
    "LINT": "LInt",
    "ULINT": "ULInt",
    "REAL": "Real",
    "LREAL": "LReal",
    "TIME": "Time",
    "LTIME": "LTime",
}


def input_pins(spec: PartSpec, card: int | None) -> set[str]:
    pins = set(spec.inputs)
    if spec.card_inputs and card:
        pins |= {f"{spec.card_inputs}{i}" for i in range(1, card + 1)}
    return pins
