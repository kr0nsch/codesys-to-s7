"""Печать SCL/ST: скобки по приоритетам (печать → разбор даёт тот же AST), S=/R=, литералы, срезы."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from c2s7.emit.printer import Printer, scl_name
from c2s7.st import nodes as A
from c2s7.st import parser as P

ST = Printer("st")
SCL = Printer("scl")


def test_scl_names_and_refs() -> None:
    e = A.Member(A.SclRef("global", "DB_Plant"), "flow")
    assert SCL.expr(e) == '"DB_Plant".flow'
    assert SCL.expr(A.SclRef("local", "begin")) == '#"begin"'
    assert SCL.expr(A.SclRef("tag", "P101_Run")) == '"P101_Run"'
    assert SCL.expr(A.BitRef(A.SclRef("local", "w"), 3)) == "#w.%X3"
    assert SCL.expr(A.Slice(A.SclRef("local", "dw"), "B", 1)) == "#dw.%B1"
    assert scl_name("TIME") == '"TIME"' and scl_name("x") == "x"


def test_set_reset_and_ref_in_scl() -> None:
    lines = SCL.stmt(A.Assign(A.SclRef("local", "q"), A.SclRef("local", "s"), "S="), 0)
    assert lines == ["IF #s THEN", "    #q := TRUE;", "END_IF;"]
    assert SCL.stmt(A.Assign(A.SclRef("local", "r"), A.SclRef("local", "a"), "REF="), 0) == ["#r := REF(#a);"]


def test_literals_scl() -> None:
    assert SCL.literal(A.Literal("time", "T#1h30m", 5_400_000)) == "T#1H30M"
    assert SCL.literal(A.Literal("time", "T#0s", 0)) == "T#0MS"
    assert SCL.literal(A.Literal("ltime", "LTIME#5ms", 5_000_000)) == "LT#5MS"
    assert SCL.literal(A.Literal("wstring", '"ab"', "ab")) == "WSTRING#'ab'"
    assert SCL.literal(A.Literal("string", "'a$'b'", "a'b")) == "'a$'b'"
    assert SCL.literal(A.Literal("s5time", "T#300MS", 300)) == "S5T#300MS"


def test_statements_end_with_semicolon_in_scl() -> None:
    body, _ = P.parse_body(
        "IF a THEN b := 1; END_IF\nFOR i := 1 TO 2 DO END_FOR\nWHILE a DO END_WHILE\nREPEAT UNTIL a END_REPEAT\nCASE n OF 1: ; END_CASE"
    )
    text = "\n".join(SCL.stmts(body, 0))
    for kw in ("END_IF;", "END_FOR;", "END_WHILE;", "END_REPEAT;", "END_CASE;"):
        assert kw in text


# ---- печать со скобками → тот же AST (property, ТЗ §8.6)
names = st.sampled_from(["a", "b", "c", "x1"])
ops = st.sampled_from(["OR", "XOR", "AND", "=", "<>", "<", ">=", "+", "-", "*", "/", "MOD", "**"])


def exprs() -> st.SearchStrategy[A.Expr]:
    leaf: st.SearchStrategy[A.Expr] = st.one_of(
        names.map(A.Name), st.integers(0, 99).map(lambda v: A.Literal("int", str(v), v))
    )

    def ext(children: st.SearchStrategy[A.Expr]) -> st.SearchStrategy[A.Expr]:
        return st.one_of(
            st.tuples(ops, children, children).map(lambda t: A.Binary(t[0], t[1], t[2])),
            st.tuples(st.sampled_from(["NOT", "NEG"]), children).map(lambda t: A.Unary(t[0], t[1])),
        )

    return st.recursive(leaf, ext, max_leaves=8)


def _strip(e: A.Expr) -> A.Expr:
    """Отрицательный литерал после разбора = NEG(литерал): приводим к одной форме."""
    if isinstance(e, A.Literal) and e.kind == "int" and e.text.startswith("-"):
        return A.Unary("NEG", A.Literal("int", e.text[1:], -e.value))
    if isinstance(e, A.Binary):
        return A.Binary(e.op, _strip(e.left), _strip(e.right))
    if isinstance(e, A.Unary):
        inner = _strip(e.operand)
        return A.Unary(e.op, inner)
    return e


@settings(max_examples=300, derandomize=True, deadline=None)
@given(exprs())
def test_print_parse_roundtrip(e: A.Expr) -> None:
    text = ST.expr(e)
    back = P.parse_expr(text)
    assert _strip(back) == _strip(e), text
