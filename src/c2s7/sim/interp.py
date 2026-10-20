"""c2s7.sim — исполнитель ST AST с семантикой CODESYS 3.5 (оракул CI, ADR-7).

Подмножество (docs/ORACLES.md): элементарные типы с переносом по разрядности, REAL — float32, TIME —
32 бита без знака; структуры, массивы, экземпляры ФБ; IF/CASE/FOR/WHILE/REPEAT/EXIT/CONTINUE/RETURN;
вызовы функций и ФБ (формальные и позиционные параметры, выходы =>), действия, программы, GVL;
стандартные блоки TON/TOF/TP, R_TRIG/F_TRIG, SR/RS, CTU/CTD/CTUD и функции (sim/stdlib.py). Время —
моделируемое (Clock): таймеры и TIME() читают одни часы. Вне подмножества — SimError с причиной.
"""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass, field
from typing import Any

from c2s7.model import Pou, Project
from c2s7.sim import stdlib as SL
from c2s7.sim import values as V
from c2s7.st import nodes as A
from c2s7.st import types as T

OUT_OF_SUBSET = "вне подмножества"


class SimError(RuntimeError):
    """Конструкция вне подмножества c2s7.sim или ошибка исполнения."""


@dataclass
class Clock:
    now_ms: int = 0


class _Exit(Exception):
    pass


class _Continue(Exception):
    pass


class _Return(Exception):
    pass


@dataclass
class Instance:
    """Экземпляр ФБ/программы или кадр функции: переменные (ключ — имя в верхнем регистре) и типы."""

    type_name: str
    vars: dict[str, Any] = field(default_factory=dict)
    types: dict[str, A.TypeRef | None] = field(default_factory=dict)
    pou: Pou | None = None
    builtin: SL.Builtin | None = None

    def get(self, name: str) -> Any:
        if self.builtin is not None:
            return self.builtin.get(name)
        return self.vars[name.upper()]

    def set(self, name: str, value: Any) -> None:
        if self.builtin is not None:
            self.builtin.set(name, value)
            return
        up = name.upper()
        self.vars[up] = V.coerce(value, T.type_name(self.types.get(up)))

    def has(self, name: str) -> bool:
        if self.builtin is not None:
            return self.builtin.has(name)
        return name.upper() in self.vars


class Struct(dict[str, Any]):
    """Значение структуры: ключи — имена членов в верхнем регистре."""

    types: dict[str, A.TypeRef | None]

    def __init__(self) -> None:
        super().__init__()
        self.types = {}


class Sim:
    def __init__(self, project: Project, clock: Clock | None = None) -> None:
        self.p = project
        self.clock = clock or Clock()
        self.pous = {p.name.upper(): p for p in project.pous}
        self.duts = {d.name.upper(): d for d in project.duts}
        self.enums: dict[str, dict[str, int]] = {}
        for dut in project.duts:
            if isinstance(dut.decl.type, A.EnumType):
                vals: dict[str, int] = {}
                nxt = 0
                for n, e in dut.decl.type.values:
                    if e is not None:
                        nxt = int(self.const(e))
                    vals[n.upper()] = nxt
                    nxt += 1
                self.enums[dut.name.upper()] = vals
        self.gvls: dict[str, Instance] = {}
        self.unqualified: dict[str, Instance] = {}
        for g in project.gvls:
            inst = Instance(g.name)
            for _, d in g.decls():
                inst.types[d.name.upper()] = d.type
                inst.vars[d.name.upper()] = self.init_value(d.type, d.init)
            self.gvls[g.name.upper()] = inst
            if not g.qualified_only:
                for _, d in g.decls():
                    self.unqualified[d.name.upper()] = inst
        self.programs: dict[str, Instance] = {}

    # ------------------------------------------------------------ значения
    def const(self, e: A.Expr) -> Any:
        v, _ = self.eval(e, Instance("__const__"))
        return v

    def init_value(self, tr: A.TypeRef | None, init: A.Expr | None = None) -> Any:
        if tr is None:
            return None
        if isinstance(tr, A.ArrayType):
            dims = []
            for d in tr.dims:
                if d is None:
                    raise SimError("ARRAY[*] вне подмножества")
                dims.append((int(self.const(d[0])), int(self.const(d[1]))))
            arr = self._array(dims, tr.elem)
            if isinstance(init, A.ArrayInit):
                flat: list[A.Expr | None] = []
                for ie in init.elems:
                    for _ in range(ie.repeat or 1):
                        flat.append(ie.value)
                self._fill_array(arr, flat, tr.elem)
            return arr
        if isinstance(tr, A.StringType):
            return self.const(init) if init is not None else ""
        if isinstance(tr, A.SubrangeType):
            return V.coerce(self.const(init), tr.base) if init is not None else int(self.const(tr.lo))
        if isinstance(tr, A.NamedType):
            name = T.type_name(tr) or tr.name
            up = name.upper()
            el = T.elem(up)
            if el is not None:
                return V.coerce(self.const(init), up) if init is not None else V.default(up)
            if up in self.enums:
                if init is not None:
                    return self.const(init)
                return next(iter(self.enums[up].values()), 0)
            if up in SL.BUILTINS:
                b = Instance(up, builtin=SL.BUILTINS[up](self.clock))
                if isinstance(init, A.StructInit):
                    for n, v in init.fields:
                        b.set(n, self.const(v))
                return b
            dut = self.duts.get(up)
            if dut is not None:
                t = dut.decl.type
                if isinstance(t, A.StructType):
                    s = Struct()
                    for m in t.members:
                        s.types[m.name.upper()] = m.type
                        s[m.name.upper()] = self.init_value(m.type, m.init)
                    if isinstance(init, A.StructInit):
                        for n, v in init.fields:
                            s[n.upper()] = self._init_field(s.types.get(n.upper()), v)
                    return s
                if isinstance(t, A.EnumType):
                    return self.const(init) if init is not None else 0
                return self.init_value(t, init or dut.decl.init)
            pou = self.pous.get(up)
            if pou is not None and pou.kind in ("FUNCTION_BLOCK", "PROGRAM"):
                inst = self.new_instance(pou)
                if isinstance(init, A.StructInit):
                    for n, v in init.fields:
                        inst.set(n, self._init_field(inst.types.get(n.upper()), v))
                return inst
            raise SimError(f"тип {name} вне подмножества c2s7.sim")
        raise SimError(f"тип {type(tr).__name__} вне подмножества")

    def _init_field(self, tr: A.TypeRef | None, v: A.Expr) -> Any:
        if isinstance(v, A.StructInit | A.ArrayInit):
            return self.init_value(tr, v)
        return V.coerce(self.const(v), T.type_name(tr))

    def _array(self, dims: list[tuple[int, int]], elem: A.TypeRef) -> Any:
        lo, hi = dims[0]
        if len(dims) == 1:
            en = T.type_name(elem)
            elem_name = en if en and T.elem(en) is not None else None
            return SL.Arr(lo, [self.init_value(elem) for _ in range(hi - lo + 1)], elem_name)
        return SL.Arr(lo, [self._array(dims[1:], elem) for _ in range(hi - lo + 1)])

    def _fill_array(self, arr: SL.Arr, flat: list[A.Expr | None], elem: A.TypeRef) -> None:
        for i, e in enumerate(flat):
            if i >= len(arr.items) or e is None:
                continue
            arr.items[i] = self._init_field(elem, e)

    def new_instance(self, pou: Pou) -> Instance:
        inst = Instance(pou.name, pou=pou)
        for _, d in pou.decls():
            inst.types[d.name.upper()] = d.type
            inst.vars[d.name.upper()] = self.init_value(d.type, d.init)
        return inst

    def program(self, name: str) -> Instance:
        up = name.upper()
        if up not in self.programs:
            self.programs[up] = self.new_instance(self.pous[up])
        return self.programs[up]

    # ------------------------------------------------------------ вызовы
    def call_fb(self, inst: Instance, args: dict[str, Any] | None = None) -> None:
        for n, v in (args or {}).items():
            inst.set(n, v)
        if inst.builtin is not None:
            inst.builtin.run()
            return
        pou = inst.pou
        assert pou is not None
        for _, d in pou.decls():
            if self._is_temp(pou, d):
                inst.vars[d.name.upper()] = self.init_value(d.type, d.init)
        with contextlib.suppress(_Return):
            self.exec_stmts(pou.body, inst)

    @staticmethod
    def _is_temp(pou: Pou, d: A.VarDecl) -> bool:
        for b, dd in pou.decls():
            if dd is d:
                return b.kind == "VAR_TEMP"
        return False

    def call_function(self, pou: Pou, args: list[A.Arg], frame: Instance) -> tuple[Any, str | None]:
        f = Instance(pou.name, pou=pou)
        for _, d in pou.decls():
            f.types[d.name.upper()] = d.type
            f.vars[d.name.upper()] = self.init_value(d.type, d.init)
        rt = pou.return_type
        f.types[pou.name.upper()] = rt
        f.vars[pou.name.upper()] = self.init_value(rt) if rt is not None else None
        inputs = [d.name for b, d in pou.decls() if b.kind in ("VAR_INPUT", "VAR_IN_OUT")]
        outs: list[tuple[str, A.Expr | None, bool]] = []
        for i, a in enumerate(args):
            if a.output:
                outs.append((a.name or "", a.value, a.negated))
                continue
            name = a.name or (inputs[i] if i < len(inputs) else None)
            if name is None or a.value is None:
                continue
            v, _ = self.eval(a.value, frame)
            f.set(name, v)
        with contextlib.suppress(_Return):
            self.exec_stmts(pou.body, f)
        for name, target, neg in outs:
            if target is not None:
                val = f.get(name)
                self.assign(target, (not val) if neg else val, frame)
        return f.vars[pou.name.upper()], T.type_name(rt)

    # ------------------------------------------------------------ операторы
    def exec_stmts(self, stmts: list[A.Stmt], frame: Instance) -> None:
        for s in stmts:
            self.exec(s, frame)

    def exec(self, s: A.Stmt, frame: Instance) -> None:
        if isinstance(s, A.Assign):
            v, _ = self.eval(s.value, frame)
            if s.op == ":=":
                self.assign(s.target, v, frame)
            elif s.op == "S=":
                if v:
                    self.assign(s.target, True, frame)
            elif s.op == "R=":
                if v:
                    self.assign(s.target, False, frame)
            else:
                raise SimError(f"присваивание {s.op} вне подмножества")
        elif isinstance(s, A.CallStmt):
            self.call_stmt(s.call, frame)
        elif isinstance(s, A.If):
            for cond, body in s.branches:
                if self.eval(cond, frame)[0]:
                    self.exec_stmts(body, frame)
                    return
            if s.else_body is not None:
                self.exec_stmts(s.else_body, frame)
        elif isinstance(s, A.Case):
            sel = self.eval(s.selector, frame)[0]
            for br in s.branches:
                for lb in br.labels:
                    lo = self.eval(lb.lo, frame)[0]
                    hit = sel == lo if lb.hi is None else lo <= sel <= self.eval(lb.hi, frame)[0]
                    if hit:
                        self.exec_stmts(br.body, frame)
                        return
            if s.else_body is not None:
                self.exec_stmts(s.else_body, frame)
        elif isinstance(s, A.For):
            start = self.eval(s.start, frame)[0]
            stop = self.eval(s.stop, frame)[0]
            step = self.eval(s.step, frame)[0] if s.step is not None else 1
            var = A.Name(s.var)
            self.assign(var, start, frame)
            guard = 0
            while (step > 0 and self.eval(var, frame)[0] <= stop) or (step < 0 and self.eval(var, frame)[0] >= stop):
                try:
                    self.exec_stmts(s.body, frame)
                except _Exit:
                    break
                except _Continue:
                    pass
                self.assign(var, self.eval(var, frame)[0] + step, frame)
                guard += 1
                if guard > 1_000_000:
                    raise SimError("FOR: больше 10^6 итераций")
        elif isinstance(s, A.While):
            guard = 0
            while self.eval(s.cond, frame)[0]:
                try:
                    self.exec_stmts(s.body, frame)
                except _Exit:
                    break
                except _Continue:
                    pass
                guard += 1
                if guard > 1_000_000:
                    raise SimError("WHILE: больше 10^6 итераций")
        elif isinstance(s, A.Repeat):
            guard = 0
            while True:
                try:
                    self.exec_stmts(s.body, frame)
                except _Exit:
                    break
                except _Continue:
                    pass
                if self.eval(s.cond, frame)[0]:
                    break
                guard += 1
                if guard > 1_000_000:
                    raise SimError("REPEAT: больше 10^6 итераций")
        elif isinstance(s, A.Exit):
            raise _Exit()
        elif isinstance(s, A.Continue):
            raise _Continue()
        elif isinstance(s, A.Return):
            raise _Return()
        elif isinstance(s, A.Region):
            self.exec_stmts(s.body, frame)
        elif isinstance(s, A.Empty | A.Label):
            return
        elif isinstance(s, A.Jump):
            raise SimError("JMP вне подмножества c2s7.sim (понижение jumps.py до исполнения)")
        else:
            raise SimError(f"оператор {type(s).__name__} вне подмножества")

    def call_stmt(self, c: A.Call, frame: Instance) -> None:
        func = c.func
        if isinstance(func, A.Name):
            up = func.id.upper()
            # действие текущего POU
            if frame.pou is not None and not frame.has(up):
                act = next((a for a in frame.pou.actions if a.name.upper() == up), None)
                if act is not None:
                    self.exec_stmts(act.body, frame)
                    return
            if not frame.has(up) and up in self.pous:
                pou = self.pous[up]
                if pou.kind == "PROGRAM":
                    self._call_instance(self.program(up), c.args, frame)
                    return
                if pou.kind == "FUNCTION":
                    self.call_function(pou, c.args, frame)
                    return
        target = self.ref_value(func, frame)
        if isinstance(target, Instance):
            self._call_instance(target, c.args, frame)
            return
        if isinstance(func, A.Name) and (func.id.upper() in SL.FUNCS or "_TO_" in func.id.upper()):
            self.eval(c, frame)
            return
        raise SimError(f"вызов {func} вне подмножества")

    def _call_instance(self, inst: Instance, args: list[A.Arg], frame: Instance) -> None:
        inputs: dict[str, Any] = {}
        outs = []
        for a in args:
            if a.output:
                outs.append(a)
                continue
            if a.name is None or a.value is None:
                raise SimError("позиционный вызов ФБ вне подмножества")
            inputs[a.name] = self.eval(a.value, frame)[0]
        self.call_fb(inst, inputs)
        for a in outs:
            if a.value is not None and a.name is not None:
                val = inst.get(a.name)
                self.assign(a.value, (not val) if a.negated else val, frame)

    # ------------------------------------------------------------ обращения
    def lookup(self, name: str, frame: Instance) -> Any:
        up = name.upper()
        if frame.has(up):
            return frame.get(up)
        if up in self.unqualified:
            return self.unqualified[up].get(up)
        if up in self.gvls:
            return self.gvls[up]
        if up in self.pous and self.pous[up].kind == "PROGRAM":
            return self.program(up)
        for vals in self.enums.values():
            if up in vals:
                return vals[up]
        raise SimError(f"имя {name} не найдено")

    def ref_value(self, e: A.Expr, frame: Instance) -> Any:
        if isinstance(e, A.Name):
            return self.lookup(e.id, frame)
        if isinstance(e, A.Member):
            path = A.var_path(e)
            if path and len(path) == 2 and path[0].upper() in self.enums:
                return self.enums[path[0].upper()][path[1].upper()]
            base = self.ref_value(e.base, frame)
            return _member_get(base, e.name)
        if isinstance(e, A.Index):
            base = self.ref_value(e.base, frame)
            idx = [int(self.eval(i, frame)[0]) for i in e.indices]
            try:
                for i in idx:
                    base = base[i]
            except IndexError as exc:
                raise SimError(str(exc)) from None
            return base
        if isinstance(e, A.BitRef):
            base = self.ref_value(e.base, frame)
            return bool((int(base) >> e.bit) & 1)
        raise SimError(f"обращение {type(e).__name__} вне подмножества")

    def type_of(self, e: A.Expr, frame: Instance) -> str | None:
        if isinstance(e, A.Name):
            up = e.id.upper()
            if up in frame.types:
                return T.type_name(frame.types[up])
            if up in self.unqualified:
                return T.type_name(self.unqualified[up].types.get(up))
            return None
        if isinstance(e, A.Member):
            base = self.ref_value(e.base, frame) if not _is_enum_path(e, self.enums) else None
            if isinstance(base, Instance):
                if base.builtin is not None:
                    return base.builtin.type_of(e.name)
                return T.type_name(base.types.get(e.name.upper()))
            if isinstance(base, Struct):
                return T.type_name(base.types.get(e.name.upper()))
            return None
        if isinstance(e, A.Index):
            return None
        return None

    def assign(self, target: A.Expr, value: Any, frame: Instance) -> None:
        if isinstance(target, A.Name):
            up = target.id.upper()
            if frame.has(up):
                frame.set(up, value)
                return
            if up in self.unqualified:
                self.unqualified[up].set(up, value)
                return
            raise SimError(f"запись в неизвестное имя {target.id}")
        if isinstance(target, A.Member):
            base = self.ref_value(target.base, frame)
            if isinstance(base, Instance):
                base.set(target.name, value)
                return
            if isinstance(base, Struct):
                up = target.name.upper()
                base[up] = V.coerce(value, T.type_name(base.types.get(up)))
                return
            raise SimError(f"запись в член {target.name} вне подмножества")
        if isinstance(target, A.Index):
            arr = self.ref_value(target.base, frame)
            idx = [int(self.eval(i, frame)[0]) for i in target.indices]
            for i in idx[:-1]:
                arr = arr[i]
            arr[idx[-1]] = value
            return
        if isinstance(target, A.BitRef):
            cur = int(self.eval(target.base, frame)[0])
            new = cur | (1 << target.bit) if value else cur & ~(1 << target.bit)
            self.assign(target.base, new, frame)
            return
        raise SimError(f"запись в {type(target).__name__} вне подмножества")

    # ------------------------------------------------------------ выражения
    def eval(self, e: A.Expr, frame: Instance) -> tuple[Any, str | None]:
        if isinstance(e, A.Literal):
            return _literal(e)
        if isinstance(e, A.Name | A.Member | A.Index | A.BitRef):
            v = self.ref_value(e, frame)
            return v, self.type_of(e, frame) if not isinstance(e, A.BitRef) else "BOOL"
        if isinstance(e, A.Unary):
            v, t = self.eval(e.operand, frame)
            if e.op == "NOT":
                if isinstance(v, bool):
                    return (not v), "BOOL"
                bits = V.BITS.get((t or "").upper(), V.INT_BITS.get((t or "").upper(), (32, False))[0] if t else 32)
                return (~int(v)) & ((1 << bits) - 1), t
            if e.op == "NEG":
                return -v, t
            return v, t
        if isinstance(e, A.Binary):
            return self.binary(e, frame)
        if isinstance(e, A.Call):
            return self.call_expr(e, frame)
        raise SimError(f"выражение {type(e).__name__} вне подмножества")

    def binary(self, e: A.Binary, frame: Instance) -> tuple[Any, str | None]:
        op = e.op
        if op in ("AND_THEN", "OR_ELSE"):
            lv, _ = self.eval(e.left, frame)
            if op == "AND_THEN" and not lv:
                return False, "BOOL"
            if op == "OR_ELSE" and lv:
                return True, "BOOL"
            rv, _ = self.eval(e.right, frame)
            return bool(rv), "BOOL"
        lv, lt = self.eval(e.left, frame)
        rv, rt = self.eval(e.right, frame)
        rtype = V.result_type(lt, rt)
        if (rtype or "").upper() == "LTIME":  # TIME (мс) неявно расширяется до LTIME (нс)
            if (lt or "").upper() == "TIME":
                lv = int(lv) * 1_000_000
            if (rt or "").upper() == "TIME":
                rv = int(rv) * 1_000_000
        if op in ("AND", "OR", "XOR"):
            if isinstance(lv, bool) and isinstance(rv, bool):
                return {"AND": lv and rv, "OR": lv or rv, "XOR": lv != rv}[op], "BOOL"
            a, b = int(lv), int(rv)
            return {"AND": a & b, "OR": a | b, "XOR": a ^ b}[op], rtype
        if op in ("=", "<>", "<", ">", "<=", ">="):
            res = {"=": lv == rv, "<>": lv != rv, "<": lv < rv, ">": lv > rv, "<=": lv <= rv, ">=": lv >= rv}[op]
            return res, "BOOL"
        is_real = isinstance(lv, float) or isinstance(rv, float) or (rtype or "").upper() in ("REAL", "LREAL")
        if op == "+":
            r = lv + rv
        elif op == "-":
            r = lv - rv
        elif op == "*":
            r = lv * rv
        elif op == "/":
            if is_real:
                r = lv / rv if rv != 0 else (math.copysign(math.inf, lv) if lv else math.nan)
            else:
                if rv == 0:
                    raise SimError("деление на 0 (в CODESYS — исключение)")
                r = int(lv / rv)
        elif op == "MOD":
            if rv == 0:
                raise SimError("MOD 0")
            r = int(math.fmod(lv, rv)) if not is_real else math.fmod(lv, rv)
        elif op == "**":
            r = float(lv) ** float(rv)
            rtype = "LREAL" if (rtype or "").upper() == "LREAL" else "REAL"
            is_real = True
        else:
            raise SimError(f"оператор {op}")
        if is_real and (rtype or "").upper() != "LREAL":
            r = V.f32(float(r))
        return r, rtype

    def call_expr(self, c: A.Call, frame: Instance) -> tuple[Any, str | None]:
        func = c.func
        if not isinstance(func, A.Name):
            raise SimError("вызов метода вне подмножества")
        up = func.id.upper()
        pou = self.pous.get(up)
        if pou is not None and pou.kind == "FUNCTION":
            return self.call_function(pou, c.args, frame)
        args = [(a.name, self.eval(a.value, frame)) for a in c.args if a.value is not None and not a.output]
        if up == "TIME" and not args:
            return V.coerce(self.clock.now_ms, "TIME"), "TIME"
        try:
            return SL.call_function(up, args)
        except KeyError as exc:
            raise SimError(str(exc)) from None


def _is_enum_path(e: A.Member, enums: dict[str, dict[str, int]]) -> bool:
    path = A.var_path(e)
    return bool(path and len(path) == 2 and path[0].upper() in enums)


def _member_get(base: Any, name: str) -> Any:
    if isinstance(base, Instance):
        return base.get(name)
    if isinstance(base, Struct):
        return base[name.upper()]
    raise SimError(f"член {name} у значения {type(base).__name__}")


def _literal(e: A.Literal) -> tuple[Any, str | None]:
    k = e.kind
    if k == "bool":
        return bool(e.value), "BOOL"
    if k == "int":
        return int(e.value), e.type_name
    if k == "real":
        return float(e.value), e.type_name
    if k in ("time", "s5time"):
        return int(e.value), "TIME"
    if k == "ltime":
        return int(e.value), "LTIME"
    if k in ("string", "wstring"):
        return str(e.value), "STRING"
    if k in ("date", "tod", "dt"):
        return int(e.value), e.type_name
    raise SimError(f"литерал {e.text}")
