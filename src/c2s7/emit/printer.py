"""Печать ST AST: диалект SCL (TIA Portal, внешний исходник) и ST CODESYS.

Скобки ставятся по приоритетам (у SCL и МЭК они совпадают: ** выше унарного минуса и NOT, далее
* / MOD, + -, сравнения, = <>, AND, XOR, OR); левоассоциативные операторы правым операндом с тем же
приоритетом берутся в скобки, поэтому печать → разбор даёт тот же AST.
"""

from __future__ import annotations

import re

from c2s7.st import literals as L
from c2s7.st import nodes as A

PREC = {
    "OR": 1,
    "OR_ELSE": 1,
    "XOR": 2,
    "AND": 3,
    "AND_THEN": 3,
    "=": 4,
    "<>": 4,
    "<": 5,
    ">": 5,
    "<=": 5,
    ">=": 5,
    "+": 6,
    "-": 6,
    "*": 7,
    "/": 7,
    "MOD": 7,
    "**": 9,
}
UNARY_PREC = 8
ATOM = 10

SCL_KEYWORDS = {
    "AND",
    "ANY",
    "ARRAY",
    "AT",
    "BEGIN",
    "BLOCK_DB",
    "BLOCK_FB",
    "BLOCK_FC",
    "BOOL",
    "BY",
    "BYTE",
    "CASE",
    "CHAR",
    "CONST",
    "CONTINUE",
    "COUNTER",
    "DATA_BLOCK",
    "DATE",
    "DINT",
    "DIV",
    "DO",
    "DT",
    "DWORD",
    "ELSE",
    "ELSIF",
    "EN",
    "ENO",
    "END_CASE",
    "END_CONST",
    "END_DATA_BLOCK",
    "END_FOR",
    "END_FUNCTION",
    "END_FUNCTION_BLOCK",
    "END_IF",
    "END_LABEL",
    "END_ORGANIZATION_BLOCK",
    "END_REPEAT",
    "END_STRUCT",
    "END_TYPE",
    "END_VAR",
    "END_WHILE",
    "EXIT",
    "FALSE",
    "FOR",
    "FUNCTION",
    "FUNCTION_BLOCK",
    "GOTO",
    "IF",
    "INT",
    "LABEL",
    "MOD",
    "NIL",
    "NOT",
    "OF",
    "OK",
    "OR",
    "ORGANIZATION_BLOCK",
    "POINTER",
    "REAL",
    "REPEAT",
    "RETURN",
    "S5TIME",
    "STRING",
    "STRUCT",
    "THEN",
    "TIME",
    "TIMER",
    "TIME_OF_DAY",
    "TO",
    "TOD",
    "TRUE",
    "TYPE",
    "UNTIL",
    "VAR",
    "VAR_IN_OUT",
    "VAR_INPUT",
    "VAR_OUTPUT",
    "VAR_TEMP",
    "VOID",
    "WHILE",
    "WORD",
    "XOR",
    "REGION",
    "END_REGION",
}
_PLAIN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def scl_name(name: str) -> str:
    """Имя члена/переменной в SCL: в кавычках, если не идентификатор или ключевое слово."""
    if _PLAIN.match(name) and name.upper() not in SCL_KEYWORDS:
        return name
    return '"' + name.replace('"', '""') + '"'


class Printer:
    def __init__(self, dialect: str = "scl", indent: str = "    ", plain_names: bool = False) -> None:
        if dialect not in ("scl", "st"):
            raise ValueError(dialect)
        self.dialect = dialect
        self.indent = indent
        self.plain_names = plain_names  # начальные значения: имена без #

    # ------------------------------------------------------------------ выражения
    def expr(self, e: A.Expr, parent: int = 0) -> str:
        text, prec = self._expr(e)
        return f"({text})" if prec < parent else text

    def _expr(self, e: A.Expr) -> tuple[str, int]:
        if isinstance(e, A.Literal):
            return self.literal(e), ATOM if not str(self.literal(e)).startswith("-") else UNARY_PREC
        if isinstance(e, A.SclRef):
            return self.ref(e), ATOM
        if isinstance(e, A.Name):
            if self.dialect == "scl" and not self.plain_names:
                return "#" + scl_name(e.id), ATOM
            return e.id, ATOM
        if isinstance(e, A.Member):
            return f"{self.expr(e.base, ATOM)}.{self.member(e.name)}", ATOM
        if isinstance(e, A.Index):
            return f"{self.expr(e.base, ATOM)}[{', '.join(self.expr(i) for i in e.indices)}]", ATOM
        if isinstance(e, A.BitRef):
            sep = ".%X" if self.dialect == "scl" else "."
            return f"{self.expr(e.base, ATOM)}{sep}{e.bit}", ATOM
        if isinstance(e, A.Deref):
            return f"{self.expr(e.base, ATOM)}^", ATOM
        if isinstance(e, A.Slice):
            return f"{self.expr(e.base, ATOM)}.%{e.size}{e.number}", ATOM
        if isinstance(e, A.DirectAddr):
            return e.text, ATOM
        if isinstance(e, A.Unary):
            if e.op == "NOT":
                return f"NOT {self.expr(e.operand, UNARY_PREC)}", UNARY_PREC
            sign = "-" if e.op == "NEG" else "+"
            inner = self.expr(e.operand, UNARY_PREC)
            if inner.startswith(("-", "+")):
                inner = f"({inner})"
            return f"{sign}{inner}", UNARY_PREC
        if isinstance(e, A.Binary):
            return self.binary(e)
        if isinstance(e, A.Call):
            return self.call(e), ATOM
        if isinstance(e, A.ArrayInit):
            parts = []
            for el in e.elems:
                v = self.expr(el.value) if el.value is not None else ""
                parts.append(f"{el.repeat}({v})" if el.repeat is not None else v)
            return "[" + ", ".join(parts) + "]", ATOM
        if isinstance(e, A.StructInit):
            return "(" + ", ".join(f"{n} := {self.expr(v)}" for n, v in e.fields) + ")", ATOM
        raise TypeError(f"выражение {type(e).__name__}")

    def binary(self, e: A.Binary) -> tuple[str, int]:
        op = e.op
        prec = PREC[op]
        shown = op
        if self.dialect == "scl" and op in ("AND_THEN", "OR_ELSE"):
            shown = "AND" if op == "AND_THEN" else "OR"
        if op == "**":
            # правоассоциативный: левый операнд того же приоритета — в скобки
            left = self.expr(e.left, prec + 1)
            right = self.expr(e.right, UNARY_PREC)
            return f"{left} ** {right}", prec
        left = self.expr(e.left, prec)
        right = self.expr(e.right, prec + 1)
        return f"{left} {shown} {right}", prec

    def call(self, c: A.Call) -> str:
        func = self.expr(c.func, ATOM)
        args = []
        for a in c.args:
            if a.name is None:
                args.append(self.expr(a.value) if a.value is not None else "")
            elif a.output:
                neg = "NOT " if a.negated else ""
                val = self.expr(a.value) if a.value is not None else ""
                args.append(f"{neg}{a.name} => {val}".rstrip())
            else:
                val = self.expr(a.value) if a.value is not None else ""
                args.append(f"{a.name} := {val}")
        return f"{func}({', '.join(args)})"

    def ref(self, r: A.SclRef) -> str:
        if self.dialect == "st":
            return r.name
        if r.kind == "local":
            return "#" + scl_name(r.name)
        if r.kind in ("global", "tag"):
            return '"' + r.name.replace('"', '""') + '"'
        return r.name

    def member(self, name: str) -> str:
        return scl_name(name) if self.dialect == "scl" else name

    def literal(self, lit: A.Literal) -> str:
        k = lit.kind
        if k == "bool":
            return "TRUE" if lit.value else "FALSE"
        if k == "time":
            return L.format_duration(int(lit.value), "T#")
        if k == "s5time":
            return "S5T#" + L.format_duration(int(lit.value), "")
        if k == "ltime":
            return L.format_duration_ns(int(lit.value), "LT#" if self.dialect == "scl" else "LTIME#")
        if k == "string":
            return "'" + L.escape(str(lit.value), "'") + "'"
        if k == "wstring":
            if self.dialect == "scl":
                return "WSTRING#'" + L.escape(str(lit.value), "'") + "'"
            return '"' + L.escape(str(lit.value), '"') + '"'
        if k == "int":
            if lit.type_name and lit.text.upper().startswith(lit.type_name.upper() + "#"):
                return lit.text.upper().replace("16#", "16#")
            return lit.text.replace("_", "") if "#" not in lit.text else lit.text.upper()
        if k == "real":
            t = lit.text
            if lit.type_name and "#" in t:
                return t.upper()
            return t
        if k in ("date", "tod", "dt"):
            head, body = L.split_prefix(lit.text)
            canon = {"date": "D#", "tod": "TOD#", "dt": "DT#"}[k]
            if head.upper() in ("LTOD", "LDT"):
                canon = head.upper() + "#"
            return canon + body
        if k == "enum":
            return lit.text
        return lit.text

    # ------------------------------------------------------------------ операторы
    def stmts(self, stmts: list[A.Stmt], level: int) -> list[str]:
        out: list[str] = []
        for s in stmts:
            out.extend(self.stmt(s, level))
        return out

    def _end(self, kw: str) -> str:
        return f"{kw};" if self.dialect == "scl" else kw

    def stmt(self, s: A.Stmt, level: int) -> list[str]:
        pad = self.indent * level
        lines = [f"{pad}// {c}" if c else f"{pad}//" for c in self._split_comments(s.lead)]
        body = self._stmt(s, level)
        if s.trail and body:
            body[0] = f"{body[0]}  // {s.trail}" if len(body) == 1 else body[0]
            if len(body) > 1:
                body[-1] = f"{body[-1]}  // {s.trail}"
        return lines + body

    @staticmethod
    def _split_comments(items: list[str]) -> list[str]:
        out: list[str] = []
        for c in items:
            out.extend(c.splitlines() or [""])
        return out

    def _stmt(self, s: A.Stmt, level: int) -> list[str]:
        pad = self.indent * level
        if isinstance(s, A.Assign):
            op = s.op
            if self.dialect == "scl" and op in ("S=", "R="):
                # SCL не знает S=/R=: IF value THEN target := TRUE/FALSE
                val = "TRUE" if op == "S=" else "FALSE"
                return [
                    f"{pad}IF {self.expr(s.value)} THEN",
                    f"{pad}{self.indent}{self.expr(s.target)} := {val};",
                    f"{pad}{self._end('END_IF')}",
                ]
            if self.dialect == "scl" and op == "REF=":
                return [f"{pad}{self.expr(s.target)} := REF({self.expr(s.value)});"]
            return [f"{pad}{self.expr(s.target)} {op} {self.expr(s.value)};"]
        if isinstance(s, A.CallStmt):
            return [f"{pad}{self.call(s.call)};"]
        if isinstance(s, A.If):
            out = []
            for i, (cond, body) in enumerate(s.branches):
                kw = "IF" if i == 0 else "ELSIF"
                out.append(f"{pad}{kw} {self.expr(cond)} THEN")
                out.extend(self.stmts(body, level + 1))
            if s.else_body is not None:
                out.append(f"{pad}ELSE")
                out.extend(self.stmts(s.else_body, level + 1))
            out.append(f"{pad}{self._end('END_IF')}")
            return out
        if isinstance(s, A.Case):
            out = [f"{pad}CASE {self.expr(s.selector)} OF"]
            for br in s.branches:
                labels = ", ".join(
                    self.expr(lb.lo) + (f"..{self.expr(lb.hi)}" if lb.hi is not None else "") for lb in br.labels
                )
                out.append(f"{pad}{self.indent}{labels}:")
                out.extend(self.stmts(br.body, level + 2))
            if s.else_body is not None:
                out.append(f"{pad}{self.indent}ELSE")
                out.extend(self.stmts(s.else_body, level + 2))
            out.append(f"{pad}{self._end('END_CASE')}")
            return out
        if isinstance(s, A.For):
            var = self.expr(s.var_expr) if hasattr(s, "var_expr") else self._for_var(s.var)
            step = f" BY {self.expr(s.step)}" if s.step is not None else ""
            out = [f"{pad}FOR {var} := {self.expr(s.start)} TO {self.expr(s.stop)}{step} DO"]
            out.extend(self.stmts(s.body, level + 1))
            out.append(f"{pad}{self._end('END_FOR')}")
            return out
        if isinstance(s, A.While):
            out = [f"{pad}WHILE {self.expr(s.cond)} DO"]
            out.extend(self.stmts(s.body, level + 1))
            out.append(f"{pad}{self._end('END_WHILE')}")
            return out
        if isinstance(s, A.Repeat):
            out = [f"{pad}REPEAT"]
            out.extend(self.stmts(s.body, level + 1))
            out.append(f"{pad}UNTIL {self.expr(s.cond)}")
            out.append(f"{pad}{self._end('END_REPEAT')}")
            return out
        if isinstance(s, A.Exit):
            return [f"{pad}EXIT;"]
        if isinstance(s, A.Continue):
            return [f"{pad}CONTINUE;"]
        if isinstance(s, A.Return):
            return [f"{pad}RETURN;"]
        if isinstance(s, A.Jump):
            kw = "GOTO" if self.dialect == "scl" else "JMP"
            if s.cond is not None:
                return [
                    f"{pad}IF {self.expr(s.cond)} THEN",
                    f"{pad}{self.indent}{kw} {s.label};",
                    f"{pad}{self._end('END_IF')}",
                ]
            return [f"{pad}{kw} {s.label};"]
        if isinstance(s, A.Label):
            return [f"{s.name}:"] if self.dialect == "scl" else [f"{pad}{s.name}:"]
        if isinstance(s, A.Empty):
            return [f"{pad};"]
        if isinstance(s, A.Region):
            if self.dialect == "scl":
                out = [f"{pad}REGION {s.name}"]
                out.extend(self.stmts(s.body, level + 1))
                out.append(f"{pad}END_REGION")
                return out
            out = [f"{pad}// REGION {s.name}"]
            out.extend(self.stmts(s.body, level))
            out.append(f"{pad}// END_REGION {s.name}")
            return out
        if isinstance(s, A.Verbatim):
            return [f"{pad}{line}" if line else "" for line in s.text.splitlines()]
        raise TypeError(f"оператор {type(s).__name__}")

    def _for_var(self, name: str) -> str:
        if self.dialect == "scl":
            return "#" + scl_name(name)
        return name


def to_text(lines: list[str]) -> str:
    return "\n".join(lines) + ("\n" if lines else "")
