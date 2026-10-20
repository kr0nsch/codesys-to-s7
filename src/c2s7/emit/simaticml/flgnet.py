"""FlgNet V19/V21 (SimaticML LAD/FBD) из NetIR на закрытом подмножестве (ТЗ M5, M8).

LD → LAD: поток каждой катушки строится из дерева AND/OR контактов (последовательно — цепочка,
параллельно — часть `O` с Card); катушки с общим потоком висят на одном проводе. Фронтовый контакт
допускается только в ветви, которая начинается от шины: `Contact` + `PBox`/`NBox` с тем же битом
памяти в статике, что и в SCL-пути (C2S7-GFX-EDGE). Инверсная катушка — `Not` перед `Coil`.

FBD → FBD: приёмники — выходы (`Coil` для BOOL логических частей, прямой провод на операнд для
боксов), прыжки. Операторы AND/OR/XOR → `A/O/X` с Card, NOT уходит в отрицание входа приёмника,
сравнения — `Gt…` (SrcType), ADD… — `Add…`, MOVE — `Move`, TON/TOF/TP — части с экземпляром.

Всё вне подмножества (`parts.py`) — исключение Unsupported: POU остаётся в SCL с находкой
C2S7-GFX-SCL. UId — по обходу (с 21 в каждой сети), ID объектов — шестнадцатеричный счётчик, метка
времени фиксирована (ADR-6): два прогона дают одинаковые байты.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from xml.sax.saxutils import escape, quoteattr

from c2s7.emit.files import safe
from c2s7.emit.simaticml.parts import ARITH_PART, CMP_PART, PARTS, S7_ELEM, TIMER_PART
from c2s7.ir.netir import Conn, Element, Network
from c2s7.lower.net import NetMeta
from c2s7.st import nodes as A

if TYPE_CHECKING:
    from c2s7.convert.core import Result
    from c2s7.model import Pou
    from c2s7.s7 import S7Block, S7Member

CREATED = "2026-10-19T00:00:00.0000000Z"  # фиксированная метка (детерминизм), не время экспорта TIA
CULTURE = "en-US"
SECTION = {
    "VAR_INPUT": "Input",
    "VAR_OUTPUT": "Output",
    "VAR_IN_OUT": "InOut",
    "VAR": "Static",
    "VAR_STAT": "Static",
    "VAR_TEMP": "Temp",
}
FB_SECTIONS = ("Input", "Output", "InOut", "Static", "Temp", "Constant")
FC_SECTIONS = ("Input", "Output", "InOut", "Temp", "Constant", "Return")


class Unsupported(Exception):
    """Конструкция вне подмножества FlgNet P0."""


Src = tuple[Any, ...]  # ("rail",) | ("name", uid, pin) | ("ident", uid)
RAIL: Src = ("rail",)


@dataclass
class _Part:
    uid: int
    name: str
    templates: list[tuple[str, str, str]] = field(default_factory=list)  # (имя, тип, значение)
    negated: list[str] = field(default_factory=list)
    instance: list[str] | None = None
    instance_uid: int | None = None
    version: str | None = None
    disabled_eno: bool = False


class _Unit:
    """Одна сеть (CompileUnit): части, обращения, провода."""

    def __init__(self, lang: str, locals_: set[str], constants: set[str]) -> None:
        self.lang = lang
        self.uid = 20
        self.accesses: list[str] = []
        self.parts: list[_Part] = []
        self.wires: dict[Src, list[Src]] = {}
        self.labels: list[str] = []
        self.locals = locals_
        self.constants = constants

    def next(self) -> int:
        self.uid += 1
        return self.uid

    # -------------------------------------------------------------- обращения
    def access(self, e: A.Expr) -> int:
        uid = self.next()
        self.accesses.append(_access_xml(e, uid, self.locals, self.constants))
        return uid

    def label_access(self, name: str) -> int:
        uid = self.next()
        self.accesses.append(f'<Access Scope="Label" UId="{uid}"><Label Name={quoteattr(name)} /></Access>')
        return uid

    def part(self, name: str, **kw: Any) -> _Part:
        if name not in PARTS:
            raise Unsupported(f"часть {name} вне реестра")
        p = _Part(self.next(), name, **kw)
        if p.instance is not None:
            p.instance_uid = self.next()
        self.parts.append(p)
        return p

    def connect(self, src: Src, uid: int, pin: str) -> None:
        self.wires.setdefault(src, []).append(("name", uid, pin))

    def to_operand(self, src: Src, e: A.Expr) -> None:
        self.wires.setdefault(src, []).append(("ident", self.access(e)))

    def render(self) -> str:
        out: list[str] = []
        if self.labels:
            out.append("<Labels>")
            for lbl in self.labels:
                out.append(f'<LabelDeclaration UId="{self.next()}"><Label Name={quoteattr(lbl)} /></LabelDeclaration>')
            out.append("</Labels>")
        out.append("<Parts>")
        out.extend(self.accesses)
        for p in self.parts:
            attrs = f' Name="{p.name}"'
            if p.version:
                attrs += f' Version="{p.version}"'
            attrs += f' UId="{p.uid}"'
            if p.disabled_eno:
                attrs += ' DisabledENO="true"'
            inner: list[str] = []
            if p.instance is not None:
                comps = "".join(f"<Component Name={quoteattr(c)} />" for c in p.instance)
                inner.append(f'<Instance Scope="LocalVariable" UId="{p.instance_uid}">{comps}</Instance>')
            for n, t, v in p.templates:
                inner.append(f'<TemplateValue Name="{n}" Type="{t}">{escape(v)}</TemplateValue>')
            for n in p.negated:
                inner.append(f'<Negated Name="{n}" />')
            out.append(f"<Part{attrs}>{''.join(inner)}</Part>" if inner else f"<Part{attrs} />")
        out.append("</Parts>")
        if self.wires:
            out.append("<Wires>")
            for src, targets in self.wires.items():
                uid = self.next()
                out.append(f'<Wire UId="{uid}">{_con(src)}{"".join(_con(t) for t in targets)}</Wire>')
            out.append("</Wires>")
        return "".join(out)


def _con(s: Src) -> str:
    if s[0] == "rail":
        return "<Powerrail />"
    if s[0] == "ident":
        return f'<IdentCon UId="{s[1]}" />'
    return f'<NameCon UId="{s[1]}" Name="{s[2]}" />'


def _components(e: A.Expr) -> tuple[str, list[str]]:
    """Обращение S7 → (область, компоненты)."""
    parts: list[str] = []
    cur = e
    while isinstance(cur, A.Member):
        parts.insert(0, cur.name)
        cur = cur.base
    if isinstance(cur, A.SclRef):
        return cur.kind, [cur.name, *parts]
    if isinstance(cur, A.Name):
        return "local", [cur.id, *parts]
    raise Unsupported(f"операнд {type(cur).__name__} вне подмножества FlgNet")


def _access_xml(e: A.Expr, uid: int, locals_: set[str], constants: set[str]) -> str:
    if isinstance(e, A.Literal):
        if e.kind == "time":
            return (
                f'<Access Scope="TypedConstant" UId="{uid}"><Constant>'
                f"<ConstantValue>{escape(e.text)}</ConstantValue></Constant></Access>"
            )
        ctype = {"bool": "Bool", "int": S7_ELEM.get((e.type_name or "INT").upper(), "Int"), "real": "Real"}.get(e.kind)
        if ctype is None:
            raise Unsupported(f"литерал {e.text} вне подмножества FlgNet")
        value = e.text.upper() if e.kind == "bool" else e.text.split("#")[-1]
        return (
            f'<Access Scope="LiteralConstant" UId="{uid}"><Constant><ConstantType>{ctype}</ConstantType>'
            f"<ConstantValue>{escape(value)}</ConstantValue></Constant></Access>"
        )
    kind, comps = _components(e)
    if kind == "global" and len(comps) == 1 and comps[0].upper() in constants:
        return f'<Access Scope="GlobalConstant" UId="{uid}"><Constant Name={quoteattr(comps[0])} /></Access>'
    if kind == "local":
        if comps[0].upper() not in locals_:
            raise Unsupported(f"локальная {comps[0]} не найдена в интерфейсе")
        scope = "LocalVariable"
    elif kind in ("global", "tag"):
        scope = "GlobalVariable"
    else:
        raise Unsupported(f"обращение {'.'.join(comps)} не разрешено")
    sym = "".join(f"<Component Name={quoteattr(c)} />" for c in comps)
    return f'<Access Scope="{scope}" UId="{uid}"><Symbol>{sym}</Symbol></Access>'


class _Builder:
    def __init__(self, pou: Pou, meta: NetMeta, locals_: set[str], constants: set[str]) -> None:
        self.pou = pou
        self.meta = meta
        self.locals = locals_
        self.constants = constants
        self.els: dict[str, Element] = {}
        self.u: _Unit
        self.made: dict[str, Src] = {}
        self.joins: dict[tuple[str, ...], Src] = {}

    def operand(self, text: str | None) -> A.Expr:
        if not text:
            raise Unsupported("пустой операнд")
        e = self.meta.operands.get(text)
        if e is None:
            raise Unsupported(f"операнд {text} не переведён")
        return e

    def src_type(self, texts: list[str | None]) -> str:
        for t in texts:
            ty = self.meta.types.get(t or "")
            if ty and ty in S7_ELEM:
                return S7_ELEM[ty]
        raise Unsupported("тип операндов не выведен (нужен SrcType)")

    # ----------------------------------------------------------- LD
    def ld_join(self, conns: list[Conn]) -> Src:
        """Вход элемента: один провод — выход источника, несколько — часть O (параллель)."""
        if not conns:
            raise Unsupported("элемент LD без входа")
        if len(conns) == 1:
            return self.ld_out(conns[0].ref)
        key = tuple(sorted(c.ref for c in conns))
        if key in self.joins:
            return self.joins[key]
        srcs = [self.ld_out(c.ref) for c in conns]
        o = self.u.part("O", templates=[("Card", "Cardinality", str(len(srcs)))])
        for i, s in enumerate(srcs, start=1):
            self.u.connect(s, o.uid, f"in{i}")
        self.joins[key] = ("name", o.uid, "out")
        return self.joins[key]

    def ld_out(self, ref: str) -> Src:
        """Выход элемента NetIR как часть LAD (каждый элемент строится один раз — общие контакты не дублируются)."""
        if ref in self.made:
            return self.made[ref]
        u = self.u
        el = self.els.get(ref)
        if el is None:
            raise Unsupported(f"провод на {ref}")
        if el.kind == "left_rail":
            return RAIL
        if el.kind == "contact":
            src = self.ld_join(el.conns)
            edge = el.edge in ("rising", "falling")
            if edge and (src != RAIL or el.negated):
                raise Unsupported(f"фронтовый контакт {el.var} не от шины или с отрицанием")
            c = u.part("Contact", negated=["operand"] if el.negated else [])
            u.connect(src, c.uid, "in")
            u.wires.setdefault(("ident", u.access(self.operand(el.var))), []).append(("name", c.uid, "operand"))
            out: Src = ("name", c.uid, "out")
            if edge:
                bit = self.meta.edge_bits.get(el.id)
                if bit is None:
                    raise Unsupported(f"нет бита памяти фронта {el.var}")
                box = u.part("PBox" if el.edge == "rising" else "NBox")
                u.connect(out, box.uid, "in")
                u.wires.setdefault(("ident", u.access(self.operand(bit))), []).append(("name", box.uid, "bit"))
                out = ("name", box.uid, "out")
            self.made[ref] = out
            return out
        if el.kind == "coil":
            return self.ld_coil(el)
        raise Unsupported(f"элемент LD {el.kind} {el.type_name or ''} вне подмножества FlgNet")

    def ld_coil(self, el: Element) -> Src:
        if el.id in self.made:
            return self.made[el.id]
        u = self.u
        s = self.ld_join(el.conns)
        if el.negated and el.storage == "none":
            n = u.part("Not")
            u.connect(s, n.uid, "in")
            s = ("name", n.uid, "out")
        name = {"set": "SCoil", "reset": "RCoil"}.get(el.storage, "Coil")
        c = u.part(name)
        u.connect(s, c.uid, "in")
        u.wires.setdefault(("ident", u.access(self.operand(el.var))), []).append(("name", c.uid, "operand"))
        self.made[el.id] = ("name", c.uid, "out")
        return self.made[el.id]

    def ld_network(self, net: Network) -> None:
        u = self.u
        self.made = {}
        self.joins = {}
        jumps = [e for e in net.elements if e.kind == "jump"]
        if len(jumps) > 1:
            raise Unsupported("больше одного прыжка в сети")
        for el in net.elements:
            if el.kind in ("block", "return", "in_var", "out_var"):
                raise Unsupported(f"элемент LD {el.kind} вне подмножества FlgNet")
        for el in net.elements:
            if el.kind == "coil":
                self.ld_coil(el)
            elif el.kind == "jump":
                j = u.part("Jump")
                u.connect(self.ld_join(el.conns), j.uid, "in")
                u.wires.setdefault(("ident", u.label_access(el.label or "")), []).append(("name", j.uid, "operand"))

    # ----------------------------------------------------------- FBD
    def fsrc(self, conn: Conn) -> tuple[Src, bool, bool]:
        """Источник значения: (провод, отрицание, логический ли результат)."""
        u = self.u
        el = self.els.get(conn.ref)
        if el is None:
            raise Unsupported(f"провод на {conn.ref}")
        if el.kind == "in_var":
            is_bool = self.meta.types.get(el.var or "") == "BOOL"
            return ("ident", u.access(self.operand(el.var))), el.negated, is_bool
        if el.kind != "block":
            raise Unsupported(f"элемент FBD {el.kind} вне подмножества FlgNet")
        t = (el.type_name or "").upper()
        if el.call_type == "functionblock" or el.instance:
            if t not in TIMER_PART:
                raise Unsupported(f"вызов ФБ {el.type_name} вне подмножества FlgNet")
            p = self.fb_part(el)
            pin = conn.formal or "Q"
            if pin.upper() not in ("Q", "ET"):
                raise Unsupported(f"выход {pin} таймера")
            return ("name", p.uid, pin.upper()), False, pin.upper() == "Q"
        if t == "NOT":
            s, neg, b = self.fsrc_pin(el, 0)
            return s, not neg, b
        if t in ("AND", "OR", "XOR"):
            p = u.part({"AND": "A", "OR": "O", "XOR": "X"}[t], templates=[("Card", "Cardinality", str(len(el.inputs)))])
            for i in range(len(el.inputs)):
                s, neg, _ = self.fsrc_pin(el, i)
                pin = f"in{i + 1}"
                u.connect(s, p.uid, pin)
                if neg:
                    p.negated.append(pin)
            return ("name", p.uid, "out"), False, True
        if t in ("GT", "GE", "EQ", "NE", "LE", "LT"):
            op = {"GT": ">", "GE": ">=", "EQ": "=", "NE": "<>", "LE": "<=", "LT": "<"}[t]
            p = u.part(CMP_PART[op], templates=[("SrcType", "Type", self.src_type(self.pin_texts(el)))])
            for i, pin in enumerate(("in1", "in2")):
                s, neg, _ = self.fsrc_pin(el, i)
                if neg:
                    raise Unsupported("отрицание числового входа")
                u.connect(s, p.uid, pin)
            return ("name", p.uid, "out"), False, True
        if t in ARITH_PART:
            name = ARITH_PART[t]
            n = len(el.inputs)
            tmpl = [("SrcType", "Type", self.src_type(self.pin_texts(el)))]
            if name in ("Add", "Mul"):
                tmpl.append(("Card", "Cardinality", str(n)))
            elif n != 2:
                raise Unsupported(f"{t} с {n} входами")
            p = u.part(name, templates=tmpl, disabled_eno=True)
            for i in range(n):
                s, neg, _ = self.fsrc_pin(el, i)
                if neg:
                    raise Unsupported("отрицание числового входа")
                u.connect(s, p.uid, f"in{i + 1}")
            return ("name", p.uid, "out"), False, False
        if t == "MOVE":
            p = u.part("Move", templates=[("Card", "Cardinality", "1")], disabled_eno=True)
            s, neg, _ = self.fsrc_pin(el, 0)
            if neg:
                raise Unsupported("отрицание входа MOVE")
            u.connect(s, p.uid, "in")
            return ("name", p.uid, "out1"), False, False
        raise Unsupported(f"блок {el.type_name} вне подмножества FlgNet")

    def pin_texts(self, el: Element) -> list[str | None]:
        out: list[str | None] = []
        for pin in el.inputs:
            for c in pin.conns:
                src = self.els.get(c.ref)
                if src is not None and src.kind == "in_var":
                    out.append(src.var)
        return out

    def fsrc_pin(self, el: Element, i: int) -> tuple[Src, bool, bool]:
        pin = el.inputs[i]
        if len(pin.conns) != 1:
            raise Unsupported(f"вход {pin.name} блока {el.type_name}: проводов {len(pin.conns)}")
        s, neg, b = self.fsrc(pin.conns[0])
        return s, neg != pin.negated, b

    def fb_part(self, el: Element) -> _Part:
        u = self.u
        made: dict[str, _Part] = getattr(u, "_fb", {})
        if el.id in made:
            return made[el.id]
        inst = self.operand(el.instance)
        kind, comps = _components(inst)
        if kind != "local":
            raise Unsupported("экземпляр таймера не в статике блока")
        t = (el.type_name or "").upper()
        p = u.part(TIMER_PART[t], version="1.0", instance=comps, templates=[("time_type", "Type", "Time")])
        for i, pin in enumerate(el.inputs):
            if not pin.conns:
                continue
            s, neg, _ = self.fsrc_pin(el, i)
            name = pin.name.upper()
            if name not in ("IN", "PT"):
                raise Unsupported(f"вход {pin.name} таймера")
            u.connect(s, p.uid, name)
            if neg:
                p.negated.append(name)
        made[el.id] = p
        u._fb = made  # type: ignore[attr-defined]
        return p

    def fbd_network(self, net: Network) -> None:
        u = self.u
        sinks = 0
        for el in net.elements:
            if el.kind == "out_var":
                if not el.conns:
                    raise Unsupported("выход без входа")
                s, neg, is_bool = self.fsrc(el.conns[0])
                neg = neg != el.negated
                target = self.operand(el.var)
                if s[0] == "name" and not is_bool:
                    if neg:
                        raise Unsupported("отрицание числового выхода")
                    u.to_operand(s, target)
                else:
                    c = u.part("Coil", negated=["in"] if neg else [])
                    u.connect(s, c.uid, "in")
                    u.wires.setdefault(("ident", u.access(target)), []).append(("name", c.uid, "operand"))
                sinks += 1
            elif el.kind == "jump":
                if not el.conns:
                    raise Unsupported("прыжок без входа")
                s, neg, _ = self.fsrc(el.conns[0])
                j = u.part("Jump", negated=["in"] if neg else [])
                u.connect(s, j.uid, "in")
                u.wires.setdefault(("ident", u.label_access(el.label or "")), []).append(("name", j.uid, "operand"))
                sinks += 1
            elif el.kind in ("return", "coil", "contact", "connector", "continuation", "inout_var"):
                raise Unsupported(f"элемент FBD {el.kind} вне подмножества FlgNet")
            elif el.kind == "block" and (el.call_type == "functionblock" or el.instance):
                consumed = any(c.ref == el.id for e in net.elements for p in e.inputs for c in p.conns)
                if not consumed:
                    self.fsrc(Conn(el.id, "Q"))
        if sinks == 0 and not u.parts:
            raise Unsupported("пустая сеть")


# ---------------------------------------------------------------------- блок
class _Ids:
    def __init__(self) -> None:
        self.n = -1

    def next(self) -> str:
        self.n += 1
        return format(self.n, "X")


def _mltext(ids: _Ids, composition: str, text: str) -> str:
    return (
        f'<MultilingualText ID="{ids.next()}" CompositionName="{composition}"><ObjectList>'
        f'<MultilingualTextItem ID="{ids.next()}" CompositionName="Items"><AttributeList>'
        f"<Culture>{CULTURE}</Culture><Text>{escape(text)}</Text></AttributeList></MultilingualTextItem>"
        "</ObjectList></MultilingualText>"
    )


def _member_xml(m: S7Member, retain: bool) -> str:
    if m.raw is not None:
        raise Unsupported(f"член {m.name}: объявление без разбора")
    attrs = f"Name={quoteattr(m.name)} Datatype={quoteattr(m.type if m.struct is None else 'Struct')}"
    if m.attrs.get("LibVersion"):
        attrs += f" Version={quoteattr(m.attrs['LibVersion'])}"
    if retain:
        attrs += ' Remanence="Retain"'
    inner = ""
    if m.comment:
        inner += f'<Comment><MultiLanguageText Lang="{CULTURE}">{escape(m.comment)}</MultiLanguageText></Comment>'
    if m.struct is not None:
        inner += "".join(_member_xml(s, False) for s in m.struct)
    if m.init is not None and m.struct is None:
        inner += f"<StartValue>{escape(m.init)}</StartValue>"
    return f"<Member {attrs}>{inner}</Member>" if inner else f"<Member {attrs} />"


def _interface(blk: S7Block, ns: str) -> tuple[str, set[str]]:
    is_fc = blk.kind == "FUNCTION"
    names = FC_SECTIONS if is_fc else FB_SECTIONS
    by: dict[str, list[str]] = {n: [] for n in names}
    locals_: set[str] = set()
    for sec in blk.sections:
        name = "Constant" if sec.constant else SECTION.get(sec.kind)
        if name == "Static" and is_fc:
            name = "Temp"
        if name is None or name not in by:
            raise Unsupported(f"секция {sec.header}")
        for m in sec.members:
            by[name].append(_member_xml(m, sec.retain))
            locals_.add(m.name.upper())
    if is_fc:
        by["Return"].append(f'<Member Name="Ret_Val" Datatype={quoteattr(blk.return_type or "Void")} />')
        locals_.add(blk.name.upper())
    body = "".join(
        f'<Section Name="{n}">{"".join(by[n])}</Section>' if by[n] else f'<Section Name="{n}" />' for n in names
    )
    return f'<Sections xmlns="{ns}">{body}</Sections>', locals_


def build_block(res: Result, pou: Pou, blk: S7Block, number: int) -> str:
    """Документ SimaticML одного блока; Unsupported — если что-то вне подмножества."""
    if pou.net is None or pou.net.meta is None:
        raise Unsupported("нет NetIR")
    if blk.kind not in ("FUNCTION_BLOCK", "FUNCTION"):
        raise Unsupported(f"{blk.kind} в FlgNet не выдаётся (тело OB — SCL)")
    tia = res.profile.tia
    vers = res.profile.tia_data["versions"][tia]
    nss = res.profile.tia_data["namespaces"]
    ns_if = nss["interface"].format(v=vers["interface"])
    ns_flg = nss["flgnet"].format(v=vers["flgnet"])
    lang = "LAD" if pou.language == "LD" else "FBD"
    iface, locals_ = _interface(blk, ns_if)
    constants = {c.name.upper() for c in res.constants}
    b = _Builder(pou, pou.net.meta, locals_, constants)
    ids = _Ids()
    tag = "SW.Blocks.FC" if blk.kind == "FUNCTION" else "SW.Blocks.FB"
    block_id = ids.next()
    comment = " ".join(blk.comment) if blk.comment else f"{pou.language} {pou.name} → {lang} (c2s7)"
    comment_xml = _mltext(ids, "Comment", comment)
    units: list[str] = []
    for net in pou.net.networks:
        b.els = net.by_id()
        b.u = _Unit(lang, locals_, constants)
        if net.label:
            b.u.labels.append(net.label)
        if pou.language == "LD":
            b.ld_network(net)
        else:
            b.fbd_network(net)
        flg = f'<FlgNet xmlns="{ns_flg}">{b.u.render()}</FlgNet>'
        cu = (
            f'<SW.Blocks.CompileUnit ID="{ids.next()}" CompositionName="CompileUnits"><AttributeList>'
            f"<NetworkSource>{flg}</NetworkSource><ProgrammingLanguage>{lang}</ProgrammingLanguage>"
            "</AttributeList><ObjectList>"
            + _mltext(ids, "Comment", net.comment)
            + _mltext(ids, "Title", net.title)
            + "</ObjectList></SW.Blocks.CompileUnit>"
        )
        units.append(cu)
    attrs = [
        "<AutoNumber>true</AutoNumber>",
        f"<Interface>{iface}</Interface>",
        "<MemoryLayout>Optimized</MemoryLayout>",
    ]
    if blk.kind == "FUNCTION_BLOCK":
        attrs.append("<MemoryReserve>100</MemoryReserve>")
    attrs.append(f"<Name>{escape(blk.name)}</Name>")
    if tia == "V21":
        attrs.append("<Namespace />")
    attrs.append(f"<Number>{number}</Number>")
    attrs.append(f"<ProgrammingLanguage>{lang}</ProgrammingLanguage>")
    attrs.append("<SetENOAutomatically>false</SetENOAutomatically>")
    doc = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<Document><Engineering version="{tia}" />'
        f"<DocumentInfo><Created>{CREATED}</Created><ExportSetting>None</ExportSetting></DocumentInfo>"
        f'<{tag} ID="{block_id}"><AttributeList>{"".join(attrs)}</AttributeList><ObjectList>'
        + comment_xml
        + "".join(units)
        + _mltext(ids, "Title", blk.title or pou.name)
        + f"</ObjectList></{tag}></Document>"
    )
    return pretty(doc)


def pretty(xml: str) -> str:
    from lxml import etree

    root = etree.fromstring(xml.encode("utf-8"))
    etree.indent(root, space="  ")
    body = etree.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + body + "\n"


def emit_all(res: Result) -> dict[str, str]:
    from c2s7.emit.simaticml.validate import validate

    out: dict[str, str] = {}
    number = 0
    for pou in res.project.pous:
        if pou.language not in ("LD", "FBD") or pou.net is None:
            continue
        blk = next(
            (x for x in res.blocks if x.source_pou == pou.name and x.kind in ("FUNCTION_BLOCK", "FUNCTION")), None
        )
        where = pou.impl_origin or pou.origin
        if blk is None:
            res.collector.add("C2S7-GFX-SCL", pou.name, pou.language, where, pou.name, "блок FB/FC не создан (OB)")
            continue
        try:
            number += 1
            xml = build_block(res, pou, blk, number)
            errors = validate(xml, res.profile.tia)
            if errors:
                raise Unsupported("валидатор: " + "; ".join(errors[:3]))
        except Unsupported as exc:
            number -= 1
            res.collector.add("C2S7-GFX-SCL", pou.name, pou.language, where, pou.name, str(exc))
            continue
        path = f"tia/simaticml/{safe(blk.name)}.xml"
        blk.flgnet = path
        out[path] = xml
    return out
