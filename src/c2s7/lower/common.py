"""Общие средства понижений: обход-замена выражений, имена служебных переменных, добавление секций."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from c2s7.model import Pou
from c2s7.st import nodes as A

PREFIX = "_c2s7_"  # служебные переменные понижений (имя видно в SCL и в отчёте)

TRUE = A.Literal("bool", "TRUE", True)
FALSE = A.Literal("bool", "FALSE", False)


def name(n: str) -> A.Name:
    return A.Name(n)


def lit_true() -> A.Literal:
    return A.Literal("bool", "TRUE", True)


def lit_false() -> A.Literal:
    return A.Literal("bool", "FALSE", False)


def is_true(e: A.Expr) -> bool:
    return isinstance(e, A.Literal) and e.kind == "bool" and e.value is True


def is_false(e: A.Expr) -> bool:
    return isinstance(e, A.Literal) and e.kind == "bool" and e.value is False


def and_(*terms: A.Expr) -> A.Expr:
    """Конъюнкция с упрощением TRUE/FALSE."""
    out: list[A.Expr] = []
    for t in terms:
        if is_true(t):
            continue
        if is_false(t):
            return lit_false()
        out.append(t)
    if not out:
        return lit_true()
    e = out[0]
    for t in out[1:]:
        e = A.Binary("AND", e, t)
    return e


def or_(*terms: A.Expr) -> A.Expr:
    out: list[A.Expr] = []
    for t in terms:
        if is_false(t):
            continue
        if is_true(t):
            return lit_true()
        out.append(t)
    if not out:
        return lit_false()
    e = out[0]
    for t in out[1:]:
        e = A.Binary("OR", e, t)
    return e


def not_(e: A.Expr) -> A.Expr:
    if is_true(e):
        return lit_false()
    if is_false(e):
        return lit_true()
    if isinstance(e, A.Unary) and e.op == "NOT":
        return e.operand
    return A.Unary("NOT", e)


def map_expr(e: Any, fn: Callable[[A.Expr], A.Expr | None]) -> Any:
    """Копия узла (выражения или оператора), где fn заменяет подвыражения (None — не менять)."""
    if isinstance(e, A.Expr):
        r = fn(e)
        if r is not None:
            return r
    if isinstance(e, list):
        return [map_expr(x, fn) for x in e]
    if isinstance(e, tuple):
        return tuple(map_expr(x, fn) for x in e)
    if not isinstance(e, A.Node):
        return e
    out = copy.copy(e)
    for f in e.__dataclass_fields__:
        if f in ("pos", "end", "lead", "trail"):
            continue
        v = getattr(e, f)
        if isinstance(v, A.Node | list | tuple):
            setattr(out, f, map_expr(v, fn))
    return out


def expr_vars(e: A.Expr) -> set[str]:
    """Корневые имена переменных выражения (в верхнем регистре)."""
    return {n.id.upper() for n in A.walk(e) if isinstance(n, A.Name)}


def add_vars(pou: Pou, kind: str, decls: list[A.VarDecl]) -> None:
    """Добавляет объявления в секцию kind (VAR / VAR_TEMP) POU, создавая её при необходимости."""
    if not decls:
        return
    blk = next((b for b in pou.text.var_blocks if b.kind == kind and not b.qualifiers), None)
    if blk is None:
        blk = A.VarBlock(kind, [], [])
        pou.text.var_blocks.append(blk)
    have = {d.name.upper() for d in blk.decls}
    for d in decls:
        if d.name.upper() not in have:
            blk.decls.append(d)
            have.add(d.name.upper())


def decl_types(pou: Pou) -> dict[str, A.TypeRef]:
    return {d.name.upper(): d.type for _, d in pou.decls()}


class Names:
    """Уникальные служебные имена в пределах POU."""

    def __init__(self, pou: Pou) -> None:
        self.used = {d.name.upper() for _, d in pou.decls()}
        self.n = 0

    def fresh(self, stem: str) -> str:
        base = f"{PREFIX}{stem}"
        cand = base
        while cand.upper() in self.used:
            self.n += 1
            cand = f"{base}{self.n}"
        self.used.add(cand.upper())
        return cand
