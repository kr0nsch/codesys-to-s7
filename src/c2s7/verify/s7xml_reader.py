"""SimaticML FlgNet → ST AST (ТЗ M10, «Графика»): обратное чтение своего выхода для c2s7.sim.

s7conv читает только SCL, поэтому блоки LAD/FBD проверяются так: XML → операторы ST → c2s7.sim
против понижения источника (NetIR → ST) на тех же входах. Reader делит с эмиттером реестр частей и
автора — это проверка самосогласованности, а не независимое доказательство (так и написано в
README и EQUIVALENCE.md). Независимые проверки — XSD и, в планах, plc-code и импортёр s7-to-codesys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lxml import etree

from c2s7.lower.common import and_, lit_false, lit_true, not_, or_
from c2s7.lower.jumps import remove_jumps
from c2s7.st import nodes as A
from c2s7.st import parser as P

CMP = {"Gt": ">", "Ge": ">=", "Lt": "<", "Le": "<=", "Eq": "=", "Ne": "<>"}
ARITH = {"Add": "+", "Sub": "-", "Mul": "*", "Div": "/", "Mod": "MOD"}


class ReaderError(ValueError):
    """Документ вне подмножества, которое пишет c2s7."""


@dataclass
class ReadBlock:
    name: str
    kind: str  # FB | FC
    language: str
    body: list[A.Stmt] = field(default_factory=list)
    temps: list[str] = field(default_factory=list)
    members: dict[str, str] = field(default_factory=dict)  # имя → тип S7 из интерфейса


def _ln(el: Any) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _kids(el: Any, name: str) -> list[Any]:
    return [c for c in el if _ln(c) == name]


def _first(el: Any, name: str) -> Any:
    return next((c for c in el.iter() if _ln(c) == name), None)


class _Net:
    def __init__(self, flg: Any, block: ReadBlock, temp_counter: list[int]) -> None:
        self.block = block
        self.counter = temp_counter
        parts_el = next(c for c in flg if _ln(c) == "Parts")
        self.parts: dict[str, Any] = {p.get("UId"): p for p in parts_el if _ln(p) == "Part"}
        self.access: dict[str, Any] = {a.get("UId"): a for a in parts_el if _ln(a) == "Access"}
        self.inputs: dict[tuple[str, str], Any] = {}
        self.out_assign: dict[str, list[tuple[str, Any]]] = {}  # uid части → [(пин, Access)]
        for w in (c for c in flg.iter() if _ln(c) == "Wire"):
            ends = [c for c in w if isinstance(c.tag, str)]
            src = ends[0]
            for t in ends[1:]:
                if _ln(t) == "NameCon":
                    self.inputs[(t.get("UId"), t.get("Name"))] = src
                elif _ln(t) == "IdentCon" and _ln(src) == "NameCon":
                    self.out_assign.setdefault(src.get("UId"), []).append((src.get("Name"), self.access[t.get("UId")]))
        self.labels = [
            lbl.get("Name") for lbl in flg.iter() if _ln(lbl) == "Label" and _ln(lbl.getparent()) == "LabelDeclaration"
        ]
        self.pre: list[A.Stmt] = []
        self.memo: dict[str, A.Expr] = {}
        self.called: set[str] = set()

    def access_expr(self, a: Any) -> A.Expr:
        scope = a.get("Scope")
        if scope in ("LocalVariable", "GlobalVariable"):
            comps = [c.get("Name") for c in a.iter() if _ln(c) == "Component"]
            e: A.Expr = A.Name(comps[0])
            for c in comps[1:]:
                e = A.Member(e, c)
            return e
        if scope == "GlobalConstant":
            return A.Name(_first(a, "Constant").get("Name"))
        if scope in ("LiteralConstant", "TypedConstant"):
            val = (_first(a, "ConstantValue").text or "").strip()
            ctype = _first(a, "ConstantType")
            text = val
            if ctype is not None and (ctype.text or "") in ("Bool",):
                text = val.upper()
            return P.parse_expr(text)
        raise ReaderError(f"Access Scope={scope}")

    def end_value(self, end: Any) -> A.Expr:
        kind = _ln(end)
        if kind == "Powerrail":
            return lit_true()
        if kind == "IdentCon":
            return self.access_expr(self.access[end.get("UId")])
        if kind == "NameCon":
            return self.part_out(end.get("UId"), end.get("Name"))
        raise ReaderError(f"конец провода {kind}")

    def negated(self, uid: str, pin: str) -> bool:
        return any(n.get("Name") == pin for n in _kids(self.parts[uid], "Negated"))

    def pin(self, uid: str, pin: str, default: A.Expr | None = None) -> A.Expr:
        src = self.inputs.get((uid, pin))
        if src is None:
            if default is None:
                raise ReaderError(f"вход {pin} части {uid} не подключён")
            return default
        v = self.end_value(src)
        return not_(v) if self.negated(uid, pin) else v

    def card(self, uid: str) -> int:
        for t in _kids(self.parts[uid], "TemplateValue"):
            if t.get("Name") == "Card":
                return int(t.text or "0")
        return 2

    def temp(self) -> str:
        self.counter[0] += 1
        name = f"_rd_e{self.counter[0]}"
        self.block.temps.append(name)
        return name

    def part_out(self, uid: str, pin: str) -> A.Expr:
        key = f"{uid}:{pin}"
        if key in self.memo:
            return self.memo[key]
        p = self.parts[uid]
        name = p.get("Name")
        if name == "Contact":
            op = self.pin(uid, "operand")
            v = and_(self.pin(uid, "in"), op)
        elif name in ("Coil", "SCoil", "RCoil"):
            v = self.pin(uid, "in")
        elif name == "Not":
            v = not_(self.pin(uid, "in"))
        elif name in ("O", "A", "X"):
            ins = [self.pin(uid, f"in{i}") for i in range(1, self.card(uid) + 1)]
            if name == "O":
                v = or_(*ins)
            elif name == "A":
                v = and_(*ins)
            else:
                v = ins[0]
                for x in ins[1:]:
                    v = A.Binary("XOR", v, x)
        elif name in ("PBox", "NBox"):
            tmp = self.temp()
            inp = self.pin(uid, "in")
            bit = self.pin(uid, "bit")
            val = and_(inp, not_(bit)) if name == "PBox" else and_(not_(inp), bit)
            self.pre += [A.Assign(A.Name(tmp), val), A.Assign(bit, inp)]
            v = A.Name(tmp)
        elif name in CMP:
            v = and_(self.pin(uid, "pre", lit_true()), A.Binary(CMP[name], self.pin(uid, "in1"), self.pin(uid, "in2")))
        elif name in ARITH:
            n = self.card(uid) if name in ("Add", "Mul") else 2
            ins = [self.pin(uid, f"in{i}") for i in range(1, n + 1)]
            v = ins[0]
            for x in ins[1:]:
                v = A.Binary(ARITH[name], v, x)
        elif name == "Move":
            v = self.pin(uid, "in")
        elif name in ("TON", "TOF", "TP"):
            inst = self.instance(uid)
            self.call_timer(uid, inst)
            v = A.Member(inst, pin)
        else:
            raise ReaderError(f"часть {name}")
        self.memo[key] = v
        return v

    def instance(self, uid: str) -> A.Expr:
        inst = next(iter(_kids(self.parts[uid], "Instance")))
        comps = [c.get("Name") for c in inst if _ln(c) == "Component"]
        e: A.Expr = A.Name(comps[0])
        for c in comps[1:]:
            e = A.Member(e, c)
        return e

    def call_timer(self, uid: str, inst: A.Expr) -> None:
        if uid in self.called:
            return
        self.called.add(uid)
        args = []
        for pin in ("IN", "PT"):
            if (uid, pin) in self.inputs:
                args.append(A.Arg(self.pin(uid, pin), pin))
        self.pre.append(A.CallStmt(A.Call(inst, args)))

    def statements(self) -> list[A.Stmt]:
        out: list[A.Stmt] = [A.Label(lbl) for lbl in self.labels]
        for uid in sorted(self.parts, key=int):
            p = self.parts[uid]
            name = p.get("Name")
            stmt: list[A.Stmt] = []
            if name in ("Coil", "SCoil", "RCoil"):
                flow = self.pin(uid, "in")
                target = self.pin(uid, "operand")
                if name == "Coil":
                    stmt = [A.Assign(target, flow)]
                else:
                    stmt = [A.If([(flow, [A.Assign(target, lit_true() if name == "SCoil" else lit_false())])])]
            elif name == "Jump":
                flow = self.pin(uid, "in")
                lbl = next(iter(self.access[self.inputs[(uid, "operand")].get("UId")].iter("{*}Label", "Label")))
                stmt = [A.Jump(lbl.get("Name"), None if flow == lit_true() else flow)]
            elif name in ("TON", "TOF", "TP"):
                self.call_timer(uid, self.instance(uid))
            for pin, acc in self.out_assign.get(uid, []):
                stmt.append(A.Assign(self.access_expr(acc), self.part_out(uid, pin)))
            out.extend(self.pre)
            self.pre = []
            out.extend(stmt)
        return out


def read_flgnet(xml: str) -> ReadBlock:
    root = etree.fromstring(xml.encode("utf-8"))
    blk_el = next((c for c in root if _ln(c) in ("SW.Blocks.FB", "SW.Blocks.FC")), None)
    if blk_el is None:
        raise ReaderError("нет SW.Blocks.FB/FC")
    attrs = next(c for c in blk_el if _ln(c) == "AttributeList")
    name = next((c.text for c in attrs if _ln(c) == "Name"), "") or ""
    lang = next((c.text for c in attrs if _ln(c) == "ProgrammingLanguage"), "LAD") or "LAD"
    rb = ReadBlock(name, "FC" if _ln(blk_el) == "SW.Blocks.FC" else "FB", lang)
    for m in (c for c in attrs.iter() if _ln(c) == "Member" and _ln(c.getparent()) == "Section"):
        rb.members[m.get("Name") or ""] = m.get("Datatype") or ""
    counter = [0]
    stmts: list[A.Stmt] = []
    for cu in (c for c in blk_el.iter() if _ln(c) == "SW.Blocks.CompileUnit"):
        flg = _first(cu, "FlgNet")
        if flg is None:
            continue
        stmts.extend(_Net(flg, rb, counter).statements())
    rb.body = remove_jumps(stmts).stmts
    return rb
