"""DSL корпуса → PLCopen XML в форме экспорта CODESYS 3.5.17 (tc6_0200, BOM).

Описание POU в `corpus/<язык>/<кейс>/spec.py` строится из классов этого модуля; `build_xml()` пишет
файл, который CODESYS принимает через `import_xml` (проба M0). Формы элементов взяты из собственных
экспортов CODESYS 3.5.17.30 на этой машине (docs/FORMAT-CODESYS.md):
- POU и DUT — `types/pous`, `types/dataTypes`; объявление дублируется текстом в addData
  `interfaceasplaintext` (CODESYS предпочитает его при импорте);
- GVL — `project/addData/data[globalvars]` с `MixedAttrsVarList` для RETAIN/PERSISTENT;
- LD/FBD — стандартные `<LD>`/`<FBD>`, все `position` = 0,0, сети — `localId div 10^10`;
- CFC — пустой `<ST>` и `addData/data[cfc]/<CFC>` с `executionOrderId`;
- SFC — стандартный `<SFC>`, действия шагов — атрибут `700a583f…` (по публичным экспортам);
- IL — стандартный `<IL>` (CODESYS при выключенной опции IL его пропускает — проба).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from xml.sax.saxutils import escape, quoteattr

NS = "http://www.plcopen.org/xml/tc6_0200"
XHTML = "http://www.w3.org/1999/xhtml"
S3 = "http://www.3s-software.com/plcopenxml/"
PRODUCT_VERSION = "CODESYS V3.5 SP17 Patch 3"
FIXED_TIME = "2026-10-19T00:00:00"
NET_STRIDE = 10_000_000_000

# GUID атрибутов элементов SFC (публичные экспорты CODESYS/TwinCAT, см. FORMAT-CODESYS.md)
SFC_NAME = "38391c6d-6d4a-42f8-8ee7-9f45e5adafa8"
SFC_INITIAL = "6844a48e-46c2-4cc8-a185-a478f3b99cc0"
SFC_STEP_ACTION = "700a583f-b4d4-43e4-8c14-629c7cd3bec8"
SFC_QUALIFIER = "e174fc0d-80b0-4a9e-a530-ca239c249a50"

# ---------------------------------------------------------------------------
# Переменные и объекты
# ---------------------------------------------------------------------------

SECTION_TAG = {
    "VAR_INPUT": "inputVars",
    "VAR_OUTPUT": "outputVars",
    "VAR_IN_OUT": "inOutVars",
    "VAR": "localVars",
    "VAR_TEMP": "tempVars",
    "VAR_EXTERNAL": "externalVars",
    "VAR_GLOBAL": "globalVars",
}


@dataclass
class V:
    """Переменная: имя, тип ST, секция, начальное значение (текст ST), адрес, комментарий."""

    name: str
    type: str
    section: str = "VAR"
    init: str | None = None
    address: str | None = None
    comment: str | None = None
    qualifiers: tuple[str, ...] = ()


@dataclass
class Gvl:
    name: str
    vars: list[V]
    qualified_only: bool = True
    doc: str = ""


@dataclass
class Dut:
    """DUT: текст ST целиком (TYPE ... END_TYPE) и структура для XML (тип и члены)."""

    name: str
    text: str


# ---- тела ----


@dataclass
class St:
    text: str


@dataclass
class Il:
    text: str


# LD
@dataclass
class Contact:
    var: str
    neg: bool = False
    edge: str | None = None  # rising | falling


@dataclass
class Coil:
    var: str
    neg: bool = False
    storage: str | None = None  # set | reset


@dataclass
class Series:
    items: list[LdElem]

    def __init__(self, *items: LdElem) -> None:
        self.items = list(items)


@dataclass
class Parallel:
    branches: list[LdElem]

    def __init__(self, *branches: LdElem) -> None:
        self.branches = list(branches)


@dataclass
class Box:
    """Блок в LD/FBD: тип, экземпляр ФБ, входы (имя → выражение), выходы (имя → переменная)."""

    type: str
    inst: str | None = None
    inputs: dict[str, FbdExpr] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    negated: tuple[str, ...] = ()
    call_type: str | None = None  # operator | function | functionblock (по умолчанию — по наличию inst)
    en: bool = False
    eno: str | None = None  # переменная, куда идёт ENO (только FBD); в LD ENO продолжает цепь
    out_pin: str = "Out1"
    out_pins: tuple[str, ...] = ()  # выходы экземпляра ФБ, на которые ссылаются FbOut


LdElem = Contact | Coil | Series | Parallel | Box


@dataclass
class Rung:
    elem: LdElem
    title: str = ""
    comment: str = ""
    label: str | None = None


@dataclass
class LdJump:
    target: str
    cond: LdElem | None = None
    title: str = ""
    label: str | None = None


@dataclass
class LdReturn:
    cond: LdElem | None = None
    title: str = ""
    label: str | None = None


@dataclass
class Ld:
    networks: list[Rung | LdJump | LdReturn]


# FBD
@dataclass
class In:
    expr: str


@dataclass
class FbOut:
    """Выход экземпляра ФБ, объявленного блоком `Box(inst=...)` в той же сети."""

    inst: str
    pin: str


FbdExpr = In | Box | FbOut


@dataclass
class Out:
    var: str
    expr: FbdExpr
    negated: bool = False


@dataclass
class Call:
    """Вызов ФБ без присваивания выхода (выходы читаются через FbOut или в других сетях)."""

    box: Box


@dataclass
class FbdJump:
    target: str
    cond: FbdExpr | None = None
    negated: bool = False


@dataclass
class FbdReturn:
    cond: FbdExpr | None = None
    negated: bool = False


@dataclass
class Network:
    items: list[Out | Call | FbdJump | FbdReturn]
    title: str = ""
    comment: str = ""
    label: str | None = None


@dataclass
class Fbd:
    networks: list[Network]


# CFC
@dataclass
class CfcIn:
    id: str
    expr: str


@dataclass
class CfcBlock:
    id: str
    type: str
    order: int
    inputs: dict[str, str | tuple[str, str]] = field(default_factory=dict)  # пин → id или (id, пин)
    outputs: tuple[str, ...] = ("Out1",)
    inst: str | None = None
    call_type: str | None = None
    negated: tuple[str, ...] = ()
    page: int = 0


@dataclass
class CfcOut:
    id: str
    var: str
    src: str | tuple[str, str]
    order: int
    page: int = 0


@dataclass
class Cfc:
    nodes: list[CfcIn | CfcBlock | CfcOut]
    pages: int = 0  # 0 — обычный CFC, N — page-oriented c N страницами


# SFC
@dataclass
class Act:
    qualifier: str
    action: str
    duration: str = ""
    indicator: str = ""


@dataclass
class Step:
    name: str
    initial: bool = False
    actions: list[Act] = field(default_factory=list)
    step_action: str | None = None


@dataclass
class Trans:
    cond: str


@dataclass
class Alt:
    branches: list[list[SfcItem]]


@dataclass
class Par:
    branches: list[list[SfcItem]]


@dataclass
class JumpTo:
    target: str


SfcItem = Step | Trans | Alt | Par | JumpTo


@dataclass
class Sfc:
    seq: list[SfcItem]


@dataclass
class Action:
    name: str
    body: St


@dataclass
class Method:
    name: str
    return_type: str | None
    vars: list[V]
    body: St
    access: str = ""


@dataclass
class Property:
    name: str
    type: str
    get: St | None = None
    set: St | None = None


Body = St | Il | Ld | Fbd | Cfc | Sfc


@dataclass
class Pou:
    name: str
    kind: str  # program | functionBlock | function
    body: Body
    vars: list[V] = field(default_factory=list)
    return_type: str | None = None
    doc: str = ""
    actions: list[Action] = field(default_factory=list)
    methods: list[Method] = field(default_factory=list)
    properties: list[Property] = field(default_factory=list)
    extends: str | None = None

    @property
    def language(self) -> str:
        if isinstance(self.body, Cfc):
            return "CFC"
        return type(self.body).__name__.upper()


@dataclass
class TaskSpec:
    name: str
    interval_ms: int | None
    priority: int
    pous: list[str]
    kind: str = "cyclic"  # cyclic | freewheeling


@dataclass
class Case:
    """Кейс корпуса: объекты, задачи и описание."""

    name: str
    pous: list[Pou] = field(default_factory=list)
    gvls: list[Gvl] = field(default_factory=list)
    duts: list[Dut] = field(default_factory=list)
    tasks: list[TaskSpec] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Типы ST → XML PLCopen
# ---------------------------------------------------------------------------

ELEMENTARY = {
    "BOOL",
    "BYTE",
    "WORD",
    "DWORD",
    "LWORD",
    "SINT",
    "USINT",
    "INT",
    "UINT",
    "DINT",
    "UDINT",
    "LINT",
    "ULINT",
    "REAL",
    "LREAL",
    "TIME",
    "LTIME",
    "DATE",
    "TOD",
    "DT",
    "TIME_OF_DAY",
    "DATE_AND_TIME",
}
_ARRAY = re.compile(r"^ARRAY\s*\[(.+?)\]\s*OF\s+(.+)$", re.IGNORECASE | re.DOTALL)
_STRING = re.compile(r"^(W?STRING)\s*(?:[(\[]\s*(\d+)\s*[)\]])?$", re.IGNORECASE)


def type_xml(text: str) -> str:
    t = text.strip()
    up = t.upper()
    if up in ELEMENTARY:
        return f"<{_canon_elem(up)} />"
    m = _STRING.match(t)
    if m:
        tag = "wstring" if m.group(1).upper() == "WSTRING" else "string"
        return f'<{tag} length="{m.group(2)}" />' if m.group(2) else f"<{tag} />"
    m = _ARRAY.match(t)
    if m:
        dims = "".join(
            f'<dimension lower="{a.strip()}" upper="{b.strip()}" />'
            for a, b in (d.split("..") for d in m.group(1).split(","))
        )
        return f"<array>{dims}<baseType>{type_xml(m.group(2))}</baseType></array>"
    if up.startswith("POINTER TO "):
        return f"<pointer><baseType>{type_xml(t[11:])}</baseType></pointer>"
    return f"<derived name={quoteattr(t)} />"


def _canon_elem(up: str) -> str:
    return {"TIME_OF_DAY": "TOD", "DATE_AND_TIME": "DT"}.get(up, up)


def var_xml(v: V) -> str:
    attrs = f" name={quoteattr(v.name)}"
    if v.address:
        attrs += f" address={quoteattr(v.address)}"
    out = [f"<variable{attrs}><type>{type_xml(v.type)}</type>"]
    if v.init is not None:
        out.append(f"<initialValue><simpleValue value={quoteattr(v.init)} /></initialValue>")
    if v.comment:
        out.append(f'<documentation><xhtml xmlns="{XHTML}">{escape(v.comment)}</xhtml></documentation>')
    out.append("</variable>")
    return "".join(out)


def decl_text(header: str, vars_: list[V]) -> str:
    """Объявление ST: заголовок и секции в порядке первого появления."""
    lines = [header]
    order: list[tuple[str, tuple[str, ...]]] = []
    groups: dict[tuple[str, tuple[str, ...]], list[V]] = {}
    for v in vars_:
        key = (v.section, v.qualifiers)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(v)
    for key in order:
        sec, quals = key
        lines.append(" ".join([sec, *quals]))
        for v in groups[key]:
            at = f" AT {v.address}" if v.address else ""
            init = f" := {v.init}" if v.init is not None else ""
            com = f" // {v.comment}" if v.comment else ""
            lines.append(f"    {v.name}{at} : {v.type}{init};{com}")
        lines.append("END_VAR")
    return "\n".join(lines) + "\n"


def interface_xml(vars_: list[V], return_type: str | None) -> str:
    parts: list[str] = []
    if return_type:
        parts.append(f"<returnType>{type_xml(return_type)}</returnType>")
    order: list[tuple[str, tuple[str, ...]]] = []
    groups: dict[tuple[str, tuple[str, ...]], list[V]] = {}
    for v in vars_:
        key = (v.section, v.qualifiers)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(v)
    for sec, quals in order:
        tag = SECTION_TAG[sec]
        qa = "".join(f' {q.lower()}="true"' for q in quals)
        parts.append(f"<{tag}{qa}>" + "".join(var_xml(v) for v in groups[(sec, quals)]) + f"</{tag}>")
    return "<interface>" + "".join(parts) + "</interface>"


def plaintext_data(text: str) -> str:
    return (
        f'<data name="{S3}interfaceasplaintext" handleUnknown="implementation"><InterfaceAsPlainText>'
        f'<xhtml xmlns="{XHTML}">{escape(text)}</xhtml></InterfaceAsPlainText></data>'
    )


def xhtml(text: str) -> str:
    return f'<xhtml xmlns="{XHTML}">{escape(text)}</xhtml>'


# ---------------------------------------------------------------------------
# Сети LD/FBD
# ---------------------------------------------------------------------------


class _Ids:
    def __init__(self, net: int) -> None:
        self.base = net * NET_STRIDE
        self.n = 0

    def next(self) -> int:
        self.n += 1
        return self.base + self.n


def _pos() -> str:
    return '<position x="0" y="0" />'


def _cp_in(refs: Iterable[tuple[int, str | None]]) -> str:
    conns = "".join(f'<connection refLocalId="{r}"' + (f' formalParameter="{p}"' if p else "") + " />" for r, p in refs)
    return f"<connectionPointIn>{conns}</connectionPointIn>"


def _call_type(box: Box) -> str:
    if box.call_type:
        return box.call_type
    if box.inst:
        return "functionblock"
    if box.type.upper() in _OPERATORS:
        return "operator"
    return "function"


_OPERATORS = {
    "AND",
    "OR",
    "XOR",
    "NOT",
    "ADD",
    "SUB",
    "MUL",
    "DIV",
    "MOD",
    "MOVE",
    "SEL",
    "MUX",
    "LIMIT",
    "MIN",
    "MAX",
    "GT",
    "GE",
    "EQ",
    "NE",
    "LE",
    "LT",
    "ABS",
    "SQRT",
    "EXPT",
    "SHL",
    "SHR",
    "ROL",
    "ROR",
}


def _block_xml(
    lid: int,
    box: Box,
    inputs: list[tuple[str, list[tuple[int, str | None]], bool]],
    outputs: list[str],
    order: int | None = None,
    calltype_name: str = "fbdcalltype",
) -> str:
    inst = f" instanceName={quoteattr(box.inst)}" if box.inst else ""
    eo = f' executionOrderId="{order}"' if order is not None else ""
    ins = "".join(
        f'<variable formalParameter="{name}"' + (' negated="true"' if neg else "") + f">{_cp_in(refs)}</variable>"
        for name, refs, neg in inputs
    )
    outs = "".join(f'<variable formalParameter="{name}"><connectionPointOut /></variable>' for name in outputs)
    add = (
        f'<addData><data name="{S3}{calltype_name}" handleUnknown="implementation">'
        f'<CallType xmlns="">{_call_type(box)}</CallType></data>'
    )
    if calltype_name == "fbdcalltype":
        add += (
            f'<data name="{S3}inputparamtypes" handleUnknown="implementation"><InputParamTypes xmlns="" /></data>'
            f'<data name="{S3}outputparamtypes" handleUnknown="implementation"><OutputParamTypes xmlns="" /></data>'
        )
    add += "</addData>"
    return (
        f'<block localId="{lid}"{eo} typeName={quoteattr(box.type)}{inst}>{_pos()}<inputVariables>{ins}</inputVariables>'
        f"<inOutVariables /><outputVariables>{outs}</outputVariables>{add}</block>"
    )


def _network_title(lid: int, title: str) -> str:
    return (
        f'<vendorElement localId="{lid}">{_pos()}<alternativeText>{xhtml(title)}</alternativeText>'
        f'<addData><data name="{S3}fbdelementtype" handleUnknown="implementation">'
        f'<ElementType xmlns="">networktitle</ElementType></data></addData></vendorElement>'
    )


def _comment(lid: int, text: str) -> str:
    return f'<comment localId="{lid}" height="0" width="0">{_pos()}<content>{xhtml(text)}</content></comment>'


class _FbdNet:
    """Сборка одной сети FBD: выражения → элементы с localId."""

    def __init__(self, net: int) -> None:
        self.ids = _Ids(net)
        self.parts: list[str] = []
        self.fb_ids: dict[str, int] = {}

    def expr(self, e: FbdExpr) -> tuple[int, str | None]:
        if isinstance(e, In):
            lid = self.ids.next()
            self.parts.append(
                f'<inVariable localId="{lid}">{_pos()}<connectionPointOut /><expression>{escape(e.expr)}</expression></inVariable>'
            )
            return lid, None
        if isinstance(e, FbOut):
            return self.fb_ids[e.inst], e.pin
        return self.box(e)

    def box(self, b: Box) -> tuple[int, str | None]:
        inputs: list[tuple[str, list[tuple[int, str | None]], bool]] = []
        for name, src in b.inputs.items():
            inputs.append((name, [self.expr(src)], name in b.negated))
        lid = self.ids.next()
        outputs = list(dict.fromkeys([*b.out_pins, *b.outputs])) or [b.out_pin]
        if b.en:
            inputs.insert(0, ("EN", [], False))
            outputs.insert(0, "ENO")
        self.parts.append(_block_xml(lid, b, inputs, outputs))
        if b.inst:
            self.fb_ids[b.inst] = lid
        for pin, var in b.outputs.items():
            oid = self.ids.next()
            self.parts.append(
                f'<outVariable localId="{oid}">{_pos()}{_cp_in([(lid, pin)])}<expression>{escape(var)}</expression></outVariable>'
            )
        if b.eno:
            oid = self.ids.next()
            self.parts.append(
                f'<outVariable localId="{oid}">{_pos()}{_cp_in([(lid, "ENO")])}<expression>{escape(b.eno)}</expression></outVariable>'
            )
        return lid, (b.out_pin if not b.inst else None)


def _fbd_body(fbd: Fbd) -> str:
    parts: list[str] = []
    first = True
    for idx, net in enumerate(fbd.networks):
        n = _FbdNet(idx + 1)
        if first:
            lid0 = n.ids.base
            parts.append(
                f'<vendorElement localId="{lid0}">{_pos()}<alternativeText>{xhtml("FBD Implementation Attributes")}</alternativeText>'
                f'<addData><data name="{S3}fbd/implementationattributes" handleUnknown="implementation">'
                f'<fbdattributes xmlns=""><attribute name="BoxInputFlagsSupported" value="true" /></fbdattributes>'
                f"</data></addData></vendorElement>"
            )
            first = False
        else:
            n.parts.append(_network_title(n.ids.base, net.title))
        if net.comment:
            n.parts.append(_comment(n.ids.next(), net.comment))
        if net.label:
            n.parts.append(f'<label localId="{n.ids.next()}" label={quoteattr(net.label)}>{_pos()}</label>')
        for item in net.items:
            if isinstance(item, Out):
                src = n.expr(item.expr)
                lid = n.ids.next()
                neg = ' negated="true"' if item.negated else ""
                n.parts.append(
                    f'<outVariable localId="{lid}"{neg}>{_pos()}{_cp_in([src])}<expression>{escape(item.var)}</expression></outVariable>'
                )
            elif isinstance(item, Call):
                n.box(item.box)
            elif isinstance(item, FbdJump | FbdReturn):
                cond = item.cond
                if cond is not None and item.negated:
                    cond = Box("NOT", inputs={"In1": cond})
                refs = [n.expr(cond)] if cond is not None else []
                lid = n.ids.next()
                if isinstance(item, FbdJump):
                    n.parts.append(
                        f'<jump localId="{lid}" label={quoteattr(item.target)}>{_pos()}{_cp_in(refs)}</jump>'
                    )
                else:
                    n.parts.append(f'<return localId="{lid}">{_pos()}{_cp_in(refs)}</return>')
        parts.extend(n.parts)
    return "<FBD>" + "".join(parts) + "</FBD>"


class _LdNet:
    def __init__(self, net: int) -> None:
        self.ids = _Ids(net)
        self.parts: list[str] = []

    def elem(self, e: LdElem, inp: list[tuple[int, str | None]]) -> list[tuple[int, str | None]]:
        """Элемент с входами-проводами inp; возвращает выходы (для последовательного соединения)."""
        if isinstance(e, Contact):
            lid = self.ids.next()
            edge = e.edge or "none"
            self.parts.append(
                f'<contact localId="{lid}" negated="{str(e.neg).lower()}" storage="none" edge="{edge}">{_pos()}'
                f"{_cp_in(inp)}<connectionPointOut /><variable>{escape(e.var)}</variable></contact>"
            )
            return [(lid, None)]
        if isinstance(e, Coil):
            lid = self.ids.next()
            storage = e.storage or "none"
            self.parts.append(
                f'<coil localId="{lid}" negated="{str(e.neg).lower()}" storage="{storage}">{_pos()}'
                f"{_cp_in(inp)}<connectionPointOut /><variable>{escape(e.var)}</variable></coil>"
            )
            return [(lid, None)]
        if isinstance(e, Series):
            cur = inp
            for it in e.items:
                cur = self.elem(it, cur)
            return cur
        if isinstance(e, Parallel):
            outs: list[tuple[int, str | None]] = []
            for br in e.branches:
                outs.extend(self.elem(br, inp))
            return outs
        if isinstance(e, Box):
            inputs: list[tuple[str, list[tuple[int, str | None]], bool]] = [("EN", inp, False)]
            fn = _FbdNet(0)
            fn.ids = self.ids
            fn.parts = self.parts
            for name, src in e.inputs.items():
                inputs.append((name, [fn.expr(src)], name in e.negated))
            lid = self.ids.next()
            outputs = (
                ["ENO", *dict.fromkeys([*e.out_pins, *e.outputs])] if (e.outputs or e.out_pins) else ["ENO", e.out_pin]
            )
            self.parts.append(_block_xml(lid, e, inputs, outputs))
            for pin, var in e.outputs.items():
                oid = self.ids.next()
                self.parts.append(
                    f'<outVariable localId="{oid}">{_pos()}{_cp_in([(lid, pin)])}<expression>{escape(var)}</expression></outVariable>'
                )
            return [(lid, "ENO")]
        raise TypeError(e)


def _ld_body(ld: Ld) -> str:
    """LD в форме экспорта CODESYS: одна левая шина (localId 0), сквозная нумерация, сеть начинается
    парой comment + vendorElement networktitle (так CODESYS 3.5.17.30 экспортирует LD)."""
    parts: list[str] = [
        '<leftPowerRail localId="0">' + _pos() + '<connectionPointOut formalParameter="none" /></leftPowerRail>'
    ]
    n = _LdNet(0)
    for net in ld.networks:
        n.parts = []
        n.parts.append(_comment(n.ids.next(), getattr(net, "comment", "")))
        n.parts.append(_network_title(n.ids.next(), net.title))
        if net.label:
            n.parts.append(f'<label localId="{n.ids.next()}" label={quoteattr(net.label)}>{_pos()}</label>')
        start: list[tuple[int, str | None]] = [(0, None)]
        if isinstance(net, Rung):
            n.elem(net.elem, start)
        elif isinstance(net, LdJump):
            src = n.elem(net.cond, start) if net.cond is not None else start
            n.parts.append(f'<jump localId="{n.ids.next()}" label={quoteattr(net.target)}>{_pos()}{_cp_in(src)}</jump>')
        elif isinstance(net, LdReturn):
            src = n.elem(net.cond, start) if net.cond is not None else start
            n.parts.append(f'<return localId="{n.ids.next()}">{_pos()}{_cp_in(src)}</return>')
        parts.extend(n.parts)
    parts.append(f'<rightPowerRail localId="2147483646">{_pos()}<connectionPointIn /></rightPowerRail>')
    return "<LD>" + "".join(parts) + "</LD>"


# ---------------------------------------------------------------------------
# CFC
# ---------------------------------------------------------------------------


def _cfc_body(cfc: Cfc) -> str:
    ids: dict[str, int] = {}
    for i, node in enumerate(cfc.nodes):
        ids[node.id] = i + 1 + (1 if cfc.pages else 0) * 10

    counter = [len(cfc.nodes) + 1 + (10 if cfc.pages else 0)]
    connectors: list[str] = []

    def ref(src: str | tuple[str, str]) -> tuple[int, str | None]:
        """Провод CFC идёт через connector: источник (пин или выражение входа) → connector → вход."""
        node = next(x for x in cfc.nodes if x.id == (src[0] if isinstance(src, tuple) else src))
        formal: str | None
        if isinstance(node, CfcBlock):
            # у оператора и функции выход в CFC без имени (formalParameter=""), у ФБ — имя пина
            fb = node.inst is not None or node.call_type == "functionblock"
            formal = (src[1] if isinstance(src, tuple) else node.outputs[0]) if fb else ""
        else:
            formal = node.expr if isinstance(node, CfcIn) else None
        cid = counter[0]
        counter[0] += 1
        conn = (
            f'<connection refLocalId="{ids[node.id]}"'
            + (f" formalParameter={quoteattr(formal)}" if formal is not None else "")
            + " />"
        )
        connectors.append(
            f'<connector localId="{cid}" name="">{_pos()}<connectionPointIn>{conn}</connectionPointIn><connectionPointOut /></connector>'
        )
        return cid, None

    parts: list[str] = []
    if cfc.pages:
        for p in range(cfc.pages):
            parts.append(
                f'<vendorElement localId="{p}">{_pos()}<alternativeText>{xhtml("page")}</alternativeText>'
                f'<addData><data name="{S3}cfcpage" handleUnknown="implementation">'
                f'<page name="" description="" marginwidth="12" width="72" height="96" index="{p}" xmlns="" />'
                f"</data></addData></vendorElement>"
            )
    for node in cfc.nodes:
        lid = ids[node.id]
        if isinstance(node, CfcIn):
            parts.append(
                f'<inVariable localId="{lid}">{_pos()}<connectionPointOut><expression /></connectionPointOut>'
                f"<expression>{escape(node.expr)}</expression></inVariable>"
            )
        elif isinstance(node, CfcBlock):
            box = Box(node.type, inst=node.inst, call_type=node.call_type)
            inputs = [(pin, [ref(src)], pin in node.negated) for pin, src in node.inputs.items()]
            parts.append(
                _block_xml(lid, box, inputs, list(node.outputs), order=node.order, calltype_name="cfccalltype")
            )
        elif isinstance(node, CfcOut):
            parts.append(
                f'<outVariable localId="{lid}" executionOrderId="{node.order}">{_pos()}{_cp_in([ref(node.src)])}'
                f"<expression>{escape(node.var)}</expression></outVariable>"
            )
    head = '<CFC page-oriented="true">' if cfc.pages else "<CFC>"
    return (
        f'<ST><xhtml xmlns="{XHTML}" /></ST><addData><data name="{S3}cfc" handleUnknown="implementation">'
        + head
        + "".join(parts)
        + "".join(connectors)
        + "</CFC></data></addData>"
    )


# ---------------------------------------------------------------------------
# SFC
# ---------------------------------------------------------------------------


def _sfc_attrs(pairs: list[tuple[str, str]]) -> str:
    inner = "".join(f'<attribute guid="{g}">{escape(v)}</attribute>' for g, v in pairs)
    return f'<addData><data name="{S3}sfc/element" handleUnknown="implementation"><attributes xmlns="">{inner}</attributes></data></addData>'


class _SfcBuild:
    def __init__(self) -> None:
        self.n = -1
        self.parts: list[str] = []

    def nid(self) -> int:
        self.n += 1
        return self.n

    def seq(self, items: list[SfcItem], inp: list[tuple[int, str | None]]) -> list[tuple[int, str | None]]:
        cur = inp
        for it in items:
            cur = self.item(it, cur)
        return cur

    def item(self, it: SfcItem, inp: list[tuple[int, str | None]]) -> list[tuple[int, str | None]]:
        if isinstance(it, Step):
            lid = self.nid()
            init = ' initialStep="true"' if it.initial else ""
            attrs = [(SFC_NAME, it.name), (SFC_INITIAL, "TRUE" if it.initial else "FALSE")]
            if it.step_action:
                attrs.append((SFC_STEP_ACTION, it.step_action))
            cp_in = _cp_in(inp) if inp else "<connectionPointIn />"
            out_action = '<connectionPointOutAction formalParameter="x" />' if it.actions else ""
            self.parts.append(
                f'<step localId="{lid}"{init} name={quoteattr(it.name)}>{_pos()}{cp_in}'
                f'<connectionPointOut formalParameter="sfc" />{out_action}{_sfc_attrs(attrs)}</step>'
            )
            if it.actions:
                blk = self.nid()
                acts = []
                for a in it.actions:
                    aid = self.nid()
                    acts.append(
                        f'<action localId="{aid}" qualifier="{a.qualifier}" duration={quoteattr(a.duration)} indicator={quoteattr(a.indicator)}>'
                        f'<relPosition x="0" y="0" /><reference name={quoteattr(a.action)} /><connectionPointOut />'
                        f"{_sfc_attrs([(SFC_NAME, a.action), (SFC_QUALIFIER, a.qualifier)])}</action>"
                    )
                self.parts.append(
                    f'<actionBlock localId="{blk}">{_pos()}{_cp_in([(lid, None)])}{"".join(acts)}</actionBlock>'
                )
            return [(lid, "sfc")]
        if isinstance(it, Trans):
            cond_id = self.nid()
            self.parts.append(
                f'<inVariable localId="{cond_id}">{_pos()}<connectionPointOut /><expression>{escape(it.cond)}</expression></inVariable>'
            )
            lid = self.nid()
            self.parts.append(
                f'<transition localId="{lid}">{_pos()}{_cp_in(inp)}<condition>{_cp_in([(cond_id, None)])}</condition>'
                f"{_sfc_attrs([(SFC_NAME, it.cond)])}</transition>"
            )
            return [(lid, None)]
        if isinstance(it, JumpTo):
            lid = self.nid()
            self.parts.append(
                f'<jumpStep localId="{lid}" targetName={quoteattr(it.target)}>{_pos()}{_cp_in(inp)}'
                f"{_sfc_attrs([(SFC_NAME, it.target)])}</jumpStep>"
            )
            return []
        if isinstance(it, Alt | Par):
            tag = "selection" if isinstance(it, Alt) else "simultaneous"
            div = self.nid()
            outs = '<connectionPointOut formalParameter="sfc" />' * len(it.branches)
            name = ' name=""' if tag == "simultaneous" else ""
            self.parts.append(f'<{tag}Divergence{name} localId="{div}">{_pos()}{_cp_in(inp)}{outs}</{tag}Divergence>')
            ends: list[list[tuple[int, str | None]]] = []
            for br in it.branches:
                ends.append(self.seq(br, [(div, None)]))
            live = [e for e in ends if e]
            if not live:
                return []
            conv = self.nid()
            cps = "".join(_cp_in(e) for e in live)
            self.parts.append(
                f'<{tag}Convergence localId="{conv}">{_pos()}{cps}<connectionPointOut /></{tag}Convergence>'
            )
            return [(conv, None)]
        raise TypeError(it)


def _sfc_body(sfc: Sfc) -> str:
    b = _SfcBuild()
    b.seq(sfc.seq, [])
    return "<SFC>" + "".join(b.parts) + "</SFC>"


# ---------------------------------------------------------------------------
# POU, GVL, DUT, проект
# ---------------------------------------------------------------------------


def pou_header(p: Pou) -> str:
    kw = {"program": "PROGRAM", "functionBlock": "FUNCTION_BLOCK", "function": "FUNCTION"}[p.kind]
    head = f"{kw} {p.name}"
    if p.extends:
        head += f" EXTENDS {p.extends}"
    if p.return_type:
        head += f" : {p.return_type}"
    if p.doc:
        head = "\n".join(f"// {line}" if line else "//" for line in p.doc.strip().splitlines()) + "\n" + head
    return head


def body_xml(body: Body) -> str:
    if isinstance(body, St):
        return f"<ST>{xhtml(body.text)}</ST>"
    if isinstance(body, Il):
        return f"<IL>{xhtml(body.text)}</IL>"
    if isinstance(body, Ld):
        return _ld_body(body)
    if isinstance(body, Fbd):
        return _fbd_body(body)
    if isinstance(body, Cfc):
        return _cfc_body(body)
    if isinstance(body, Sfc):
        return _sfc_body(body)
    raise TypeError(body)


def pou_xml(p: Pou) -> str:
    out = [f'<pou name={quoteattr(p.name)} pouType="{p.kind}">', interface_xml(p.vars, p.return_type)]
    if p.actions:
        out.append("<actions>")
        for a in p.actions:
            out.append(f"<action name={quoteattr(a.name)}><body>{body_xml(a.body)}</body><addData /></action>")
        out.append("</actions>")
    out.append(f"<body>{body_xml(p.body)}</body>")
    add = [plaintext_data(decl_text(pou_header(p), p.vars))]
    for m in p.methods:
        head = f"METHOD {m.access + ' ' if m.access else ''}{m.name}" + (f" : {m.return_type}" if m.return_type else "")
        add.append(
            f'<data name="{S3}method" handleUnknown="implementation"><Method name={quoteattr(m.name)}>'
            f"{interface_xml(m.vars, m.return_type)}<body>{body_xml(m.body)}</body>"
            f"<addData>{plaintext_data(decl_text(head, m.vars))}</addData></Method></data>"
        )
    for pr in p.properties:
        acc = []
        if pr.set is not None:
            acc.append(f"<SetAccessor><interface /><body>{body_xml(pr.set)}</body><addData /></SetAccessor>")
        if pr.get is not None:
            acc.append(f"<GetAccessor><interface /><body>{body_xml(pr.get)}</body><addData /></GetAccessor>")
        add.append(
            f'<data name="{S3}property" handleUnknown="implementation"><Property name={quoteattr(pr.name)}>'
            f"<interface><returnType>{type_xml(pr.type)}</returnType></interface>{''.join(acc)}<addData /></Property></data>"
        )
    out.append("<addData>" + "".join(add) + "</addData>")
    out.append("</pou>")
    return "".join(out)


def gvl_xml(g: Gvl) -> str:
    def block_text() -> str:
        head = "{attribute 'qualified_only'}\n" if g.qualified_only else ""
        groups: dict[tuple[str, ...], list[V]] = {}
        for v in g.vars:
            groups.setdefault(v.qualifiers, []).append(v)
        chunks = []
        for quals, vs in groups.items():
            chunks.append(
                decl_text(
                    "", [V(x.name, x.type, " ".join(["VAR_GLOBAL", *quals]), x.init, x.address, x.comment) for x in vs]
                ).lstrip("\n")
            )
        return head + "".join(chunks)

    mixed = []
    groups2: dict[tuple[str, ...], list[V]] = {}
    for v in g.vars:
        groups2.setdefault(v.qualifiers, []).append(v)
    for quals, vs in groups2.items():
        qa = "".join(f' {q.lower()}="true"' for q in quals if q in ("RETAIN", "PERSISTENT", "CONSTANT"))
        mixed.append(f"<globalVars name={quoteattr(g.name)}{qa}>" + "".join(var_xml(v) for v in vs) + "</globalVars>")
    attrs = (
        f'<data name="{S3}attributes" handleUnknown="implementation"><Attributes>'
        f'<Attribute Name="qualified_only" Value="" /></Attributes></data>'
        if g.qualified_only
        else ""
    )
    return (
        f"<globalVars name={quoteattr(g.name)}>"
        + "".join(var_xml(v) for v in g.vars)
        + "<addData>"
        + attrs
        + f'<data name="{S3}mixedattrsvarlist" handleUnknown="implementation"><MixedAttrsVarList>'
        + "".join(mixed)
        + "</MixedAttrsVarList></data>"
        # GVL с секцией PERSISTENT и текстом объявления CODESYS 3.5.17 импортирует как список
        # Persistent Variables (все переменные становятся постоянными, проба M0) — текст не пишем
        + ("" if any("PERSISTENT" in v.qualifiers for v in g.vars) else plaintext_data(block_text()))
        + "</addData></globalVars>"
    )


def dut_xml(d: Dut) -> str:
    """DUT: тип в XML строится по тексту (STRUCT, ENUM, alias); текст — в interfaceasplaintext."""
    base = _dut_base_xml(d.text)
    return f"<dataType name={quoteattr(d.name)}><baseType>{base}</baseType><addData>{plaintext_data(d.text)}</addData></dataType>"


_MEMBER = re.compile(r"^\s*(\w+)\s*:\s*([^;:=]+?)\s*(?::=\s*([^;]+))?;", re.MULTILINE)


def _dut_base_xml(text: str) -> str:
    body = re.sub(r"\(\*.*?\*\)|//[^\n]*|\{[^}]*\}", "", text, flags=re.S)
    m = re.search(r":\s*STRUCT(.*?)END_STRUCT", body, re.S | re.I)
    if m:
        vs = [V(mm.group(1), mm.group(2), init=mm.group(3)) for mm in _MEMBER.finditer(m.group(1))]
        return "<struct>" + "".join(var_xml(v) for v in vs) + "</struct>"
    m = re.search(r":\s*UNION(.*?)END_UNION", body, re.S | re.I)
    if m:
        vs = [V(mm.group(1), mm.group(2)) for mm in _MEMBER.finditer(m.group(1))]
        return "<union>" + "".join(var_xml(v) for v in vs) + "</union>"
    m = re.search(r":\s*\((.*?)\)\s*(\w+)?", body, re.S)
    if m and "END_TYPE" in body.upper():
        vals = []
        for part in m.group(1).split(","):
            name, _, val = part.partition(":=")
            vals.append(
                f"<value name={quoteattr(name.strip())}"
                + (f" value={quoteattr(val.strip())}" if val.strip() else "")
                + " />"
            )
        base = f"<baseType>{type_xml(m.group(2))}</baseType>" if m.group(2) else ""
        return f"<enum><values>{''.join(vals)}</values>{base}</enum>"
    m = re.search(r":\s*(\w+)\s*\(\s*(-?\d+)\s*\.\.\s*(-?\d+)\s*\)", body)
    if m:
        tag = "subrangeUnsigned" if m.group(1).upper().startswith("U") else "subrangeSigned"
        return f'<{tag}><range lower="{m.group(2)}" upper="{m.group(3)}" /><baseType>{type_xml(m.group(1))}</baseType></{tag}>'
    m = re.search(r":\s*([^;]+?)\s*;", body)
    return type_xml(m.group(1)) if m else "<BOOL />"


def project_xml(case: Case, name: str | None = None) -> str:
    """Файл PLCopen для import_xml: POU и DUT в types, GVL в addData проекта."""
    head = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<project xmlns="{NS}">'
        f'<fileHeader companyName="" productName="CODESYS" productVersion="{PRODUCT_VERSION}" creationDateTime="{FIXED_TIME}" />'
        f'<contentHeader name={quoteattr((name or case.name) + ".project")} modificationDateTime="{FIXED_TIME}">'
        '<coordinateInfo><fbd><scaling x="1" y="1" /></fbd><ld><scaling x="1" y="1" /></ld><sfc><scaling x="1" y="1" /></sfc></coordinateInfo>'
        f'<addData><data name="{S3}projectinformation" handleUnknown="implementation"><ProjectInformation /></data></addData>'
        "</contentHeader>"
    )
    types = (
        "<types><dataTypes>"
        + "".join(dut_xml(d) for d in case.duts)
        + "</dataTypes><pous>"
        + "".join(pou_xml(p) for p in case.pous)
        + "</pous></types><instances><configurations /></instances>"
    )
    add = ""
    if case.gvls:
        add = (
            "<addData>"
            + "".join(
                f'<data name="{S3}globalvars" handleUnknown="implementation">{gvl_xml(g)}</data>' for g in case.gvls
            )
            + "</addData>"
        )
    return head + types + add + "</project>"


def pretty(xml_text: str) -> str:
    """Отступы для читаемого diff (lxml), UTF-8 с BOM — как у экспорта CODESYS."""
    from lxml import etree

    root = etree.fromstring(xml_text.encode("utf-8"))
    etree.indent(root, space="  ")
    body = etree.tostring(root, encoding="unicode")
    return '﻿<?xml version="1.0" encoding="utf-8"?>\n' + body + "\n"
