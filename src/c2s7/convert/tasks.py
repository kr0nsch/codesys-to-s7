"""Задачи CODESYS → план OB (ТЗ M5, «Задачи → OB»).

- циклические задачи по возрастанию интервала → OB30…38, дальше с OB123;
- freewheeling → тело в OB1 (program cycle, приоритет 1), остальные свободные → program cycle OB ≥ 123;
- старт → OB100, событийная → вручную;
- превышение числа циклических прерываний профиля → C2S7-TASK-LIMIT;
- приоритеты: различные приоритеты циклических задач CODESYS (0 — самый важный) получают ранг
  r = 0…k−1; P = P_max − r при k ≤ P_max − 1, иначе P = 2 + ⌊(k−1−r)·(P_max−2)/(k−1)⌋;
  равные приоритеты дают равные, слияние разных — C2S7-TASK-PRIO-MERGE.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from c2s7.model import Origin
from c2s7.s7 import ObPlan
from c2s7.st import nodes as A

if TYPE_CHECKING:
    from c2s7.convert.core import Converter


def ob_priorities(cds_prios: list[int], p_max: int) -> dict[int, int]:
    """Приоритет CODESYS → приоритет OB по формуле ТЗ."""
    distinct = sorted(set(cds_prios))
    k = len(distinct)
    out: dict[int, int] = {}
    for r, cp in enumerate(distinct):
        if k <= p_max - 1:
            out[cp] = p_max - r
        else:
            out[cp] = 2 + ((k - 1 - r) * (p_max - 2)) // (k - 1)
    return out


def plan_tasks(conv: Converter) -> None:
    proj = conv.p
    prof = conv.prof
    ob_cfg = prof.ob
    covered = {o.task for o in conv.obs}
    origin = Origin(proj.path)
    cyclic = sorted(
        [t for t in proj.tasks if t.kind == "cyclic" and t.interval_ms is not None],
        key=lambda t: (t.interval_ms or 0, t.priority, t.name),
    )
    prios = ob_priorities([t.priority for t in cyclic], conv.opt.max_ob_priority)
    if len(set(prios.values())) < len(prios):
        conv.c.add("C2S7-TASK-PRIO-MERGE", "", "PROJECT", origin, ", ".join(t.name for t in cyclic))
    numbers = [30, 31, 32, 33, 34, 35, 36, 37, 38]  # cyclic interrupt OB S7-1200/1500, далее с OB123
    nxt = int(ob_cfg["extra_numbers_from"])
    limit = int(ob_cfg["max_cyclic_interrupts"])
    for i, t in enumerate(cyclic):
        if conv.opt.ob_from_tasks and t.name in covered:
            _fill(conv, t.name, t.interval_ms, prios.get(t.priority), t.priority)
            continue
        if i >= limit:
            conv.c.add(
                "C2S7-TASK-LIMIT",
                "",
                "PROJECT",
                origin,
                f"{t.name} ({t.interval_ms} мс)",
                detail=f"лимит {prof.title}: {limit}",
            )
            num: int | None = None
        elif i < len(numbers):
            num = numbers[i]
        else:
            num = nxt
            nxt += 1
        _plan(
            conv,
            t.name,
            f"Cyclic_{t.name}",
            num,
            "CyclicInterrupt",
            t.interval_ms,
            prios.get(t.priority),
            t.priority,
            t.pous,
        )
    free = [t for t in proj.tasks if t.kind == "freewheeling" or (t.kind == "cyclic" and t.interval_ms is None)]
    for j, t in enumerate(free):
        if conv.opt.ob_from_tasks and t.name in covered:
            continue
        num = 1 if j == 0 else nxt
        if j:
            nxt += 1
        _plan(conv, t.name, "Main" if num == 1 else f"Cycle_{t.name}", num, "ProgramCycle", None, 1, t.priority, t.pous)
    for t in proj.tasks:
        if t.kind in ("event", "status", "external"):
            conv.c.add("C2S7-TASK-EVENT", "", "PROJECT", origin, f"{t.name} ({t.kind})")
            _plan(conv, t.name, f"Event_{t.name}", None, "Event", None, None, t.priority, t.pous)
        elif t.kind == "startup" and not (conv.opt.ob_from_tasks and t.name in covered):
            _plan(conv, t.name, "Startup", 100, "Startup", None, 1, t.priority, t.pous)


def _fill(conv: Converter, task: str, interval: float | None, prio: int | None, cds_prio: int) -> None:
    for o in conv.obs:
        if o.task == task:
            o.interval_ms = interval if o.kind == "CyclicInterrupt" else None
            o.priority = prio if o.kind == "CyclicInterrupt" else 1
            o.cds_priority = cds_prio


def _plan(
    conv: Converter,
    task: str,
    name: str,
    number: int | None,
    kind: str,
    interval: float | None,
    prio: int | None,
    cds_prio: int,
    pous: list[str],
) -> None:
    calls: list[str] = []
    body: list[A.Stmt] = []
    for p in pous:
        sym = conv.g.get(p.upper())
        if sym is not None and sym.kind == "program":
            db = f"{sym.name}_DB"
            calls.append(db)
            body.append(A.CallStmt(A.Call(A.SclRef("global", db), [])))
        else:
            calls.append(p)
            body.append(A.CallStmt(A.Call(A.SclRef("global", p), [])))
    plan = ObPlan(task, name, number, kind, interval, prio, calls, cds_priority=cds_prio, body=body)
    conv.c.add(
        "C2S7-TASK-OB", "", "PROJECT", Origin(conv.p.path), f"{task} → OB{number if number is not None else '?'}"
    )
    conv.c.construct("task", "PROJECT", task, Origin(conv.p.path))
    conv.obs.append(plan)
