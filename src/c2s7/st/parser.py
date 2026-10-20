"""Разбор ST CODESYS: препроцессор (комментарии, прагмы) + грамматика lark (LALR) → ST AST.

Препроцессор заменяет комментарии `//`, `(* *)` (с вложенностью), `/* */` и прагмы `{...}` пробелами,
сохраняя переводы строк, поэтому позиции lark совпадают с исходным текстом. Комментарии потом
привязываются к операторам и объявлениям, прагмы — к POU/переменным (`attrs`).
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from importlib import resources
from typing import Any

from lark import Lark, Token, Transformer, Tree, v_args
from lark.exceptions import LarkError, UnexpectedInput

from c2s7.st import literals as L
from c2s7.st import nodes as A


class StSyntaxError(ValueError):
    """Синтаксическая ошибка ST с позицией."""

    def __init__(self, message: str, line: int | None = None, column: int | None = None, source: str = "") -> None:
        where = f"{source}:" if source else ""
        if line is not None:
            where += f"{line}:{column or 0}: "
        super().__init__(where + message)
        self.line = line
        self.column = column
        self.source = source


@dataclass
class Comment:
    line: int
    column: int
    end_line: int
    text: str
    pragma: bool = False


# ---------------------------------------------------------------------------
# Препроцессор
# ---------------------------------------------------------------------------


def strip_comments(text: str) -> tuple[str, list[Comment]]:
    """Комментарии и прагмы → пробелы; возвращает очищенный текст и найденное."""
    out = list(text)
    found: list[Comment] = []
    i = 0
    n = len(text)
    line = 1
    col = 1

    def blank(a: int, b: int) -> None:
        for k in range(a, b):
            if out[k] not in "\r\n":
                out[k] = " "

    def advance(a: int, b: int) -> tuple[int, int]:
        nonlocal line, col
        for k in range(a, b):
            if text[k] == "\n":
                line += 1
                col = 1
            else:
                col += 1
        return line, col

    while i < n:
        ch = text[i]
        if ch in "'\"":
            j = i + 1
            while j < n and text[j] != ch and text[j] != "\n":
                j += 2 if text[j] == "$" else 1
            j = min(j + 1, n)
            advance(i, j)
            i = j
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            found.append(Comment(line, col, line, text[i + 2 : j].strip()))
            blank(i, j)
            advance(i, j)
            i = j
            continue
        if text.startswith("(*", i):
            depth = 0
            j = i
            while j < n:
                if text.startswith("(*", j):
                    depth += 1
                    j += 2
                elif text.startswith("*)", j):
                    depth -= 1
                    j += 2
                    if depth == 0:
                        break
                else:
                    j += 1
            sl, sc = line, col
            body = text[i + 2 : j - 2] if j - 2 >= i + 2 else ""
            blank(i, j)
            el, _ = advance(i, j)
            found.append(Comment(sl, sc, el, body.strip()))
            i = j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            sl, sc = line, col
            body = text[i + 2 : j - 2]
            blank(i, j)
            el, _ = advance(i, j)
            found.append(Comment(sl, sc, el, body.strip()))
            i = j
            continue
        if ch == "{":
            j = text.find("}", i + 1)
            j = n if j < 0 else j + 1
            sl, sc = line, col
            body = text[i + 1 : j - 1]
            blank(i, j)
            el, _ = advance(i, j)
            found.append(Comment(sl, sc, el, body.strip(), pragma=True))
            i = j
            continue
        advance(i, i + 1)
        i += 1
    return "".join(out), found


# ---------------------------------------------------------------------------
# Грамматика
# ---------------------------------------------------------------------------

STARTS = ["pou_text", "stmts", "type_text", "gvl_text", "expr_text", "type_ref_text", "init_text"]


@functools.cache
def _lark() -> Lark:
    grammar = resources.files("c2s7.st").joinpath("grammar.lark").read_text(encoding="utf-8")
    return Lark(
        grammar,
        parser="lalr",
        start=STARTS,
        propagate_positions=True,
        maybe_placeholders=False,
        cache=False,
    )


def _pos(meta: Any) -> A.Pos:
    if meta is None or getattr(meta, "empty", True):
        return None
    return (meta.line, meta.column)


def _end(meta: Any) -> A.Pos:
    if meta is None or getattr(meta, "empty", True):
        return None
    return (meta.end_line, meta.end_column)


def _tokens(items: list[Any]) -> list[Any]:
    """Убирает ключевые слова (именованные токены-ключевые слова), оставляя значимые."""
    return [it for it in items if not (isinstance(it, Token) and it.type in _KEYWORD_TYPES)]


_KEYWORD_TYPES = {
    "PROGRAM",
    "FUNCTION_BLOCK",
    "FUNCTION",
    "METHOD",
    "PROPERTY",
    "INTERFACE",
    "ACTION",
    "EXTENDS",
    "IMPLEMENTS",
    "END_VAR",
    "AT",
    "ARRAY",
    "OF",
    "POINTER",
    "REFERENCE",
    "TO",
    "TYPE",
    "END_TYPE",
    "STRUCT",
    "END_STRUCT",
    "UNION",
    "END_UNION",
    "IF",
    "THEN",
    "ELSIF",
    "ELSE",
    "END_IF",
    "CASE",
    "END_CASE",
    "FOR",
    "BY",
    "DO",
    "END_FOR",
    "WHILE",
    "END_WHILE",
    "REPEAT",
    "UNTIL",
    "END_REPEAT",
    "EXIT",
    "CONTINUE",
    "RETURN",
    "JMP",
    "NOT",
    "END_POU",
}

_OPS = {"&": "AND", "AND_THEN": "AND_THEN", "OR_ELSE": "OR_ELSE"}


@v_args(meta=True)
class _ToAst(Transformer[Token, Any]):
    # ---- заголовки ----
    def h_program(self, meta: Any, items: list[Any]) -> A.PouHeader:
        it = _tokens(items)
        return A.PouHeader("PROGRAM", str(it[0]), pos=_pos(meta))

    def h_fb(self, meta: Any, items: list[Any]) -> A.PouHeader:
        it = _tokens(items)
        mods = [x for x in it if isinstance(x, str) and isinstance(x, _Mod)]
        name = next(str(x) for x in it if isinstance(x, Token) and x.type == "NAME")
        ext = next((x for x in it if isinstance(x, _Ext)), None)
        imp = next((x for x in it if isinstance(x, _Impl)), None)
        return A.PouHeader(
            "FUNCTION_BLOCK",
            name,
            modifiers=[str(m) for m in mods],
            extends=list(ext.names) if ext else [],
            implements=list(imp.names) if imp else [],
            pos=_pos(meta),
        )

    def h_function(self, meta: Any, items: list[Any]) -> A.PouHeader:
        it = _tokens(items)
        name = str(it[0])
        rt = it[1] if len(it) > 1 else None
        return A.PouHeader("FUNCTION", name, return_type=rt, pos=_pos(meta))

    def h_method(self, meta: Any, items: list[Any]) -> A.PouHeader:
        it = _tokens(items)
        mods = [str(x) for x in it if isinstance(x, _Mod)]
        name = next(str(x) for x in it if isinstance(x, Token) and x.type == "NAME")
        rt = next((x for x in it if isinstance(x, A.TypeRef)), None)
        return A.PouHeader("METHOD", name, return_type=rt, modifiers=mods, pos=_pos(meta))

    def h_property(self, meta: Any, items: list[Any]) -> A.PouHeader:
        it = _tokens(items)
        mods = [str(x) for x in it if isinstance(x, _Mod)]
        name = next(str(x) for x in it if isinstance(x, Token) and x.type == "NAME")
        rt = next((x for x in it if isinstance(x, A.TypeRef)), None)
        return A.PouHeader("PROPERTY", name, return_type=rt, modifiers=mods, pos=_pos(meta))

    def h_interface(self, meta: Any, items: list[Any]) -> A.PouHeader:
        it = _tokens(items)
        name = str(it[0])
        ext = next((x for x in it if isinstance(x, _Ext)), None)
        return A.PouHeader("INTERFACE", name, extends=list(ext.names) if ext else [], pos=_pos(meta))

    def h_action(self, meta: Any, items: list[Any]) -> A.PouHeader:
        it = _tokens(items)
        return A.PouHeader("ACTION", str(it[0]), pos=_pos(meta))

    def modifier(self, meta: Any, items: list[Any]) -> _Mod:
        return _Mod(str(items[0]).upper())

    def extends_one(self, meta: Any, items: list[Any]) -> _Ext:
        return _Ext([str(x) for x in _tokens(items)])

    def extends_many(self, meta: Any, items: list[Any]) -> _Ext:
        return _Ext([str(x) for x in _tokens(items)])

    def implements(self, meta: Any, items: list[Any]) -> _Impl:
        return _Impl([str(x) for x in _tokens(items)])

    def qname(self, meta: Any, items: list[Any]) -> _QName:
        return _QName(".".join(str(x) for x in items))

    # ---- текст POU ----
    def pou_text(self, meta: Any, items: list[Any]) -> A.PouText:
        header = items[0]
        blocks = [x for x in items[1:] if isinstance(x, A.VarBlock)]
        body = next((x for x in items[1:] if isinstance(x, _Stmts)), _Stmts([]))
        return A.PouText(header, blocks, list(body.items), pos=_pos(meta))

    def pou_end(self, meta: Any, items: list[Any]) -> None:
        return None

    def stmts(self, meta: Any, items: list[Any]) -> _Stmts:
        return _Stmts(_clean_stmts(items))

    def case_stmts(self, meta: Any, items: list[Any]) -> _Stmts:
        return _Stmts(_clean_stmts(items))

    def gvl_text(self, meta: Any, items: list[Any]) -> A.GvlText:
        return A.GvlText([x for x in items if isinstance(x, A.VarBlock)], pos=_pos(meta))

    def type_text(self, meta: Any, items: list[Any]) -> A.TypeDecl:
        decl: A.TypeDecl = items[0]
        return decl

    def expr_text(self, meta: Any, items: list[Any]) -> A.Expr:
        expr: A.Expr = items[0]
        return expr

    def type_ref_text(self, meta: Any, items: list[Any]) -> A.TypeRef:
        tr: A.TypeRef = items[0]
        return tr

    def init_text(self, meta: Any, items: list[Any]) -> A.Expr:
        expr: A.Expr = items[0]
        return expr

    # ---- переменные ----
    def var_block(self, meta: Any, items: list[Any]) -> A.VarBlock:
        kind = str(items[0]).upper()
        quals = [str(x).upper() for x in items[1:] if isinstance(x, _Qual)]
        decls: list[A.VarDecl] = []
        for x in items[1:]:
            if isinstance(x, list):
                decls.extend(x)
        return A.VarBlock(kind, quals, decls, pos=_pos(meta), end=_end(meta))

    def var_qual(self, meta: Any, items: list[Any]) -> _Qual:
        return _Qual(str(items[0]).upper())

    def var_decl(self, meta: Any, items: list[Any]) -> list[A.VarDecl]:
        it = _tokens(items)
        names = [str(x) for x in it if isinstance(x, Token) and x.type == "NAME"]
        loc = next((x for x in it if isinstance(x, _Loc)), None)
        typ = next(x for x in it if isinstance(x, A.TypeRef))
        rest = it[it.index(typ) + 1 :]
        init = rest[0] if rest else None
        return [
            A.VarDecl(n, typ, init, address=str(loc) if loc else None, pos=_pos(meta), end=_end(meta)) for n in names
        ]

    def location(self, meta: Any, items: list[Any]) -> _Loc:
        return _Loc(str(_tokens(items)[0]).upper())

    def named_type(self, meta: Any, items: list[Any]) -> A.NamedType:
        return A.NamedType(str(items[0]), pos=_pos(meta))

    def array_type(self, meta: Any, items: list[Any]) -> A.ArrayType:
        it = _tokens(items)
        dims = [x for x in it if isinstance(x, _Dim)]
        elem = it[-1]
        return A.ArrayType([d.bounds for d in dims], elem, pos=_pos(meta))

    def dim(self, meta: Any, items: list[Any]) -> _Dim:
        return _Dim((items[0], items[1]))

    def dim_star(self, meta: Any, items: list[Any]) -> _Dim:
        return _Dim(None)

    def pointer_type(self, meta: Any, items: list[Any]) -> A.PointerType:
        return A.PointerType(_tokens(items)[-1], pos=_pos(meta))

    def reference_type(self, meta: Any, items: list[Any]) -> A.ReferenceType:
        return A.ReferenceType(_tokens(items)[-1], pos=_pos(meta))

    def string_type(self, meta: Any, items: list[Any]) -> A.StringType:
        kw = str(items[0]).upper()
        length = items[1] if len(items) > 1 else None
        return A.StringType(kw.startswith("W"), length, pos=_pos(meta))

    def subrange_type(self, meta: Any, items: list[Any]) -> A.SubrangeType:
        return A.SubrangeType(str(items[0]), items[1], items[2], pos=_pos(meta))

    def array_init(self, meta: Any, items: list[Any]) -> A.ArrayInit:
        return A.ArrayInit(list(items), pos=_pos(meta))

    def init_plain(self, meta: Any, items: list[Any]) -> A.ArrayInitElem:
        return A.ArrayInitElem(items[0], pos=_pos(meta))

    def init_repeat(self, meta: Any, items: list[Any]) -> A.ArrayInitElem:
        count = L.parse_int(str(items[0]))
        value = items[1] if len(items) > 1 else None
        return A.ArrayInitElem(value, repeat=count, pos=_pos(meta))

    def struct_init(self, meta: Any, items: list[Any]) -> A.StructInit:
        return A.StructInit([(f[0], f[1]) for f in items], pos=_pos(meta))

    def field_init(self, meta: Any, items: list[Any]) -> tuple[str, A.Expr]:
        return (str(items[0]), items[1])

    # ---- типы ----
    def type_decl(self, meta: Any, items: list[Any]) -> A.TypeDecl:
        it = _tokens(items)
        name = str(it[0])
        ext = next((x for x in it if isinstance(x, _Ext)), None)
        body = next(x for x in it[1:] if isinstance(x, _TypeBody))
        return A.TypeDecl(name, body.type, body.init, extends=ext.names[0] if ext else None, pos=_pos(meta))

    def struct_def(self, meta: Any, items: list[Any]) -> _TypeBody:
        members: list[A.VarDecl] = []
        for x in items:
            if isinstance(x, list):
                members.extend(x)
        return _TypeBody(A.StructType(members, pos=_pos(meta)), None)

    def union_def(self, meta: Any, items: list[Any]) -> _TypeBody:
        members: list[A.VarDecl] = []
        for x in items:
            if isinstance(x, list):
                members.extend(x)
        return _TypeBody(A.StructType(members, union=True, pos=_pos(meta)), None)

    def enum_def(self, meta: Any, items: list[Any]) -> _TypeBody:
        values = [x for x in items if isinstance(x, tuple)]
        base = next((str(x) for x in items if isinstance(x, _QName)), None)
        init = next((x for x in items if isinstance(x, A.Expr)), None)
        return _TypeBody(A.EnumType(values, base, pos=_pos(meta)), init)

    def enum_value_init(self, meta: Any, items: list[Any]) -> tuple[str, A.Expr | None]:
        return (str(items[0]), items[1])

    def enum_value_plain(self, meta: Any, items: list[Any]) -> tuple[str, A.Expr | None]:
        return (str(items[0]), None)

    def alias_def(self, meta: Any, items: list[Any]) -> _TypeBody:
        return _TypeBody(items[0], items[1] if len(items) > 1 else None)

    # ---- операторы ----
    def assign_simple(self, meta: Any, items: list[Any]) -> A.Stmt:
        target = A.Name(str(items[0]), pos=(items[0].line, items[0].column))
        rhs = items[1]
        return _chain(target, rhs, meta)

    def chain_assign(self, meta: Any, items: list[Any]) -> _Chain:
        tok = items[0]
        return _Chain(A.Name(str(tok), pos=(tok.line, tok.column)), items[1])

    def rhs_expr(self, meta: Any, items: list[Any]) -> A.Expr:
        expr: A.Expr = items[0]
        return expr

    def assign_complex(self, meta: Any, items: list[Any]) -> A.Assign:
        return A.Assign(items[0], items[1], ":=", pos=_pos(meta), end=_end(meta))

    def assign_op(self, meta: Any, items: list[Any]) -> A.Assign:
        op = str(items[1]).upper().replace(" ", "")
        return A.Assign(items[0], items[2], op, pos=_pos(meta), end=_end(meta))

    def call_stmt(self, meta: Any, items: list[Any]) -> A.CallStmt:
        return A.CallStmt(items[0], pos=_pos(meta), end=_end(meta))

    def if_stmt(self, meta: Any, items: list[Any]) -> A.If:
        it = _tokens(items)
        branches: list[tuple[A.Expr, list[A.Stmt]]] = [(it[0], list(it[1].items))]
        else_body = None
        for x in it[2:]:
            if isinstance(x, _Elsif):
                branches.append((x.cond, x.body))
            elif isinstance(x, _Else):
                else_body = x.body
        return A.If(branches, else_body, pos=_pos(meta), end=_end(meta))

    def elsif_part(self, meta: Any, items: list[Any]) -> _Elsif:
        it = _tokens(items)
        return _Elsif(it[0], list(it[1].items))

    def else_part(self, meta: Any, items: list[Any]) -> _Else:
        it = _tokens(items)
        return _Else(list(it[0].items))

    def case_stmt(self, meta: Any, items: list[Any]) -> A.Case:
        it = _tokens(items)
        sel = it[0]
        branches = [x for x in it[1:] if isinstance(x, A.CaseBranch)]
        els = next((x for x in it[1:] if isinstance(x, _Else)), None)
        return A.Case(sel, branches, els.body if els else None, pos=_pos(meta), end=_end(meta))

    def case_elem(self, meta: Any, items: list[Any]) -> A.CaseBranch:
        labels = [x for x in items if isinstance(x, A.CaseLabel)]
        body = next(x for x in items if isinstance(x, _Stmts))
        return A.CaseBranch(labels, list(body.items), pos=_pos(meta))

    def case_label(self, meta: Any, items: list[Any]) -> A.CaseLabel:
        return A.CaseLabel(items[0], pos=_pos(meta))

    def case_range(self, meta: Any, items: list[Any]) -> A.CaseLabel:
        return A.CaseLabel(items[0], items[1], pos=_pos(meta))

    def case_name(self, meta: Any, items: list[Any]) -> A.Expr:
        parts = str(items[0]).split(".")
        expr: A.Expr = A.Name(parts[0], pos=_pos(meta))
        for p in parts[1:]:
            expr = A.Member(expr, p, pos=_pos(meta))
        return expr

    def case_neg_int(self, meta: Any, items: list[Any]) -> A.Literal:
        text = "-" + str(items[-1])
        return A.Literal("int", text, L.parse_int(text), pos=_pos(meta))

    def case_else(self, meta: Any, items: list[Any]) -> _Else:
        it = _tokens(items)
        return _Else(list(it[0].items))

    def for_stmt(self, meta: Any, items: list[Any]) -> A.For:
        it = _tokens(items)
        var = str(it[0])
        start, stop = it[1], it[2]
        if len(it) == 5:
            step, body = it[3], it[4]
        else:
            step, body = None, it[3]
        return A.For(var, start, stop, step, list(body.items), pos=_pos(meta), end=_end(meta))

    def while_stmt(self, meta: Any, items: list[Any]) -> A.While:
        it = _tokens(items)
        return A.While(it[0], list(it[1].items), pos=_pos(meta), end=_end(meta))

    def repeat_stmt(self, meta: Any, items: list[Any]) -> A.Repeat:
        it = _tokens(items)
        return A.Repeat(list(it[0].items), it[1], pos=_pos(meta), end=_end(meta))

    def exit_stmt(self, meta: Any, items: list[Any]) -> A.Exit:
        return A.Exit(pos=_pos(meta), end=_end(meta))

    def continue_stmt(self, meta: Any, items: list[Any]) -> A.Continue:
        return A.Continue(pos=_pos(meta), end=_end(meta))

    def return_stmt(self, meta: Any, items: list[Any]) -> A.Return:
        return A.Return(pos=_pos(meta), end=_end(meta))

    def jmp_stmt(self, meta: Any, items: list[Any]) -> A.Jump:
        return A.Jump(str(_tokens(items)[0]), pos=_pos(meta), end=_end(meta))

    def label_stmt(self, meta: Any, items: list[Any]) -> A.Label:
        return A.Label(str(items[0]), pos=_pos(meta), end=_end(meta))

    def empty_stmt(self, meta: Any, items: list[Any]) -> A.Empty:
        return A.Empty(pos=_pos(meta), end=_end(meta))

    # ---- выражения ----
    def binop(self, meta: Any, items: list[Any]) -> A.Binary:
        left, op, right = items
        o = str(op).upper()
        o = _OPS.get(o, o)
        return A.Binary(o, left, right, pos=_pos(meta))

    def neg(self, meta: Any, items: list[Any]) -> A.Expr:
        operand = items[-1]
        if isinstance(operand, A.Literal) and operand.kind in ("int", "real") and not operand.text.startswith("-"):
            return A.Literal(operand.kind, "-" + operand.text, -operand.value, operand.type_name, pos=_pos(meta))
        return A.Unary("NEG", operand, pos=_pos(meta))

    def plus(self, meta: Any, items: list[Any]) -> A.Expr:
        return A.Unary("PLUS", items[-1], pos=_pos(meta))

    def not_(self, meta: Any, items: list[Any]) -> A.Expr:
        return A.Unary("NOT", _tokens(items)[-1], pos=_pos(meta))

    def direct_addr(self, meta: Any, items: list[Any]) -> A.DirectAddr:
        return A.DirectAddr(str(items[0]).upper(), pos=_pos(meta))

    def call(self, meta: Any, items: list[Any]) -> A.Call:
        func = items[0]
        args = [a if isinstance(a, A.Arg) else A.Arg(a) for a in items[1:]]
        return A.Call(func, args, pos=_pos(meta))

    def pos_arg(self, meta: Any, items: list[Any]) -> A.Arg:
        return A.Arg(items[0], pos=_pos(meta))

    def named_arg(self, meta: Any, items: list[Any]) -> A.Arg:
        return A.Arg(items[1], name=str(items[0]), pos=_pos(meta))

    def out_arg(self, meta: Any, items: list[Any]) -> A.Arg:
        value = items[1] if len(items) > 1 else None
        return A.Arg(value, name=str(items[0]), output=True, pos=_pos(meta))

    def out_arg_neg(self, meta: Any, items: list[Any]) -> A.Arg:
        it = _tokens(items)
        return A.Arg(it[1], name=str(it[0]), output=True, negated=True, pos=_pos(meta))

    def var_name(self, meta: Any, items: list[Any]) -> A.Name:
        return A.Name(str(items[0]), pos=_pos(meta))

    def var_member(self, meta: Any, items: list[Any]) -> A.Member:
        return A.Member(items[0], str(items[1]), pos=_pos(meta))

    def var_bit(self, meta: Any, items: list[Any]) -> A.BitRef:
        return A.BitRef(items[0], int(str(items[1])), pos=_pos(meta))

    def var_index(self, meta: Any, items: list[Any]) -> A.Index:
        return A.Index(items[0], list(items[1:]), pos=_pos(meta))

    def var_deref(self, meta: Any, items: list[Any]) -> A.Deref:
        return A.Deref(items[0], pos=_pos(meta))

    # ---- литералы ----
    def lit_int(self, meta: Any, items: list[Any]) -> A.Literal:
        t = str(items[0])
        return A.Literal("int", t, L.parse_int(t), pos=_pos(meta))

    def lit_based(self, meta: Any, items: list[Any]) -> A.Literal:
        t = str(items[0])
        return A.Literal("int", t.upper().replace("16#", "16#"), L.parse_int(t), pos=_pos(meta))

    def lit_real(self, meta: Any, items: list[Any]) -> A.Literal:
        t = str(items[0])
        return A.Literal("real", t, float(t.replace("_", "")), pos=_pos(meta))

    def lit_time(self, meta: Any, items: list[Any]) -> A.Literal:
        t = str(items[0])
        head, body = L.split_prefix(t)
        if head.upper() in ("LT", "LTIME"):
            return A.Literal("ltime", t, L.parse_duration_ns(body), "LTIME", pos=_pos(meta))
        return A.Literal("time", t, L.parse_time_ms(t), "TIME", pos=_pos(meta))

    def lit_date(self, meta: Any, items: list[Any]) -> A.Literal:
        t = str(items[0])
        return A.Literal("date", t, L.parse_date_days(t), "DATE", pos=_pos(meta))

    def lit_tod(self, meta: Any, items: list[Any]) -> A.Literal:
        t = str(items[0])
        return A.Literal("tod", t, L.parse_tod_ms(t), "TOD", pos=_pos(meta))

    def lit_dt(self, meta: Any, items: list[Any]) -> A.Literal:
        t = str(items[0])
        return A.Literal("dt", t, L.parse_dt_s(t), "DT", pos=_pos(meta))

    def lit_typed(self, meta: Any, items: list[Any]) -> A.Literal:
        t = str(items[0])
        tname, body = L.parse_typed(t)
        if tname == "BOOL":
            return A.Literal("bool", t, body.upper() in ("TRUE", "1"), tname, pos=_pos(meta))
        if tname in ("REAL", "LREAL"):
            return A.Literal("real", t, float(body.replace("_", "")), tname, pos=_pos(meta))
        return A.Literal("int", t, L.parse_int(body), tname, pos=_pos(meta))

    def lit_enum(self, meta: Any, items: list[Any]) -> A.Literal:
        t = str(items[0])
        tname, _, value = t.partition("#")
        return A.Literal("enum", t, value, tname, pos=_pos(meta))

    def lit_string(self, meta: Any, items: list[Any]) -> A.Literal:
        t = str(items[0])
        return A.Literal("string", t, L.unescape(t[1:-1]), pos=_pos(meta))

    def lit_wstring(self, meta: Any, items: list[Any]) -> A.Literal:
        t = str(items[0])
        return A.Literal("wstring", t, L.unescape(t[1:-1]), pos=_pos(meta))

    def lit_true(self, meta: Any, items: list[Any]) -> A.Literal:
        return A.Literal("bool", "TRUE", True, pos=_pos(meta))

    def lit_false(self, meta: Any, items: list[Any]) -> A.Literal:
        return A.Literal("bool", "FALSE", False, pos=_pos(meta))


# Вспомогательные значения трансформера


class _Mod(str):
    pass


class _Qual(str):
    pass


class _Loc(str):
    pass


class _QName(str):
    pass


@dataclass
class _Ext:
    names: list[str]


@dataclass
class _Impl:
    names: list[str]


@dataclass
class _Dim:
    bounds: tuple[A.Expr, A.Expr] | None


@dataclass
class _Stmts:
    items: list[A.Stmt]


@dataclass
class _Elsif:
    cond: A.Expr
    body: list[A.Stmt]


@dataclass
class _Else:
    body: list[A.Stmt]


@dataclass
class _TypeBody:
    type: A.TypeRef
    init: A.Expr | None


@dataclass
class _Chain:
    target: A.Expr
    rhs: Any


def _chain(target: A.Expr, rhs: Any, meta: Any) -> A.Stmt:
    """`a := b := c` → a := (b := c) раскрывается в два присваивания: b := c; a := b."""
    if isinstance(rhs, _Chain):
        inner = _chain(rhs.target, rhs.rhs, meta)
        last = inner.body[-1] if isinstance(inner, A.Region) else inner
        assert isinstance(last, A.Assign)
        stmts = [*(inner.body if isinstance(inner, A.Region) else [inner])]
        stmts.append(A.Assign(target, last.target, pos=_pos(meta), end=_end(meta)))
        return A.Region("__chain__", stmts, pos=_pos(meta), end=_end(meta))
    return A.Assign(target, rhs, pos=_pos(meta), end=_end(meta))


_STRUCTURED = (A.If, A.Case, A.For, A.While, A.Repeat)


def _clean_stmts(items: list[Any]) -> list[A.Stmt]:
    """Убирает `;` после END_IF/END_CASE/...; раскрывает цепочки присваиваний."""
    out: list[A.Stmt] = []
    for it in items:
        if isinstance(it, A.Region) and it.name == "__chain__":
            out.extend(it.body)
            continue
        if isinstance(it, A.Empty) and out and isinstance(out[-1], _STRUCTURED):
            prev_end = out[-1].end
            if prev_end is not None and it.pos is not None and prev_end[0] == it.pos[0]:
                continue
        out.append(it)
    return out


# ---------------------------------------------------------------------------
# Привязка комментариев
# ---------------------------------------------------------------------------


def _flatten(stmts: list[A.Stmt]) -> list[A.Stmt]:
    out: list[A.Stmt] = []
    for s in stmts:
        out.append(s)
        for body in A.stmt_bodies(s):
            out.extend(_flatten(body))
    return out


def attach_comments(stmts: list[A.Stmt], comments: list[Comment]) -> list[str]:
    """Комментарии → lead/trail операторов; возвращает «хвостовые» (после последнего оператора)."""
    flat = [s for s in _flatten(stmts) if s.pos is not None]
    tail: list[str] = []
    ends_on: dict[int, A.Stmt] = {}
    for s in flat:
        if s.end is not None and not isinstance(s, _STRUCTURED):
            ends_on[s.end[0]] = s
        elif s.end is not None and s.pos is not None and s.pos[0] == s.end[0]:
            # однострочная структура (IF ... END_IF; на одной строке)
            ends_on[s.end[0]] = s
    starts = sorted(flat, key=lambda s: s.pos or (0, 0))
    for c in comments:
        if c.pragma:
            continue
        owner = ends_on.get(c.line)
        if owner is not None and owner.end is not None and c.column >= owner.end[1] - 1:
            owner.trail = c.text if owner.trail is None else owner.trail + " " + c.text
            continue
        nxt = next((s for s in starts if s.pos is not None and s.pos[0] > c.end_line), None)
        if nxt is None:
            nxt_same = next(
                (s for s in starts if s.pos is not None and s.pos[0] == c.line and s.pos[1] > c.column), None
            )
            if nxt_same is not None:
                nxt_same.lead.append(c.text)
            else:
                tail.append(c.text)
        else:
            nxt.lead.append(c.text)
    return tail


def attach_decl_comments(blocks: list[A.VarBlock], comments: list[Comment]) -> None:
    """Комментарий в строке объявления → VarDecl.comment; прагма перед объявлением → attrs."""
    decls = [d for b in blocks for d in b.decls]
    by_line: dict[int, list[A.VarDecl]] = {}
    for d in decls:
        if d.end is not None:
            by_line.setdefault(d.end[0], []).append(d)
    for c in comments:
        if c.pragma:
            nxt = next((d for d in decls if d.pos is not None and d.pos[0] >= c.end_line), None)
            if nxt is not None and nxt.pos is not None and nxt.pos[0] - c.end_line <= 1:
                nxt.attrs.append(c.text)
            continue
        owners = by_line.get(c.line)
        if owners:
            for d in owners:
                if d.end is not None and c.column >= d.end[1] - 1 and d.comment is None:
                    d.comment = c.text


def leading_pragmas(text: str, comments: list[Comment]) -> list[str]:
    """Прагмы перед первым значимым словом (атрибуты POU/GVL/DUT)."""
    clean_lines = text.splitlines()
    first_code_line = None
    for idx, line in enumerate(clean_lines, 1):
        if line.strip():
            first_code_line = idx
            break
    return [c.text for c in comments if c.pragma and (first_code_line is None or c.end_line <= first_code_line)]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def _parse(text: str, start: str, source: str) -> tuple[Any, str, list[Comment]]:
    clean, comments = strip_comments(text)
    try:
        tree = _lark().parse(clean, start=start)
    except UnexpectedInput as exc:
        line = getattr(exc, "line", None)
        col = getattr(exc, "column", None)
        ctx = exc.get_context(clean, 40).strip() if hasattr(exc, "get_context") else ""
        tok = getattr(exc, "token", None)
        what = f"неожиданное «{tok}»" if tok is not None else "неожиданный символ"
        raise StSyntaxError(f"{what}: {ctx}", line, col, source) from None
    except LarkError as exc:  # pragma: no cover - ошибки самой грамматики
        raise StSyntaxError(str(exc), source=source) from None
    try:
        result = _ToAst().transform(tree)
    except Exception as exc:
        raise StSyntaxError(f"разбор: {exc}", source=source) from exc
    return result, clean, comments


def parse_pou(text: str, source: str = "") -> A.PouText:
    """Заголовок POU, секции VAR и (необязательно) тело."""
    result, clean, comments = _parse(text, "pou_text", source)
    assert isinstance(result, A.PouText)
    result.attrs = leading_pragmas(clean, comments)
    attach_decl_comments(result.var_blocks, comments)
    result.tail = attach_comments(result.body, [c for c in comments if not _in_decls(c, result.var_blocks)])
    return result


def _in_decls(c: Comment, blocks: list[A.VarBlock]) -> bool:
    return any(b.pos is not None and b.end is not None and b.pos[0] <= c.line <= b.end[0] for b in blocks)


def parse_body(text: str, source: str = "") -> tuple[list[A.Stmt], list[str]]:
    """Тело POU (операторы); возвращает операторы и хвостовые комментарии."""
    if not text.strip():
        _, comments = strip_comments(text)
        return [], [c.text for c in comments if not c.pragma]
    result, _, comments = _parse(text, "stmts", source)
    assert isinstance(result, _Stmts)
    tail = attach_comments(result.items, comments)
    return result.items, tail


def parse_type(text: str, source: str = "") -> A.TypeDecl:
    result, clean, comments = _parse(text, "type_text", source)
    assert isinstance(result, A.TypeDecl)
    result.attrs = leading_pragmas(clean, comments)
    if isinstance(result.type, A.StructType):
        attach_decl_comments([A.VarBlock("STRUCT", [], result.type.members)], comments)
    return result


def parse_gvl(text: str, source: str = "") -> A.GvlText:
    result, clean, comments = _parse(text, "gvl_text", source)
    assert isinstance(result, A.GvlText)
    result.attrs = leading_pragmas(clean, comments)
    attach_decl_comments(result.var_blocks, comments)
    return result


def parse_expr(text: str, source: str = "") -> A.Expr:
    result, _, _ = _parse(text, "expr_text", source)
    assert isinstance(result, A.Expr)
    return result


def parse_type_ref(text: str, source: str = "") -> A.TypeRef:
    result, _, _ = _parse(text, "type_ref_text", source)
    assert isinstance(result, A.TypeRef)
    return result


def parse_init(text: str, source: str = "") -> A.Expr:
    result, _, _ = _parse(text, "init_text", source)
    assert isinstance(result, A.Expr)
    return result


def is_tree(value: object) -> bool:  # pragma: no cover - для отладки
    return isinstance(value, Tree)
