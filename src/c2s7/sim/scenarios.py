"""Сценарии CSV s7-to-codesys (scenarios/README.md @ 2285760c) и их исполнение в c2s7.sim (режим R1).

Строка = вызов: часы ставятся на t_ms (у проекта с GVL_S7Clock — ещё xSimulation/tSimNow, как в
тестах s7-to-codesys), непустые входы присваиваются экземпляру, блок вызывается один раз без
параметров, непустые выходы сравниваются (REAL/LREAL — с допуском tol). Каждый сценарий начинается с
нового экземпляра и новых глобальных переменных.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from c2s7.model import Project
from c2s7.sim.interp import OUT_OF_SUBSET, Clock, Instance, Sim, SimError
from c2s7.st import literals as L
from c2s7.st import nodes as A

_COL = re.compile(r"^(in|out)\.(?P<path>[^:]+):(?P<type>\w+(?:\(\d+\))?)$")


@dataclass
class Row:
    scenario: str
    cycle: int
    t_ms: int
    inputs: dict[str, tuple[str, Any]]
    outputs: dict[str, tuple[str, Any, float]]
    boundary: bool
    comment: str


@dataclass
class RowResult:
    scenario: str
    cycle: int
    t_ms: int
    ok: bool
    mismatches: list[tuple[str, Any, Any]] = field(default_factory=list)
    error: str = ""
    skipped: str = ""  # причина: конструкция вне подмножества c2s7.sim (docs/ORACLES.md)


def parse_value(typ: str, text: str) -> Any:
    t = typ.upper()
    if t == "BOOL":
        return text.strip().upper() == "TRUE"
    if t in ("REAL", "LREAL"):
        return float(text)
    if t == "TIME":
        return L.parse_time_ms(text)
    if t.startswith("STRING"):
        return text
    return L.parse_int(text)


def read_csv(path: Path) -> list[Row]:
    with path.open(encoding="utf-8", newline="") as fh:
        rd = csv.reader(fh)
        header = next(rd)
        rows: list[Row] = []
        cols = []
        for i, h in enumerate(header):
            m = _COL.match(h)
            if m:
                cols.append((i, h.split(".", 1)[0], m.group("path"), m.group("type")))
        tol_idx = {header[i][4:]: i for i in range(len(header)) if header[i].startswith("tol.")}
        bidx = header.index("boundary")
        cidx = header.index("comment")
        for rec in rd:
            ins: dict[str, tuple[str, Any]] = {}
            outs: dict[str, tuple[str, Any, float]] = {}
            for i, kind, p, typ in cols:
                cell = rec[i]
                if cell == "":
                    continue
                if kind == "in":
                    ins[p] = (typ, parse_value(typ, cell))
                else:
                    tol = float(rec[tol_idx[p]]) if p in tol_idx and rec[tol_idx[p]] else 0.0
                    outs[p] = (typ, parse_value(typ, cell), tol)
            rows.append(
                Row(rec[0], int(rec[1]), int(rec[2]), ins, outs, rec[bidx].strip().upper() == "TRUE", rec[cidx])
            )
    return rows


def _path_expr(path: str) -> A.Expr:
    expr: A.Expr = A.Name("__INST__")
    for part in re.findall(r"[A-Za-z_]\w*|\[\d+\]", path):
        if part.startswith("["):
            expr = A.Index(expr, [A.Literal("int", part[1:-1], int(part[1:-1]))])
        else:
            expr = A.Member(expr, part)
    return expr


def _equal(typ: str, expected: Any, actual: Any, tol: float) -> bool:
    if typ.upper() in ("REAL", "LREAL"):
        try:
            return abs(float(actual) - float(expected)) <= tol + 1e-12
        except (TypeError, ValueError):
            return False
    if typ.upper() == "BOOL":
        return bool(actual) == bool(expected)
    return bool(actual == expected)


def run_block(project: Project, block: str, rows: list[Row], t_offset: int = 0) -> list[RowResult]:
    """Исполняет сценарии одного блока (ФБ или функции)."""
    results: list[RowResult] = []
    by_scenario: dict[str, list[Row]] = {}
    for r in rows:
        by_scenario.setdefault(r.scenario, []).append(r)
    for scen, srows in by_scenario.items():
        clock = Clock()
        try:
            sim = Sim(project, clock)
        except SimError as exc:
            results.extend(RowResult(scen, r.cycle, r.t_ms, False, error=f"инициализация: {exc}") for r in srows)
            continue
        pou = sim.pous.get(block.upper())
        if pou is None:
            results.extend(RowResult(scen, r.cycle, r.t_ms, False, error=f"нет блока {block}") for r in srows)
            continue
        frame = Instance("__scenario__")
        is_fn = pou.kind == "FUNCTION"
        fn_inputs: dict[str, Any] = {}
        if not is_fn:
            frame.vars["__INST__"] = sim.new_instance(pou)
        s7clock = sim.gvls.get("GVL_S7CLOCK")
        for r in srows:
            clock.now_ms = r.t_ms + t_offset
            if s7clock is not None:
                s7clock.set("xSimulation", True)
                s7clock.set("tSimNow", r.t_ms)
            res = RowResult(scen, r.cycle, r.t_ms, True)
            try:
                if is_fn:
                    for p, (_t, v) in r.inputs.items():
                        fn_inputs[p] = v
                    args = [A.Arg(_const(v), name=p) for p, v in fn_inputs.items()]
                    outs = [d.name for b, d in pou.decls() if b.kind == "VAR_OUTPUT"]
                    for o in outs:
                        frame.vars[f"__OUT_{o.upper()}"] = None
                        frame.types[f"__OUT_{o.upper()}"] = None
                        args.append(A.Arg(A.Name(f"__OUT_{o.upper()}"), name=o, output=True))
                    ret, _ = sim.call_function(pou, args, frame)
                    actual_of = {pou.name.upper(): ret, **{o.upper(): frame.vars[f"__OUT_{o.upper()}"] for o in outs}}
                    for p, (typ, exp, tol) in r.outputs.items():
                        act = actual_of.get(p.upper())
                        if not _equal(typ, exp, act, tol):
                            res.ok = False
                            res.mismatches.append((p, exp, act))
                else:
                    for p, (_t, v) in r.inputs.items():
                        sim.assign(_path_expr(p), v, frame)
                    sim.call_fb(frame.vars["__INST__"])
                    for p, (typ, exp, tol) in r.outputs.items():
                        act = sim.ref_value(_path_expr(p), frame)
                        if not _equal(typ, exp, act, tol):
                            res.ok = False
                            res.mismatches.append((p, exp, act))
            except SimError as exc:
                res.ok = False
                if OUT_OF_SUBSET in str(exc):
                    res.skipped = str(exc)
                else:
                    res.error = str(exc)
            except (KeyError, IndexError) as exc:
                res.ok = False
                res.error = str(exc)
            results.append(res)
    return results


def _const(v: Any) -> A.Literal:
    if isinstance(v, bool):
        return A.Literal("bool", str(v).upper(), v)
    if isinstance(v, float):
        return A.Literal("real", repr(v), v)
    if isinstance(v, str):
        return A.Literal("string", f"'{v}'", v)
    return A.Literal("int", str(v), v)


def summarize(results: list[RowResult]) -> dict[str, Any]:
    """Итог: skip (вне подмножества) не считается ни совпадением, ни расхождением."""
    scen: dict[str, bool] = {}
    skipped: set[str] = set()
    for r in results:
        scen[r.scenario] = scen.get(r.scenario, True) and r.ok
        if r.skipped:
            skipped.add(r.scenario)
    return {
        "rows": len(results),
        "rows_ok": sum(1 for r in results if r.ok),
        "rows_skipped": sum(1 for r in results if r.skipped),
        "scenarios": len(scen),
        "scenarios_ok": sum(1 for v in scen.values() if v),
        "scenarios_skipped": len(skipped),
    }
