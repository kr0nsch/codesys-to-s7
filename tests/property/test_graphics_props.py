"""Свойства графики (ТЗ §8.6, hypothesis ≥ 300, фиксированный seed):

- jumps.py сохраняет трассу: плоская программа с переходами и её свёртка дают одинаковые значения;
- NetIR → FlgNet → reader — та же таблица истинности, что и понижение NetIR → ST (случайные сети LD);
- автомат SFC (понижение в ST, исполнение c2s7.sim) = модель порядка CODESYS на SfcIR (Python).
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, given, seed, settings
from hypothesis import strategies as st

from c2s7.api import migrate
from c2s7.convert.core import Options
from c2s7.ingest.plcopen import load_plcopen
from c2s7.lower import lower_pou
from c2s7.lower.jumps import remove_jumps
from c2s7.model import Project
from c2s7.sim.interp import Clock, Sim
from c2s7.st import nodes as A
from c2s7.verify.s7xml_reader import read_flgnet

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools" / "corpus")]
import builder as B  # noqa: E402

SETTINGS = settings(max_examples=300, deadline=None, derandomize=True, suppress_health_check=[HealthCheck.too_slow])


# ------------------------------------------------------------------ мини-интерпретатор переходов
class _Stop(Exception):
    pass


def _ev(e: A.Expr, env: dict[str, Any]) -> Any:
    if isinstance(e, A.Literal):
        return e.value
    if isinstance(e, A.Name):
        return env[e.id]
    if isinstance(e, A.Unary):
        return not _ev(e.operand, env)
    if isinstance(e, A.Binary):
        a, b = _ev(e.left, env), _ev(e.right, env)
        return {"+": lambda: a + b, "<": lambda: a < b, "AND": lambda: a and b, "OR": lambda: a or b}[e.op]()
    raise TypeError(type(e).__name__)


def _run_flat(stmts: list[A.Stmt], env: dict[str, Any], budget: int = 2000) -> list[tuple[str, Any]]:
    """Плоский список с Jump/Label: трасса присваиваний."""
    trace: list[tuple[str, Any]] = []
    labels = {s.name: i for i, s in enumerate(stmts) if isinstance(s, A.Label)}
    pc = 0
    while pc < len(stmts):
        budget -= 1
        if budget < 0:
            raise _Stop
        s = stmts[pc]
        if isinstance(s, A.Assign):
            assert isinstance(s.target, A.Name)
            env[s.target.id] = _ev(s.value, env)
            trace.append((s.target.id, env[s.target.id]))
        elif isinstance(s, A.Jump) and (s.cond is None or _ev(s.cond, env)):
            pc = labels[s.label]
            continue
        pc += 1
    return trace


def _run_struct(stmts: list[A.Stmt], env: dict[str, Any], trace: list[tuple[str, Any]], budget: list[int]) -> None:
    for s in stmts:
        budget[0] -= 1
        if budget[0] < 0:
            raise _Stop
        if isinstance(s, A.Assign):
            assert isinstance(s.target, A.Name)
            env[s.target.id] = _ev(s.value, env)
            trace.append((s.target.id, env[s.target.id]))
        elif isinstance(s, A.If):
            for cond, body in s.branches:
                if _ev(cond, env):
                    _run_struct(body, env, trace, budget)
                    break
        elif isinstance(s, A.Repeat):
            while True:
                _run_struct(s.body, env, trace, budget)
                if _ev(s.cond, env):
                    break


@st.composite
def flat_programs(draw: Any) -> list[A.Stmt]:
    n = draw(st.integers(2, 7))
    stmts: list[A.Stmt] = []
    labels = [f"L{i}" for i in range(draw(st.integers(1, 3)))]
    for i in range(n):
        kind = draw(st.sampled_from(["assign", "assign", "jump", "label"]))
        if kind == "assign":
            v = draw(st.sampled_from(["x", "y", "k"]))
            stmts.append(A.Assign(A.Name(v), A.Binary("+", A.Name(v), A.Literal("int", "1", 1))))
        elif kind == "jump":
            cond = draw(st.sampled_from(["a", "b", "loop"]))
            c: A.Expr = A.Binary("<", A.Name("k"), A.Literal("int", "3", 3)) if cond == "loop" else A.Name(cond)
            stmts.append(A.Jump(draw(st.sampled_from(labels)), c))
        else:
            stmts.append(A.Label(labels[i % len(labels)]))
    used = {s.name for s in stmts if isinstance(s, A.Label)}
    return [s for s in stmts if not isinstance(s, A.Jump) or s.label in used] + [
        A.Label(lbl) for lbl in labels if False
    ]


@seed(20261019)
@SETTINGS
@given(flat_programs(), st.booleans(), st.booleans())
def test_jumps_preserve_trace(prog: list[A.Stmt], a: bool, b: bool) -> None:
    if len({s.name for s in prog if isinstance(s, A.Label)}) != sum(isinstance(s, A.Label) for s in prog):
        return  # повторная метка — некорректная программа
    env0 = {"x": 0, "y": 0, "k": 0, "a": a, "b": b}
    try:
        want = _run_flat(prog, dict(env0))
    except _Stop:
        return  # бесконечный цикл в исходнике
    res = remove_jumps(prog)
    if res.remaining:
        return  # неприводимое: остаётся GOTO (C2S7-GFX-GOTO)
    got: list[tuple[str, Any]] = []
    _run_struct(res.stmts, dict(env0), got, [5000])
    assert got == want


# ------------------------------------------------------------------ LD: таблица истинности через FlgNet
VARS = ["a", "b", "c", "d"]


@st.composite
def ld_trees(draw: Any, depth: int = 0) -> Any:
    if depth >= 2 or draw(st.integers(0, 2)) == 0:
        return B.Contact(draw(st.sampled_from(VARS)), neg=draw(st.booleans()))
    items = [draw(ld_trees(depth + 1)) for _ in range(draw(st.integers(2, 3)))]
    return B.Series(*items) if draw(st.booleans()) else B.Parallel(*items)


@st.composite
def ld_pous(draw: Any) -> Any:
    rungs = []
    for i in range(draw(st.integers(1, 3))):
        tree = draw(ld_trees())
        if draw(st.booleans()):
            tree = B.Series(
                B.Contact(draw(st.sampled_from(VARS)), edge=draw(st.sampled_from(["rising", "falling"]))), tree
            )
        storage = draw(st.sampled_from([None, None, "set", "reset"]))
        neg = storage is None and draw(st.booleans())
        rungs.append(B.Rung(B.Series(tree, B.Coil(f"q{i}", neg=neg, storage=storage))))
    vars_ = [B.V(v, "BOOL", "VAR_INPUT") for v in VARS] + [B.V(f"q{i}", "BOOL", "VAR_OUTPUT") for i in range(3)]
    return B.Pou("FB_Rnd", "functionBlock", B.Ld(rungs), vars_)


@seed(20261019)
@SETTINGS
@given(ld_pous(), st.lists(st.tuples(*[st.booleans()] * 4), min_size=6, max_size=12))
def test_ld_flgnet_reader_truth_table(tmp_path_factory: Any, pou_spec: Any, inputs: list[tuple[bool, ...]]) -> None:
    d = tmp_path_factory.mktemp("ld")
    f = d / "p.xml"
    f.write_text(B.pretty(B.project_xml(B.Case("r", pous=[pou_spec]))), encoding="utf-8")
    proj = load_plcopen(f)
    res = migrate(proj, Options(tia="V21"))
    pou = proj.pous[0]
    if not res.simaticml:
        assert any(x.rule == "C2S7-GFX-SCL" for x in res.collector.findings)
        return
    rb = read_flgnet(next(iter(res.simaticml.values())))
    p2 = copy.deepcopy(pou)
    p2.text.body = rb.body
    p2.text.var_blocks.append(A.VarBlock("VAR_TEMP", [], [A.VarDecl(t, A.NamedType("BOOL")) for t in rb.temps]))
    s1, s2 = Sim(Project("a", "st", "a", "-", pous=[pou])), Sim(Project("b", "st", "b", "-", pous=[p2]))
    i1, i2 = s1.new_instance(s1.pous["FB_RND"]), s2.new_instance(s2.pous["FB_RND"])
    for row in inputs:
        vals = dict(zip(VARS, row, strict=True))
        s1.call_fb(i1, dict(vals))
        s2.call_fb(i2, dict(vals))
        for q in ("Q0", "Q1", "Q2"):
            assert i1.vars[q] == i2.vars[q]


# ------------------------------------------------------------------ SFC: автомат = модель порядка
SFC_FILE = REPO / "tests" / "fixtures" / "sp17" / "PRG_ProbeSfc.xml"


class SfcModel:
    """Модель цикла CODESYS на SfcIR пробы PRG_ProbeSfc (порядок — docs/ORACLES.md, lower/sfc.py)."""

    def __init__(self, sfc: Any) -> None:
        self.sfc = sfc
        self.x = {s.name: s.initial for s in sfc.steps}
        self.xp = {s.name: False for s in sfc.steps}
        self.since: dict[str, int | None] = {s.name: None for s in sfc.steps}
        self.q: dict[str, bool] = {}
        self.stored: dict[str, bool] = {}
        self.out = {"iN": 0, "xS": False, "iP": 0, "iInit": 0}

    def act(self, name: str) -> None:
        if name == "ActInit":
            self.out["iInit"] += 1
        elif name == "ActN":
            self.out["iN"] += 1
        elif name == "ActS":
            self.out["xS"] = True
        elif name == "ActP":
            self.out["iP"] += 1

    def cycle(self, now: int, inputs: dict[str, bool]) -> None:
        t: dict[str, int] = {}
        for s in self.sfc.steps:  # 4. время шага (TON по активности) и действие шага
            if self.x[s.name]:
                if self.since[s.name] is None:
                    self.since[s.name] = now
                t[s.name] = now - (self.since[s.name] or 0)
                if s.step_action:
                    self.act(s.step_action)
            else:
                self.since[s.name] = None
                t[s.name] = 0
        assoc: dict[str, list[tuple[str, str]]] = {}
        for s in self.sfc.steps:
            for a in s.actions:
                assoc.setdefault(a.action, []).append((s.name, a.qualifier))
        names = sorted(assoc, key=str.upper)
        qp = dict(self.q)
        for an in names:  # 5. IEC-действия
            pairs = assoc[an]
            if any(q in ("S", "R") for _, q in pairs):
                st_ = self.stored.get(an, False) or any(self.x[s] for s, q in pairs if q == "S")
                self.stored[an] = st_ and not any(self.x[s] for s, q in pairs if q == "R")
            n = any(self.x[s] for s, q in pairs if q == "N")
            p = any(self.x[s] and not self.xp[s] for s, q in pairs if q == "P")
            self.q[an] = n or p or self.stored.get(an, False)
        for an in names:
            if qp.get(an, False) and not self.q[an]:
                self.act(an)
        for an in names:
            if self.q[an]:
                self.act(an)
        snap = dict(self.x)  # 6. переходы
        self.xp = dict(self.x)
        env = {**inputs, "Par1.t": t["Par1"]}
        for tr in sorted(self.sfc.transitions, key=lambda tr: tr.order):
            cond = tr.text
            ok = env["Par1.t"] >= 100 if cond == "Par1.t >= T#100MS" else bool(env[cond])
            if all(snap[s] for s in tr.source) and ok:
                for s in tr.source:
                    snap[s] = False
                    self.x[s] = False
                for s in tr.target:
                    self.x[s] = True
        for s in self.sfc.steps:  # время шага — с цикла активирующего перехода
            if self.x[s.name] and self.since[s.name] is None:
                self.since[s.name] = now
            elif not self.x[s.name]:
                self.since[s.name] = None


@seed(20261019)
@SETTINGS
@given(
    st.lists(
        st.tuples(st.booleans(), st.booleans(), st.booleans(), st.sampled_from([10, 50, 120])), min_size=5, max_size=25
    )
)
def test_sfc_automaton_matches_model(steps: list[tuple[bool, bool, bool, int]]) -> None:
    proj = load_plcopen(SFC_FILE)
    pou = proj.pous[0]
    model = SfcModel(copy.deepcopy(pou.sfc))
    stmts = lower_pou(pou, None)
    assert stmts is not None
    pou.text.body = stmts
    clock = Clock()
    sim = Sim(Project("s", "st", "s", "-", pous=[pou]), clock)
    inst = sim.new_instance(sim.pous["PRG_PROBESFC"])
    now = 0
    for xa, xb, xn, dt in steps:
        now += dt
        clock.now_ms = now
        inputs = {"xA": xa, "xB": xb, "xNext": xn}
        sim.call_fb(inst, dict(inputs))
        model.cycle(now, inputs)
        got = {k: inst.get(k) for k in model.out}
        assert got == model.out
        assert {s: inst.get(f"{s}_x") for s in model.x} == model.x
