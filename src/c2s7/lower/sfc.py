"""SfcIR → автомат SCL (ТЗ M5, `--sfc scl`, P0) в порядке цикла CODESYS.

Порядок (справка CODESYS «Sequence of processing in SFC»):
1. флаги IEC-действий пересчитываются заново;
2. exit-действия шагов, деактивированных в прошлом цикле;
3. entry-действия шагов, активированных в прошлом цикле;
4. время активного шага (`<Шаг>_t`, TON) и действие шага;
5. IEC-действия по алфавиту в два прохода: сначала деактивированные (последний вызов с Q = FALSE),
   затем активные;
6. переходы слева направо по снимку активности на начало шага 6: сработавший переход гасит свои
   шаги-источники в снимке, поэтому альтернатива берёт первый истинный переход, а только что
   активированный шаг дальше не уходит в этом же цикле.

Состояние: `<Шаг>_x` (активен), `<Шаг>_xp` (был активен в прошлом цикле), `<Шаг>_t` (время шага);
у IEC-действия — `_c2s7_<Д>_q`, `_qp`, `_s` (флаг S). `Шаг.x/Шаг.t` в условиях и действиях
переписываются на `Шаг_x/Шаг_t`. Квалификаторы P0: N, S, R, P; остальные — C2S7-GFX-SFCQ (manual).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from c2s7.ir.sfcir import SfcBody
from c2s7.lower.common import PREFIX, add_vars, and_, lit_false, lit_true, map_expr, not_, or_
from c2s7.model import Origin, Pou
from c2s7.st import nodes as A
from c2s7.st import parser as P

if TYPE_CHECKING:
    from c2s7.convert.core import Converter

P0_QUALIFIERS = {"N", "S", "R", "P"}
TIME_MAX = P.parse_expr("T#24D20H31M23S647MS")
STEP_FIELDS = {"X": "x", "_X": "x", "T": "t", "_T": "t"}


class SfcLowering:
    def __init__(self, pou: Pou, conv: Converter | None) -> None:
        assert pou.sfc is not None
        self.pou = pou
        self.sfc: SfcBody = pou.sfc
        self.conv = conv
        self.where = pou.impl_origin or pou.origin
        self.used = {d.name.upper() for _, d in pou.decls()}
        self.statics: list[A.VarDecl] = []
        self.temps: list[A.VarDecl] = []
        self.steps = {s.name.upper(): s.name for s in self.sfc.steps}

    def add(self, rule: str, detail: str) -> None:
        if self.conv is not None:
            self.conv.add(rule, Origin(self.where.file, self.where.line), detail)

    def var(self, name: str, typ: str, init: A.Expr | None = None, temp: bool = False) -> str:
        n = name
        k = 1
        while n.upper() in self.used:
            k += 1
            n = f"{name}{k}"
        self.used.add(n.upper())
        (self.temps if temp else self.statics).append(A.VarDecl(n, A.NamedType(typ), init))
        return n

    def rewrite(self, e: object) -> object:
        """`Шаг.x/.t` → `Шаг_x/Шаг_t`."""

        def fn(x: A.Expr) -> A.Expr | None:
            if isinstance(x, A.Member) and isinstance(x.base, A.Name):
                step = self.steps.get(x.base.id.upper())
                f = STEP_FIELDS.get(x.name.upper())
                if step is not None and f is not None:
                    return A.Name(self.sx[step.upper()] if f == "x" else self.st[step.upper()])
            return None

        return map_expr(e, fn)

    def call_action(self, name: str) -> A.Stmt:
        return A.CallStmt(A.Call(A.Name(name), []))

    def lower(self) -> list[A.Stmt]:
        sfc = self.sfc
        self.add("C2S7-GFX-SFC", f"SFC {self.pou.name}: {len(sfc.steps)} шаг(ов), {len(sfc.transitions)} переход(ов)")
        self.sx: dict[str, str] = {}
        self.sxp: dict[str, str] = {}
        self.st: dict[str, str] = {}
        self.ton: dict[str, str] = {}
        for s in sfc.steps:
            key = s.name.upper()
            self.sx[key] = self.var(f"{s.name}_x", "BOOL", lit_true() if s.initial else None)
            self.sxp[key] = self.var(f"{s.name}_xp", "BOOL")
            self.st[key] = self.var(f"{s.name}_t", "TIME")
            self.ton[key] = self.var(f"{PREFIX}{s.name}_ton", "TON")
        # действия: тела переписываются (Шаг.x → Шаг_x)
        for act in self.pou.actions:
            act.body = self.rewrite(act.body)  # type: ignore[assignment]
        body: list[A.Stmt] = []

        def x(s: str) -> A.Expr:
            return A.Name(self.sx[s.upper()])

        def xp(s: str) -> A.Expr:
            return A.Name(self.sxp[s.upper()])

        # 2. exit
        for s in sfc.steps:
            if s.exit:
                body.append(A.If([(and_(xp(s.name), not_(x(s.name))), [self.call_action(s.exit)])]))
        # 3. entry
        for s in sfc.steps:
            if s.entry:
                body.append(A.If([(and_(x(s.name), not_(xp(s.name))), [self.call_action(s.entry)])]))
        # 4. время и действие шага
        for s in sfc.steps:
            key = s.name.upper()
            body.append(
                A.CallStmt(
                    A.Call(A.Name(self.ton[key]), [A.Arg(x(s.name), "IN"), A.Arg(TIME_MAX, "PT")]),
                )
            )
            body.append(A.Assign(A.Name(self.st[key]), A.Member(A.Name(self.ton[key]), "ET")))
            if s.step_action:
                body.append(A.If([(x(s.name), [self.call_action(s.step_action)])]))
        if body:
            body[0].lead = [" SFC → автомат SCL (c2s7, порядок цикла CODESYS)", *list(body[0].lead)]
        # 5. IEC-действия
        assoc: dict[str, list[tuple[str, str]]] = {}
        for s in sfc.steps:
            for a in s.actions:
                q = a.qualifier.upper()
                if q not in P0_QUALIFIERS:
                    self.add("C2S7-GFX-SFCQ", f"шаг {s.name}: {q} {a.action}")
                    continue
                assoc.setdefault(a.action, []).append((s.name, q))
        names = sorted(assoc, key=str.upper)
        qv: dict[str, str] = {}
        qpv: dict[str, str] = {}
        for an in names:
            qv[an] = self.var(f"{PREFIX}{an}_q", "BOOL")
            qpv[an] = self.var(f"{PREFIX}{an}_qp", "BOOL")
            pairs = assoc[an]
            n_terms = [x(s) for s, q in pairs if q == "N"]
            p_terms = [and_(x(s), not_(xp(s))) for s, q in pairs if q == "P"]
            s_terms = [x(s) for s, q in pairs if q == "S"]
            r_terms = [x(s) for s, q in pairs if q == "R"]
            body.append(A.Assign(A.Name(qpv[an]), A.Name(qv[an])))
            stored: A.Expr = lit_false()
            if s_terms or r_terms:
                sv = self.var(f"{PREFIX}{an}_s", "BOOL")
                body.append(A.Assign(A.Name(sv), and_(or_(A.Name(sv), *s_terms), not_(or_(*r_terms)))))
                stored = A.Name(sv)
            body.append(A.Assign(A.Name(qv[an]), or_(*n_terms, *p_terms, stored)))
        for an in names:  # проход 1: последний вызов деактивированных
            body.append(A.If([(and_(A.Name(qpv[an]), not_(A.Name(qv[an]))), [self.call_action(an)])]))
        for an in names:  # проход 2: активные
            body.append(A.If([(A.Name(qv[an]), [self.call_action(an)])]))
        # 6. переходы
        snap: dict[str, str] = {}
        for s in sfc.steps:
            key = s.name.upper()
            snap[key] = self.var(f"{PREFIX}{s.name}_a", "BOOL", temp=True)
            body.append(A.Assign(A.Name(snap[key]), x(s.name)))
            body.append(A.Assign(xp(s.name), x(s.name)))
        for t in sorted(sfc.transitions, key=lambda t: t.order):
            if not t.source or not t.target:
                self.add("C2S7-GFX-SFC", f"переход {t.text or t.id}: нет источника или цели")
                continue
            cond = self.rewrite(t.condition)
            assert isinstance(cond, A.Expr)
            guard = and_(*[A.Name(snap[s.upper()]) for s in t.source], cond)
            then: list[A.Stmt] = [A.Assign(A.Name(snap[s.upper()]), lit_false()) for s in t.source]
            then += [A.Assign(x(s), lit_false()) for s in t.source]
            then += [A.Assign(x(s), lit_true()) for s in t.target]
            body.append(A.If([(guard, then)]))
        add_vars(self.pou, "VAR", self.statics)
        add_vars(self.pou, "VAR_TEMP", self.temps)
        return body


def sfc_to_st(pou: Pou, conv: Converter | None = None) -> list[A.Stmt]:
    return SfcLowering(pou, conv).lower()
