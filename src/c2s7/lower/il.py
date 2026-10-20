"""IL → ST AST (ТЗ M2): LD/ST/S/R, логика с N и скобками, арифметика, сравнения, JMP*, CAL*, RET*.

Текущий результат (CR) держится символьно — выражением. После `ST x` CR становится `x` (значение
то же, а выражение, ссылающееся на уже изменённые переменные, повторно не вычисляется), поэтому
`LD a; ST b; AND c` = `b AND c` = `a AND c`. Если `STN/S/R` пишут переменную, от которой зависит CR,
CR сначала сохраняется во временную переменную. Вызов функции `F op2, op3` даёт `F(CR, op2, op3)`.
Переходы снимает `lower/jumps.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from c2s7.lower.common import Names, add_vars, and_, expr_vars, not_, or_
from c2s7.lower.jumps import remove_jumps
from c2s7.model import Origin, Pou
from c2s7.st import nodes as A
from c2s7.st import parser as P

if TYPE_CHECKING:
    from c2s7.convert.core import Converter


class IlError(ValueError):
    """Строка IL вне поддерживаемого подмножества."""


BOOL_OPS = {"AND": "AND", "OR": "OR", "XOR": "XOR", "ANDN": "AND", "ORN": "OR", "XORN": "XOR"}
ARITH = {"ADD": "+", "SUB": "-", "MUL": "*", "DIV": "/", "MOD": "MOD"}
CMP = {"GT": ">", "GE": ">=", "EQ": "=", "NE": "<>", "LE": "<=", "LT": "<"}
_LINE = re.compile(r"^\s*(?:(?P<label>[A-Za-z_]\w*)\s*:(?!=))?\s*(?P<rest>.*?)\s*$")


@dataclass
class Instr:
    op: str
    operand: str
    line: int
    label: str | None = None


def strip_comments(text: str) -> str:
    clean, _ = P.strip_comments(text)
    return clean


def parse_il(text: str) -> list[Instr]:
    out: list[Instr] = []
    for i, raw in enumerate(strip_comments(text).splitlines(), start=1):
        m = _LINE.match(raw)
        if m is None:
            continue
        label = m.group("label")
        rest = m.group("rest")
        if label and not rest:
            out.append(Instr("", "", i, label))
            continue
        if not rest:
            continue
        if rest == ")":
            out.append(Instr(")", "", i, label))
            continue
        parts = rest.split(None, 1)
        op = parts[0].upper()
        operand = parts[1].strip() if len(parts) > 1 else ""
        if op.endswith("(") and len(op) > 1:
            op, operand = op[:-1], ("(" + " " + operand).strip()
        out.append(Instr(op, operand, i, label))
    return out


class _Lower:
    def __init__(self, pou: Pou, conv: Converter | None) -> None:
        self.pou = pou
        self.conv = conv
        self.names = Names(pou)
        self.stmts: list[A.Stmt] = []
        self.cr: A.Expr | None = None
        self.stack: list[tuple[str, bool, A.Expr | None]] = []  # (оператор, N, сохранённый CR)
        self.temps: list[A.VarDecl] = []
        self.where = pou.impl_origin or pou.origin

    def expr(self, text: str, line: int) -> A.Expr:
        try:
            return P.parse_expr(text, self.where.file)
        except Exception as exc:
            raise IlError(f"строка {line}: операнд «{text}»: {exc}") from None

    def need_cr(self, ins: Instr) -> A.Expr:
        if self.cr is None:
            raise IlError(f"строка {ins.line}: {ins.op} без текущего результата")
        return self.cr

    def protect(self, target: str, ins: Instr) -> None:
        """Перед записью в переменную, от которой зависит CR, CR сохраняется во временную."""
        if self.cr is not None and target.split(".")[0].split("[")[0].upper() in expr_vars(self.cr):
            tmp = self.names.fresh("cr")
            self.temps.append(A.VarDecl(tmp, A.NamedType("BOOL")))
            self.stmts.append(A.Assign(A.Name(tmp), self.cr))
            self.cr = A.Name(tmp)

    def run(self, instrs: list[Instr]) -> list[A.Stmt]:
        for ins in instrs:
            if ins.label:
                self.stmts.append(A.Label(ins.label))
            if ins.op:
                self.one(ins)
        add_vars(self.pou, "VAR_TEMP", self.temps)
        return self.stmts

    def one(self, ins: Instr) -> None:
        op, arg = ins.op, ins.operand
        nested = arg.startswith("(")
        if nested:
            arg = arg[1:].strip()
        if op in ("LD", "LDN"):
            e = self.expr(arg, ins.line)
            self.cr = not_(e) if op == "LDN" else e
            return
        if op in ("ST", "STN"):
            cr = self.need_cr(ins)
            target = self.expr(arg, ins.line)
            if op == "STN":
                self.protect(arg, ins)
                self.stmts.append(A.Assign(target, not_(self.need_cr(ins))))
            else:
                self.stmts.append(A.Assign(target, cr))
                self.cr = target
            return
        if op in ("S", "R"):
            self.protect(arg, ins)
            cr = self.need_cr(ins)
            val = A.Literal("bool", "TRUE" if op == "S" else "FALSE", op == "S")
            self.stmts.append(A.If([(cr, [A.Assign(self.expr(arg, ins.line), val)])]))
            return
        if op == "NOT":
            self.cr = not_(self.need_cr(ins))
            return
        if op in BOOL_OPS or op in ARITH or op in CMP:
            neg = op.endswith("N") and op in ("ANDN", "ORN", "XORN")
            if nested:
                self.stack.append((op, neg, self.cr))
                self.cr = self.expr(arg, ins.line) if arg else None
                return
            self.cr = self.combine(op, neg, self.need_cr(ins), self.expr(arg, ins.line))
            return
        if op == ")":
            if not self.stack:
                raise IlError(f"строка {ins.line}: лишняя «)»")
            sop, neg, saved = self.stack.pop()
            if saved is None:
                raise IlError(f"строка {ins.line}: «(» без текущего результата")
            self.cr = self.combine(sop, neg, saved, self.need_cr(ins))
            return
        if op in ("JMP", "JMPC", "JMPCN"):
            cond = None if op == "JMP" else (self.need_cr(ins) if op == "JMPC" else not_(self.need_cr(ins)))
            self.stmts.append(A.Jump(arg, cond))
            return
        if op in ("RET", "RETC", "RETCN"):
            if op == "RET":
                self.stmts.append(A.Return())
            else:
                cond = self.need_cr(ins) if op == "RETC" else not_(self.need_cr(ins))
                self.stmts.append(A.If([(cond, [A.Return()])]))
            return
        if op in ("CAL", "CALC", "CALCN"):
            call = self.expr(arg if "(" in arg else arg + "()", ins.line)
            if not isinstance(call, A.Call):
                raise IlError(f"строка {ins.line}: CAL {arg}")
            st: A.Stmt = A.CallStmt(call)
            if op != "CAL":
                cond = self.need_cr(ins) if op == "CALC" else not_(self.need_cr(ins))
                st = A.If([(cond, [st])])
            self.stmts.append(st)
            return
        # вызов функции: F op2, op3 → F(CR, op2, op3)
        if re.fullmatch(r"[A-Za-z_]\w*", op):
            args = [A.Arg(self.need_cr(ins))]
            if arg:
                args += [A.Arg(self.expr(a.strip(), ins.line)) for a in _split_args(arg)]
            self.cr = A.Call(A.Name(op), args)
            return
        raise IlError(f"строка {ins.line}: оператор {op} вне подмножества")

    @staticmethod
    def combine(op: str, neg: bool, left: A.Expr, right: A.Expr) -> A.Expr:
        if neg:
            right = not_(right)
        if op in BOOL_OPS:
            base = BOOL_OPS[op]
            if base == "AND":
                return and_(left, right)
            if base == "OR":
                return or_(left, right)
            return A.Binary("XOR", left, right)
        if op in ARITH:
            return A.Binary(ARITH[op], left, right)
        return A.Binary(CMP[op], left, right)


def _split_args(text: str) -> list[str]:
    out: list[str] = []
    depth = 0
    cur = ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return out


def il_to_st(text: str, pou: Pou, conv: Converter | None = None) -> list[A.Stmt]:
    """Тело IL → операторы ST; переходы свёрнуты, неприводимые остаются Jump (C2S7-GFX-GOTO)."""
    where = pou.impl_origin or pou.origin
    if conv is not None:
        conv.add("C2S7-IL", where, f"IL {pou.name}")
    try:
        stmts = _Lower(pou, conv).run(parse_il(text))
    except IlError as exc:
        if conv is None:
            raise
        conv.add("C2S7-LIB", Origin(where.file, where.line), f"IL не разобрано: {exc}")
        return [A.Verbatim("// IL не переведено (C2S7-LIB): " + str(exc))]
    res = remove_jumps(stmts)
    return res.stmts
