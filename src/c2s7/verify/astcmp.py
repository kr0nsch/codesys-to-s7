"""Сравнение SCL по нормализованному AST (разбор — s7conv/parser.py клона @ 2285760c).

Кольцо: исходный SCL корпуса s7-to-codesys ↔ SCL, который c2s7 получил из его выхода. Нормализация
(ТЗ M12): атрибуты, комментарии и пробелы не сравниваются; порядок атрибутов шапки; REGION
раскрывается; имена — без учёта регистра и без `#`/кавычек; литералы — по значению; начальные
значения DB — по значению (объявление и BEGIN); абсолютный адрес ↔ тег с этим адресом (таблица тегов
исходного проекта); секции одного вида сливаются. Каждое правило нормализации имеет id `norm.*` и
считается в отчёте.
"""

from __future__ import annotations

import csv
import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from c2s7.st import literals as L

NORM_RULES = {
    "norm.comments": "комментарии, атрибуты переменных и пробелы не сравниваются",
    "norm.header": "TITLE, AUTHOR, FAMILY, VERSION и атрибуты блока не сравниваются (кроме S7_Optimized_Access)",
    "norm.region": "REGION раскрывается в операторы",
    "norm.case": "имена без учёта регистра, без # и кавычек",
    "norm.literal": "литералы по значению (T#5S = T#5s = 5000 мс, 16#FF = 255)",
    "norm.db_init": "начальные значения DB по значению: объявление и BEGIN",
    "norm.addr_tag": "абсолютный адрес и тег с этим адресом — одно и то же",
    "norm.sections": "секции одного вида сливаются, объявления «a, b : T» раскрываются",
    "norm.string_default": "String = String[254], WString = WString[254]",
    "norm.empty": "пустые операторы не сравниваются",
}


@dataclass
class Divergence:
    block: str
    where: str
    original: str
    ours: str
    category: str = "bug"
    rule: str = ""
    note: str = ""


@dataclass
class BlockResult:
    name: str
    kind: str
    status: str  # match | diverged | missing | extra
    divergences: list[Divergence] = field(default_factory=list)


def load_tag_addresses(path: Path) -> dict[str, str]:
    """Адрес → имя тега (таблица тегов исходного проекта S7)."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            addr = (row.get("Logical Address") or "").strip().upper()
            if addr:
                out[addr.replace(" ", "")] = row["Name"].strip()
    return out


class Canon:
    """Каноническая форма узлов s7conv: вложенные кортежи и строки."""

    def __init__(self, tags: dict[str, str]) -> None:
        self.tags = tags

    # ---- выражения
    def expr(self, e: Any) -> Any:
        if e is None:
            return None
        n = type(e).__name__
        if n == "Literal":
            return ("lit", self.literal(e.kind, e.text))
        if n in ("LocalRef", "Ident"):
            return ("v", e.name.lower())
        if n == "GlobalRef":
            return ("g", e.name.lower())
        if n == "AddressRef":
            text = e.text.upper().replace(" ", "")
            tag = self.tags.get(text)
            if tag is not None:
                return ("g", tag.lower())
            return ("addr", text)
        if n == "Member":
            return ("m", self.expr(e.base), e.name.lower())
        if n == "Index":
            return ("i", self.expr(e.base), tuple(self.expr(i) for i in e.indices))
        if n == "Slice":
            return ("slice", self.expr(e.base), e.size.upper(), e.number)
        if n == "Call":
            return ("call", self.expr(e.callee), tuple(self.arg(a) for a in e.args))
        if n == "Unary":
            return ("u", e.op.upper(), self.expr(e.operand))
        if n == "Binary":
            op = e.op.upper()
            op = "AND" if op == "&" else op
            return ("b", op, self.expr(e.left), self.expr(e.right))
        if n == "ArrayInit":
            return ("arr", tuple((self.expr(k), self.expr(v)) for k, v in e.items))
        return (n,)

    def arg(self, a: Any) -> Any:
        return ("a", (a.name or "").lower(), bool(a.output), self.expr(a.value))

    @staticmethod
    def literal(kind: str, text: str) -> Any:
        t = text.strip()
        up = t.upper()
        try:
            if up.startswith(("T#", "TIME#")):
                return ("time", L.parse_time_ms(t))
            if up.startswith(("LT#", "LTIME#")):
                return ("ltime", L.parse_duration_ns(t.split("#", 1)[1]))
            if up in ("TRUE", "FALSE", "BOOL#TRUE", "BOOL#FALSE"):
                return ("bool", up.endswith("TRUE"))
            if up.startswith("S5T#") or up.startswith("S5TIME#"):
                return ("s5time", L.parse_time_ms("T#" + t.split("#", 1)[1]))
            if t.startswith("'"):
                return ("str", L.unescape(t[1:-1]))
            if up.startswith("WSTRING#"):
                return ("wstr", L.unescape(t.split("#", 1)[1][1:-1]))
            if "#" in t and up.split("#")[0] in ("D", "DATE", "TOD", "TIME_OF_DAY", "DT", "DATE_AND_TIME"):
                return ("dt", up)
            if "#" in t and up.split("#")[0] in ("REAL", "LREAL"):
                return ("num", float(t.split("#", 1)[1]))
            if "." in t or ("E" in up and not up.startswith(("16#", "W#", "DW#", "B#"))):
                return ("num", float(t.replace("_", "")))
            body = up
            for p in ("B#", "W#", "DW#", "LW#", "L#"):
                if body.startswith(p):
                    body = body[len(p) :]
            return ("num", L.parse_int(body))
        except (ValueError, IndexError):
            return ("text", up)

    # ---- типы
    def type(self, t: Any) -> Any:
        if t is None:
            return None
        n = type(t).__name__
        if n == "NamedType":
            name = t.name.lower()
            return ("t", name)
        if n == "StringType":
            length = self.expr(t.length) if t.length is not None else ("lit", ("num", 254))
            return ("s", t.wide, length)
        if n == "ArrayType":
            return (
                "arr",
                tuple(None if r is None else (self.expr(r[0]), self.expr(r[1])) for r in t.ranges),
                self.type(t.element),
            )
        if n == "RefType":
            return ("ref", self.type(t.target))
        if n == "StructType":
            return ("struct", tuple(self.decl(d) for d in self._decls(t.decls)))
        return (n,)

    def _decls(self, items: list[Any]) -> list[tuple[str | None, Any]]:
        out: list[tuple[str | None, Any]] = []
        for d in items:
            if type(d).__name__ == "RawDecl":
                out.append((None, d))
                continue
            for name in d.names:
                out.append((name, d))
        return out

    def decl(self, nd: tuple[str | None, Any]) -> Any:
        name, d = nd
        if name is None:
            return ("rawdecl", " ".join(d.text.split()))
        return (
            "d",
            name.lower(),
            self.type(d.type),
            self.expr(d.init) if d.init is not None else None,
            self.expr(d.at),
        )

    # ---- операторы
    def stmts(self, stmts: list[Any]) -> list[Any]:
        out: list[Any] = []
        for s in stmts:
            n = type(s).__name__
            if n == "Region":
                out.extend(self.stmts(s.body))
            elif n in ("Empty", "CommentStmt", "Pragma"):
                continue
            else:
                out.append(self.stmt(s))
        return out

    def stmt(self, s: Any) -> Any:
        n = type(s).__name__
        if n == "Assign":
            return ("asg", self.expr(s.target), s.op, self.expr(s.value))
        if n == "CallStmt":
            return ("call", self.expr(s.call))
        if n == "If":
            return (
                "if",
                tuple((self.expr(c), tuple(self.stmts(b))) for c, b in s.branches),
                tuple(self.stmts(s.else_body)) if s.else_body is not None else None,
            )
        if n == "Case":
            clauses = []
            for cl in s.clauses:
                labels = tuple(
                    ("r", self.expr(lb.lo), self.expr(lb.hi)) if type(lb).__name__ == "CaseRange" else self.expr(lb)
                    for lb in cl.labels
                )
                clauses.append((labels, tuple(self.stmts(cl.body))))
            return (
                "case",
                self.expr(s.selector),
                tuple(clauses),
                tuple(self.stmts(s.else_body)) if s.else_body is not None else None,
            )
        if n == "For":
            return (
                "for",
                self.expr(s.var),
                self.expr(s.start),
                self.expr(s.end),
                self.expr(s.step),
                tuple(self.stmts(s.body)),
            )
        if n == "While":
            return ("while", self.expr(s.cond), tuple(self.stmts(s.body)))
        if n == "Repeat":
            return ("repeat", tuple(self.stmts(s.body)), self.expr(s.cond))
        if n in ("Exit", "Continue", "Return"):
            return (n.lower(),)
        if n == "Goto":
            return ("goto", s.label.lower())
        if n == "Label":
            return ("label", s.name.lower())
        if n == "RawStmt":
            return ("raw", " ".join(s.text.split()))
        return (n,)

    # ---- блоки
    def sections(self, block: Any) -> dict[str, list[Any]]:
        out: dict[str, list[Any]] = {}
        for sec in block.sections:
            mods = [m.upper() for m in sec.modifiers if m.upper() not in ("NON_RETAIN",)]
            key = " ".join([sec.kind.upper(), *mods])
            out.setdefault(key, []).extend(self.decl(d) for d in self._decls(sec.items))
        return out

    def _expand_array(self, name: str, typ: Any, init: Any) -> dict[str, Any]:
        """`a : Array[1..3] of T := [x, 2(y)]` → {a[1]: x, a[2]: y, a[3]: y} (как BEGIN)."""
        rng = typ.ranges[0] if typ.ranges else None
        lo = _lit_num(self.expr(rng[0])) if rng is not None else 0
        idx = lo if lo is not None else 0
        out: dict[str, Any] = {}
        for count, value in init.items:
            n = _lit_num(self.expr(count)) if count is not None else 1
            for _ in range(n or 1):
                out[f"{name}[{('lit', ('num', idx))}]"] = self.expr(value)
                idx += 1
        return out

    def db_values(self, block: Any) -> dict[str, Any]:
        """Начальные значения DB: из объявлений и BEGIN (путь → значение)."""
        vals: dict[str, Any] = {}
        for sec in block.sections:
            for name, d in self._decls(sec.items):
                if name is not None and d.init is not None:
                    if type(d.init).__name__ == "ArrayInit" and type(d.type).__name__ == "ArrayType":
                        vals.update(self._expand_array(name.lower(), d.type, d.init))
                    else:
                        vals[name.lower()] = self.expr(d.init)
        for s in block.body:
            if type(s).__name__ == "Assign":
                vals[_path_text(self.expr(s.target))] = self.expr(s.value)
        return vals


def _lit_num(c: Any) -> int | None:
    if isinstance(c, tuple) and c and c[0] == "lit" and c[1][0] == "num" and isinstance(c[1][1], int):
        return int(c[1][1])
    return None


def _path_text(c: Any) -> str:
    if isinstance(c, tuple) and c and c[0] == "v":
        return str(c[1])
    if isinstance(c, tuple) and c and c[0] == "m":
        return f"{_path_text(c[1])}.{c[2]}"
    if isinstance(c, tuple) and c and c[0] == "i":
        return f"{_path_text(c[1])}[{','.join(str(x) for x in c[2])}]"
    return repr(c)


def show(c: Any) -> str:
    """Короткий текст канонической формы для отчёта."""
    s = repr(c)
    return s if len(s) <= 300 else s[:297] + "..."


def type_defaults(canon: Canon, types: dict[str, Any], db_type: Any) -> dict[str, Any]:
    """Начальные значения членов UDT (для типизированного DB): путь → значение."""
    if db_type is None or type(db_type).__name__ != "NamedType":
        return {}
    udt = types.get(db_type.name.lower())
    if udt is None or udt.struct is None:
        return {}
    out: dict[str, Any] = {}
    for name, d in canon._decls(udt.struct.decls):
        if name is None or d.init is None:
            continue
        if type(d.init).__name__ == "ArrayInit" and type(d.type).__name__ == "ArrayType":
            out.update(canon._expand_array(name.lower(), d.type, d.init))
        else:
            out[name.lower()] = canon.expr(d.init)
    return out


def compare_blocks(orig: Any, ours: Any, canon: Canon, types: dict[str, Any] | None = None) -> list[Divergence]:
    name = orig.name
    out: list[Divergence] = []
    if orig.kind != ours.kind:
        out.append(Divergence(name, "kind", orig.kind, ours.kind))
        return out
    opt_o = orig.attributes.get("S7_Optimized_Access", "TRUE").upper().strip("'")
    opt_n = ours.attributes.get("S7_Optimized_Access", "TRUE").upper().strip("'")
    if opt_o != opt_n:
        out.append(Divergence(name, "S7_Optimized_Access", opt_o, opt_n))
    if (orig.kind == "FUNCTION") and canon.type(orig.return_type) != canon.type(ours.return_type):
        out.append(
            Divergence(name, "return_type", show(canon.type(orig.return_type)), show(canon.type(ours.return_type)))
        )
    if orig.kind == "TYPE":
        a = canon.type(orig.struct)
        b = canon.type(ours.struct)
        if a != b:
            out.extend(_seq_diff(name, "STRUCT", list(a[1]), list(b[1])))
        return out
    if orig.kind == "DATA_BLOCK":
        ta, tb = canon.type(orig.db_type), canon.type(ours.db_type)
        if ta != tb:
            out.append(Divergence(name, "тип DB", show(ta), show(tb)))
        sa, sb = canon.sections(orig), canon.sections(ours)
        out.extend(_sections_diff(name, sa, sb, values=True))
        va, vb = canon.db_values(orig), canon.db_values(ours)
        dflt = type_defaults(canon, types or {}, orig.db_type)
        for k in sorted(set(va) | set(vb)):
            if va.get(k, dflt.get(k)) != vb.get(k, dflt.get(k)):
                out.append(Divergence(name, f"начальное значение {k}", show(va.get(k)), show(vb.get(k))))
        return out
    sa, sb = canon.sections(orig), canon.sections(ours)
    out.extend(_sections_diff(name, sa, sb))
    ba, bb = canon.stmts(orig.body), canon.stmts(ours.body)
    if ba != bb:
        out.extend(_seq_diff(name, "тело", ba, bb))
    return out


def _sections_diff(
    name: str, sa: dict[str, list[Any]], sb: dict[str, list[Any]], values: bool = False
) -> list[Divergence]:
    out: list[Divergence] = []
    for key in sorted(set(sa) | set(sb)):
        a = [_strip_init(d) if values else d for d in sa.get(key, [])]
        b = [_strip_init(d) if values else d for d in sb.get(key, [])]
        if a != b:
            out.extend(_seq_diff(name, key, a, b))
    return out


def _strip_init(d: Any) -> Any:
    if isinstance(d, tuple) and d and d[0] == "d":
        return (d[0], d[1], d[2], None, d[4])
    return d


def _seq_diff(name: str, where: str, a: list[Any], b: list[Any]) -> list[Divergence]:
    sm = difflib.SequenceMatcher(a=[repr(x) for x in a], b=[repr(x) for x in b], autojunk=False)
    out: list[Divergence] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace" and i2 - i1 == j2 - j1:
            for k in range(i2 - i1):
                if a[i1 + k] != b[j1 + k]:
                    out.append(Divergence(name, f"{where} [{i1 + k}]", show(a[i1 + k]), show(b[j1 + k])))
            continue
        left = a[i1:i2]
        right = b[j1:j2]
        out.append(Divergence(name, f"{where} [{i1}:{i2}]↔[{j1}:{j2}]", show(left), show(right)))
    return out


RAW_NODES = ("RawStmt", "RawDecl", "RawBlock")


def raw_nodes(blocks: dict[str, Any]) -> list[str]:
    """Узлы, которые s7conv не разобрал (RawStmt/RawDecl): «блок: тип: текст» (ТЗ — без них, кроме закрытого списка)."""
    found: list[str] = []
    seen: set[int] = set()

    def walk(name: str, obj: Any) -> None:
        if id(obj) in seen or obj is None or isinstance(obj, str | int | float | bool | bytes):
            return
        seen.add(id(obj))
        tn = type(obj).__name__
        if tn in RAW_NODES:
            text = getattr(obj, "text", None) or getattr(obj, "reason", "")
            found.append(f"{name}: {tn}: {' '.join(str(text).split())[:80]}")
            return
        if isinstance(obj, list | tuple | set):
            for x in obj:
                walk(name, x)
        elif isinstance(obj, dict):
            for x in obj.values():
                walk(name, x)
        elif hasattr(obj, "__dataclass_fields__"):
            for f in obj.__dataclass_fields__:
                walk(name, getattr(obj, f, None))

    for name, b in sorted(blocks.items()):
        walk(b.name if hasattr(b, "name") else name, b)
    return found


def parse_scl_files(parser: Any, files: list[Path]) -> tuple[dict[str, Any], list[str]]:
    """Блоки по имени (без учёта регистра) и замечания разбора."""
    blocks: dict[str, Any] = {}
    issues: list[str] = []
    for f in files:
        text = f.read_text(encoding="utf-8-sig")
        sf = parser.parse_source(text, str(f))
        for b in sf.blocks:
            if type(b).__name__ == "RawBlock":
                issues.append(f"{f.name}: не разобран блок {b.name}: {b.reason}")
                continue
            blocks[b.name.lower()] = b
        for iss in sf.issues:
            if iss.severity == "error":
                issues.append(f"{f.name}:{iss.line}:{iss.col}: {iss.message}")
    return blocks, issues
