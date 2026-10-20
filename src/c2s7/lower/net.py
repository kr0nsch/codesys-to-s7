"""NetIR (LD/FBD/CFC) → ST AST (ТЗ M3, M5).

LD/FBD: сети по порядку; в сети — элементы-приёмники в порядке документа (катушки, выходы,
прыжки, возвраты, вызовы ФБ без потребителей). Поток питания LD — выражение: контакт = AND, слияние
проводов = OR, катушки передают поток дальше. Фронтовый контакт P/N → бит памяти в статике
(C2S7-GFX-EDGE): фронт считается в начале сети во временную переменную. Вызов ФБ ставится перед
первым чтением его выхода. Прыжки снимает `lower/jumps.py`.

CFC: элементы по `executionOrderId`. Выход оператора/функции сохраняется в переменную в момент
своего шага; если его читает элемент с меньшим порядком (обратная связь) — в статике, со значением
прошлого цикла (C2S7-GFX-CFCFB), иначе во временной. ФБ вызываются в свой шаг, выходы читаются как
члены экземпляра.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from c2s7.ir.netir import Conn, Element, NetBody, Network
from c2s7.lower.common import Names, add_vars, and_, decl_types, lit_false, lit_true, not_, or_
from c2s7.lower.jumps import remove_jumps
from c2s7.model import Origin, Pou
from c2s7.st import nodes as A
from c2s7.st import parser as P
from c2s7.st import types as T

if TYPE_CHECKING:
    from c2s7.convert.core import Converter

LOGIC = {"AND": "AND", "OR": "OR", "XOR": "XOR"}
ARITH = {"ADD": "+", "SUB": "-", "MUL": "*", "DIV": "/", "MOD": "MOD"}
CMP = {"GT": ">", "GE": ">=", "EQ": "=", "NE": "<>", "LE": "<=", "LT": "<"}
STD_FB_OUT = {
    "TON": {"Q": "BOOL", "ET": "TIME"},
    "TOF": {"Q": "BOOL", "ET": "TIME"},
    "TP": {"Q": "BOOL", "ET": "TIME"},
    "R_TRIG": {"Q": "BOOL"},
    "F_TRIG": {"Q": "BOOL"},
    "SR": {"Q1": "BOOL"},
    "RS": {"Q1": "BOOL"},
    "CTU": {"Q": "BOOL", "CV": "WORD"},
    "CTD": {"Q": "BOOL", "CV": "WORD"},
    "CTUD": {"QU": "BOOL", "QD": "BOOL", "CV": "WORD"},
}


class NetError(ValueError):
    """Сеть не сводится к ST (цикл без порядка, обрыв провода)."""


@dataclass
class NetMeta:
    """Что понижение добавило к POU — нужно эмиттеру FlgNet (те же имена битов фронтов)."""

    edge_bits: dict[str, str] = field(default_factory=dict)  # id контакта → статический бит памяти
    feedback: list[str] = field(default_factory=list)
    operands: dict[str, A.Expr] = field(default_factory=dict)  # текст операнда → обращение S7 (конвертер)
    types: dict[str, str] = field(default_factory=dict)  # текст операнда → тип CODESYS


class NetLowering:
    def __init__(self, pou: Pou, conv: Converter | None) -> None:
        assert pou.net is not None
        self.pou = pou
        self.body: NetBody = pou.net
        self.conv = conv
        self.names = Names(pou)
        self.types = decl_types(pou)
        self.statics: list[A.VarDecl] = []
        self.temps: list[A.VarDecl] = []
        self.meta = NetMeta()
        self.where = pou.impl_origin or pou.origin
        # состояние текущей сети
        self.els: dict[str, Element] = {}
        self.out: list[A.Stmt] = []
        self.called: set[str] = set()
        self.edge_tmp: dict[str, str] = {}
        self.cfc_values: dict[str, str] | None = None  # CFC: id блока → переменная его выхода

    # ------------------------------------------------------------------ находки
    def add(self, rule: str, detail: str, line: int | None = None) -> None:
        if self.conv is not None:
            self.conv.add(rule, Origin(self.where.file, line or self.where.line), detail)

    # ------------------------------------------------------------------ вход
    def lower(self) -> list[A.Stmt]:
        if self.body.language == "CFC":
            stmts = self.cfc(self.body.networks[0] if self.body.networks else Network(1))
        else:
            stmts = []
            for net in self.body.networks:
                stmts.extend(self.network(net))
            self.double_coils()
        res = remove_jumps(stmts)
        for lbl in res.remaining:
            self.add("C2S7-GFX-GOTO", f"переход {lbl} не свёлся к IF/REPEAT")
        add_vars(self.pou, "VAR", self.statics)
        add_vars(self.pou, "VAR_TEMP", self.temps)
        return res.stmts

    # ------------------------------------------------------------------ выражения
    def var_expr(self, text: str | None, line: int | None) -> A.Expr:
        if not text:
            raise NetError(f"строка {line}: пустой операнд")
        return P.parse_expr(text, self.where.file)

    def value(self, conn: Conn, line: int | None = None) -> A.Expr:
        """Значение на конце провода: переменная, выход блока, поток LD."""
        if self.cfc_values is not None and self._source(conn) is not None:
            return self.cfc_value(conn, line)
        el = self.els.get(conn.ref)
        if el is None:
            raise NetError(f"строка {line}: провод на несуществующий элемент {conn.ref}")
        if el.kind == "left_rail":
            return lit_true()
        if el.kind == "in_var":
            e = self.var_expr(el.var, el.line)
            return not_(e) if el.negated else e
        if el.kind == "connector":
            if not el.conns:
                raise NetError(f"строка {el.line}: коннектор без входа")
            return self.value(el.conns[0], el.line)
        if el.kind == "continuation":
            src = next((x for x in self.els.values() if x.kind == "connector" and x.var == el.var and x.var), None)
            if src is None:
                raise NetError(f"строка {el.line}: продолжение {el.var} без коннектора")
            return self.value(src.conns[0], src.line)
        if el.kind == "contact":
            return and_(self.flow(el), self.contact_term(el))
        if el.kind == "coil":
            return self.flow(el)
        if el.kind == "block":
            return self.block_out(el, conn.formal)
        if el.kind in ("out_var", "inout_var"):
            return self.var_expr(el.var, el.line)
        raise NetError(f"строка {el.line}: элемент {el.kind} не даёт значения")

    def flow(self, el: Element) -> A.Expr:
        """Входной поток элемента: OR по проводам."""
        conns = el.conns
        if not conns:
            return lit_false()
        return or_(*[self.value(c, el.line) for c in conns])

    def contact_term(self, el: Element) -> A.Expr:
        v = self.var_expr(el.var, el.line)
        if el.edge in ("rising", "falling"):
            tmp = self.edge_tmp.get(el.id)
            if tmp is None:
                raise NetError(f"строка {el.line}: фронт без подготовки")
            term: A.Expr = A.Name(tmp)
        else:
            term = v
        return not_(term) if el.negated else term

    def prepare_edges(self, net: Network) -> list[A.Stmt]:
        """Фронтовые контакты сети: `e := x AND NOT m; m := x` (P) или `e := NOT x AND m; m := x` (N)."""
        pre: list[A.Stmt] = []
        for el in net.elements:
            if el.kind != "contact" or el.edge not in ("rising", "falling"):
                continue
            v = self.var_expr(el.var, el.line)
            stem = (el.var or "x").replace(".", "_")
            mem = self.meta.edge_bits.get(el.id)
            if mem is None:
                mem = self.names.fresh(f"{stem}_{'P' if el.edge == 'rising' else 'N'}")
                self.meta.edge_bits[el.id] = mem
                self.statics.append(A.VarDecl(mem, A.NamedType("BOOL")))
                self.add(
                    "C2S7-GFX-EDGE", f"{'P' if el.edge == 'rising' else 'N'}-контакт {el.var} → бит {mem}", el.line
                )
            tmp = self.names.fresh(f"{stem}_e")
            self.temps.append(A.VarDecl(tmp, A.NamedType("BOOL")))
            self.edge_tmp[el.id] = tmp
            if el.edge == "rising":
                val = and_(v, not_(A.Name(mem)))
            else:
                val = and_(not_(v), A.Name(mem))
            pre.append(A.Assign(A.Name(tmp), val))
            pre.append(A.Assign(A.Name(mem), v))
        return pre

    def pin_value(self, el: Element, pin_index: int) -> A.Expr:
        pin = el.inputs[pin_index]
        if not pin.conns:
            raise NetError(f"строка {el.line}: вход {pin.name} блока {el.type_name} не подключён")
        v = (
            or_(*[self.value(c, el.line) for c in pin.conns])
            if len(pin.conns) > 1
            else self.value(pin.conns[0], el.line)
        )
        return not_(v) if pin.negated else v

    def block_kind(self, el: Element) -> str:
        t = (el.type_name or "").upper()
        if el.call_type == "functionblock" or (el.instance and el.call_type != "function"):
            return "fb"
        if el.call_type == "function":
            return "function"
        if t in LOGIC or t in ARITH or t in CMP or t in ("NOT", "MOVE"):
            return "operator"
        return "function"

    def block_expr(self, el: Element) -> A.Expr:
        """Выражение оператора/функции по входам."""
        t = (el.type_name or "").upper()
        ins = [self.pin_value(el, i) for i in range(len(el.inputs)) if el.inputs[i].name.upper() != "EN"]
        if t in LOGIC:
            if t == "AND":
                return and_(*ins)
            if t == "OR":
                return or_(*ins)
            e = ins[0]
            for x in ins[1:]:
                e = A.Binary("XOR", e, x)
            return e
        if t == "NOT":
            return not_(ins[0])
        if t == "MOVE":
            return ins[0]
        if t in ARITH:
            e = ins[0]
            for x in ins[1:]:
                e = A.Binary(ARITH[t], e, x)
            return e
        if t in CMP:
            return A.Binary(CMP[t], ins[0], ins[1])
        names = [p.name for p in el.inputs if p.name.upper() != "EN"]
        positional = (
            all(n.upper().startswith("IN") and n[2:].isdigit() for n in names) or self.block_kind(el) != "function"
        )
        if positional or el.call_type == "operator":
            return A.Call(A.Name(el.type_name or ""), [A.Arg(x) for x in ins])
        return A.Call(A.Name(el.type_name or ""), [A.Arg(x, name=n) for x, n in zip(ins, names, strict=True)])

    def ensure_call(self, el: Element) -> None:
        if el.id in self.called:
            return
        self.called.add(el.id)
        inst = el.instance or ""
        args: list[A.Arg] = []
        en: A.Expr | None = None
        for i, pin in enumerate(el.inputs):
            if not pin.conns:
                continue
            v = self.pin_value(el, i)
            if pin.name.upper() == "EN":
                en = v
                continue
            args.append(A.Arg(v, name=pin.name))
        call: A.Stmt = A.CallStmt(A.Call(self.var_expr(inst, el.line), args))
        if en is not None:
            self.add("C2S7-GFX-ENO", f"EN у {el.type_name} {inst}", el.line)
            call = A.If([(en, [call])])
        self.out.append(call)

    def block_out(self, el: Element, formal: str | None) -> A.Expr:
        kind = self.block_kind(el)
        if kind == "fb":
            self.ensure_call(el)
            pin = formal or (el.outputs[0] if el.outputs else "Q")
            if pin.upper() == "ENO":
                self.add("C2S7-GFX-ENO", f"ENO у {el.type_name} {el.instance}", el.line)
                return lit_true()
            return A.Member(self.var_expr(el.instance, el.line), pin)
        if formal and formal.upper() == "ENO":
            self.add("C2S7-GFX-ENO", f"ENO у {el.type_name}", el.line)
            return lit_true()
        return self.block_expr(el)

    # ------------------------------------------------------------------ LD / FBD
    def network(self, net: Network) -> list[A.Stmt]:
        self.els = net.by_id()
        self.out = []
        self.called = set()
        self.edge_tmp = {}
        stmts: list[A.Stmt] = []
        if net.label:
            stmts.append(A.Label(net.label))
        lead = [f" {net.title}"] if net.title else []
        self.out.extend(self.prepare_edges(net))
        consumed = {c.ref for e in net.elements for p in e.inputs for c in p.conns}
        coil_vars: dict[str, int] = {}
        for el in net.elements:
            if el.kind == "coil":
                target = self.var_expr(el.var, el.line)
                f = self.flow(el)
                key = (el.var or "").upper()
                coil_vars[key] = coil_vars.get(key, 0) + 1
                if el.storage == "set":
                    self.out.append(A.If([(f, [A.Assign(target, lit_true())])]))
                elif el.storage == "reset":
                    self.out.append(A.If([(f, [A.Assign(target, lit_false())])]))
                else:
                    self.out.append(A.Assign(target, not_(f) if el.negated else f))
            elif el.kind == "out_var":
                v = self.value(el.conns[0], el.line) if el.conns else lit_false()
                self.out.append(A.Assign(self.var_expr(el.var, el.line), not_(v) if el.negated else v))
            elif el.kind == "jump":
                f = self.flow(el)
                self.out.append(A.Jump(el.label or "", None if f == lit_true() else f))
            elif el.kind == "return":
                f = self.flow(el)
                self.out.append(A.Return() if f == lit_true() else A.If([(f, [A.Return()])]))
            elif el.kind == "block" and self.block_kind(el) == "fb" and el.id not in consumed:
                self.ensure_call(el)
        sinks = [e for e in net.elements if e.kind in ("coil", "out_var", "jump", "return")]
        calls = sum(1 for e in net.elements if e.kind == "block" and self.block_kind(e) == "fb")
        if len(sinks) + calls > 1 and self.body.language == "FBD":
            self.add("C2S7-GFX-ORDER", f"сеть {net.index}: {len(sinks)} выход(ов), {calls} вызов(ов)")
        if self.out:
            self.out[0].lead = lead + list(self.out[0].lead)
        stmts.extend(self.out)
        return stmts

    def double_coils(self) -> None:
        """Одна переменная — несколько обычных катушек/выходов: побеждает последняя (C2S7-GFX-DOUBLECOIL)."""
        writes: dict[str, list[int]] = {}
        for net in self.body.networks:
            for el in net.elements:
                if (el.kind == "coil" and el.storage == "none") or el.kind == "out_var":
                    writes.setdefault((el.var or "").upper(), []).append(net.index)
        for var, nets in sorted(writes.items()):
            if len(nets) > 1:
                self.add("C2S7-GFX-DOUBLECOIL", f"{var}: катушки в сетях {', '.join(map(str, nets))}")

    # ------------------------------------------------------------------ CFC
    def cfc(self, net: Network) -> list[A.Stmt]:
        self.els = net.by_id()
        self.out = []
        self.called = set()
        ordered = sorted((e for e in net.elements if e.order is not None), key=lambda e: e.order or 0)
        unordered_blocks = [e for e in net.elements if e.kind == "block" and e.order is None]
        if unordered_blocks:
            raise NetError(f"блок {unordered_blocks[0].type_name} без executionOrderId")
        order_of = {e.id: e.order or 0 for e in ordered}
        # потребители выходов: по коннекторам до блока-источника
        consumers: dict[str, list[int]] = {}
        for e in ordered:
            for p in e.inputs:
                for c in p.conns:
                    src = self._source(c)
                    if src is not None:
                        consumers.setdefault(src, []).append(order_of[e.id])
        values: dict[str, str] = {}
        feedback: set[str] = set()
        for el in ordered:
            if el.kind == "block" and self.block_kind(el) != "fb":
                values[el.id] = self.names.fresh(f"{(el.type_name or 'v').lower()}_{el.order}")
                if any(o <= order_of[el.id] for o in consumers.get(el.id, [])):
                    feedback.add(el.id)
        self.cfc_values = values
        for el in ordered:
            if el.kind == "block":
                if self.block_kind(el) == "fb":
                    self.ensure_call(el)
                    continue
                expr = self.block_expr(el)
                vname = values[el.id]
                typ = self.infer(expr) or A.NamedType("REAL")
                self.types[vname.upper()] = typ
                is_fb = el.id in feedback
                (self.statics if is_fb else self.temps).append(A.VarDecl(vname, typ))
                if is_fb:
                    self.meta.feedback.append(vname)
                    self.add(
                        "C2S7-GFX-CFCFB",
                        f"выход {el.type_name} (шаг {el.order}) читается раньше — статика {vname}",
                        el.line,
                    )
                self.out.append(A.Assign(A.Name(vname), expr))
            elif el.kind == "out_var":
                v = self.value(el.conns[0], el.line) if el.conns else lit_false()
                self.out.append(A.Assign(self.var_expr(el.var, el.line), not_(v) if el.negated else v))
            elif el.kind == "jump":
                v = self.value(el.conns[0], el.line) if el.conns else lit_true()
                self.out.append(A.Jump(el.label or "", v))
            elif el.kind == "return":
                v = self.value(el.conns[0], el.line) if el.conns else lit_true()
                self.out.append(A.If([(v, [A.Return()])]))
        self.cfc_values = None
        labels = [e for e in net.elements if e.kind == "label"]
        if labels:
            self.add("C2S7-GFX-GOTO", "метки CFC: порядок меток не задан executionOrderId")
        return list(self.out)

    def _source(self, c: Conn) -> str | None:
        el = self.els.get(c.ref)
        seen = 0
        while el is not None and el.kind in ("connector", "continuation") and seen < 64:
            seen += 1
            if el.kind == "continuation":
                el = next((x for x in self.els.values() if x.kind == "connector" and x.var == el.var and x.var), None)
                continue
            if not el.conns:
                return None
            el = self.els.get(el.conns[0].ref)
        if el is not None and el.kind == "block":
            return el.id
        return None

    def cfc_value(self, conn: Conn, line: int | None) -> A.Expr:
        values = self.cfc_values or {}
        src = self._source(conn)
        if src is not None and src in values:
            return A.Name(values[src])
        if src is not None:
            el = self.els[src]
            if self.block_kind(el) == "fb":
                # формальный параметр — у последнего провода цепочки коннекторов
                formal = self._formal(conn)
                pin = formal or (el.outputs[0] if el.outputs else "Q")
                return A.Member(self.var_expr(el.instance, el.line), pin)
            raise NetError(f"строка {line}: выход {el.type_name} без порядка")
        raise NetError(f"строка {line}: провод CFC без источника")

    def _formal(self, c: Conn) -> str | None:
        el = self.els.get(c.ref)
        cur = c
        while el is not None and el.kind == "connector" and el.conns:
            cur = el.conns[0]
            el = self.els.get(cur.ref)
        return cur.formal or None

    # ------------------------------------------------------------------ типы
    def infer(self, e: A.Expr) -> A.TypeRef | None:
        if isinstance(e, A.Name):
            return self.types.get(e.id.upper())
        if isinstance(e, A.Literal):
            return {
                "int": A.NamedType(e.type_name or "INT"),
                "real": A.NamedType(e.type_name or "REAL"),
                "bool": A.NamedType("BOOL"),
                "time": A.NamedType("TIME"),
            }.get(e.kind)
        if isinstance(e, A.Member) and isinstance(e.base, A.Name):
            t = T.type_name(self.types.get(e.base.id.upper()))
            if t and t.upper() in STD_FB_OUT:
                ty = STD_FB_OUT[t.upper()].get(e.name.upper())
                return A.NamedType(ty) if ty else None
            if t and self.conv is not None:
                fb = self.conv.p.pou(t)
                if fb is not None:
                    for _, d in fb.decls():
                        if d.name.upper() == e.name.upper():
                            return d.type
            return None
        if isinstance(e, A.Binary):
            if e.op in ("=", "<>", "<", ">", "<=", ">="):
                return A.NamedType("BOOL")
            return self.infer(e.left) or self.infer(e.right)
        if isinstance(e, A.Unary):
            return self.infer(e.operand)
        if isinstance(e, A.Call) and isinstance(e.func, A.Name):
            up = e.func.id.upper()
            if "_TO_" in up:
                return A.NamedType(up.split("_TO_")[1])
            args = [a.value for a in e.args if a.value is not None]
            if up in ("LIMIT", "SEL", "MUX") and len(args) >= 2:
                return self.infer(args[1])
            if args and up in ("MIN", "MAX", "ABS", "SQRT", "EXPT", "LN", "EXP", "MOVE"):
                return self.infer(args[0])
            if self.conv is not None:
                fn = self.conv.p.pou(e.func.id)
                if fn is not None:
                    return fn.return_type
        return None


def net_to_st(pou: Pou, conv: Converter | None = None) -> list[A.Stmt]:
    low = NetLowering(pou, conv)
    try:
        stmts = low.lower()
    except NetError as exc:
        if conv is None:
            raise
        conv.add("C2S7-LIB", pou.impl_origin or pou.origin, f"сеть не разобрана: {exc}")
        return [A.Verbatim(f"// {pou.language} не переведено (C2S7-LIB): {exc}")]
    if pou.net is not None:
        pou.net.meta = low.meta
    return stmts
