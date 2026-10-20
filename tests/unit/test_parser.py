"""Грамматика ST CODESYS (lark LALR): объявления, операторы, литералы, комментарии, позиции."""

from __future__ import annotations

import pytest

from c2s7.st import nodes as A
from c2s7.st import parser as P

DECL = """{attribute 'hide'}
FUNCTION_BLOCK PUBLIC FB_X EXTENDS FB_Base IMPLEMENTS I_A, I_B
VAR_INPUT
    xIn AT %IX0.0 : BOOL := TRUE; // вход
    a, b : ARRAY[1..10, 0..2] OF INT := [1, 2, 3(0)];
    s : STRING(80) := 'abc$'';
    ws : WSTRING[20];
    st : ST_X := (a := 1, b := (c := 2));
    r : INT(0..100);
END_VAR
VAR RETAIN PERSISTENT
    p : POINTER TO INT;
    q : REFERENCE TO REAL;
    arr : ARRAY[*] OF BYTE;
END_VAR
VAR_STAT
    n : UDINT;
END_VAR
"""


def test_declarations() -> None:
    pt = P.parse_pou(DECL, "x.st")
    h = pt.header
    assert (h.kind, h.name, h.modifiers, h.extends, h.implements) == (
        "FUNCTION_BLOCK",
        "FB_X",
        ["PUBLIC"],
        ["FB_Base"],
        ["I_A", "I_B"],
    )
    assert pt.attrs == ["attribute 'hide'"]
    vin = pt.var_blocks[0]
    assert [d.name for d in vin.decls] == ["xIn", "a", "b", "s", "ws", "st", "r"]
    x = vin.decls[0]
    assert x.address == "%IX0.0" and x.comment == "вход" and isinstance(x.init, A.Literal)
    assert isinstance(vin.decls[1].type, A.ArrayType) and len(vin.decls[1].type.dims) == 2
    assert vin.decls[1].init is not None and isinstance(vin.decls[1].init, A.ArrayInit)
    assert vin.decls[1].init.elems[2].repeat == 3
    assert isinstance(vin.decls[3].type, A.StringType) and vin.decls[3].init.value == "abc'"  # type: ignore[union-attr]
    assert isinstance(vin.decls[4].type, A.StringType) and vin.decls[4].type.wide
    assert isinstance(vin.decls[5].init, A.StructInit)
    assert isinstance(vin.decls[6].type, A.SubrangeType)
    rp = pt.var_blocks[1]
    assert rp.retain and rp.persistent
    assert isinstance(rp.decls[0].type, A.PointerType) and isinstance(rp.decls[1].type, A.ReferenceType)
    assert rp.decls[2].type.dims == [None]  # type: ignore[union-attr]
    assert pt.var_blocks[2].kind == "VAR_STAT"


def test_statements_and_chain() -> None:
    body, _ = P.parse_body(
        "x := y := 5;\nx S= a; x R= b;\nfb(IN := a OR b, PT := T#5S, Q => q, NOT ET => e);\n"
        "IF a THEN lbl: JMP lbl; ELSIF b THEN ; ELSE c := 1; END_IF;\n"
        "CASE n OF 1, 2: x := 1; E_Mode.Auto: y := 2; 3..5, -1: ; ELSE z := 3; END_CASE\n"
        "FOR i := 1 TO 10 BY 2 DO EXIT; END_FOR\nWHILE TRUE DO CONTINUE; END_WHILE\nREPEAT x := x + 1; UNTIL x >= 10 END_REPEAT\nRETURN;"
    )
    kinds = [type(s).__name__ for s in body]
    assert kinds[:3] == ["Assign", "Assign", "Assign"]  # цепочка раскрыта: y := 5; x := y
    assert body[0].target == A.Name("y") and body[1].value == A.Name("y")
    assert body[2].op == "S=" and body[3].op == "R="
    call = body[4]
    assert isinstance(call, A.CallStmt)
    assert [(a.name, a.output, a.negated) for a in call.call.args] == [
        ("IN", False, False),
        ("PT", False, False),
        ("Q", True, False),
        ("ET", True, True),
    ]
    iff = body[5]
    assert (
        isinstance(iff, A.If)
        and isinstance(iff.branches[0][1][0], A.Label)
        and isinstance(iff.branches[0][1][1], A.Jump)
    )
    case = body[6]
    assert isinstance(case, A.Case) and case.branches[1].labels[0].lo == A.Member(A.Name("E_Mode"), "Auto")
    assert case.branches[2].labels[0].hi is not None and case.branches[2].labels[1].lo.value == -1  # type: ignore[union-attr]
    assert [type(s).__name__ for s in body[7:]] == ["For", "While", "Repeat", "Return"]


def test_expression_precedence() -> None:
    e = P.parse_expr("a OR b AND NOT c = d + e * f ** 2")
    assert isinstance(e, A.Binary) and e.op == "OR"
    assert isinstance(e.right, A.Binary) and e.right.op == "AND"
    cmp = e.right.right  # type: ignore[union-attr]
    assert cmp.op == "=" and isinstance(cmp.left, A.Unary) and cmp.left.op == "NOT"  # NOT сильнее сравнения
    assert cmp.right.op == "+" and cmp.right.right.op == "*" and cmp.right.right.right.op == "**"
    neg = P.parse_expr("-2 ** 2")
    assert isinstance(neg, A.Unary) and neg.op == "NEG"


@pytest.mark.parametrize(
    ("text", "kind", "value"),
    [
        ("T#1h30m", "time", 5_400_000),
        ("TIME#1.5s", "time", 1500),
        ("LTIME#5ms", "ltime", 5_000_000),
        ("16#FF", "int", 255),
        ("2#1010_1010", "int", 170),
        ("WORD#16#FF", "int", 255),
        ("INT#-5", "int", -5),
        ("REAL#1.5", "real", 1.5),
        ("1.0E3", "real", 1000.0),
        ("D#2024-01-31", "date", 19753),
        ("TOD#12:30:00", "tod", 45_000_000),
        ("E_Mode#Auto", "enum", "Auto"),
        ('"wide"', "wstring", "wide"),
    ],
)
def test_literals(text: str, kind: str, value: object) -> None:
    lit = P.parse_expr(text)
    assert isinstance(lit, A.Literal) and lit.kind == kind and lit.value == value


def test_comments_attach_and_nested() -> None:
    body, tail = P.parse_body("(* внешний (* вложенный *) *)\nx := 1; // хвост\n// перед y\ny := 2;\n// конец\n")
    assert body[0].lead == ["внешний (* вложенный *)"] and body[0].trail == "хвост"
    assert body[1].lead == ["перед y"]
    assert tail == ["конец"]


def test_types_and_gvl() -> None:
    t = P.parse_type("TYPE E_M : (Off := 0, On) INT; END_TYPE")
    assert isinstance(t.type, A.EnumType) and t.type.base == "INT" and t.type.values[1] == ("On", None)
    u = P.parse_type("TYPE U : UNION a : DWORD; b : REAL; END_UNION END_TYPE")
    assert isinstance(u.type, A.StructType) and u.type.union
    g = P.parse_gvl("{attribute 'qualified_only'}\nVAR_GLOBAL CONSTANT\n    C : INT := 3;\nEND_VAR\n")
    assert g.attrs == ["attribute 'qualified_only'"] and g.var_blocks[0].constant


def test_syntax_error_has_position() -> None:
    with pytest.raises(P.StSyntaxError) as exc:
        P.parse_body("x := ;\n", "bad.st")
    assert exc.value.line == 1 and "bad.st" in str(exc.value)


def test_positions() -> None:
    body, _ = P.parse_body("\n\n  x := 1;\n")
    assert body[0].pos == (3, 3)
