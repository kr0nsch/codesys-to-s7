"""Модель проекта CODESYS после разбора: POU, GVL, DUT, задачи, библиотеки, ввод-вывод, происхождение."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from c2s7.st import nodes as A

if TYPE_CHECKING:
    from c2s7.ir.netir import NetBody
    from c2s7.ir.sfcir import SfcBody

LANGUAGES = ("ST", "IL", "LD", "FBD", "CFC", "SFC")


@dataclass
class Origin:
    file: str
    line: int | None = None
    column: int | None = None
    local_id: str | None = None

    def at(self, pos: A.Pos) -> Origin:
        if pos is None:
            return self
        base = self.line or 1
        return Origin(self.file, base + pos[0] - 1, pos[1], self.local_id)

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"file": self.file}
        if self.line is not None:
            d["line"] = self.line
        if self.column is not None:
            d["column"] = self.column
        if self.local_id is not None:
            d["local_id"] = self.local_id
        return d


@dataclass
class Action:
    name: str
    language: str
    body: list[A.Stmt] = field(default_factory=list)
    il: str | None = None
    net: NetBody | None = None
    origin: Origin | None = None


@dataclass
class Property:
    name: str
    type: A.TypeRef
    get_body: list[A.Stmt] | None = None
    set_body: list[A.Stmt] | None = None
    get_vars: list[A.VarBlock] = field(default_factory=list)
    set_vars: list[A.VarBlock] = field(default_factory=list)


@dataclass
class Pou:
    """POU CODESYS. text — заголовок, секции и тело ST (у графики тело появляется после понижения)."""

    name: str
    kind: str  # PROGRAM | FUNCTION_BLOCK | FUNCTION
    language: str
    text: A.PouText
    origin: Origin
    il: str | None = None
    net: NetBody | None = None
    sfc: SfcBody | None = None
    actions: list[Action] = field(default_factory=list)
    methods: list[A.PouText] = field(default_factory=list)
    properties: list[Property] = field(default_factory=list)
    folder: list[str] = field(default_factory=list)
    doc: list[str] = field(default_factory=list)
    impl_origin: Origin | None = None

    @property
    def var_blocks(self) -> list[A.VarBlock]:
        return self.text.var_blocks

    @property
    def body(self) -> list[A.Stmt]:
        return self.text.body

    @property
    def return_type(self) -> A.TypeRef | None:
        return self.text.header.return_type

    def decls(self) -> list[tuple[A.VarBlock, A.VarDecl]]:
        return [(b, d) for b in self.text.var_blocks for d in b.decls]


@dataclass
class Gvl:
    name: str
    text: A.GvlText
    origin: Origin
    folder: list[str] = field(default_factory=list)
    persistent_list: bool = False
    doc: list[str] = field(default_factory=list)

    @property
    def qualified_only(self) -> bool:
        return any("qualified_only" in a for a in self.text.attrs)

    def decls(self) -> list[tuple[A.VarBlock, A.VarDecl]]:
        return [(b, d) for b in self.text.var_blocks for d in b.decls]


@dataclass
class Dut:
    name: str
    decl: A.TypeDecl
    origin: Origin
    folder: list[str] = field(default_factory=list)
    doc: list[str] = field(default_factory=list)


@dataclass
class Task:
    name: str
    kind: str  # cyclic | freewheeling | event | status | startup
    interval_ms: float | None
    priority: int
    pous: list[str]
    sources: list[str] = field(default_factory=list)
    watchdog_ms: float | None = None


@dataclass
class Library:
    name: str
    namespace: str = ""
    resolution: str = ""


@dataclass
class IoChannel:
    variable: str
    address: str
    device: str = ""
    channel: str = ""
    type: str = ""
    comment: str = ""


@dataclass
class Project:
    name: str
    kind: str  # plcopen-xml | st-layout | st
    path: str
    sha256: str
    pous: list[Pou] = field(default_factory=list)
    gvls: list[Gvl] = field(default_factory=list)
    duts: list[Dut] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    libraries: list[Library] = field(default_factory=list)
    io_map: list[IoChannel] | None = None
    ide: str = "CODESYS"
    ide_version: str = ""
    notes: list[str] = field(default_factory=list)
    obs: list[dict[str, Any]] = field(default_factory=list)  # подсказки OB из tasks.json s7conv
    root: str = ""  # абсолютный каталог входа (для чтения файлов раскладки)

    def pou(self, name: str) -> Pou | None:
        low = name.lower()
        return next((p for p in self.pous if p.name.lower() == low), None)

    def gvl(self, name: str) -> Gvl | None:
        low = name.lower()
        return next((g for g in self.gvls if g.name.lower() == low), None)

    def dut(self, name: str) -> Dut | None:
        low = name.lower()
        return next((d for d in self.duts if d.name.lower() == low), None)
