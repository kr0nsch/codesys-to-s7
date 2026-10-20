"""Снятие переходов (ТЗ M3): JMP ST, JMP/JMPC/JMPCN IL, Jump/Label FBD и LD.

Работает на плоском списке операторов верхнего уровня (так их дают понижения графики и IL):
- прыжок вперёд `Jump(L, c) … L:` → `IF NOT c THEN … END_IF` (безусловный — участок недостижим
  и удаляется);
- прыжок назад `L: … Jump(L, c)` → `REPEAT … UNTIL NOT c END_REPEAT`;
- метки без прыжков удаляются.

Участок сворачивается, только если в него не входят прыжки снаружи и из него не выходят прыжки
наружу. Что не свелось, остаётся `GOTO` (C2S7-GFX-GOTO, verify): s7conv такой POU разбирает, но не
переносит, поэтому он исключается из кольца поведения.
"""

from __future__ import annotations

from dataclasses import dataclass

from c2s7.lower.common import not_
from c2s7.st import nodes as A


@dataclass
class JumpResult:
    stmts: list[A.Stmt]
    remaining: list[str]  # метки неприводимых переходов


def _targets(stmts: list[A.Stmt]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for i, s in enumerate(stmts):
        if isinstance(s, A.Jump):
            out.setdefault(s.label.upper(), []).append(i)
    return out


def _labels(stmts: list[A.Stmt]) -> dict[str, int]:
    return {s.name.upper(): i for i, s in enumerate(stmts) if isinstance(s, A.Label)}


def _closed(stmts: list[A.Stmt], lo: int, hi: int, own: str) -> bool:
    """Участок [lo, hi) замкнут: прыжки внутри ведут внутрь, в метки внутри не прыгают снаружи."""
    labels = _labels(stmts)
    jumps = _targets(stmts)
    inside_labels = {n for n, i in labels.items() if lo <= i < hi}
    for i in range(lo, hi):
        s = stmts[i]
        if isinstance(s, A.Jump):
            li = labels.get(s.label.upper())
            if li is None or not (lo <= li < hi):
                return False
    for n in inside_labels:
        if any(not (lo <= j < hi) for j in jumps.get(n, [])):
            return False
    return own.upper() not in inside_labels


def _step(stmts: list[A.Stmt]) -> list[A.Stmt] | None:
    """Один шаг свёртки: самый короткий сворачиваемый переход; None — сворачивать нечего."""
    labels = _labels(stmts)
    best: tuple[int, int, int] | None = None  # (длина, индекс прыжка, индекс метки)
    for i, s in enumerate(stmts):
        if not isinstance(s, A.Jump):
            continue
        li = labels.get(s.label.upper())
        if li is None:
            continue
        lo, hi = (i + 1, li) if li > i else (li + 1, i)
        if li < i and s.cond is None:
            continue  # бесконечный цикл
        if not _closed(stmts, lo, hi, s.label):
            continue
        if best is None or hi - lo < best[0]:
            best = (hi - lo, i, li)
    if best is None:
        return None
    _, i, li = best
    jump = stmts[i]
    assert isinstance(jump, A.Jump)
    if li > i:
        body = stmts[i + 1 : li]
        if jump.cond is None:
            repl: list[A.Stmt] = []
        else:
            repl = [A.If([(not_(jump.cond), body)], None, pos=jump.pos, lead=list(jump.lead))] if body else []
        return stmts[:i] + repl + stmts[li:]
    body = stmts[li + 1 : i]
    assert jump.cond is not None
    loop = A.Repeat(body, not_(jump.cond), pos=jump.pos, lead=list(jump.lead))
    return [*stmts[: li + 1], loop, *stmts[i + 1 :]]


def remove_jumps(stmts: list[A.Stmt]) -> JumpResult:
    cur = list(stmts)
    while True:
        nxt = _step(cur)
        if nxt is None:
            break
        cur = nxt
    used = set(_targets(cur))
    cur = [s for s in cur if not (isinstance(s, A.Label) and s.name.upper() not in used)]
    remaining = sorted({s.label for s in cur if isinstance(s, A.Jump)})
    return JumpResult(cur, remaining)
