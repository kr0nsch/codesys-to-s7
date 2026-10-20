"""Деревья отображения сетей: LD/LAD — последовательно/параллельно контакты и катушки, FBD — боксы.

Источник — NetIR CODESYS, цель — FlgNet c2s7. Общие элементы DAG при отображении повторяются (дерево),
семантику это не меняет: схема — иллюстрация, проверки — в tests/formats и tests/property.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lxml import etree

from c2s7.ir.netir import Conn, Element, NetBody


@dataclass
class Contact:
    label: str
    neg: bool = False
    edge: str = ""  # P | N | ""


@dataclass
class Series:
    items: list[Any]


@dataclass
class Par:
    items: list[Any]


@dataclass
class Coil:
    label: str
    kind: str = ""  # "" | S | R | / | JMP


@dataclass
class Rung:
    flow: Any
    coils: list[Coil]


@dataclass
class Var:
    text: str
    neg: bool = False


@dataclass
class Box:
    type: str
    inputs: list[tuple[str, Any, bool]] = field(default_factory=list)  # (пин, узел, отрицание)
    instance: str = ""


@dataclass
class Sink:
    label: str
    node: Any
    kind: str = "OUT"  # OUT | JMP | RET
    neg: bool = False


@dataclass
class NetView:
    title: str
    label: str | None
    rungs: list[Rung] = field(default_factory=list)
    sinks: list[Sink] = field(default_factory=list)


# ---------------------------------------------------------------- NetIR (источник)
def _flow(els: dict[str, Element], conns: list[Conn]) -> Any:
    items = [_fnode(els, c.ref) for c in conns]
    items = [i for i in items if i is not None]
    if not items:
        return None
    return items[0] if len(items) == 1 else Par(items)


def _fnode(els: dict[str, Element], ref: str) -> Any:
    el = els.get(ref)
    if el is None or el.kind == "left_rail":
        return None
    if el.kind == "contact":
        me = Contact(el.var or "?", el.negated, {"rising": "P", "falling": "N"}.get(el.edge, ""))
        prev = _flow(els, el.conns)
        if prev is None:
            return me
        return Series([*prev.items, me] if isinstance(prev, Series) else [prev, me])
    if el.kind == "coil":
        return _flow(els, el.conns)
    if el.kind == "block":
        return Contact(f"[{el.type_name}]")
    return Contact(f"<{el.kind}>")


def _fbd_node(els: dict[str, Element], conn: Conn, seen: frozenset[str] = frozenset()) -> tuple[Any, bool]:
    el = els.get(conn.ref)
    if el is None:
        return Var("?"), False
    if el.kind == "in_var":
        return Var(el.var or "?", el.negated), False
    if el.kind == "connector" and el.conns:
        return _fbd_node(els, el.conns[0], seen)
    if el.kind == "block":
        if el.id in seen:  # обратная связь CFC: выход блока прошлого цикла
            return Var(f"↻ {el.type_name}"), False
        ins = []
        for pin in el.inputs:
            if pin.conns:
                node, neg = _fbd_node(els, pin.conns[0], seen | {el.id})
                ins.append((pin.name, node, pin.negated != neg))
        return Box(el.type_name or "?", ins, el.instance or ""), False
    return Var(f"<{el.kind}>"), False


def from_netir(body: NetBody) -> list[NetView]:
    views: list[NetView] = []
    for net in body.networks:
        els = net.by_id()
        v = NetView(net.title, net.label)
        if body.language == "LD":
            groups: dict[tuple[str, ...], list[Element]] = {}
            for el in net.elements:
                if el.kind in ("coil", "jump", "return"):
                    groups.setdefault(tuple(sorted(c.ref for c in el.conns)), []).append(el)
            for key, coils in groups.items():
                cs = [
                    Coil(
                        e.var or e.label or "RET",
                        "JMP"
                        if e.kind == "jump"
                        else "RET"
                        if e.kind == "return"
                        else {"set": "S", "reset": "R"}.get(e.storage, "/" if e.negated else ""),
                    )
                    for e in coils
                ]
                v.rungs.append(Rung(_flow(els, [Conn(r) for r in key]), cs))
        else:
            for el in net.elements:
                if el.kind in ("out_var", "jump", "return") and el.conns:
                    node, neg = _fbd_node(els, el.conns[0])
                    kind = {"out_var": "OUT", "jump": "JMP", "return": "RET"}[el.kind]
                    v.sinks.append(Sink(el.var or el.label or "", node, kind, neg != el.negated))
                elif (
                    el.kind == "block"
                    and el.instance
                    and not any(c.ref == el.id for e in net.elements for p in e.inputs for c in p.conns)
                ):
                    node, _ = _fbd_node(els, Conn(el.id))
                    v.sinks.append(Sink(el.instance, node, "CALL"))
        views.append(v)
    return views


# ---------------------------------------------------------------- FlgNet (цель)
def _ln(el: Any) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


class _Flg:
    def __init__(self, flg: Any) -> None:
        parts_el = next(c for c in flg if _ln(c) == "Parts")
        self.parts = {p.get("UId"): p for p in parts_el if _ln(p) == "Part"}
        self.access = {a.get("UId"): a for a in parts_el if _ln(a) == "Access"}
        self.inputs: dict[tuple[str, str], Any] = {}
        self.outs: dict[str, list[tuple[str, Any]]] = {}
        for w in (c for c in flg.iter() if _ln(c) == "Wire"):
            ends = [c for c in w if isinstance(c.tag, str)]
            for t in ends[1:]:
                if _ln(t) == "NameCon":
                    self.inputs[(t.get("UId"), t.get("Name"))] = ends[0]
                elif _ln(t) == "IdentCon" and _ln(ends[0]) == "NameCon":
                    self.outs.setdefault(ends[0].get("UId"), []).append((ends[0].get("Name"), t))

    def text(self, a: Any) -> str:
        comps = [c.get("Name") for c in a.iter() if _ln(c) == "Component"]
        if comps:
            return ".".join(comps)
        lbl = next((c.get("Name") for c in a.iter() if _ln(c) == "Label"), None)
        if lbl:
            return str(lbl)
        val = next((c.text for c in a.iter() if _ln(c) == "ConstantValue"), None)
        name = next((c.get("Name") for c in a.iter() if _ln(c) == "Constant" and c.get("Name")), None)
        return val or name or "?"

    def neg(self, uid: str, pin: str) -> bool:
        return any(n.get("Name") == pin for n in self.parts[uid] if _ln(n) == "Negated")

    def operand(self, uid: str, pin: str = "operand") -> str:
        src = self.inputs.get((uid, pin))
        return self.text(self.access[src.get("UId")]) if src is not None and _ln(src) == "IdentCon" else "?"

    def lad(self, end: Any) -> Any:
        if end is None or _ln(end) == "Powerrail":
            return None
        uid = end.get("UId")
        p = self.parts.get(uid)
        if p is None:
            return None
        name = p.get("Name")
        prev = self.lad(self.inputs.get((uid, "in")))
        me: Any
        if name == "Contact":
            me = Contact(self.operand(uid), self.neg(uid, "operand"))
        elif name in ("PBox", "NBox"):
            me = Contact(self.operand(uid, "bit"), False, name[0])
        elif name == "Not":
            me = Contact("NOT")
        elif name == "O":
            card = int(next((t.text for t in p if _ln(t) == "TemplateValue" and t.get("Name") == "Card"), "2") or 2)
            items = [self.lad(self.inputs.get((uid, f"in{i}"))) for i in range(1, card + 1)]
            return Par([i if i is not None else Series([]) for i in items])
        else:
            me = Contact(f"[{name}]")
        if prev is None:
            return me
        return Series([*prev.items, me] if isinstance(prev, Series) else [prev, me])

    def fbd(self, end: Any) -> tuple[Any, bool]:
        if end is None:
            return Var("?"), False
        if _ln(end) == "IdentCon":
            return Var(self.text(self.access[end.get("UId")])), False
        return self.fbd_part(end.get("UId")), False

    def fbd_part(self, uid: str) -> Any:
        p = self.parts[uid]
        name = p.get("Name")
        inst = next(
            (".".join(c.get("Name") for c in i if _ln(c) == "Component") for i in p if _ln(i) == "Instance"), ""
        )
        ins = []
        for (u, pin), src in sorted(self.inputs.items(), key=lambda kv: kv[0][1]):
            if u != uid or pin in ("en", "operand", "pre"):
                continue
            node, neg = self.fbd(src)
            ins.append((pin, node, self.neg(uid, pin) != neg))
        return Box(name, ins, inst)


def from_flgnet(xml: str) -> list[NetView]:
    root = etree.fromstring(xml.encode("utf-8"))
    views: list[NetView] = []
    for cu in (c for c in root.iter() if _ln(c) == "SW.Blocks.CompileUnit"):
        flg = next((c for c in cu.iter() if _ln(c) == "FlgNet"), None)
        lang = next((c.text for c in cu.iter() if _ln(c) == "ProgrammingLanguage"), "LAD")
        title = ""
        for mt in (c for c in cu.iter() if _ln(c) == "MultilingualText" and c.get("CompositionName") == "Title"):
            title = next((t.text or "" for t in mt.iter() if _ln(t) == "Text"), "")
        if flg is None:
            continue
        f = _Flg(flg)
        label = next(
            (c.get("Name") for c in flg.iter() if _ln(c) == "Label" and _ln(c.getparent()) == "LabelDeclaration"), None
        )
        v = NetView(title, label)
        coil_names = {"Coil": "", "SCoil": "S", "RCoil": "R", "Jump": "JMP"}
        if lang == "LAD":
            groups: dict[str, tuple[Any, list[Coil]]] = {}
            for uid in sorted(f.parts, key=int):
                p = f.parts[uid]
                if p.get("Name") not in coil_names:
                    continue
                src = f.inputs.get((uid, "in"))
                key = "rail" if src is None or _ln(src) == "Powerrail" else f"{src.get('UId')}:{src.get('Name')}"
                flow = f.lad(src)
                if (
                    isinstance(flow, Series)
                    and flow.items
                    and isinstance(flow.items[-1], Contact)
                    and flow.items[-1].label == "NOT"
                ):
                    kind = "/"
                    flow = Series(flow.items[:-1]) if len(flow.items) > 2 else flow.items[0]
                    key += ":not"
                else:
                    kind = coil_names[p.get("Name")]
                coil = Coil(f.operand(uid), kind)
                groups.setdefault(key, (flow, []))[1].append(coil)
            v.rungs = [Rung(flow, coils) for flow, coils in groups.values()]
        else:
            for uid in sorted(f.parts, key=int):
                p = f.parts[uid]
                name = p.get("Name")
                if name in ("Coil", "SCoil", "RCoil", "Jump"):
                    node, neg = f.fbd(f.inputs.get((uid, "in")))
                    v.sinks.append(
                        Sink(f.operand(uid), node, "JMP" if name == "Jump" else "OUT", neg != f.neg(uid, "in"))
                    )
                for _pin, ident in f.outs.get(uid, []):
                    v.sinks.append(Sink(f.text(f.access[ident.get("UId")]), f.fbd_part(uid), "OUT"))
        views.append(v)
    return views
