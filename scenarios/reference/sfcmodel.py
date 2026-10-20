"""Модель цикла SFC CODESYS для эталонных моделей корпуса (порядок — справка CODESYS, docs/ORACLES.md).

Шаги и переходы задаются таблицей, условия — функциями Python от входов и времени шагов, тела
действий — функциями, меняющими выходы. Описание порядка: сброс флагов IEC → exit → entry → время и
действие шага → IEC-действия по алфавиту в два прохода (последний вызов деактивированных, затем
активные) → переходы по снимку активности. Время шага отсчитывается с цикла, в котором сработал
активирующий переход (так показала трасса CODESYS Control Win PRG_Backwash, R2).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SfcDef:
    steps: list[str]
    initial: str
    actions: dict[str, list[tuple[str, str]]]  # шаг → [(квалификатор, действие)]
    transitions: list[tuple[list[str], Callable[[dict[str, Any], dict[str, int]], bool], list[str]]]
    bodies: dict[str, Callable[[dict[str, Any]], None]]
    step_actions: dict[str, str] = field(default_factory=dict)


class SfcRun:
    def __init__(self, d: SfcDef, outputs: dict[str, Any]) -> None:
        self.d = d
        self.x = {s: s == d.initial for s in d.steps}
        self.xp = dict.fromkeys(d.steps, False)
        self.since: dict[str, int | None] = dict.fromkeys(d.steps)
        self.q: dict[str, bool] = {}
        self.stored: dict[str, bool] = {}
        self.out = dict(outputs)

    def call(self, inputs: dict[str, Any], now: int) -> dict[str, Any]:
        d = self.d
        t: dict[str, int] = {}
        for s in d.steps:
            if self.x[s]:
                if self.since[s] is None:
                    self.since[s] = now
                t[s] = now - (self.since[s] or 0)
                if s in d.step_actions:
                    d.bodies[d.step_actions[s]](self.out)
            else:
                self.since[s] = None
                t[s] = 0
        assoc: dict[str, list[tuple[str, str]]] = {}
        for s, acts in d.actions.items():
            for q, a in acts:
                assoc.setdefault(a, []).append((s, q))
        names = sorted(assoc, key=str.upper)
        qp = dict(self.q)
        for a in names:
            pairs = assoc[a]
            if any(q in ("S", "R") for _, q in pairs):
                st = self.stored.get(a, False) or any(self.x[s] for s, q in pairs if q == "S")
                self.stored[a] = st and not any(self.x[s] for s, q in pairs if q == "R")
            n = any(self.x[s] for s, q in pairs if q == "N")
            p = any(self.x[s] and not self.xp[s] for s, q in pairs if q == "P")
            self.q[a] = n or p or self.stored.get(a, False)
        for a in names:
            if qp.get(a, False) and not self.q[a]:
                d.bodies[a](self.out)
        for a in names:
            if self.q[a]:
                d.bodies[a](self.out)
        snap = dict(self.x)
        self.xp = dict(self.x)
        for src, cond, dst in d.transitions:
            if all(snap[s] for s in src) and cond(inputs, t):
                for s in src:
                    snap[s] = False
                    self.x[s] = False
                for s in dst:
                    self.x[s] = True
        for s in d.steps:  # время шага — с цикла активирующего перехода (трасса Control Win)
            if self.x[s] and self.since[s] is None:
                self.since[s] = now
            elif not self.x[s]:
                self.since[s] = None
        return dict(self.out)
