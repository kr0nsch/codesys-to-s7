"""Свой структурный валидатор SimaticML FlgNet (ТЗ §8.3). Включён всегда, XSD — отдельно (`xsd.py`).

Правила (у каждого есть негатив в tests/formats):
- V-ENG: `Engineering version` ∈ версий профиля с SimaticML (V19, V21) и совпадает с целью;
- V-UID: UId уникальны внутри FlgNet;
- V-REF: каждый NameCon/IdentCon ссылается на существующую часть/обращение (IdentCon — на Access);
- V-PIN: имя пина NameCon есть у части (реестр `parts.py`, входы по Card);
- V-ONCE: вход части подключён не больше одного раза;
- V-PART: Part@Name — из реестра;
- V-TEMPLATE: обязательные TemplateValue на месте (TON — time_type, сравнения и арифметика — SrcType,
  A/O/X/Move — Card);
- V-VERSION: Version у частей-экземпляров = реестру, у остальных Version нет;
- V-REACH: в LAD каждая часть достижима от Powerrail;
- V-SCOPE: Access LocalVariable ссылается на член интерфейса блока, GlobalVariable — не на него.
"""

from __future__ import annotations

from typing import Any

from lxml import etree

from c2s7.emit.simaticml.parts import PARTS, input_pins

ENGINEERING = ("V19", "V21")


def _ln(el: Any) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _kids(el: Any, name: str) -> list[Any]:
    return [c for c in el if _ln(c) == name]


def _desc(el: Any, name: str) -> list[Any]:
    return [c for c in el.iter() if _ln(c) == name]


def validate(xml: str, tia: str | None = None) -> list[str]:
    """Список нарушений «правило: описание»; пустой — документ проходит."""
    errors: list[str] = []
    try:
        root = etree.fromstring(xml.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        return [f"V-XML: {exc}"]
    eng = next(iter(_desc(root, "Engineering")), None)
    ver = eng.get("version") if eng is not None else None
    if ver not in ENGINEERING or (tia is not None and ver != tia):
        errors.append(f"V-ENG: Engineering version {ver!r} (ожидается {tia or ENGINEERING})")
    members = {m.get("Name", "").upper() for sec in _desc(root, "Sections") for m in _kids_sections(sec)}
    for block in [b for b in root if _ln(b).startswith("SW.Blocks.")]:
        if _ln(block) == "SW.Blocks.FC":
            name = next((n.text for n in _desc(block, "Name")), None)
            if name:
                members.add(name.upper())
    for cu in _desc(root, "CompileUnit") + [c for c in root.iter() if _ln(c) == "SW.Blocks.CompileUnit"]:
        lang = next((p.text for p in _kids(_kid(cu, "AttributeList"), "ProgrammingLanguage")), "LAD")
        for flg in _desc(cu, "FlgNet"):
            errors.extend(_check_net(flg, lang or "LAD", members))
    return errors


def _kid(el: Any, name: str) -> Any:
    for c in el:
        if _ln(c) == name:
            return c
    return el


def _kids_sections(sections: Any) -> list[Any]:
    out: list[Any] = []
    for sec in _kids(sections, "Section"):
        out.extend(_kids(sec, "Member"))
    return out


def _check_net(flg: Any, lang: str, members: set[str]) -> list[str]:
    errs: list[str] = []
    uids: dict[str, Any] = {}

    def reg(el: Any) -> None:
        u = el.get("UId")
        if u is None:
            return
        if u in uids:
            errs.append(f"V-UID: UId {u} повторяется ({_ln(uids[u])}, {_ln(el)})")
        uids[u] = el

    parts_el = _kid(flg, "Parts")
    for el in parts_el:
        if not isinstance(el.tag, str):
            continue
        reg(el)
        for inst in _kids(el, "Instance"):
            reg(inst)
    for lbl in _desc(flg, "LabelDeclaration"):
        reg(lbl)
    wires = _desc(flg, "Wire")
    for w in wires:
        reg(w)
        for c in w:
            if _ln(c) == "OpenCon":
                reg(c)
    parts = {el.get("UId"): el for el in parts_el if _ln(el) in ("Part", "Call")}
    access = {el.get("UId"): el for el in parts_el if _ln(el) == "Access"}
    # части
    for uid, p in parts.items():
        if _ln(p) != "Part":
            continue
        name = p.get("Name", "")
        spec = PARTS.get(name)
        if spec is None:
            errs.append(f"V-PART: часть {name} (UId {uid}) не из реестра")
            continue
        if lang not in spec.langs:
            errs.append(f"V-PART: часть {name} не для {lang}")
        tv = {t.get("Name"): t.text for t in _kids(p, "TemplateValue")}
        for t in spec.templates:
            if not tv.get(t):
                errs.append(f"V-TEMPLATE: у {name} (UId {uid}) нет TemplateValue {t}")
        v = p.get("Version")
        if spec.version != v:
            errs.append(f"V-VERSION: у {name} (UId {uid}) Version {v!r}, ожидается {spec.version!r}")
        if spec.instance and not _kids(p, "Instance"):
            errs.append(f"V-PART: у {name} (UId {uid}) нет Instance")
    # провода
    seen_in: set[tuple[str, str]] = set()
    edges: dict[str, set[str]] = {}
    rail_targets: set[str] = set()
    for w in wires:
        ends = [c for c in w if isinstance(c.tag, str)]
        if not ends:
            errs.append(f"V-REF: пустой провод {w.get('UId')}")
            continue
        src = ends[0]
        src_uid = src.get("UId") if _ln(src) in ("NameCon", "IdentCon") else None
        for i, c in enumerate(ends):
            kind = _ln(c)
            if kind == "IdentCon":
                if c.get("UId") not in access:
                    errs.append(f"V-REF: IdentCon {c.get('UId')} — нет такого Access")
            elif kind == "NameCon":
                u = c.get("UId")
                pin = c.get("Name", "")
                p = parts.get(u)
                if p is None:
                    errs.append(f"V-REF: NameCon {u} — нет такой части")
                    continue
                if _ln(p) == "Part":
                    spec = PARTS.get(p.get("Name", ""))
                    if spec is not None:
                        card = next((t.text for t in _kids(p, "TemplateValue") if t.get("Name") == "Card"), None)
                        ins = input_pins(spec, int(card) if card and card.isdigit() else None)
                        outs = set(spec.outputs)
                        if pin not in ins | outs:
                            errs.append(f"V-PIN: у {p.get('Name')} (UId {u}) нет пина {pin}")
                        if i > 0 and pin in ins:
                            key = (u, pin)
                            if key in seen_in:
                                errs.append(f"V-ONCE: вход {pin} части UId {u} подключён дважды")
                            seen_in.add(key)
                if i > 0:
                    if _ln(src) == "Powerrail":
                        rail_targets.add(u)
                    elif src_uid is not None:
                        edges.setdefault(src_uid, set()).add(u)
    # достижимость от шины (LAD)
    if lang == "LAD":
        reach = set(rail_targets)
        stack = list(rail_targets)
        while stack:
            cur = stack.pop()
            for nxt in edges.get(cur, ()):
                if nxt not in reach:
                    reach.add(nxt)
                    stack.append(nxt)
        for uid, p in parts.items():
            if uid not in reach:
                errs.append(f"V-REACH: часть {p.get('Name')} (UId {uid}) не достижима от Powerrail")
    # области обращений
    for uid, a in access.items():
        scope = a.get("Scope")
        comps = [c.get("Name", "") for c in _desc(a, "Component")]
        if not comps:
            continue
        head = comps[0].upper()
        if scope == "LocalVariable" and head not in members:
            errs.append(f"V-SCOPE: LocalVariable {comps[0]} (UId {uid}) нет в интерфейсе")
        if scope == "GlobalVariable" and head in members:
            errs.append(f"V-SCOPE: GlobalVariable {comps[0]} (UId {uid}) совпадает с членом интерфейса")
    return errs
