"""Модель цели S7: блоки внешнего исходника (TYPE, DATA_BLOCK, FUNCTION_BLOCK, FUNCTION, ORGANIZATION_BLOCK),
теги, план OB. Тела — ST AST с разрешёнными именами (SclRef), печать — c2s7.emit.scl."""

from __future__ import annotations

from dataclasses import dataclass, field

from c2s7.model import Origin
from c2s7.st import nodes as A


@dataclass
class S7Member:
    name: str
    type: str
    init: str | None = None
    comment: str | None = None
    attrs: dict[str, str] = field(default_factory=dict)
    struct: list[S7Member] | None = None  # анонимная структура (тип — "Struct")
    raw: str | None = None  # объявление как есть (восстановлено из пометки s7conv)
    begin: list[tuple[str, str]] = field(default_factory=list)  # начальные значения структуры/массива → BEGIN DB


@dataclass
class S7Section:
    kind: str  # VAR_INPUT VAR_OUTPUT VAR_IN_OUT VAR VAR_TEMP VAR CONSTANT ...
    members: list[S7Member] = field(default_factory=list)
    retain: bool = False
    constant: bool = False

    @property
    def header(self) -> str:
        if self.constant:
            return f"{self.kind} CONSTANT"
        if self.retain:
            return f"{self.kind} RETAIN"
        return self.kind


@dataclass
class S7Block:
    kind: str  # TYPE DATA_BLOCK FUNCTION_BLOCK FUNCTION ORGANIZATION_BLOCK
    name: str
    title: str | None = None
    author: str | None = None
    family: str | None = None
    version: str = "0.1"
    optimized: bool = True
    return_type: str | None = None
    sections: list[S7Section] = field(default_factory=list)
    body: list[A.Stmt] = field(default_factory=list)
    db_of: str | None = None  # экземплярный/типизированный DB: тип
    db_begin: list[tuple[str, str]] = field(default_factory=list)
    non_retain: bool = True
    struct: list[S7Member] = field(default_factory=list)  # TYPE
    comment: list[str] = field(default_factory=list)
    origin: Origin | None = None
    source_pou: str = ""
    language: str = "ST"
    deps: set[str] = field(default_factory=set)
    order: int = 0  # 0 — типы, 1 — глобальные DB, 2 — FC/FB, 3 — экземплярные DB, 4 — OB

    @property
    def ext(self) -> str:
        return {"TYPE": "udt", "DATA_BLOCK": "db"}.get(self.kind, "scl")


@dataclass
class Tag:
    name: str
    type: str
    address: str
    comment: str = ""
    table: str = "c2s7"
    value: str | None = None  # пользовательская константа
    source: str = ""


@dataclass
class ObPlan:
    task: str
    name: str
    number: int | None
    kind: str  # ProgramCycle | CyclicInterrupt | Startup | Event
    interval_ms: float | None
    priority: int | None
    calls: list[str]
    cds_priority: int | None = None
    notes: list[str] = field(default_factory=list)
    body: list[A.Stmt] = field(default_factory=list)
    full_block: S7Block | None = None  # кольцо: OB целиком (--ob-from-tasks)
