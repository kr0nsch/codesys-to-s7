"""ST AST CODESYS — центр конвертера: в него сводятся ST, IL, LD/FBD/CFC и SFC, из него печатается SCL.

Узлы — изменяемые dataclass. Позиция `pos` — (строка, столбец) от 1 в исходном тексте; в сравнении
узлов не участвует. Комментарии исходника привязываются к операторам (`lead`/`trail`).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, fields
from typing import Any

Pos = tuple[int, int] | None


@dataclass
class Node:
    pos: Pos = field(default=None, compare=False, kw_only=True, repr=False)
    end: Pos = field(default=None, compare=False, kw_only=True, repr=False)


# ---------------------------------------------------------------------------
# Выражения
# ---------------------------------------------------------------------------


@dataclass
class Expr(Node):
    pass


@dataclass
class Literal(Expr):
    """Литерал. kind: bool int real time ltime date tod dt string wstring enum."""

    kind: str
    text: str
    value: Any = None
    type_name: str | None = None


@dataclass
class Name(Expr):
    id: str


@dataclass
class Member(Expr):
    base: Expr
    name: str


@dataclass
class Index(Expr):
    base: Expr
    indices: list[Expr]


@dataclass
class BitRef(Expr):
    """Битовый доступ `w.3`."""

    base: Expr
    bit: int


@dataclass
class Deref(Expr):
    base: Expr


@dataclass
class Slice(Expr):
    """Срез SCL `x.%B1` (только цель; size: B, W, D)."""

    base: Expr
    size: str
    number: int


@dataclass
class DirectAddr(Expr):
    text: str


@dataclass
class SclRef(Expr):
    """Разрешённое имя цели (SCL): kind = local (#x), global ("DB"), tag ("tag"), raw (как есть)."""

    kind: str
    name: str


@dataclass
class Unary(Expr):
    """op: NOT, NEG, PLUS."""

    op: str
    operand: Expr


@dataclass
class Binary(Expr):
    """op: OR OR_ELSE XOR AND AND_THEN = <> < > <= >= + - * / MOD **."""

    op: str
    left: Expr
    right: Expr


@dataclass
class Arg(Node):
    value: Expr | None
    name: str | None = None
    output: bool = False
    negated: bool = False


@dataclass
class Call(Expr):
    func: Expr
    args: list[Arg]


@dataclass
class ArrayInitElem(Node):
    value: Expr | None
    repeat: int | None = None


@dataclass
class ArrayInit(Expr):
    elems: list[ArrayInitElem]


@dataclass
class StructInit(Expr):
    fields: list[tuple[str, Expr]]


# ---------------------------------------------------------------------------
# Операторы
# ---------------------------------------------------------------------------


@dataclass
class Stmt(Node):
    lead: list[str] = field(default_factory=list, compare=False, kw_only=True, repr=False)
    trail: str | None = field(default=None, compare=False, kw_only=True, repr=False)


@dataclass
class Assign(Stmt):
    target: Expr
    value: Expr
    op: str = ":="


@dataclass
class CallStmt(Stmt):
    call: Call


@dataclass
class If(Stmt):
    branches: list[tuple[Expr, list[Stmt]]]
    else_body: list[Stmt] | None = None


@dataclass
class CaseLabel(Node):
    lo: Expr
    hi: Expr | None = None


@dataclass
class CaseBranch(Node):
    labels: list[CaseLabel]
    body: list[Stmt]


@dataclass
class Case(Stmt):
    selector: Expr
    branches: list[CaseBranch]
    else_body: list[Stmt] | None = None


@dataclass
class For(Stmt):
    var: str
    start: Expr
    stop: Expr
    step: Expr | None
    body: list[Stmt]


@dataclass
class While(Stmt):
    cond: Expr
    body: list[Stmt]


@dataclass
class Repeat(Stmt):
    body: list[Stmt]
    cond: Expr


@dataclass
class Exit(Stmt):
    pass


@dataclass
class Continue(Stmt):
    pass


@dataclass
class Return(Stmt):
    pass


@dataclass
class Jump(Stmt):
    """Переход на метку (ST JMP, IL JMP/JMPC, FBD Jump). cond — условие перехода (None — всегда)."""

    label: str
    cond: Expr | None = None


@dataclass
class Label(Stmt):
    name: str


@dataclass
class Empty(Stmt):
    pass


@dataclass
class Region(Stmt):
    """Группа операторов (REGION в SCL); в ST CODESYS — комментарии `// REGION`."""

    name: str
    body: list[Stmt]


@dataclass
class Verbatim(Stmt):
    """Текст цели без перевода (восстановленный из пометки или заготовка)."""

    text: str


# ---------------------------------------------------------------------------
# Типы и объявления
# ---------------------------------------------------------------------------


@dataclass
class TypeRef(Node):
    pass


@dataclass
class NamedType(TypeRef):
    name: str


@dataclass
class StringType(TypeRef):
    wide: bool
    length: Expr | None = None


@dataclass
class ArrayType(TypeRef):
    dims: list[tuple[Expr, Expr] | None]
    elem: TypeRef


@dataclass
class PointerType(TypeRef):
    elem: TypeRef


@dataclass
class ReferenceType(TypeRef):
    elem: TypeRef


@dataclass
class SubrangeType(TypeRef):
    base: str
    lo: Expr
    hi: Expr


@dataclass
class EnumType(TypeRef):
    values: list[tuple[str, Expr | None]]
    base: str | None = None


@dataclass
class VarDecl(Node):
    name: str
    type: TypeRef
    init: Expr | None = None
    address: str | None = None
    comment: str | None = None
    attrs: list[str] = field(default_factory=list)


@dataclass
class StructType(TypeRef):
    members: list[VarDecl]
    union: bool = False


@dataclass
class VarBlock(Node):
    """kind: VAR VAR_INPUT VAR_OUTPUT VAR_IN_OUT VAR_GLOBAL VAR_TEMP VAR_STAT VAR_EXTERNAL VAR_INST."""

    kind: str
    qualifiers: list[str]
    decls: list[VarDecl]

    @property
    def constant(self) -> bool:
        return "CONSTANT" in self.qualifiers

    @property
    def retain(self) -> bool:
        return "RETAIN" in self.qualifiers

    @property
    def persistent(self) -> bool:
        return "PERSISTENT" in self.qualifiers


@dataclass
class PouHeader(Node):
    """Заголовок POU/метода/свойства/интерфейса."""

    kind: str
    name: str
    return_type: TypeRef | None = None
    modifiers: list[str] = field(default_factory=list)
    extends: list[str] = field(default_factory=list)
    implements: list[str] = field(default_factory=list)


@dataclass
class PouText(Node):
    """Разобранный текст POU: заголовок, секции переменных, тело (может быть пустым)."""

    header: PouHeader
    var_blocks: list[VarBlock]
    body: list[Stmt]
    attrs: list[str] = field(default_factory=list)
    tail: list[str] = field(default_factory=list, compare=False)


@dataclass
class TypeDecl(Node):
    name: str
    type: TypeRef
    init: Expr | None = None
    extends: str | None = None
    attrs: list[str] = field(default_factory=list)


@dataclass
class GvlText(Node):
    var_blocks: list[VarBlock]
    attrs: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Обход
# ---------------------------------------------------------------------------


def children(node: Node) -> Iterator[Node]:
    """Дочерние узлы в порядке полей."""
    for f in fields(node):
        if f.name in ("pos", "end", "lead", "trail"):
            continue
        yield from _nodes_in(getattr(node, f.name))


def _nodes_in(value: Any) -> Iterator[Node]:
    if isinstance(value, Node):
        yield value
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _nodes_in(item)


def walk(node: Node) -> Iterator[Node]:
    """Все узлы поддерева в прямом порядке."""
    yield node
    for child in children(node):
        yield from walk(child)


def walk_stmts(stmts: list[Stmt]) -> Iterator[Node]:
    for stmt in stmts:
        yield from walk(stmt)


def stmt_bodies(stmt: Stmt) -> list[list[Stmt]]:
    """Вложенные списки операторов (для понижений, которые меняют тела)."""
    if isinstance(stmt, If):
        out = [body for _, body in stmt.branches]
        if stmt.else_body is not None:
            out.append(stmt.else_body)
        return out
    if isinstance(stmt, Case):
        out = [b.body for b in stmt.branches]
        if stmt.else_body is not None:
            out.append(stmt.else_body)
        return out
    if isinstance(stmt, For | While | Repeat | Region):
        return [stmt.body]
    return []


def var_path(expr: Expr) -> list[str] | None:
    """`a.b.c` → ['a', 'b', 'c']; не путь — None."""
    if isinstance(expr, Name):
        return [expr.id]
    if isinstance(expr, Member):
        base = var_path(expr.base)
        return None if base is None else [*base, expr.name]
    return None


def root_name(expr: Expr) -> str | None:
    """Имя в начале обращения: `a.b[1].c` → 'a'."""
    while True:
        if isinstance(expr, Name):
            return expr.id
        if isinstance(expr, Member | Index | BitRef | Deref | Slice):
            expr = expr.base
            continue
        return None
