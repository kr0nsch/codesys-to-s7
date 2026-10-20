"""PLCopen XML CODESYS 3.5 (tc6_0200/tc6_0201, BOM) → модель проекта c2s7.

Размещения POU (канон plcopen-diff §4/§7): types/pous; resource/addData/data[…/pou] (полный экспорт);
project/addData/data[…/application]/resource (экспорт Application CODESYS 3.5.17). Объявления — из
addData interfaceasplaintext, если он есть, иначе из стандартного <interface>. Тела: ST, IL (текст),
LD/FBD (NetIR), CFC в addData (NetIR), SFC (SfcIR). Формы — docs/FORMAT-CODESYS.md.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from lxml import etree

from c2s7.ingest.common import IngestError, split_doc
from c2s7.ir.netir import Conn, Element, NetBody, Network, Pin
from c2s7.ir.sfcir import ActionAssoc, SfcBody, SfcStep, SfcTransition
from c2s7.model import Action, Dut, Gvl, Library, Origin, Pou, Project, Property, Task
from c2s7.st import nodes as A
from c2s7.st import parser as P

S3 = "http://www.3s-software.com/plcopenxml/"
SECTION_TAGS = {
    "inputVars": "VAR_INPUT",
    "outputVars": "VAR_OUTPUT",
    "inOutVars": "VAR_IN_OUT",
    "localVars": "VAR",
    "tempVars": "VAR_TEMP",
    "externalVars": "VAR_EXTERNAL",
    "globalVars": "VAR_GLOBAL",
}
POU_KIND = {"program": "PROGRAM", "functionBlock": "FUNCTION_BLOCK", "function": "FUNCTION"}
SFC_NAME = "38391c6d-6d4a-42f8-8ee7-9f45e5adafa8"
SFC_STEP_ACTION = "700a583f-b4d4-43e4-8c14-629c7cd3bec8"
NET_STRIDE = 10_000_000_000


def _ln(el: Any) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _kids(el: Any, name: str) -> list[Any]:
    return [c for c in el if isinstance(c.tag, str) and _ln(c) == name]


def _kid(el: Any, name: str) -> Any:
    for c in el:
        if isinstance(c.tag, str) and _ln(c) == name:
            return c
    return None


def _desc(el: Any, name: str) -> list[Any]:
    return [c for c in el.iter() if isinstance(c.tag, str) and _ln(c) == name]


def _data(el: Any, suffix: str) -> list[Any]:
    """addData/data[@name=…/suffix] (прямые дети addData)."""
    out: list[Any] = []
    add = _kid(el, "addData")
    if add is None:
        return out
    for d in _kids(add, "data"):
        if (d.get("name") or "").endswith("/plcopenxml/" + suffix):
            out.append(d)
    return out


def _text(el: Any) -> str:
    if el is None:
        return ""
    x = _kid(el, "xhtml")
    if x is not None:
        return "".join(x.itertext())
    return "".join(el.itertext())


class PlcOpenReader:
    def __init__(self, path: Path, rel: str) -> None:
        self.path = path
        self.rel = rel
        raw = path.read_bytes()
        try:
            self.root = etree.fromstring(raw, parser=etree.XMLParser(remove_blank_text=False, huge_tree=True))
        except etree.XMLSyntaxError as exc:
            raise IngestError(f"{rel}: XML не разобран: {exc}") from None
        if _ln(self.root) != "project":
            raise IngestError(f"{rel}: корень не <project> (PLCopen XML)")
        self.sha = hashlib.sha256(raw).hexdigest()

    def origin(self, el: Any, local_id: str | None = None) -> Origin:
        return Origin(self.rel, getattr(el, "sourceline", None), None, local_id)

    # ------------------------------------------------------------ сбор
    def project(self) -> Project:
        root = self.root
        header = _kid(root, "fileHeader")
        prod = header.get("productVersion", "") if header is not None else ""
        proj = Project(name=self.path.stem, kind="plcopen-xml", path=self.rel, sha256=self.sha)
        proj.ide = header.get("productName", "CODESYS") if header is not None else "CODESYS"
        proj.ide_version = "3.5.17.30" if "SP17 Patch 3" in prod else prod
        pou_els: list[tuple[Any, list[str]]] = []
        dut_els: list[Any] = []
        gvl_els: list[Any] = []
        task_els: list[Any] = []
        lib_els: list[Any] = []
        types = _kid(root, "types")
        if types is not None:
            pous = _kid(types, "pous")
            if pous is not None:
                pou_els.extend((p, []) for p in _kids(pous, "pou"))
            dts = _kid(types, "dataTypes")
            if dts is not None:
                dut_els.extend(_kids(dts, "dataType"))
        resources: list[Any] = []
        inst = _kid(root, "instances")
        if inst is not None:
            for cfgs in _kids(inst, "configurations"):
                for cfg in _kids(cfgs, "configuration"):
                    resources.extend(_kids(cfg, "resource"))
                    gvl_els.extend(_kids(cfg, "globalVars"))
        for d in _data(root, "application"):
            resources.extend(_kids(d, "resource"))
        for d in _data(root, "globalvars"):
            gvl_els.extend(_kids(d, "globalVars"))
        for res in resources:
            task_els.extend(_kids(res, "task"))
            gvl_els.extend(_kids(res, "globalVars"))
            for d in _data(res, "pou"):
                pou_els.extend((p, []) for p in _kids(d, "pou"))
            for d in _data(res, "datatype"):
                dut_els.extend(_kids(d, "dataType"))
            for d in _data(res, "libraries"):
                lib_els.extend(_desc(d, "Library"))
        for el in dut_els:
            proj.duts.append(self.dut(el))
        for el in gvl_els:
            proj.gvls.append(self.gvl(el))
        for el, folder in pou_els:
            proj.pous.append(self.pou(el, folder))
        for t in task_els:
            proj.tasks.append(self.task(t))
        for lib in lib_els:
            proj.libraries.append(
                Library(lib.get("Name", ""), lib.get("Namespace", ""), lib.get("DefaultResolution", ""))
            )
        return proj

    # ------------------------------------------------------------ объявления
    def plaintext(self, el: Any) -> str | None:
        for d in _data(el, "interfaceasplaintext"):
            node = _kid(d, "InterfaceAsPlainText")
            return _text(node) if node is not None else None
        return None

    def type_ref(self, tel: Any) -> A.TypeRef:
        """<type> (дети: элементарный тип, string, array, derived, pointer) → TypeRef."""
        child = next((c for c in tel if isinstance(c.tag, str)), None)
        if child is None:
            return A.NamedType("BOOL")
        name = _ln(child)
        if name in ("string", "wstring"):
            length = child.get("length")
            return A.StringType(name == "wstring", A.Literal("int", length, int(length)) if length else None)
        if name == "array":
            dims: list[tuple[A.Expr, A.Expr] | None] = []
            for d in _kids(child, "dimension"):
                lo, hi = d.get("lower", "0"), d.get("upper", "0")
                dims.append((P.parse_expr(lo), P.parse_expr(hi)))
            base = _kid(child, "baseType")
            return A.ArrayType(dims, self.type_ref(base) if base is not None else A.NamedType("BOOL"))
        if name == "derived":
            return A.NamedType(child.get("name", ""))
        if name == "pointer":
            base = _kid(child, "baseType")
            return A.PointerType(self.type_ref(base) if base is not None else A.NamedType("BYTE"))
        if name in ("subrangeSigned", "subrangeUnsigned"):
            rng = _kid(child, "range")
            base = _kid(child, "baseType")
            bname = self.type_ref(base) if base is not None else A.NamedType("INT")
            return A.SubrangeType(
                bname.name if isinstance(bname, A.NamedType) else "INT",
                P.parse_expr(rng.get("lower", "0")),
                P.parse_expr(rng.get("upper", "0")),
            )
        return A.NamedType(name)

    def init(self, vel: Any) -> A.Expr | None:
        iv = _kid(vel, "initialValue")
        if iv is None:
            return None
        return self._value(next(c for c in iv if isinstance(c.tag, str)))

    def _value(self, el: Any) -> A.Expr:
        name = _ln(el)
        if name == "simpleValue":
            return P.parse_init(el.get("value", "0"))
        if name == "arrayValue":
            elems = []
            for v in _kids(el, "value"):
                inner = next((c for c in v if isinstance(c.tag, str)), None)
                rep = v.get("repetitionValue")
                elems.append(
                    A.ArrayInitElem(self._value(inner) if inner is not None else None, int(rep) if rep else None)
                )
            return A.ArrayInit(elems)
        if name == "structValue":
            fields = []
            for v in _kids(el, "value"):
                inner = next((c for c in v if isinstance(c.tag, str)), None)
                if inner is not None:
                    fields.append((v.get("member", ""), self._value(inner)))
            return A.StructInit(fields)
        return P.parse_init(el.get("value", "0"))

    def var_decls(self, sec: Any) -> list[A.VarDecl]:
        out = []
        for v in _kids(sec, "variable"):
            tel = _kid(v, "type")
            doc = _kid(v, "documentation")
            out.append(
                A.VarDecl(
                    v.get("name", ""),
                    self.type_ref(tel) if tel is not None else A.NamedType("BOOL"),
                    self.init(v),
                    address=v.get("address"),
                    comment=_text(doc).strip() or None if doc is not None else None,
                    pos=(getattr(v, "sourceline", 0) or 0, 1),
                )
            )
        return out

    def blocks_from_interface(self, iface: Any) -> list[A.VarBlock]:
        blocks: list[A.VarBlock] = []
        if iface is None:
            return blocks
        for sec in iface:
            if not isinstance(sec.tag, str):
                continue
            kind = SECTION_TAGS.get(_ln(sec))
            if kind is None:
                continue
            quals = [q.upper() for q in ("retain", "persistent", "constant") if sec.get(q) == "true"]
            blocks.append(A.VarBlock(kind, quals, self.var_decls(sec)))
        return blocks

    # ------------------------------------------------------------ объекты
    def dut(self, el: Any) -> Dut:
        name = el.get("name", "")
        text = self.plaintext(el)
        if text:
            decl = P.parse_type(text, self.rel)
            doc, _ = split_doc(text)
            return Dut(name, decl, self.origin(el), doc=doc)
        base = _kid(el, "baseType")
        child = next((c for c in base if isinstance(c.tag, str)), None) if base is not None else None
        t: A.TypeRef
        init = None
        if child is not None and _ln(child) in ("struct", "union"):
            t = A.StructType(self.var_decls(child), union=_ln(child) == "union")
        elif child is not None and _ln(child) == "enum":
            vals = []
            values = _kid(child, "values")
            for v in _kids(values, "value") if values is not None else []:
                val = v.get("value")
                vals.append((v.get("name", ""), P.parse_expr(val) if val else None))
            bt = _kid(child, "baseType")
            bname = self.type_ref(bt) if bt is not None else None
            t = A.EnumType(vals, bname.name if isinstance(bname, A.NamedType) else None)
        elif base is not None:
            t = self.type_ref(base)
        else:
            t = A.NamedType("INT")
        iv = _kid(el, "initialValue")
        if iv is not None:
            init = self._value(next(c for c in iv if isinstance(c.tag, str)))
        return Dut(name, A.TypeDecl(name, t, init), self.origin(el))

    def gvl(self, el: Any) -> Gvl:
        name = el.get("name", "")
        text = self.plaintext(el)
        persistent_list = el.get("persistent") == "true" and not _data(el, "mixedattrsvarlist")
        if text:
            parsed = P.parse_gvl(text, self.rel)
            doc, _ = split_doc(text)
            return Gvl(name, parsed, self.origin(el), persistent_list=persistent_list, doc=doc)
        blocks: list[A.VarBlock] = []
        mixed = _data(el, "mixedattrsvarlist")
        if mixed:
            for gv in _desc(mixed[0], "globalVars"):
                quals = [q.upper() for q in ("retain", "persistent", "constant") if gv.get(q) == "true"]
                blocks.append(A.VarBlock("VAR_GLOBAL", quals, self.var_decls(gv)))
        else:
            quals = [q.upper() for q in ("retain", "persistent", "constant") if el.get(q) == "true"]
            blocks.append(A.VarBlock("VAR_GLOBAL", quals, self.var_decls(el)))
        attrs = []
        for d in _data(el, "attributes"):
            for a in _desc(d, "Attribute"):
                attrs.append(f"attribute '{a.get('Name')}'")
        return Gvl(name, A.GvlText(blocks, attrs), self.origin(el), persistent_list=persistent_list)

    def pou(self, el: Any, folder: list[str]) -> Pou:
        name = el.get("name", "")
        kind = POU_KIND.get(el.get("pouType", "functionBlock"), "FUNCTION_BLOCK")
        text = self.plaintext(el)
        if text:
            pt = P.parse_pou(text, self.rel)
            doc, _ = split_doc(text)
        else:
            iface = _kid(el, "interface")
            rt = None
            if iface is not None and _kid(iface, "returnType") is not None:
                rt = self.type_ref(_kid(iface, "returnType"))
            pt = A.PouText(A.PouHeader(kind, name, return_type=rt), self.blocks_from_interface(iface), [])
            doc = []
        body = _kid(el, "body")
        pou = Pou(name, kind, "ST", pt, self.origin(el), folder=folder, doc=doc)
        if body is not None:
            self.read_body(body, pou)
        acts = _kid(el, "actions")
        if acts is not None:
            for a in _kids(acts, "action"):
                ab = _kid(a, "body")
                act = Action(a.get("name", ""), "ST", origin=self.origin(a))
                if ab is not None:
                    st = _kid(ab, "ST")
                    il = _kid(ab, "IL")
                    if st is not None:
                        act.body, _ = P.parse_body(_text(st), self.rel)
                    elif il is not None:
                        act.language, act.il = "IL", _text(il)
                    else:
                        act.language = "graphic"
                pou.actions.append(act)
        for d in _data(el, "method"):
            for m in _kids(d, "Method"):
                mtext = self.plaintext(m)
                if mtext:
                    mt = P.parse_pou(mtext, self.rel)
                else:
                    iface = _kid(m, "interface")
                    rt_el = _kid(iface, "returnType") if iface is not None else None
                    mt = A.PouText(
                        A.PouHeader(
                            "METHOD", m.get("name", ""), return_type=self.type_ref(rt_el) if rt_el is not None else None
                        ),
                        self.blocks_from_interface(iface),
                        [],
                    )
                mb = _kid(m, "body")
                st = _kid(mb, "ST") if mb is not None else None
                if st is not None:
                    mt.body, _ = P.parse_body(_text(st), self.rel)
                pou.methods.append(mt)
        for d in _data(el, "property"):
            for pr in _kids(d, "Property"):
                iface = _kid(pr, "interface")
                rt_el = _kid(iface, "returnType") if iface is not None else None
                prop = Property(pr.get("name", ""), self.type_ref(rt_el) if rt_el is not None else A.NamedType("INT"))
                for acc, attr in (("GetAccessor", "get_body"), ("SetAccessor", "set_body")):
                    a = _kid(pr, acc)
                    if a is not None:
                        ab = _kid(a, "body")
                        st = _kid(ab, "ST") if ab is not None else None
                        setattr(prop, attr, P.parse_body(_text(st), self.rel)[0] if st is not None else [])
                pou.properties.append(prop)
        return pou

    def read_body(self, body: Any, pou: Pou) -> None:
        st = _kid(body, "ST")
        cfc = None
        for d in _data(body, "cfc"):
            cfc = _kid(d, "CFC")
        if cfc is not None:
            pou.language = "CFC"
            pou.net = self.net(cfc, "CFC")
            return
        if st is not None:
            text = _text(st)
            pou.text.body, pou.text.tail = P.parse_body(text, self.rel)
            pou.impl_origin = Origin(self.rel, getattr(st, "sourceline", None))
            return
        il = _kid(body, "IL")
        if il is not None:
            pou.language = "IL"
            pou.il = _text(il)
            pou.impl_origin = Origin(self.rel, getattr(il, "sourceline", None))
            return
        for lang in ("LD", "FBD"):
            g = _kid(body, lang)
            if g is not None:
                pou.language = lang
                pou.net = self.net(g, lang)
                return
        sfc = _kid(body, "SFC")
        if sfc is not None:
            pou.language = "SFC"
            pou.sfc = self.sfc(sfc)
            return

    # ------------------------------------------------------------ сети
    def element(self, el: Any) -> Element | None:
        tag = _ln(el)
        lid = el.get("localId", "")
        line = getattr(el, "sourceline", None)
        if tag == "leftPowerRail":
            return Element(lid, "left_rail", line=line)
        if tag == "rightPowerRail":
            return Element(lid, "right_rail", line=line)
        if tag in ("contact", "coil"):
            var = _kid(el, "variable")
            return Element(
                lid,
                tag,
                var=(var.text or "").strip() if var is not None else None,
                negated=el.get("negated") == "true",
                edge=el.get("edge", "none"),
                storage=el.get("storage", "none"),
                inputs=[Pin("in", self.conns(_kid(el, "connectionPointIn")))],
                line=line,
            )
        if tag in ("inVariable", "outVariable", "inOutVariable"):
            expr = _kid(el, "expression")
            kind = {"inVariable": "in_var", "outVariable": "out_var", "inOutVariable": "inout_var"}[tag]
            inputs = [Pin("in", self.conns(_kid(el, "connectionPointIn")))] if kind != "in_var" else []
            order = el.get("executionOrderId")
            return Element(
                lid,
                kind,
                var=(expr.text or "").strip() if expr is not None else None,
                negated=el.get("negated") == "true",
                inputs=inputs,
                order=int(order) if order else None,
                line=line,
            )
        if tag == "block":
            inputs = []
            iv = _kid(el, "inputVariables")
            for v in _kids(iv, "variable") if iv is not None else []:
                inputs.append(
                    Pin(
                        v.get("formalParameter", ""),
                        self.conns(_kid(v, "connectionPointIn")),
                        v.get("negated") == "true",
                    )
                )
            outs = []
            ov = _kid(el, "outputVariables")
            for v in _kids(ov, "variable") if ov is not None else []:
                outs.append(v.get("formalParameter", ""))
            call_type = None
            for suffix in ("fbdcalltype", "cfccalltype"):
                for d in _data(el, suffix):
                    ct = _kid(d, "CallType")
                    if ct is not None:
                        call_type = (ct.text or "").strip()
            order = el.get("executionOrderId")
            return Element(
                lid,
                "block",
                type_name=el.get("typeName"),
                instance=el.get("instanceName"),
                call_type=call_type,
                inputs=inputs,
                outputs=outs,
                order=int(order) if order else None,
                line=line,
            )
        if tag in ("jump", "return"):
            order = el.get("executionOrderId")
            return Element(
                lid,
                tag,
                label=el.get("label"),
                negated=el.get("negated") == "true",
                inputs=[Pin("in", self.conns(_kid(el, "connectionPointIn")))],
                order=int(order) if order else None,
                line=line,
            )
        if tag == "label":
            return Element(lid, "label", label=el.get("label"), line=line)
        if tag == "connector":
            return Element(
                lid,
                "connector",
                var=el.get("name"),
                inputs=[Pin("in", self.conns(_kid(el, "connectionPointIn")))],
                line=line,
            )
        if tag == "continuation":
            return Element(lid, "continuation", var=el.get("name"), line=line)
        return None

    @staticmethod
    def conns(cp: Any) -> list[Conn]:
        if cp is None:
            return []
        return [Conn(c.get("refLocalId", ""), c.get("formalParameter")) for c in _kids(cp, "connection")]

    def net(self, g: Any, lang: str) -> NetBody:
        body = NetBody(lang)
        if lang == "CFC":
            body.pages = 1 if g.get("page-oriented") == "true" else 0
            net = Network(1)
            for el in g:
                if not isinstance(el.tag, str):
                    continue
                e = self.element(el)
                if e is not None:
                    net.elements.append(e)
            body.networks.append(net)
            return body
        if lang == "FBD":
            nets: dict[int, Network] = {}
            for el in g:
                if not isinstance(el.tag, str):
                    continue
                lid = el.get("localId", "0")
                idx = int(lid) // NET_STRIDE if lid.isdigit() else 0
                net = nets.setdefault(idx, Network(idx))
                if _ln(el) == "vendorElement":
                    t = self._vendor_title(el)
                    if t is not None:
                        net.title = t
                    continue
                if _ln(el) == "comment":
                    net.comment = _text(_kid(el, "content")).strip()
                    continue
                e = self.element(el)
                if e is not None:
                    if e.kind == "label":
                        net.label = e.label
                    net.elements.append(e)
            body.networks = [nets[k] for k in sorted(nets)]
            return body
        # LD: сеть начинается comment + vendorElement networktitle; шина — общая
        current: Network | None = None
        rails: list[Element] = []
        pending_comment = ""
        for el in g:
            if not isinstance(el.tag, str):
                continue
            tag = _ln(el)
            if tag == "comment":
                pending_comment = _text(_kid(el, "content")).strip()
                continue
            if tag == "vendorElement":
                t = self._vendor_title(el)
                if t is not None:
                    current = Network(len(body.networks) + 1, title=t, comment=pending_comment)
                    current.elements.extend(rails)
                    body.networks.append(current)
                    pending_comment = ""
                continue
            e = self.element(el)
            if e is None:
                continue
            if e.kind in ("left_rail", "right_rail"):
                rails.append(e)
                for n in body.networks:
                    n.elements.append(e)
                continue
            if current is None:
                current = Network(1)
                current.elements.extend(rails)
                body.networks.append(current)
            if e.kind == "label":
                current.label = e.label
            current.elements.append(e)
        return body

    @staticmethod
    def _vendor_title(el: Any) -> str | None:
        for d in _data(el, "fbdelementtype"):
            et = _kid(d, "ElementType")
            if et is not None and (et.text or "").strip() == "networktitle":
                return _text(_kid(el, "alternativeText")).strip()
        return None

    # ------------------------------------------------------------ SFC
    def sfc(self, g: Any) -> SfcBody:
        els = {e.get("localId", ""): e for e in g if isinstance(e.tag, str) and e.get("localId") is not None}
        order = [e.get("localId", "") for e in g if isinstance(e.tag, str) and e.get("localId") is not None]

        def preds(el: Any) -> list[str]:
            out: list[str] = []
            for cp in _kids(el, "connectionPointIn"):
                out.extend(c.get("refLocalId", "") for c in _kids(cp, "connection"))
            return out

        succ: dict[str, list[str]] = {lid: [] for lid in els}
        for lid, el in els.items():
            for p in preds(el):
                if p in succ:
                    succ[p].append(lid)
        body = SfcBody()
        steps_by_id: dict[str, SfcStep] = {}
        for lid in order:
            el = els[lid]
            tag = _ln(el)
            if tag == "step":
                st = SfcStep(el.get("name", ""), el.get("initialStep") == "true", local_id=lid)
                for d in _data(el, "sfc/element"):
                    for a in _desc(d, "attribute"):
                        if a.get("guid") == SFC_STEP_ACTION and (a.text or "").strip():
                            st.step_action = (a.text or "").strip()
                steps_by_id[lid] = st
                body.steps.append(st)
        for lid in order:
            el = els[lid]
            if _ln(el) == "actionBlock":
                owner = next((p for p in preds(el) if p in steps_by_id), None)
                if owner is None:
                    continue
                for a in _kids(el, "action"):
                    ref = _kid(a, "reference")
                    steps_by_id[owner].actions.append(
                        ActionAssoc(
                            a.get("qualifier", "N"),
                            ref.get("name", "") if ref is not None else "",
                            a.get("duration", ""),
                            a.get("indicator", ""),
                        )
                    )

        def back(lid: str) -> list[str]:
            el = els.get(lid)
            if el is None:
                return []
            tag = _ln(el)
            if tag == "step":
                return [el.get("name", "")]
            if tag in (
                "selectionDivergence",
                "simultaneousConvergence",
                "selectionConvergence",
                "simultaneousDivergence",
            ):
                out: list[str] = []
                for p in preds(el):
                    out.extend(back(p))
                return out
            return []

        def fwd(lid: str) -> list[str]:
            out: list[str] = []
            for s in succ.get(lid, []):
                el = els[s]
                tag = _ln(el)
                if tag == "step":
                    out.append(el.get("name", ""))
                elif tag == "jumpStep":
                    out.append(el.get("targetName", ""))
                elif tag in ("simultaneousDivergence", "selectionConvergence"):
                    out.extend(fwd(s))
            return out

        n = 0
        for lid in order:
            el = els[lid]
            if _ln(el) != "transition":
                continue
            cond_el = _kid(el, "condition")
            cond: A.Expr = A.Literal("bool", "FALSE", False)
            text = ""
            if cond_el is not None:
                inline = _kid(cond_el, "inline")
                ref = _kid(cond_el, "reference")
                cp = _kid(cond_el, "connectionPointIn")
                if inline is not None:
                    text = _text(_kid(inline, "ST") or inline).strip().rstrip(";")
                elif cp is not None:
                    src = next((c.get("refLocalId") for c in _kids(cp, "connection")), None)
                    src_el = els.get(src or "")
                    if src_el is not None and _ln(src_el) == "inVariable":
                        text = (_kid(src_el, "expression").text or "").strip()
                elif ref is not None:
                    text = ref.get("name", "")
            if text:
                cond = P.parse_expr(text, self.rel)
            body.transitions.append(
                SfcTransition(lid, cond, back(preds(el)[0]) if preds(el) else [], fwd(lid), n, text)
            )
            n += 1
        return body

    def task(self, t: Any) -> Task:
        name = t.get("name", "")
        prio = int(t.get("priority", "1") or 1)
        kind = "cyclic"
        interval: float | None = None
        for d in _data(t, "tasksettings"):
            ts = _kid(d, "TaskSettings")
            if ts is not None:
                kot = (ts.get("KindOfTask") or "Cyclic").lower()
                kind = {"cyclic": "cyclic", "freewheeling": "freewheeling", "event": "event", "status": "status"}.get(
                    kot, kot
                )
                iv = ts.get("Interval")
                unit = (ts.get("IntervalUnit") or "ms").lower()
                if iv and kind == "cyclic":
                    interval = _interval_ms(iv, unit)
        if interval is None and kind == "cyclic" and t.get("interval"):
            interval = _iso_ms(t.get("interval", ""))
        pous = [p.get("name", "") for p in _kids(t, "pouInstance")]
        return Task(name, kind, interval, prio, pous)


def _interval_ms(value: str, unit: str) -> float:
    v = value.strip().lower()
    if v.startswith("t#"):
        from c2s7.st import literals as L

        return L.parse_duration_ns(v[2:]) / 1e6
    num = float(v)
    return {"us": num / 1000, "ms": num, "s": num * 1000}.get(unit, num)


def _iso_ms(text: str) -> float | None:
    import re

    m = re.match(r"^PT(?:(\d+(?:\.\d+)?)S)?$", text)
    if m and m.group(1):
        return float(m.group(1)) * 1000
    return None


def load_plcopen(path: Path, base: Path | None = None) -> Project:
    path = path.resolve()
    base = (base or path.parent).resolve()
    try:
        rel = path.relative_to(base).as_posix()
    except ValueError:
        rel = path.name
    proj = PlcOpenReader(path, rel).project()
    proj.root = str(base)
    return proj
