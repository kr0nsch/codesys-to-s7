"""Конвертер: модель проекта CODESYS → блоки S7 (внешние исходники), теги, план OB, находки.

Порядок: символы → DUT → GVL → POU → задачи. Тела POU — ST AST (у графики — после понижения),
имена разрешаются в SclRef (#локальная, "DB".член, "тег"), вызовы стандартных блоков и функций
приводятся к формам S7 (stdlib.py), правила C2S7-* ставят находки на конструкции.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path

from c2s7.convert import addr as AD
from c2s7.convert import ring as RG
from c2s7.convert import stdlib as SL
from c2s7.ingest.common import read_text
from c2s7.model import Dut, Gvl, IoChannel, Origin, Pou, Project
from c2s7.profiles import Profile
from c2s7.rules import Collector, Construct
from c2s7.s7 import ObPlan, S7Block, S7Member, S7Section, Tag
from c2s7.st import literals as L
from c2s7.st import nodes as A
from c2s7.st import types as T
from c2s7.st.parser import parse_expr

SECTION_MAP = {
    "VAR_INPUT": "VAR_INPUT",
    "VAR_OUTPUT": "VAR_OUTPUT",
    "VAR_IN_OUT": "VAR_IN_OUT",
    "VAR": "VAR",
    "VAR_TEMP": "VAR_TEMP",
    "VAR_INST": "VAR",
}


@dataclass
class Options:
    cpu: str = "s7-1500"
    tia: str = "V21"
    graphics: str | None = None  # scl | simaticml | sd (по умолчанию simaticml при V19/V21)
    sfc: str = "scl"
    cfc: str = "scl"
    timers: str = "native"
    edges: str = "native"
    markers: str = "db"
    bit_addressing: str = "byte"
    range_check: bool = False
    max_ob_priority: int = 15
    ob_from_tasks: bool = False
    ring: bool | None = None
    io_map: list[IoChannel] | None = None
    source_date: str = "2026-10-19"


@dataclass
class Result:
    project: Project
    profile: Profile
    options: Options
    blocks: list[S7Block] = field(default_factory=list)
    tags: list[Tag] = field(default_factory=list)
    constants: list[Tag] = field(default_factory=list)
    obs: list[ObPlan] = field(default_factory=list)
    compat: list[str] = field(default_factory=list)
    collector: Collector = field(default_factory=Collector)
    trace: list[dict[str, object]] = field(default_factory=list)
    manual_steps: list[dict[str, object]] = field(default_factory=list)
    ring: bool = False
    simaticml: dict[str, str] = field(default_factory=dict)
    lowered: dict[str, list[A.Stmt]] = field(default_factory=dict)
    symbols: dict[str, GSym] = field(default_factory=dict)


@dataclass
class GSym:
    """Глобальный символ CODESYS и его место в S7."""

    kind: str  # gvar | tag | const | dbinst | program | fb | function | struct | enum | alias | union | subrange
    name: str
    db: str | None = None  # DB S7 (gvar, dbinst, program)
    s7name: str | None = None  # имя тега/константы/DB
    type: A.TypeRef | None = None
    decl: A.VarDecl | None = None
    gvl: str | None = None
    dut: Dut | None = None
    pou: Pou | None = None


@dataclass
class LSym:
    name: str
    section: str
    decl: A.VarDecl
    type: A.TypeRef
    constant: bool = False
    tag: str | None = None  # AT в переменной POU → глобальный тег (у FB/FC S7 адресов у членов нет)


def _upper(s: str) -> str:
    return s.upper()


def _lit_int(v: int, type_name: str | None = None) -> A.Literal:
    return A.Literal("int", str(v), v, type_name)


class Converter:
    def __init__(self, project: Project, profile: Profile, options: Options) -> None:
        self.p = project
        self.prof = profile
        self.opt = options
        self.c = Collector()
        self.blocks: list[S7Block] = []
        self.tags: dict[str, Tag] = {}
        self.constants: dict[str, Tag] = {}
        self.compat: set[str] = set()
        self.g: dict[str, GSym] = {}
        self.trace: list[dict[str, object]] = []
        self.manual: list[dict[str, object]] = []
        self.ring = RG.is_s7conv_project(project) if options.ring is None else options.ring
        self.enums: dict[str, dict[str, int]] = {}
        self.enum_base: dict[str, str] = {}
        self.inline_structs: dict[str, tuple[str, str]] = {}  # DUT → (блок, поле)
        self.obs: list[ObPlan] = []
        self.lowered: dict[str, list[A.Stmt]] = {}
        # текущий POU
        self.pou: Pou | None = None
        self.lang = "ST"
        self.loc: dict[str, LSym] = {}
        self.origin = Origin("")
        self.timer_rewrite: dict[str, dict[str, str]] = {}
        self.extra_static: list[S7Member] = []
        self.todo_blocks: list[RG.TodoBlock] = []
        self.todo_drop: set[str] = set()
        self.actions: dict[str, list[A.Stmt]] = {}
        self.gvl_members: dict[str, dict[str, GSym]] = {}
        self.m_overlap: set[str] = set()
        self.stat_db: str | None = None
        self.renames: dict[str, str] = {}
        self.s5_decl_lines: set[int] = set()
        self.s5_stmt_lines: set[int] = set()
        self.s5tim_lines: set[int] = set()
        self.slice_lines: set[int] = set()
        self.decl_todos: list[RG.TodoBlock] = []
        self.counter_int: set[str] = set()
        self.block_non_optimized = False

    # ================================================================= запуск
    def run(self) -> Result:
        if self.ring:
            self.opt.markers = "keep"
            if any(t.sources for t in self.p.tasks):
                self.opt.ob_from_tasks = True
        self._lower_graphics()
        self._symbols()
        for d in sorted(self.p.duts, key=lambda x: x.name.lower()):
            self._dut(d)
        for gvl in self.p.gvls:
            self._gvl(gvl)
        for pou in self.p.pous:
            if self.ring and pou.name.upper() in SL.S7COMPAT_OBJECTS:
                continue
            self._pou(pou)
        self._tasks()
        if self.opt.io_map is None and self.p.kind == "plcopen-xml" and not self.ring:
            self.c.add("C2S7-IO-NOMAP", "", "PROJECT", Origin(self.p.path), detail="--io-map не задан")
        self._compat_blocks()
        res = Result(
            project=self.p,
            profile=self.prof,
            options=self.opt,
            blocks=self._ordered_blocks(),
            tags=sorted(self.tags.values(), key=lambda t: (t.table.lower(), t.name.lower())),
            constants=sorted(self.constants.values(), key=lambda t: t.name.lower()),
            obs=self.obs,
            compat=sorted(self.compat),
            collector=self.c,
            trace=self.trace,
            manual_steps=self.manual,
            ring=self.ring,
            lowered=self.lowered,
            symbols=self.g,
        )
        return res

    def _lower_graphics(self) -> None:
        """Графические языки и IL → ST AST (c2s7.lower); тело кладётся в pou.text.body."""
        from c2s7.lower import lower_pou
        from c2s7.lower.jumps import remove_jumps

        for pou in self.p.pous:
            self.pou, self.lang = pou, pou.language
            if pou.language == "SFC" and self.opt.sfc == "graph":
                if not self.prof.language("GRAPH"):
                    self.add(
                        "C2S7-PROF-LANG",
                        pou.origin,
                        f"GRAPH для {pou.name}",
                        detail="GRAPH на этом CPU нет → автомат SCL",
                    )
                else:
                    self.add(
                        "C2S7-GFX-SFC",
                        pou.origin,
                        f"GRAPH для {pou.name}",
                        detail="GRAPH не сгенерирован (P1) → автомат SCL",
                    )
            if pou.language != "ST" or pou.actions:
                stmts = lower_pou(pou, self)
                if stmts is not None:
                    pou.text.body = stmts
                    self.lowered[pou.name] = stmts
            elif any(isinstance(s, A.Jump | A.Label) for s in pou.text.body):
                pou.text.body = remove_jumps(pou.text.body).stmts
        self.pou, self.lang = None, "ST"

    # ================================================================= символы
    def _symbols(self) -> None:
        for dut in self.p.duts:
            t = dut.decl.type
            if isinstance(t, A.StructType):
                kind = "union" if t.union else "struct"
            elif isinstance(t, A.EnumType):
                kind = "enum"
                values: dict[str, int] = {}
                nxt = 0
                for vname, vexpr in t.values:
                    if vexpr is not None:
                        v = self._const_int(vexpr)
                        nxt = v if v is not None else nxt
                    values[vname.upper()] = nxt
                    nxt += 1
                self.enums[dut.name.upper()] = values
                self.enum_base[dut.name.upper()] = t.base or "INT"
            elif isinstance(t, A.SubrangeType):
                kind = "subrange"
            else:
                kind = "alias"
            self.g[dut.name.upper()] = GSym(kind, dut.name, dut=dut, type=t)
        for pou in self.p.pous:
            kind = {"PROGRAM": "program", "FUNCTION_BLOCK": "fb", "FUNCTION": "function"}.get(pou.kind, "fb")
            if self.ring and pou.name.upper() in SL.S7COMPAT_OBJECTS:
                kind = "s7compat"
            db = f"{pou.name}_DB" if kind == "program" else None
            self.g[pou.name.upper()] = GSym(kind, pou.name, db=db, pou=pou)
        # анонимные структуры s7conv: ST_<блок>_<поле>, используемые ровно в этом поле
        if self.ring:
            self._find_inline_structs()
        # GVL: переменные, теги, константы, экземпляры ФБ
        m_addrs: list[tuple[str, AD.Addr]] = []
        for gvl in self.p.gvls:
            for _, d in gvl.decls():
                if d.address:
                    a = AD.parse(d.address)
                    if a and a.area == "M":
                        m_addrs.append((f"{gvl.name}.{d.name}", a))
        self.m_overlap = AD.overlaps(m_addrs, self.opt.bit_addressing)
        for gvl in self.p.gvls:
            gname = gvl.name
            if self.ring and gname.upper() == "GVL_S7CLOCK":
                continue
            members: dict[str, GSym] = {}
            for block, d in gvl.decls():
                sym = self._gvl_member_sym(gvl, block, d)
                members[d.name.upper()] = sym
                if not gvl.qualified_only and d.name.upper() not in self.g:
                    self.g[d.name.upper()] = sym
            self.g[gname.upper()] = GSym("gvl", gname)
            self.gvl_members[gname.upper()] = members

    def _find_inline_structs(self) -> None:
        uses: dict[str, list[tuple[str, str]]] = {}

        def note(owner: str, decls: list[A.VarDecl]) -> None:
            for d in decls:
                t = d.type.elem if isinstance(d.type, A.ArrayType) else d.type
                n = T.type_name(t)
                if n and n.upper().startswith("ST_"):
                    uses.setdefault(n.upper(), []).append((owner, d.name))

        for gvl in self.p.gvls:
            note(gvl.name, [d for _, d in gvl.decls()])
        for pou in self.p.pous:
            note(pou.name, [d for _, d in pou.decls()])
        for dut in self.p.duts:
            if isinstance(dut.decl.type, A.StructType):
                note(dut.name, dut.decl.type.members)
        for dut in self.p.duts:
            u = uses.get(dut.name.upper(), [])
            if len(u) == 1:
                owner, fld = u[0]
                owner_db = owner
                if dut.name.upper() == f"ST_{owner}_{fld}".upper():
                    self.inline_structs[dut.name.upper()] = (owner_db, fld)

    def _io_channel(self, gvl: str, name: str) -> IoChannel | None:
        """Канал из --io-map для переменной GVL (имена «Application.GVL.x», «GVL.x» или «x»)."""
        if not self.opt.io_map:
            return None
        want = {f"{gvl}.{name}".upper(), name.upper()}
        for ch in self.opt.io_map:
            parts = ch.variable.upper().split(".")
            if ".".join(parts[-2:]) in want or (len(parts) == 1 and parts[0] in want):
                return ch
        return None

    def _gvl_member_sym(self, gvl: Gvl, block: A.VarBlock, d: A.VarDecl) -> GSym:
        gname = gvl.name
        ch = self._io_channel(gname, d.name)
        if ch is not None and not d.address:
            d.address = ch.address
            d.comment = d.comment or f"--io-map: {ch.variable}"
        if block.constant:
            cname = d.name if self.ring else f"{gname}_{d.name}" if gname.upper() != "GVL_USERCONSTANTS" else d.name
            return GSym("const", d.name, s7name=cname, type=d.type, decl=d, gvl=gname)
        if d.address:
            a = AD.parse(d.address)
            keep_m = self.opt.markers == "keep" or f"{gname}.{d.name}" in self.m_overlap
            if a and (a.area in ("I", "Q") or (a.area == "M" and keep_m)):
                return GSym("tag", d.name, s7name=self._tag_name(gname, d.name), type=d.type, decl=d, gvl=gname)
            if a and a.area == "M":
                return GSym("gvar", d.name, db="DB_Markers", type=d.type, decl=d, gvl=gname)
        tname = T.type_name(d.type)
        tsym = self.g.get(tname.upper()) if tname else None
        is_fb = bool(tsym and tsym.kind in ("fb", "program")) or bool(tname and tname.upper() in SL.STD_FB)
        if self.ring and tname and tname.upper() in SL.S7COMPAT_FB:
            is_fb = True
        if gname.upper() == "GVL_INSTANCEDBS" and (is_fb or (tsym and tsym.kind == "struct")):
            return GSym("dbinst", d.name, db=d.name, type=d.type, decl=d, gvl=gname)
        if is_fb:
            return GSym("dbinst", d.name, db=f"{gname}_{d.name}", type=d.type, decl=d, gvl=gname)
        return GSym("gvar", d.name, db=gname, type=d.type, decl=d, gvl=gname)

    def _tag_name(self, gvl: str, name: str) -> str:
        clash = sum(1 for g in self.p.gvls for _, d in g.decls() if d.name.upper() == name.upper() and d.address)
        return name if clash <= 1 or self.ring else f"{gvl}_{name}"

    def _const_int(self, e: A.Expr) -> int | None:
        if isinstance(e, A.Literal) and e.kind == "int":
            return int(e.value)
        if isinstance(e, A.Unary) and e.op == "NEG":
            v = self._const_int(e.operand)
            return -v if v is not None else None
        return None

    # ================================================================= типы
    def s7_type(self, tr: A.TypeRef, where: Origin, decl: A.VarDecl | None = None) -> tuple[str, dict[str, str]]:
        """Тип CODESYS → (тип SCL, атрибуты члена)."""
        if isinstance(tr, A.StringType):
            n = self._const_int(tr.length) if tr.length is not None else None
            base = "WString" if tr.wide else "String"
            if n is None:
                if tr.wide:
                    self.add("C2S7-TYPE-WSTRING", where, "WSTRING")
                return f"{base}[80]" if tr.length is None else f"{base}[{self.expr_text(tr.length)}]", {}
            if not tr.wide and n > 254:
                self.add("C2S7-TYPE-STRLEN", where, f"STRING({n})")
            return f"{base}[{n}]", {}
        if isinstance(tr, A.ArrayType):
            dims = []
            for d in tr.dims:
                if d is None:
                    self.add("C2S7-TYPE-PTR", where, "ARRAY[*]", outcome="verify")
                    dims.append("*")
                else:
                    dims.append(f"{self.expr_text(d[0])}..{self.expr_text(d[1])}")
            elem, attrs = self.s7_type(tr.elem, where)
            return f"Array[{', '.join(dims)}] of {elem}", attrs
        if isinstance(tr, A.PointerType):
            self.add("C2S7-TYPE-PTR", where, "POINTER TO")
            return "Variant", {}
        if isinstance(tr, A.ReferenceType):
            if not self.prof.type_supported("REF_TO"):
                self.add("C2S7-PROF-REF", where, "REFERENCE TO")
            else:
                self.add("C2S7-TYPE-PTR", where, "REFERENCE TO", outcome="verify")
            inner, _ = self.s7_type(tr.elem, where)
            return f"REF_TO {inner}", {}
        if isinstance(tr, A.SubrangeType):
            self.add("C2S7-TYPE-RANGE", where, f"{tr.base}({self.expr_text(tr.lo)}..{self.expr_text(tr.hi)})")
            return self.s7_type(A.NamedType(tr.base), where)
        if isinstance(tr, A.StructType):
            return "Struct", {}
        if isinstance(tr, A.EnumType):
            self.add("C2S7-TYPE-ENUM", where, "(...)")
            return self.s7_type(A.NamedType(tr.base or "INT"), where)
        assert isinstance(tr, A.NamedType)
        name = T.type_name(tr) or tr.name
        up = name.upper()
        el = T.elem(name)
        if el is not None:
            if el.is64 and not self.prof.type_supported(el.s7):
                self.add("C2S7-TYPE-64", where, name)
            if el.cat == "dt" and not self.prof.type_supported("Date_And_Time"):
                self.add("C2S7-TYPE-DATE", where, name, outcome="verify")
            return el.s7, {}
        if self.ring and up in SL.S7COMPAT_FB:
            up = SL.S7COMPAT_FB[up]
        if up in SL.STD_FB:
            m = SL.STD_FB[up]
            if m.compat:
                self.compat.add(m.compat)
                return f'"{m.s7}"', {}
            if m.rule and decl is not None and not self.ring:
                self.add(m.rule, where, f"{decl.name} : {name}")
            return m.s7, {"InstructionName": m.instruction or m.s7, "LibVersion": "1.0"}
        if up in T.UTIL_FB:
            self.add("C2S7-STD-UTIL", where, name)
            return f'"{name}"', {}
        sym = self.g.get(up)
        if sym is not None:
            if sym.kind == "alias" and sym.type is not None:
                self.add("C2S7-TYPE-ALIAS", where, name)
                return self.s7_type(sym.type, where)
            if sym.kind == "subrange" and sym.type is not None:
                return self.s7_type(sym.type, where)
            if sym.kind == "enum":
                self.add("C2S7-TYPE-ENUM", where, name)
                return self.s7_type(A.NamedType(self.enum_base[up]), where)
            if sym.kind == "union":
                self.add("C2S7-TYPE-UNION", where, name)
                return f'"{name}"', {}
            return f'"{sym.name}"', {}
        if "." in name:
            ns = name.split(".")[0].upper()
            if ns in SL.LIB_NAMESPACES:
                self.add("C2S7-LIB", where, name)
        return f'"{name}"', {}

    # ================================================================= находки
    def add(
        self,
        rule: str,
        where: Origin,
        fragment: str = "",
        detail: str = "",
        outcome: str | None = None,
        construct: Construct | None = None,
        language: str | None = None,
    ) -> None:
        pou = self.pou.name if self.pou else ""
        self.c.add(rule, pou, language or self.lang, where, fragment, detail, outcome, construct)

    def at(self, node: A.Node | None) -> Origin:
        if node is None or node.pos is None:
            return self.origin
        return self.origin.at(node.pos)

    def expr_text(self, e: A.Expr) -> str:
        from c2s7.emit.printer import Printer

        return Printer("st").expr(e)

    # ================================================================= DUT
    def _dut(self, d: Dut) -> None:
        self.pou = None
        self.lang = "DECL"
        self.origin = d.origin
        con = self.c.construct("dut", "DECL", d.name, d.origin)
        self.c.push(con)
        try:
            t = d.decl.type
            if isinstance(t, A.StructType) and not t.union:
                if d.name.upper() in self.inline_structs:
                    return
                members = [self._member(m) for m in t.members]
                blk = S7Block(
                    "TYPE", d.name, struct=members, origin=d.origin, source_pou=d.name, language="DECL", order=0
                )
                self._doc_to_block(blk, d.doc)
                self.blocks.append(blk)
                self._trace(d.name, blk.name, d.origin)
            elif isinstance(t, A.StructType):
                self.add("C2S7-TYPE-UNION", d.origin, f"UNION {d.name}")
                for m in t.members:
                    if isinstance(m.type, A.StringType):
                        self.add("C2S7-TYPE-STRLAYOUT", self.at(m), f"{m.name} : STRING в UNION {d.name}")
                self.manual.append(
                    {"step": f"UNION {d.name}", "do": "переписать на AT в неоптимизированном блоке", "minutes": 60}
                )
            elif isinstance(t, A.EnumType):
                self.add("C2S7-TYPE-ENUM", d.origin, f"TYPE {d.name}")
                base, _ = self.s7_type(A.NamedType(self.enum_base[d.name.upper()]), d.origin)
                for vname, v in self.enums[d.name.upper()].items():
                    orig = next(n for n, _ in t.values if n.upper() == vname)
                    cname = f"{d.name}_{orig}"
                    self.constants[cname.upper()] = Tag(
                        cname, base, "", f"{d.name}.{orig}", "User constants", str(v), d.name
                    )
            elif isinstance(t, A.SubrangeType):
                self.add("C2S7-TYPE-RANGE", d.origin, f"TYPE {d.name}")
            else:
                self.add("C2S7-TYPE-ALIAS", d.origin, f"TYPE {d.name}")
        finally:
            self.c.pop()

    def _member(self, d: A.VarDecl, section_kind: str = "") -> S7Member:
        where = self.at(d)
        con = self.c.construct("decl", "DECL", self.pou.name if self.pou else "", where)
        self.c.push(con)
        name = self.renames.get(d.name.upper(), d.name)
        try:
            arr = d.type if isinstance(d.type, A.ArrayType) else None
            tname = T.type_name(arr.elem if arr is not None else d.type)
            if tname and tname.upper() in self.inline_structs:
                dut = self.p.dut(tname)
                assert dut is not None and isinstance(dut.decl.type, A.StructType)
                head = "Struct"
                if arr is not None:
                    head = self.s7_type(A.ArrayType(arr.dims, A.StructType([])), where)[0]
                return S7Member(name, head, comment=d.comment, struct=[self._member(m) for m in dut.decl.type.members])
            self._check_name(d.name, where)
            if d.address and isinstance(d.type, A.StringType):
                self.add("C2S7-TYPE-STRLAYOUT", where, f"{d.name} AT {d.address} : STRING")
            typ, attrs = self.s7_type(d.type, where, d)
            if self.counter_int and d.name.upper() in self.counter_int:
                typ = typ.replace("_UINT", "_INT")
                attrs = {k: v.replace("_UINT", "_INT") for k, v in attrs.items()}
            begin: list[tuple[str, str]] = []
            init: str | None = None
            s5 = self.ring and d.pos is not None and d.pos[0] in self.s5_decl_lines
            if s5:
                typ = "S5Time"
            if isinstance(d.init, A.StructInit):
                # начальное значение структуры в объявлении S7 не пишется — в BEGIN блока данных
                begin = self._compound_init(d.init, d.type, "")
            elif d.init is not None:
                init = self.init_text(d.init, d.type)
                if s5 and init.upper().startswith("T#"):
                    init = "S5T#" + init[2:]
            if d.address and section_kind:
                self.add("C2S7-ADDR-MAP", where, f"{d.name} AT {d.address}")
            return S7Member(name, typ, init, d.comment, attrs, begin=begin)
        finally:
            self.c.pop()

    def _check_name(self, name: str, where: Origin) -> None:
        from c2s7.emit.printer import SCL_KEYWORDS

        if name.upper() in SCL_KEYWORDS and name.upper() not in _CDS_KEYWORDS:
            self.add("C2S7-NAME-KEYWORD", where, name)
        if len(name) > 128:
            self.add("C2S7-NAME-LEN", where, name[:40] + "…")

    def init_text(self, e: A.Expr, tr: A.TypeRef | None = None) -> str:
        from c2s7.emit.printer import Printer

        conv = self._init_expr(e)
        return Printer("scl", plain_names=True).expr(conv)

    def _init_expr(self, e: A.Expr) -> A.Expr:
        if isinstance(e, A.ArrayInit):
            return A.ArrayInit(
                [A.ArrayInitElem(self._init_expr(x.value) if x.value else None, x.repeat) for x in e.elems]
            )
        if isinstance(e, A.StructInit):
            return A.StructInit([(n, self._init_expr(v)) for n, v in e.fields])
        if isinstance(e, A.Literal):
            return self.literal(e)
        if isinstance(e, A.Name):
            c = self._enum_value_unqualified(e.id)
            if c is not None:
                return c
            sym = self.g.get(e.id.upper())
            if sym and sym.kind == "const" and sym.decl and sym.decl.init is not None:
                return self._init_expr(sym.decl.init)
        if isinstance(e, A.Member):
            path = A.var_path(e)
            if path and len(path) == 2 and path[0].upper() in self.enums:
                v = self.enums[path[0].upper()].get(path[1].upper())
                if v is not None:
                    return _lit_int(v)
        if isinstance(e, A.Unary):
            return A.Unary(e.op, self._init_expr(e.operand))
        if isinstance(e, A.Binary):
            return A.Binary(e.op, self._init_expr(e.left), self._init_expr(e.right))
        return e

    # ================================================================= GVL
    def _gvl(self, gvl: Gvl) -> None:
        self.pou = None
        self.lang = "DECL"
        self.origin = gvl.origin
        gname = gvl.name
        if self.ring and gname.upper() == "GVL_S7CLOCK":
            return
        con = self.c.construct("gvl", "DECL", gname, gvl.origin)
        self.c.push(con)
        try:
            members = self.gvl_members[gname.upper()]
            db_sections: dict[tuple[bool], S7Section] = {}
            marker_section: list[S7Member] = []
            todos = self._todos_for(gvl.origin.file) if self.ring else []
            for block, d in gvl.decls():
                sym = members[d.name.upper()]
                where = self.at(d)
                if block.persistent:
                    self.add("C2S7-RET", where, f"PERSISTENT {d.name}")
                if sym.kind == "const":
                    self._constant(sym, d, where)
                    continue
                if sym.kind == "tag":
                    self._tag_from_at(gname, d, sym, where)
                    continue
                if sym.kind == "dbinst":
                    self._instance_db(sym, d, block.retain or block.persistent, where)
                    continue
                if sym.db == "DB_Markers":
                    marker_section.append(self._member(d, "VAR"))
                    continue
                key = (block.retain or block.persistent,)
                sec = db_sections.get(key)
                if sec is None:
                    sec = S7Section("VAR", retain=key[0])
                    db_sections[key] = sec
                sec.members.append(self._member(d))
            for tb in todos:
                if tb.code:
                    raw = "\n".join(tb.code)
                    self.add("C2S7-RING-TODO", Origin(gvl.origin.file, tb.line), raw.splitlines()[0][:80], tb.reason)
                    sec = db_sections.get((False,)) or db_sections.setdefault((False,), S7Section("VAR"))
                    pos = self._todo_member_index(gvl, sec, tb)
                    sec.members.insert(pos, S7Member("", "", raw=raw))
            if db_sections:
                blk = S7Block("DATA_BLOCK", gname, origin=gvl.origin, source_pou=gname, language="DECL", order=1)
                if self.ring:
                    gpath = self._resolve(gvl.origin.file)
                    first = min((d.pos[0] for _, d in gvl.decls() if d.pos), default=10**6)
                    blk.optimized = not (
                        gpath is not None and RG.non_optimized(RG.scan_checks(read_text(gpath)), first)
                    )
                blk.sections = [db_sections[k] for k in sorted(db_sections)]
                self._doc_to_block(blk, gvl.doc)
                self._ring_db_meta(blk, gvl)
                self.blocks.append(blk)
                self._trace(gname, gname, gvl.origin)
            if marker_section:
                blk = S7Block("DATA_BLOCK", "DB_Markers", origin=gvl.origin, source_pou=gname, language="DECL", order=1)
                blk.sections = [S7Section("VAR", marker_section)]
                self.blocks.append(blk)
        finally:
            self.c.pop()

    def _todo_member_index(self, gvl: Gvl, sec: S7Section, tb: RG.TodoBlock) -> int:
        decls = [d for _, d in gvl.decls() if d.pos is not None]
        names = [m.name for m in sec.members]
        before = [d.name for d in decls if d.pos is not None and d.pos[0] < tb.line]
        idx = 0
        for i, n in enumerate(names):
            if n in before:
                idx = i + 1
        return idx

    def _doc_to_block(self, blk: S7Block, doc: list[str]) -> None:
        """Комментарий объекта → комментарий блока; в кольце шапка s7conv снимается (назначение → заголовок)."""
        if self.ring:
            meta = RG.parse_header(doc)
            blk.title = meta.title or blk.title
            blk.comment = meta.comment
        else:
            blk.comment = [c for c in doc if c]

    def _ring_db_meta(self, blk: S7Block, gvl: Gvl) -> None:
        if not self.ring:
            return
        meta = RG.parse_header(gvl.doc)
        blk.title = meta.title
        blk.author, blk.version, blk.family = meta.author, meta.version or blk.version, meta.family
        blk.comment = meta.comment

    def _constant(self, sym: GSym, d: A.VarDecl, where: Origin) -> None:
        typ, _ = self.s7_type(d.type, where)
        val = self.init_text(d.init) if d.init is not None else "0"
        name = sym.s7name or d.name
        self.constants[name.upper()] = Tag(name, typ, "", d.comment or "", "User constants", val, sym.gvl or "")

    def _tag_from_at(self, gvl: str, d: A.VarDecl, sym: GSym, where: Origin) -> None:
        assert d.address is not None
        s7addr, why = AD.to_s7(d.address, self.opt.bit_addressing)
        if f"{gvl}.{d.name}" in self.m_overlap:
            self.add("C2S7-ADDR-OVERLAP", where, f"{d.name} AT {d.address}")
        elif s7addr is None:
            self.add("C2S7-ADDR-WORDBIT", where, f"{d.name} AT {d.address}", detail=why)
        elif not self.ring:
            self.add("C2S7-ADDR-MAP", where, f"{d.name} AT {d.address} → {s7addr}")
        typ, _ = self.s7_type(d.type, where)
        comment = d.comment or ""
        if self.ring:
            m = re.match(r"^S7 (%\S+?);\s*(.*)$", comment)
            if m:
                comment = m.group(2)
        name = sym.s7name or d.name
        table = gvl
        if self.ring:
            table = {"GVL_IO": "IO", "GVL_MARKERS": "Markers"}.get(gvl.upper(), gvl)
        self.tags[name.upper()] = Tag(name, typ, s7addr or "", comment, table, None, f"{gvl}.{d.name} AT {d.address}")

    def _instance_db(self, sym: GSym, d: A.VarDecl, retain: bool, where: Origin) -> None:
        tname = T.type_name(d.type) or ""
        up = tname.upper()
        if self.ring and up in SL.S7COMPAT_FB:
            up = SL.S7COMPAT_FB[up]
        typ, _ = self.s7_type(d.type, where)
        if up in SL.STD_FB and SL.STD_FB[up].instruction:
            typ = "IEC_TIMER" if up in SL.TIMERS else "IEC_COUNTER" if up in SL.COUNTERS else typ
        assert sym.db is not None
        blk = S7Block("DATA_BLOCK", sym.db, db_of=typ, origin=where, source_pou=sym.gvl or "", language="DECL", order=3)
        if d.init is not None:
            blk.db_begin = [(p.lstrip("."), v) for p, v in self._compound_init(d.init, d.type, "")]
        if retain:
            blk.non_retain = False
        self.blocks.append(blk)
        self._trace(f"{sym.gvl}.{d.name}", sym.db, where)

    def _compound_init(self, init: A.Expr, tr: A.TypeRef | None, prefix: str) -> list[tuple[str, str]]:
        """Начальное значение структуры/массива → [(путь относительно члена, значение)]."""
        out: list[tuple[str, str]] = []
        if isinstance(init, A.StructInit):
            for n, v in init.fields:
                sub = self._member_type(tr, n)
                path = f"{prefix}.{n}"
                if isinstance(v, A.StructInit | A.ArrayInit):
                    out.extend(self._compound_init(v, sub, path))
                else:
                    out.append((path, self.init_text(v)))
        elif isinstance(init, A.ArrayInit):
            lo = 0
            elem_t = None
            if isinstance(tr, A.ArrayType) and tr.dims and tr.dims[0] is not None:
                lo = self._const_int(tr.dims[0][0]) or 0
                elem_t = tr.elem
            idx = lo
            for el in init.elems:
                for _ in range(el.repeat or 1):
                    if el.value is not None:
                        path = f"{prefix}[{idx}]"
                        if isinstance(el.value, A.StructInit | A.ArrayInit):
                            out.extend(self._compound_init(el.value, elem_t, path))
                        else:
                            out.append((path, self.init_text(el.value)))
                    idx += 1
        return out

    def _begin_values(self, init: A.Expr, prefix: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        if isinstance(init, A.StructInit):
            for n, v in init.fields:
                path = f"{prefix}.{n}" if prefix else n
                if isinstance(v, A.StructInit):
                    out.extend(self._begin_values(v, path))
                elif isinstance(v, A.ArrayInit):
                    idx = 0
                    for el in v.elems:
                        for _ in range(el.repeat or 1):
                            if el.value is not None:
                                out.append((f"{path}[{idx}]", self.init_text(el.value)))
                            idx += 1
                else:
                    out.append((path, self.init_text(v)))
        return out

    # ================================================================= POU
    def _pou(self, pou: Pou) -> None:
        self.pou = pou
        self.lang = pou.language
        self.origin = pou.origin
        self.loc = {}
        self.extra_static = []
        self.todo_blocks = []
        self.actions = {a.name.upper(): a.body for a in pou.actions}
        con = self.c.construct("pou", "DECL", pou.name, pou.origin)
        self.c.push(con)
        try:
            self._pou_inner(pou)
        finally:
            self.c.pop()

    def _ring_markers(self, pou: Pou) -> None:
        self.renames, self.s5_decl_lines, self.s5_stmt_lines, self.s5tim_lines = {}, set(), set(), set()
        self.slice_lines = set()
        self.decl_todos = []
        self.block_non_optimized = False
        if not self.ring:
            return
        decl_path = self._resolve(pou.origin.file)
        impl_path = self._resolve(pou.impl_origin.file) if pou.impl_origin else None
        dchecks = RG.scan_checks(read_text(decl_path)) if decl_path else []
        ichecks = RG.scan_checks(read_text(impl_path)) if impl_path else []
        self.renames = RG.renames(dchecks + ichecks)
        self.s5_decl_lines = RG.s5time_lines(dchecks)
        self.s5_stmt_lines = RG.s5time_lines(ichecks)
        self.s5tim_lines = RG.s5ti_tim_lines(ichecks)
        self.slice_lines = {c.next_line for c in ichecks if c.reason.startswith("срез ")}
        self.decl_todos = RG.scan_todos(read_text(decl_path)) if decl_path else []
        for c in dchecks:
            self.add("C2S7-RING-CHECK", Origin(pou.origin.file, c.line), c.reason[:80], c.reason, language="DECL")
        if impl_path is not None and pou.impl_origin is not None:
            for c in ichecks:
                self.add("C2S7-RING-CHECK", Origin(pou.impl_origin.file, c.line), c.reason[:80], c.reason)
        header = pou.text.header.pos[0] if pou.text.header.pos else 10**6
        self.block_non_optimized = RG.non_optimized(dchecks, header)

    def _counter_types(self, pou: Pou) -> None:
        """Счётчик → CTx_INT, если CV уходит в знаковый приёмник или PV приходит через INT_TO_WORD."""
        self.counter_int = set()
        counters = {n for n, ls in self.loc.items() if (T.type_name(ls.type) or "").upper() in SL.COUNTERS}
        if not counters:
            return
        for node in A.walk_stmts(pou.body):
            if isinstance(node, A.CallStmt):
                root = A.root_name(node.call.func)
                if root and root.upper() in counters:
                    for a in node.call.args:
                        v = a.value
                        fname = v.func.id.upper() if isinstance(v, A.Call) and isinstance(v.func, A.Name) else ""
                        if (a.name or "").upper() == "PV" and fname in ("INT_TO_WORD", "DINT_TO_WORD"):
                            self.counter_int.add(root.upper())
            if isinstance(node, A.Call) and isinstance(node.func, A.Name) and node.func.id.upper() == "WORD_TO_INT":
                arg = node.args[0].value if node.args else None
                is_cv = isinstance(arg, A.Member) and arg.name.upper() == "CV" and isinstance(arg.base, A.Name)
                if is_cv and arg.base.id.upper() in counters:  # type: ignore[union-attr]
                    self.counter_int.add(arg.base.id.upper())  # type: ignore[union-attr]
            if isinstance(node, A.Assign) and isinstance(node.value, A.Member) and node.value.name.upper() == "CV":
                base = node.value.base
                if (
                    isinstance(base, A.Name)
                    and base.id.upper() in counters
                    and T.is_signed_int(self.infer(node.target))
                ):
                    self.counter_int.add(base.id.upper())
        for n in sorted(self.counter_int):
            self.add(
                "C2S7-SEM-CTR",
                self.at(self.loc[n].decl),
                f"{self.loc[n].name} → CTx_INT",
                detail="знаковый приёмник CV",
            )

    def _pou_inner(self, pou: Pou) -> None:
        self._ring_markers(pou)
        for block, d in pou.decls():
            self.loc[d.name.upper()] = LSym(
                self.renames.get(d.name.upper(), d.name), block.kind, d, d.type, block.constant
            )
        self._counter_types(pou)
        if pou.methods or pou.properties or pou.text.header.extends or pou.text.header.implements:
            self.add("C2S7-OOP", pou.origin, f"{pou.kind} {pou.name}")
            self.manual.append(
                {
                    "step": f"ООП в {pou.name}",
                    "do": (
                        "уплощение: статика FB → UDT, METHOD → FC с IN_OUT self, PROPERTY → поле/FC, EXTENDS → слияние"
                    ),
                    "minutes": 120,
                }
            )
        ob = None
        if self.opt.ob_from_tasks and pou.kind == "PROGRAM":
            ob = self._ob_for_program(pou.name)
        meta = RG.parse_header(pou.doc) if self.ring else None
        if pou.kind == "FUNCTION":
            kind = "FUNCTION"
        elif ob is not None:
            kind = "ORGANIZATION_BLOCK"
        else:
            kind = "FUNCTION_BLOCK"
        name = ob[0] if ob is not None else pou.name
        blk = S7Block(kind, name, origin=pou.origin, source_pou=pou.name, language=pou.language)
        blk.order = 4 if kind == "ORGANIZATION_BLOCK" else 2
        blk.optimized = not self.block_non_optimized
        if meta is not None:
            blk.title, blk.author, blk.family = meta.title, meta.author, meta.family
            blk.version = meta.version or blk.version
            blk.comment = meta.comment
        elif pou.doc:
            blk.comment = [d for d in pou.doc if d]
        if pou.kind == "FUNCTION":
            rt = pou.return_type
            blk.return_type = self.s7_type(rt, pou.origin)[0] if rt is not None else "Void"
        if self.ring and pou.impl_origin is not None:
            self.todo_blocks = self._todos_for(pou.impl_origin.file)
            self.todo_drop = {line.strip() for tb in self.todo_blocks for line in tb.code}
        self._timer_idioms(pou)
        self._temp_reads(pou)
        init_assigns = self._sections(pou, blk)
        if pou.net is not None and pou.net.meta is not None and pou.language in ("LD", "FBD"):
            self._net_operands(pou)
        if pou.impl_origin is not None:
            self.origin = pou.impl_origin
        body = [*init_assigns, *self._stmts(pou.body, 10**9)]
        if self.ring:
            body = self._ring_body_fixups(pou, blk, body)
        blk.body = body
        if self.extra_static:
            sec = next((s for s in blk.sections if s.kind == "VAR" and not s.retain and not s.constant), None)
            if sec is None:
                sec = S7Section("VAR")
                idx = next(
                    (i for i, s in enumerate(blk.sections) if s.kind in ("VAR_TEMP",) or s.constant), len(blk.sections)
                )
                blk.sections.insert(idx, sec)
            sec.members.extend(self.extra_static)
        self.blocks.append(blk)
        self._trace(pou.name, name, pou.origin)
        if pou.kind == "PROGRAM" and ob is None:
            self.add("C2S7-POU-PRG", pou.origin, f"PROGRAM {pou.name}")
            db = S7Block(
                "DATA_BLOCK", f"{pou.name}_DB", db_of=f'"{pou.name}"', origin=pou.origin, source_pou=pou.name, order=3
            )
            self.blocks.append(db)
            self._trace(pou.name, db.name, pou.origin)
        if ob is not None:
            plan = ObPlan(task=ob[2], name=ob[0], number=ob[1], kind=ob[3], interval_ms=None, priority=None, calls=[])
            plan.full_block = blk
            plan.body = blk.body
            self.obs.append(plan)

    def _net_operands(self, pou: Pou) -> None:
        """Операнды сетей LD/FBD → обращения S7 и типы (для эмиттера FlgNet)."""
        assert pou.net is not None and pou.net.meta is not None
        meta = pou.net.meta
        texts: set[str] = set(meta.edge_bits.values())
        for net in pou.net.networks:
            for el in net.elements:
                if el.var and el.kind in ("contact", "coil", "in_var", "out_var", "inout_var"):
                    texts.add(el.var)
                if el.instance:
                    texts.add(el.instance)
        for text in sorted(texts):
            try:
                e = parse_expr(text, self.origin.file)
            except Exception:
                continue
            meta.operands[text] = self._expr(e)
            t = self.infer(e)
            name = T.type_name(t)
            if name:
                meta.types[text] = name.upper()

    def _ob_for_program(self, prg: str) -> tuple[str, int, str, str] | None:
        for t in self.p.tasks:
            hit = RG.ob_source(t.sources, prg, t.pous)
            if hit:
                kind = (
                    "Startup"
                    if hit[1] == 100
                    else "ProgramCycle"
                    if hit[1] == 1 or hit[1] >= 123
                    else "CyclicInterrupt"
                )
                return hit[0], hit[1], t.name, kind
        for o in self.p_obs():
            if str(o.get("program", "")).upper() == prg.upper():
                num = int(str(o.get("number"))) if o.get("number") is not None else None
                if num is None:
                    return None
                kind = {"main": "ProgramCycle", "cyclic": "CyclicInterrupt", "startup": "Startup"}.get(
                    str(o.get("kind")), "Event"
                )
                return str(o["name"]), num, str(o.get("task") or ""), kind
        return None

    def p_obs(self) -> list[dict[str, object]]:
        obs: list[dict[str, object]] = getattr(self.p, "obs", [])
        return obs

    def _sections(self, pou: Pou, blk: S7Block) -> list[A.Stmt]:
        """Секции переменных; возвращает присваивания начальных значений (Temp, выходы FC)."""
        assigns: list[A.Stmt] = []
        is_fc = pou.kind == "FUNCTION"
        is_ob = blk.kind == "ORGANIZATION_BLOCK"
        stat_members: list[S7Member] = []
        for block in pou.var_blocks:
            kind = block.kind
            if kind == "VAR_EXTERNAL":
                continue
            if kind == "VAR_STAT" or (kind == "VAR" and is_fc and "STATIC" in block.qualifiers):
                for d in block.decls:
                    self.add("C2S7-POU-STAT", self.at(d), f"VAR_STAT {d.name}")
                    stat_members.append(self._member(d))
                continue
            target = SECTION_MAP.get(kind, "VAR")
            if is_fc and target == "VAR" and not block.constant:
                target = "VAR_TEMP"
            if block.retain and is_fc:
                self.add("C2S7-RET", self.at(block), "RETAIN в FUNCTION", outcome="manual")
            if block.persistent:
                self.add("C2S7-RET", self.at(block), "PERSISTENT")
            if kind == "VAR_INPUT" and block.constant:
                self.add("C2S7-POU-INCONST", self.at(block), "VAR_INPUT CONSTANT")
            sec = S7Section(
                target,
                retain=(block.retain or block.persistent) and not is_fc,
                constant=block.constant and kind == "VAR",
            )
            if is_ob and self.ring:
                ring_sec = self._ring_ob_section(pou, block, sec)
                if ring_sec is None:
                    continue
                sec = ring_sec
            todos_here = [
                tb
                for tb in self.decl_todos
                if tb.code and block.pos is not None and block.end is not None and block.pos[0] < tb.line < block.end[0]
            ]
            for d in block.decls:
                for tb in [t for t in todos_here if d.pos is not None and t.line < d.pos[0]]:
                    todos_here.remove(tb)
                    self.add("C2S7-RING-TODO", Origin(self.origin.file, tb.line), tb.code[0][:80], tb.reason)
                    sec.members.append(S7Member("", "", raw="\n".join(tb.code)))
                if (self.ring and d.name == RG.INITIAL_CALL_VAR) or (self.ring and d.name == RG.STARTUP_VAR):
                    continue
                tname = T.type_name(d.type)
                if (
                    is_fc
                    and tname
                    and (self.g.get(tname.upper(), GSym("x", "")).kind == "fb" or tname.upper() in SL.STD_FB)
                ):
                    self.add("C2S7-POU-FBINFC", self.at(d), f"{d.name} : {tname}")
                if d.address and not self.ring and kind in ("VAR", "VAR_INPUT", "VAR_OUTPUT"):
                    tag = f"{pou.name}_{d.name}"
                    self._tag_from_at(pou.name, d, GSym("tag", d.name, s7name=tag), self.at(d))
                    self.loc[d.name.upper()].tag = tag
                    continue
                m = self._member(d)
                needs_assign = d.init is not None and (target == "VAR_TEMP" or (is_fc and target == "VAR_OUTPUT"))
                if needs_assign and not block.constant:
                    self.add("C2S7-POU-INIT", self.at(d), f"{d.name} := {m.init}")
                    assert d.init is not None
                    assigns.append(A.Assign(A.SclRef("local", d.name), self._expr(d.init)))
                    m.init = None
                sec.members.append(m)
            for tb in todos_here:
                self.add("C2S7-RING-TODO", Origin(self.origin.file, tb.line), tb.code[0][:80], tb.reason)
                sec.members.append(S7Member("", "", raw="\n".join(tb.code)))
            if block.decls and not sec.members:
                continue  # все переменные секции ушли в теги (AT)
            blk.sections.append(sec)
        if stat_members:
            self.blocks.append(
                S7Block(
                    "DATA_BLOCK",
                    f"{pou.name}_Stat",
                    sections=[S7Section("VAR", stat_members)],
                    origin=pou.origin,
                    order=1,
                )
            )
            self.stat_db = f"{pou.name}_Stat"
        blk.sections = self._merge_sections(blk.sections)
        return assigns

    @staticmethod
    def _merge_sections(secs: list[S7Section]) -> list[S7Section]:
        out: list[S7Section] = []
        for s in secs:
            prev = next(
                (o for o in out if o.kind == s.kind and o.retain == s.retain and o.constant == s.constant), None
            )
            if prev is not None:
                prev.members.extend(s.members)
            else:
                out.append(s)
        return out

    def _ring_ob_section(self, pou: Pou, block: A.VarBlock, sec: S7Section) -> S7Section | None:
        """OB в кольце: входы стартовой информации s7conv объявил VAR — возвращаются в VAR_INPUT."""
        if block.kind == "VAR" and not block.constant:
            names = {d.name for d in block.decls}
            if names <= {RG.INITIAL_CALL_VAR, RG.STARTUP_VAR}:
                return None
            return S7Section("VAR_INPUT")
        return sec

    # ================================================================= идиомы таймеров
    def _temp_reads(self, pou: Pou) -> None:
        """VAR_TEMP (и VAR функции) читается до первой записи — C2S7-SEM-TEMP."""
        temps = {n for n, ls in self.loc.items() if ls.section == "VAR_TEMP" and ls.decl.init is None}
        if pou.kind == "FUNCTION":
            temps |= {
                n for n, ls in self.loc.items() if ls.section == "VAR" and not ls.constant and ls.decl.init is None
            }
        if not temps:
            return
        written: set[str] = set()
        reported: set[str] = set()
        for s in pou.body:
            reads = set()
            for node in A.walk(s):
                if isinstance(node, A.Name) and node.id.upper() in temps:
                    reads.add(node.id.upper())
            if isinstance(s, A.Assign) and isinstance(s.target, A.Name):
                tgt = s.target.id.upper()
                value_reads = {n.id.upper() for n in A.walk(s.value) if isinstance(n, A.Name) and n.id.upper() in temps}
                for r in sorted(value_reads - written - reported):
                    self.add("C2S7-SEM-TEMP", self.at(s), self.loc[r].name)
                    reported.add(r)
                written.add(tgt)
                continue
            if isinstance(s, A.CallStmt):
                outs = {
                    rn.upper() for a in s.call.args if a.output and a.value is not None and (rn := A.root_name(a.value))
                }
                ins = {
                    n.id.upper()
                    for a in s.call.args
                    if not a.output and a.value is not None
                    for n in A.walk(a.value)
                    if isinstance(n, A.Name) and n.id.upper() in temps
                }
                for r in sorted(ins - written - reported):
                    self.add("C2S7-SEM-TEMP", self.at(s), self.loc[r].name)
                    reported.add(r)
                written |= outs
                continue
            for r in sorted(reads - written - reported):
                self.add("C2S7-SEM-TEMP", self.at(s), self.loc[r].name)
                reported.add(r)
            break

    def _timer_idioms(self, pou: Pou) -> None:
        """t(IN := NOT t.Q) и чтение t.Q/ET до первого вызова → выход вызова Q => #t_Q (C2S7-SEM-TIMER-Q)."""
        self.timer_rewrite = {}
        timers = {}
        for name, ls in self.loc.items():
            tn = T.type_name(ls.type)
            up = tn.upper() if tn else ""
            if self.ring and up in SL.S7COMPAT_FB:
                up = SL.S7COMPAT_FB[up]
            if up in SL.TIMERS:
                timers[name] = ls.name
        if not timers:
            return
        flagged: set[str] = set()
        called: set[str] = set()
        for s in _flat_stmts(pou.body):
            calls = []
            if isinstance(s, A.CallStmt):
                root = A.root_name(s.call.func)
                if root and root.upper() in timers and isinstance(s.call.func, A.Name):
                    calls.append(root.upper())
                    for a in s.call.args:
                        if a.value is not None and _reads_member(a.value, root, ("Q", "ET")):
                            flagged.add(root.upper())
            for node in A.walk(s):
                if not (isinstance(node, A.Member) and isinstance(node.base, A.Name)):
                    continue
                tid = node.base.id.upper()
                if tid in timers and node.name.upper() in ("Q", "ET") and tid not in called and not calls:
                    flagged.add(tid)
            called.update(calls)
        for t in sorted(flagged):
            orig = timers[t]
            self.timer_rewrite[t] = {"Q": f"{orig}_Q", "ET": f"{orig}_ET"}
            self.extra_static.append(
                S7Member(f"{orig}_Q", "Bool", comment=f"выход Q {orig} после вызова (C2S7-SEM-TIMER-Q)")
            )
            self.extra_static.append(S7Member(f"{orig}_ET", "Time", comment=f"выход ET {orig} после вызова"))
            decl = self.loc[t].decl
            self.add("C2S7-SEM-TIMER-Q", self.at(decl), f"{orig}.Q")

    # ================================================================= операторы
    def _stmts(self, stmts: list[A.Stmt], limit: int | None = None) -> list[A.Stmt]:
        out: list[A.Stmt] = []
        for s in stmts:
            out.extend(self._stmt_with_todo(s))
        if self.ring and limit is not None:
            for tb in list(self.todo_blocks):
                if tb.line < limit:
                    self.todo_blocks.remove(tb)
                    out.extend(self._todo_stmt(tb))
        return out

    @staticmethod
    def _first_line(stmts: list[A.Stmt] | None) -> int | None:
        for s in stmts or []:
            if s.pos is not None:
                return s.pos[0]
        return None

    def _s5_literals(self, stmts: list[A.Stmt]) -> None:
        for st in stmts:
            for node in A.walk(st):
                if isinstance(node, A.Literal) and node.kind == "time":
                    node.kind = "s5time"

    def _stmt_with_todo(self, s: A.Stmt) -> list[A.Stmt]:
        pre: list[A.Stmt] = []
        if self.ring and s.pos is not None:
            line = s.pos[0]
            for tb in list(self.todo_blocks):
                if tb.next_line <= line:
                    self.todo_blocks.remove(tb)
                    pre.extend(self._todo_stmt(tb))
        con = self.c.construct("stmt", self.lang, self.pou.name if self.pou else "", self.at(s))
        self.c.push(con)
        try:
            conv = self._stmt(s)
        finally:
            self.c.pop()
        if self.ring and s.pos is not None and s.pos[0] in self.s5_stmt_lines:
            self._s5_literals(conv)
        return [*pre, *conv]

    def _todo_stmt(self, tb: RG.TodoBlock) -> list[A.Stmt]:
        where = Origin(self.origin.file, tb.line)
        if tb.code:
            text = "\n".join(tb.code)
            self.add("C2S7-RING-TODO", where, tb.code[0][:80], tb.reason)
            return [A.Verbatim(text, lead=[f"восстановлено из пометки s7conv: {tb.reason}"])]
        self.add("C2S7-RING-LOSS", where, tb.reason[:80], tb.reason)
        return []

    def _stmt(self, s: A.Stmt) -> list[A.Stmt]:
        lead = [c for c in s.lead if not (self.ring and (c.startswith("MIGRATION-") or c.strip() in self.todo_drop))]
        if self.ring:
            lead = [c for c in lead if not _is_continuation(c)]
        if isinstance(s, A.Assign):
            target = self._expr(s.target, lvalue=True)
            value = self._expr(s.value)
            line = s.pos[0] if s.pos else -1
            if self.ring and line in self.s5tim_lines:
                value = A.Call(A.SclRef("raw", "S5TI_TIM"), [A.Arg(value)])
            if self.ring and line in self.slice_lines:
                value = _to_slice(value)
            if s.op == "REF=" and not self.prof.type_supported("REF_TO"):
                self.add("C2S7-PROF-REF", self.at(s), "REF=")
            self._check_assign(s, target, value)
            return [A.Assign(target, value, s.op, pos=s.pos, lead=lead, trail=s.trail)]
        if isinstance(s, A.CallStmt):
            return self._call_stmt(s, lead)
        if isinstance(s, A.If):
            end = s.end[0] if s.end else None
            starts = [self._first_line(b) for _, b in s.branches] + [self._first_line(s.else_body)]
            branches = []
            for i, (c, b) in enumerate(s.branches):
                nxt = next((x for x in starts[i + 1 :] if x is not None), end)
                branches.append((self._expr(c), self._stmts(b, nxt)))
            else_body = self._stmts(s.else_body, end) if s.else_body is not None else None
            return [A.If(branches, else_body, pos=s.pos, lead=lead, trail=s.trail)]
        if isinstance(s, A.Case):
            case_branches = [
                A.CaseBranch(
                    [A.CaseLabel(self._expr(lb.lo), self._expr(lb.hi) if lb.hi else None) for lb in br.labels],
                    self._stmts(br.body),
                )
                for br in s.branches
            ]
            else_body = self._stmts(s.else_body) if s.else_body is not None else None
            return [A.Case(self._expr(s.selector), case_branches, else_body, pos=s.pos, lead=lead, trail=s.trail)]
        if isinstance(s, A.For):
            return [
                A.For(
                    s.var,
                    self._expr(s.start),
                    self._expr(s.stop),
                    self._expr(s.step) if s.step is not None else None,
                    self._stmts(s.body),
                    pos=s.pos,
                    lead=lead,
                    trail=s.trail,
                )
            ]
        if isinstance(s, A.While):
            return [A.While(self._expr(s.cond), self._stmts(s.body), pos=s.pos, lead=lead, trail=s.trail)]
        if isinstance(s, A.Repeat):
            return [A.Repeat(self._stmts(s.body), self._expr(s.cond), pos=s.pos, lead=lead, trail=s.trail)]
        if isinstance(s, A.Region):
            return [A.Region(s.name, self._stmts(s.body), pos=s.pos, lead=lead)]
        if isinstance(s, A.Jump):
            self.add("C2S7-GFX-GOTO", self.at(s), f"JMP {s.label}")
            cond = self._expr(s.cond) if s.cond is not None else None
            return [A.Jump(s.label, cond, pos=s.pos, lead=lead)]
        if isinstance(s, A.Label | A.Exit | A.Continue | A.Return | A.Empty | A.Verbatim):
            out = copy.copy(s)
            out.lead = lead
            return [out]
        raise TypeError(type(s).__name__)

    def _check_assign(self, s: A.Assign, target: A.Expr, value: A.Expr) -> None:
        ttype = self.infer(s.target)
        if T.category(ttype) == "time" and _has_sub(s.value):
            self.add(
                "C2S7-TYPE-TIME", self.at(s), self.expr_text(s.value)[:60], detail="разность TIME: в CODESYS без знака"
            )
        if T.category(ttype) == "int" and T.bits(ttype) >= 32:
            for node in A.walk(s.value):
                if isinstance(node, A.Binary) and node.op in ("*", "+", "-"):
                    lt, rt = self.infer(node.left), self.infer(node.right)
                    if (
                        T.category(lt) == "int"
                        and T.category(rt) == "int"
                        and max(T.bits(lt), T.bits(rt)) < T.bits(ttype)
                    ):
                        self.add("C2S7-SEM-OVERFLOW", self.at(s), self.expr_text(node)[:60])
                        break
        if T.is_string(ttype) and any(
            isinstance(n, A.Literal) and n.kind == "string" and _cyr(str(n.value)) for n in A.walk(s.value)
        ):
            self.add("C2S7-TYPE-CYR", self.at(s), self.expr_text(s.value)[:60])

    def _call_stmt(self, s: A.CallStmt, lead: list[str]) -> list[A.Stmt]:
        call = s.call
        func = call.func
        name = func.id if isinstance(func, A.Name) else None
        up = name.upper() if name else ""
        # действие своего POU — встраивание
        if name and up in self.actions and not call.args:
            self.add("C2S7-ACT", self.at(s), f"{name}()")
            body = self._stmts(self.actions[up])
            return [A.Region(f"ACTION {name}", body, pos=s.pos, lead=lead)]
        # программа
        sym = self.g.get(up) if name else None
        if sym is not None and sym.kind == "program":
            return [
                A.CallStmt(
                    A.Call(A.SclRef("global", f"{name}_DB"), self._args(call.args, None)),
                    pos=s.pos,
                    lead=lead,
                    trail=s.trail,
                )
            ]
        if sym is not None and sym.kind == "function":
            c = self._call(call)
            return [A.CallStmt(c, pos=s.pos, lead=lead, trail=s.trail)] if isinstance(c, A.Call) else []
        # экземпляр ФБ
        inst_type = self._instance_type(func)
        conv_func = self._expr(func)
        args = call.args
        if inst_type:
            itu = inst_type.upper()
            if self.ring and itu in SL.S7COMPAT_FB:
                itu = SL.S7COMPAT_FB[itu]
            fbmap = SL.STD_FB.get(itu)
            new_args = []
            for a in args:
                pname = a.name
                if fbmap and pname and pname.upper() in fbmap.params:
                    pname = fbmap.params[pname.upper()]
                val = self._expr(a.value) if a.value is not None else None
                if self.ring and itu in SL.COUNTERS and val is not None and pname and pname.upper() == "PV":
                    val = _unwrap_conv(val, "INT_TO_WORD")
                new_args.append(A.Arg(val, pname, a.output, a.negated))
            root = A.root_name(func)
            if root and root.upper() in self.timer_rewrite and isinstance(func, A.Name):
                rw = self.timer_rewrite[root.upper()]
                have = {(a.name or "").upper() for a in new_args if a.output}
                if "Q" not in have:
                    new_args.append(A.Arg(A.SclRef("local", rw["Q"]), "Q", output=True))
                if "ET" not in have:
                    new_args.append(A.Arg(A.SclRef("local", rw["ET"]), "ET", output=True))
            if itu in ("SR", "RS"):
                self.add("C2S7-SEM-SRRS", self.at(s), self.expr_text(func))
            if itu in T.UTIL_FB:
                self.add("C2S7-STD-UTIL", self.at(s), itu)
            return [A.CallStmt(A.Call(conv_func, new_args), pos=s.pos, lead=lead, trail=s.trail)]
        if isinstance(func, A.Member) and self._is_method_call(func):
            self.add("C2S7-OOP", self.at(s), self.expr_text(func) + "()")
        c = self._call(call)
        if isinstance(c, A.Call):
            return [A.CallStmt(c, pos=s.pos, lead=lead, trail=s.trail)]
        return [A.Verbatim(self.expr_text(c) + ";", lead=lead)]

    def _is_method_call(self, func: A.Member) -> bool:
        base_t = self._instance_type(func.base)
        if not base_t:
            return False
        sym = self.g.get(base_t.upper())
        return bool(sym and sym.pou and any(m.header.name.upper() == func.name.upper() for m in sym.pou.methods))

    def _instance_type(self, e: A.Expr) -> str | None:
        """Тип ФБ, если выражение — экземпляр (локальный, в GVL, в массиве)."""
        tr = self.infer(e)
        n = T.type_name(tr)
        if not n:
            return None
        up = n.upper()
        sym = self.g.get(up)
        if up in SL.STD_FB or up in T.UTIL_FB or (sym is not None and sym.kind in ("fb", "s7compat")):
            return n
        if self.ring and up in SL.S7COMPAT_FB:
            return n
        return None

    # ================================================================= выражения
    def _expr(self, e: A.Expr, lvalue: bool = False) -> A.Expr:
        if isinstance(e, A.Literal):
            return self.literal(e)
        if isinstance(e, A.Name | A.Member):
            return self._path(e)
        if isinstance(e, A.Index):
            return A.Index(self._expr(e.base), [self._expr(i) for i in e.indices], pos=e.pos)
        if isinstance(e, A.BitRef):
            return A.BitRef(self._expr(e.base), e.bit, pos=e.pos)
        if isinstance(e, A.Deref):
            self.add("C2S7-TYPE-PTR", self.at(e), self.expr_text(e))
            return A.Deref(self._expr(e.base), pos=e.pos)
        if isinstance(e, A.DirectAddr):
            s7a, why = AD.to_s7(e.text, self.opt.bit_addressing)
            if s7a is None:
                self.add("C2S7-ADDR-WORDBIT", self.at(e), e.text, detail=why)
                return e
            self.add("C2S7-ADDR-MAP", self.at(e), f"{e.text} → {s7a}")
            return A.DirectAddr(s7a, pos=e.pos)
        if isinstance(e, A.Unary):
            return A.Unary(e.op, self._expr(e.operand), pos=e.pos)
        if isinstance(e, A.Binary):
            if e.op in ("/", "MOD"):
                lt = self.infer(e.left)
                if T.category(lt) in ("int", "bits") and not self._is_const(e.right):
                    self.add("C2S7-SEM-DIV0", self.at(e), self.expr_text(e)[:60])
            return A.Binary(e.op, self._expr(e.left), self._expr(e.right), pos=e.pos)
        if isinstance(e, A.Call):
            return self._call(e)
        if isinstance(e, A.ArrayInit | A.StructInit):
            return self._init_expr(e)
        if isinstance(e, A.SclRef):
            return e
        raise TypeError(type(e).__name__)

    def _is_const(self, e: A.Expr) -> bool:
        if isinstance(e, A.Literal):
            return True
        if isinstance(e, A.Name):
            ls = self.loc.get(e.id.upper())
            if ls is not None:
                return ls.constant
            sym = self.g.get(e.id.upper())
            return bool(sym and sym.kind == "const")
        if isinstance(e, A.Member):
            path = A.var_path(e)
            if path and len(path) == 2:
                g = self.gvl_members.get(path[0].upper(), {}).get(path[1].upper())
                if g is not None:
                    return g.kind == "const"
                return path[0].upper() in self.enums
        return False

    def literal(self, e: A.Literal) -> A.Literal:
        if e.kind == "time" and int(e.value) > L.TIME_MAX_S7_MS:
            if self.prof.type_supported("LTime"):
                self.add("C2S7-TYPE-TIME", self.at(e), e.text, detail="литерал больше T#24D20H31M23S647MS → LTime")
                return A.Literal("ltime", e.text, int(e.value) * 1_000_000, "LTIME", pos=e.pos)
            self.add(
                "C2S7-TYPE-TIME", self.at(e), e.text, detail="литерал больше диапазона Time S7", outcome="impossible"
            )
        if e.kind == "enum":
            vals = self.enums.get((e.type_name or "").upper())
            if vals is not None and str(e.value).upper() in vals:
                return _lit_int(vals[str(e.value).upper()])
        return e

    def _enum_value_unqualified(self, name: str) -> A.Expr | None:
        hits = [(en, v[name.upper()]) for en, v in self.enums.items() if name.upper() in v]
        if len(hits) == 1:
            enum, _ = hits[0]
            dut = self.g[enum].dut
            assert dut is not None
            return A.SclRef("global", f"{dut.name}_{name}")
        return None

    def _path(self, e: A.Name | A.Member) -> A.Expr:
        """Обращение к переменной: локальная, GVL, тег, константа, программа, перечисление."""
        path = A.var_path(e)
        if path is None:
            assert isinstance(e, A.Member)
            return A.Member(self._expr(e.base), e.name, pos=e.pos)
        head = path[0]
        hu = head.upper()
        # локальная переменная или результат функции
        if hu in self.loc and self.loc[hu].tag:
            return _rest(A.SclRef("tag", self.loc[hu].tag or "", pos=e.pos), path[1:], e.pos)
        if hu in self.loc or (self.pou and hu == self.pou.name.upper() and self.pou.kind == "FUNCTION"):
            if len(path) == 2 and hu in self.timer_rewrite and path[1].upper() in ("Q", "ET"):
                return A.SclRef("local", self.timer_rewrite[hu][path[1].upper()], pos=e.pos)
            if len(path) == 2 and self.ring and path[1].upper() == "CV":
                pass
            base: A.Expr = A.SclRef(
                "local", self.loc[hu].name if hu in self.loc else self.pou.name if self.pou else head, pos=e.pos
            )
            if hu in self.loc and self.loc[hu].constant and self.ring:
                base = A.SclRef("local", self.loc[hu].name, pos=e.pos)
            return _rest(base, path[1:], e.pos)
        sym = self.g.get(hu)
        if sym is not None:
            if sym.kind == "gvl" and len(path) >= 2:
                m = self.gvl_members.get(hu, {}).get(path[1].upper())
                if m is None:
                    return _rest(A.SclRef("global", sym.name, pos=e.pos), path[1:], e.pos)
                return self._gsym_ref(m, path[2:], e.pos)
            if sym.kind in ("gvar", "tag", "const", "dbinst"):
                return self._gsym_ref(sym, path[1:], e.pos)
            if sym.kind == "program":
                return _rest(A.SclRef("global", f"{sym.name}_DB", pos=e.pos), path[1:], e.pos)
            if sym.kind == "enum" and len(path) == 2:
                dut = sym.dut
                assert dut is not None
                et = dut.decl.type
                enum_vals = et.values if isinstance(et, A.EnumType) else []
                vname = next((n for n, _ in enum_vals if n.upper() == path[1].upper()), path[1])
                return A.SclRef("global", f"{dut.name}_{vname}", pos=e.pos)
            if sym.kind in ("function", "fb"):
                return A.SclRef("global", sym.name, pos=e.pos)
        ev = self._enum_value_unqualified(head) if len(path) == 1 else None
        if ev is not None:
            return ev
        if hu in ("TRUE", "FALSE"):
            return A.Literal("bool", hu, hu == "TRUE")
        return _rest(A.SclRef("raw", head, pos=e.pos), path[1:], e.pos)

    def _gsym_ref(self, m: GSym, rest: list[str], pos: A.Pos) -> A.Expr:
        if m.kind == "tag":
            return _rest(A.SclRef("tag", m.s7name or m.name, pos=pos), rest, pos)
        if m.kind == "const":
            return A.SclRef("global", m.s7name or m.name, pos=pos)
        if m.kind == "dbinst":
            return _rest(A.SclRef("global", m.db or m.name, pos=pos), rest, pos)
        return _rest(A.Member(A.SclRef("global", m.db or "", pos=pos), m.name, pos=pos), rest, pos)

    def _args(self, args: list[A.Arg], formal: list[str] | None) -> list[A.Arg]:
        out = []
        for i, a in enumerate(args):
            name = a.name
            if name is None and formal is not None and i < len(formal):
                name = formal[i]
            out.append(A.Arg(self._expr(a.value) if a.value is not None else None, name, a.output, a.negated))
        return out

    def _call(self, c: A.Call) -> A.Expr:
        func = c.func
        name = func.id if isinstance(func, A.Name) else None
        if name is None:
            return A.Call(self._expr(func), self._args(c.args, None))
        up = name.upper()
        where = self.at(c)
        if self.ring and up in ("F_NORMX", "F_SCALEX"):
            s7 = "NORM_X" if up == "F_NORMX" else "SCALE_X"
            mp = {"RMIN": "MIN", "RVALUE": "VALUE", "RMAX": "MAX"}
            args = [
                A.Arg(self._expr(a.value) if a.value else None, mp.get((a.name or "").upper(), a.name)) for a in c.args
            ]
            return A.Call(A.SclRef("raw", s7), args)
        if self.ring and up == "F_S7NOW":
            return A.Call(A.SclRef("raw", "TIME_TCK"), [])
        if up == "EXPT" and len(c.args) == 2:
            return A.Binary("**", self._expr(c.args[0].value), self._expr(c.args[1].value))  # type: ignore[arg-type]
        if up in SL.FUNC_FORMAL:
            if up == "LIMIT":
                self.add("C2S7-SEM-LIMIT", where, self.expr_text(c)[:60])
            return A.Call(A.SclRef("raw", up), self._args(c.args, SL.FUNC_FORMAL[up]))
        if up in SL.VARIADIC_IN:
            return A.Call(A.SclRef("raw", up), self._args(c.args, [f"IN{i + 1}" for i in range(len(c.args))]))
        if up == SL.MUX:
            self.add("C2S7-SEM-MUX", where, self.expr_text(c)[:60])
            return A.Call(A.SclRef("raw", up), self._args(c.args, ["K", *[f"IN{i}" for i in range(len(c.args) - 1)]]))
        if up in SL.STRING_FUNCS:
            formal = SL.STRING_FUNCS[up]
            ren = SL.STRING_PARAM_CDS[up]
            args = []
            for i, a in enumerate(c.args):
                pname = ren.get((a.name or "").upper(), a.name) if a.name else (formal[i] if i < len(formal) else None)
                args.append(A.Arg(self._expr(a.value) if a.value is not None else None, pname))
            if not self.ring:
                self.add("C2S7-STD", where, up)
            return A.Call(A.SclRef("raw", up), args)
        if up in SL.SHIFT:
            return A.Call(A.SclRef("raw", up), self._args(c.args, ["IN", "N"]))
        if up in SL.UNARY_SAME:
            return A.Call(A.SclRef("raw", up), self._args(c.args, None))
        if up == "TIME" and not c.args:
            self.add("C2S7-STD", where, "TIME()", outcome="verify", detail="TIME() → TIME_TCK(): по CPU сверить")
            return A.Call(A.SclRef("raw", "TIME_TCK"), [])
        if up in SL.LIB_FUNCS:
            self.add(SL.LIB_FUNCS[up], where, self.expr_text(c)[:60])
            return A.Call(A.SclRef("raw", up), self._args(c.args, None))
        if self.ring and re.match(r"^REAL_TO_[A-Z]*INT$", up) and len(c.args) == 1:
            inner = c.args[0].value
            if isinstance(inner, A.Call) and isinstance(inner.func, A.Name) and inner.func.id.upper() == "F_SCALEX":
                return self._call(inner)
        if re.match(r"^(DATE|DT|DATE_AND_TIME|TOD|TIME_OF_DAY)_TO_(DWORD|UDINT|DINT|LWORD|ULINT)$", up) or re.match(
            r"^(DWORD|UDINT|DINT|LWORD|ULINT)_TO_(DATE|DT|DATE_AND_TIME|TOD|TIME_OF_DAY)$", up
        ):
            self.add("C2S7-TYPE-DATE", where, self.expr_text(c)[:60])
        if re.match(r"^[A-Z]+_TO_[A-Z]+$", up):
            src, _, dst = up.partition("_TO_")
            if src in ("REAL", "LREAL") and T.elem(dst) is not None and T.elem(dst).cat == "int":  # type: ignore[union-attr]
                self.add("C2S7-SEM-ROUND", where, self.expr_text(c)[:60])
            if (
                self.ring
                and up in ("WORD_TO_INT", "WORD_TO_UINT")
                and len(c.args) == 1
                and self._is_counter_cv(c.args[0].value)
            ):
                return self._expr(c.args[0].value)  # type: ignore[arg-type]
            return A.Call(A.SclRef("raw", up), self._args(c.args, None))
        if up.startswith("TO_") and T.elem(up[3:]) is not None:
            src_t = self.infer(c.args[0].value) if c.args and c.args[0].value is not None else None
            sn = T.type_name(src_t)
            if sn:
                return A.Call(A.SclRef("raw", f"{sn.upper()}_TO_{up[3:]}"), self._args(c.args, None))
        sym = self.g.get(up)
        if sym is not None and sym.kind == "function" and sym.pou is not None:
            inputs = [d.name for b, d in sym.pou.decls() if b.kind == "VAR_INPUT"]
            return A.Call(A.SclRef("global", sym.name), self._args(c.args, inputs))
        if "." in name:
            pass
        return A.Call(A.SclRef("raw", name), self._args(c.args, None))

    def _is_counter_cv(self, e: A.Expr | None) -> bool:
        if isinstance(e, A.Member) and e.name.upper() == "CV":
            t = self._instance_type(e.base)
            return bool(t and t.upper() in SL.COUNTERS)
        return False

    # ================================================================= типы выражений
    def infer(self, e: A.Expr | None) -> A.TypeRef | None:
        """Тип выражения CODESYS (насколько нужно правилам): переменные, члены, литералы."""
        if e is None:
            return None
        if isinstance(e, A.Name):
            ls = self.loc.get(e.id.upper())
            if ls is not None:
                return ls.type
            if self.pou and e.id.upper() == self.pou.name.upper():
                return self.pou.return_type
            sym = self.g.get(e.id.upper())
            if sym is not None and sym.type is not None and sym.kind in ("gvar", "tag", "const", "dbinst"):
                return sym.type
            return None
        if isinstance(e, A.Member):
            path = A.var_path(e)
            if path and path[0].upper() in self.gvl_members and len(path) >= 2:
                m = self.gvl_members[path[0].upper()].get(path[1].upper())
                t = m.type if m else None
                for p in path[2:]:
                    t = self._member_type(t, p)
                return t
            if path and path[0].upper() in self.enums:
                return A.NamedType(path[0])
            return self._member_type(self.infer(e.base), e.name)
        if isinstance(e, A.Index):
            bt = self.infer(e.base)
            return bt.elem if isinstance(bt, A.ArrayType) else None
        if isinstance(e, A.Literal):
            return {
                "int": A.NamedType(e.type_name or "INT"),
                "real": A.NamedType(e.type_name or "LREAL"),
                "bool": A.NamedType("BOOL"),
                "time": A.NamedType("TIME"),
                "ltime": A.NamedType("LTIME"),
                "string": A.StringType(False),
                "wstring": A.StringType(True),
            }.get(e.kind)
        if isinstance(e, A.Binary):
            if e.op in ("=", "<>", "<", ">", "<=", ">="):
                return A.NamedType("BOOL")
            lt = self.infer(e.left)
            return lt or self.infer(e.right)
        if isinstance(e, A.Unary):
            return self.infer(e.operand)
        if isinstance(e, A.Call) and isinstance(e.func, A.Name):
            up = e.func.id.upper()
            if "_TO_" in up:
                return A.NamedType(up.split("_TO_")[1])
            sym = self.g.get(up)
            if sym and sym.pou is not None:
                return sym.pou.return_type
        return None

    def _member_type(self, base: A.TypeRef | None, member: str) -> A.TypeRef | None:
        n = T.type_name(base)
        if not n:
            return None
        up = n.upper()
        if up in SL.TIMERS or (self.ring and SL.S7COMPAT_FB.get(up) in SL.TIMERS):
            return {
                "Q": A.NamedType("BOOL"),
                "ET": A.NamedType("TIME"),
                "IN": A.NamedType("BOOL"),
                "PT": A.NamedType("TIME"),
            }.get(member.upper())
        if up in SL.COUNTERS:
            return A.NamedType("WORD") if member.upper() in ("CV", "PV") else A.NamedType("BOOL")
        sym = self.g.get(up)
        if sym is None:
            return None
        if sym.dut is not None and isinstance(sym.dut.decl.type, A.StructType):
            for m in sym.dut.decl.type.members:
                if m.name.upper() == member.upper():
                    return m.type
        if sym.pou is not None:
            for _, d in sym.pou.decls():
                if d.name.upper() == member.upper():
                    return d.type
        return None

    # ================================================================= кольцо: тела
    def _todos_for(self, rel: str) -> list[RG.TodoBlock]:
        path = self._resolve(rel)
        if path is None:
            return []
        return RG.scan_todos(read_text(path))

    def _resolve(self, rel: str) -> Path | None:
        base = Path(self.p.path)
        for cand in (Path(rel), base / rel, base.parent / rel, Path.cwd() / rel):
            if cand.exists():
                return cand
        root = getattr(self.p, "root", None)
        if root:
            cand = Path(root) / rel
            if cand.exists():
                return cand
        return None

    def _ring_body_fixups(self, pou: Pou, blk: S7Block, body: list[A.Stmt]) -> list[A.Stmt]:
        """Эмуляция Initial_Call и однократного OB100 s7conv → исходная форма OB."""
        out: list[A.Stmt] = []
        for s in body:
            if isinstance(s, A.Assign) and isinstance(s.target, A.SclRef):
                if s.target.name in (RG.INITIAL_CALL_VAR, RG.STARTUP_VAR):
                    continue
                if (
                    s.target.name == "Initial_Call"
                    and isinstance(s.value, A.Unary)
                    and isinstance(s.value.operand, A.SclRef)
                    and s.value.operand.name == RG.INITIAL_CALL_VAR
                ):
                    continue
            if isinstance(s, A.If) and len(s.branches) == 1 and s.else_body is None:
                cond = s.branches[0][0]
                if (
                    isinstance(cond, A.Unary)
                    and isinstance(cond.operand, A.SclRef)
                    and cond.operand.name == RG.STARTUP_VAR
                ):
                    out.extend(
                        x
                        for x in s.branches[0][1]
                        if not (
                            isinstance(x, A.Assign)
                            and isinstance(x.target, A.SclRef)
                            and x.target.name == RG.STARTUP_VAR
                        )
                    )
                    continue
            out.append(s)
        return _regions_from_comments(out)

    # ================================================================= задачи
    def _tasks(self) -> None:
        from c2s7.convert.tasks import plan_tasks

        plan_tasks(self)

    def _compat_blocks(self) -> None:
        pass

    def _trace(self, src: str, target: str, origin: Origin) -> None:
        self.trace.append({"source": src, "target": target, "origin": origin.as_dict()})

    def _ordered_blocks(self) -> list[S7Block]:
        from c2s7.convert.order import order_blocks

        return order_blocks(self.blocks)


# ---------------------------------------------------------------------------
# Вспомогательное
# ---------------------------------------------------------------------------


_CDS_KEYWORDS = {
    "AND",
    "ANY",
    "ARRAY",
    "AT",
    "BOOL",
    "BY",
    "BYTE",
    "CASE",
    "CONTINUE",
    "DATE",
    "DINT",
    "DO",
    "DT",
    "DWORD",
    "ELSE",
    "ELSIF",
    "END_CASE",
    "END_FOR",
    "END_FUNCTION",
    "END_FUNCTION_BLOCK",
    "END_IF",
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
    "IF",
    "INT",
    "MOD",
    "NOT",
    "OF",
    "OR",
    "POINTER",
    "REAL",
    "REPEAT",
    "RETURN",
    "STRING",
    "STRUCT",
    "THEN",
    "TIME",
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
    "WHILE",
    "WORD",
    "XOR",
}


def _rest(base: A.Expr, rest: list[str], pos: A.Pos) -> A.Expr:
    for name in rest:
        base = A.Member(base, name, pos=pos)
    return base


def _flat_stmts(stmts: list[A.Stmt]) -> list[A.Stmt]:
    out: list[A.Stmt] = []
    for s in stmts:
        out.append(s)
        for b in A.stmt_bodies(s):
            out.extend(_flat_stmts(b))
    return out


def _reads_member(e: A.Expr, root: str, members: tuple[str, ...]) -> bool:
    for n in A.walk(e):
        if not (isinstance(n, A.Member) and isinstance(n.base, A.Name)):
            continue
        if n.base.id.upper() == root.upper() and n.name.upper() in members:
            return True
    return False


def _has_sub(e: A.Expr) -> bool:
    return any(
        (isinstance(n, A.Binary) and n.op == "-") or (isinstance(n, A.Unary) and n.op == "NEG") for n in A.walk(e)
    )


_SLICE_SIZE = {"BYTE": "B", "WORD": "W", "DWORD": "D"}


def _to_slice(e: A.Expr) -> A.Expr:
    """s7conv: x.%Bk → *_TO_BYTE(SHR(x, 8k)), x.%W0 → DWORD_TO_WORD(x) — обратно в срез SCL."""
    if isinstance(e, A.Call) and isinstance(e.func, A.SclRef) and "_TO_" in e.func.name and len(e.args) == 1:
        dst = e.func.name.split("_TO_")[1]
        size = _SLICE_SIZE.get(dst)
        arg = e.args[0].value
        if size is None or arg is None:
            return e
        width = {"B": 8, "W": 16, "D": 32}[size]
        if isinstance(arg, A.Call) and isinstance(arg.func, A.SclRef) and arg.func.name == "SHR" and len(arg.args) == 2:
            base, n = arg.args[0].value, arg.args[1].value
            if base is not None and isinstance(n, A.Literal) and n.kind == "int" and int(n.value) % width == 0:
                return A.Slice(base, size, int(n.value) // width)
        return A.Slice(arg, size, 0)
    return e


def _is_continuation(c: str) -> bool:
    """Хвост перенесённой строки пометки s7conv («53)», «перегрузка) — аргумент опущен (стр. 189)»)."""
    return bool(re.match(r"^[^A-Za-zА-Яа-я#\"]{0,3}.*\(стр\. \d+\)$", c)) or bool(re.match(r"^\d+\)$", c))


def _cyr(text: str) -> bool:
    return any("Ѐ" <= ch <= "ӿ" for ch in text)


def _unwrap_conv(e: A.Expr, fname: str) -> A.Expr:
    if isinstance(e, A.Call) and isinstance(e.func, A.SclRef) and e.func.name.upper() == fname and len(e.args) == 1:
        v = e.args[0].value
        if v is not None:
            return v
    return e


def _regions_from_comments(stmts: list[A.Stmt]) -> list[A.Stmt]:
    """`// REGION X` … `// END_REGION X` (так s7conv переносит REGION) → Region в SCL."""
    out: list[A.Stmt] = []
    stack: list[tuple[str, list[A.Stmt]]] = []

    def emit(s: A.Stmt) -> None:
        (stack[-1][1] if stack else out).append(s)

    for s in stmts:
        opens = [c[len("REGION ") :] for c in s.lead if c.startswith("REGION ")]
        closes = [c for c in s.lead if c.startswith("END_REGION")]
        for _ in closes:
            if stack:
                name, body = stack.pop()
                emit(A.Region(name, body))
        for name in opens:
            stack.append((name, []))
        s.lead = [c for c in s.lead if not c.startswith(("REGION ", "END_REGION"))]
        emit(s)
    while stack:
        name, body = stack.pop()
        emit(A.Region(name, body))
    return out


def parse_init_value(text: str) -> A.Expr:
    return parse_expr(text)
