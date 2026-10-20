"""Правила C2S7-*: реестр, находки, учёт конструкций по классам, модель трудозатрат."""

from __future__ import annotations

import functools
import random
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

import yaml

from c2s7.model import Origin

OUTCOMES = ("auto", "review", "verify", "manual", "impossible", "info")
SEVERITY = {"info": 0, "auto": 1, "review": 2, "verify": 3, "manual": 4, "impossible": 5}
EFFORT_SEED = 20261019
EFFORT_RUNS = 10_000


@dataclass(frozen=True)
class Rule:
    id: str
    outcome: str
    title: str
    why: str
    source: str
    effort: tuple[float, float, float]
    fix: str


@functools.cache
def registry() -> dict[str, Rule]:
    text = resources.files("c2s7.rules").joinpath("registry.yaml").read_text(encoding="utf-8")
    raw: dict[str, dict[str, Any]] = yaml.safe_load(text)
    eff_text = resources.files("c2s7.rules").joinpath("effort.yaml").read_text(encoding="utf-8")
    eff: dict[str, dict[str, Any]] = yaml.safe_load(eff_text)
    out: dict[str, Rule] = {}
    for rid, d in raw.items():
        mn, mode, mx = (float(x) for x in eff[rid]["minutes"])
        out[rid] = Rule(
            rid, str(d["outcome"]), str(d["title"]), str(d["why"]), str(d["source"]), (mn, mode, mx), str(d["fix"])
        )
    return out


@dataclass
class Finding:
    rule: str
    outcome: str
    pou: str
    language: str
    origin: Origin
    fragment: str = ""
    detail: str = ""
    related: list[str] = field(default_factory=list)

    @property
    def info(self) -> Rule:
        return registry()[self.rule]

    def sort_key(self) -> tuple[str, int, int, str]:
        return (self.origin.file, self.origin.line or 0, self.origin.column or 0, self.rule)

    def as_dict(self) -> dict[str, Any]:
        r = self.info
        mn, mode, mx = r.effort
        d: dict[str, Any] = {
            "rule": self.rule,
            "outcome": self.outcome,
            "family_outcome": self.outcome,
            "language": self.language,
            "pou": self.pou,
            "origin": self.origin.as_dict(),
            "minutes": {"min": mn, "mode": mode, "max": mx},
            "title": r.title,
            "why": r.why,
            "fix": r.fix,
            "source_ref": r.source,
        }
        if self.fragment:
            d["fragment"] = self.fragment
        if self.detail:
            d["detail"] = self.detail
        if self.related:
            d["related"] = sorted(set(self.related))
        return d


@dataclass
class Construct:
    """Учитываемая конструкция (объявление, оператор, сеть, POU, задача) и её класс."""

    kind: str
    language: str
    pou: str
    origin: Origin
    outcome: str = "auto"


class Collector:
    """Собирает находки и конструкции; на одно место — одна находка с тяжелейшим исходом (§4.1)."""

    def __init__(self) -> None:
        self.findings: list[Finding] = []
        self.constructs: list[Construct] = []
        self._stack: list[Construct] = []

    def construct(self, kind: str, language: str, pou: str, origin: Origin) -> Construct:
        c = Construct(kind, language, pou, origin)
        self.constructs.append(c)
        return c

    def push(self, c: Construct) -> None:
        self._stack.append(c)

    def pop(self) -> None:
        self._stack.pop()

    def add(
        self,
        rule: str,
        pou: str,
        language: str,
        origin: Origin,
        fragment: str = "",
        detail: str = "",
        outcome: str | None = None,
        construct: Construct | None = None,
    ) -> Finding:
        r = registry()[rule]
        out = outcome or r.outcome
        for f in self.findings:
            if f.origin == origin and f.pou == pou and f.fragment == fragment:
                if SEVERITY[out] > SEVERITY[f.outcome]:
                    f.related.append(f.rule)
                    f.rule, f.outcome, f.detail = rule, out, detail
                elif rule != f.rule:
                    f.related.append(rule)
                self._raise(construct, out)
                return f
        f = Finding(rule, out, pou, language, origin, fragment[:200], detail)
        self.findings.append(f)
        self._raise(construct, out)
        return f

    def _raise(self, construct: Construct | None, outcome: str) -> None:
        target = construct or (self._stack[-1] if self._stack else None)
        if target is not None and outcome != "info" and SEVERITY[outcome] > SEVERITY[target.outcome]:
            target.outcome = outcome

    def sorted_findings(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: f.sort_key())

    def totals(self) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
        by_outcome = dict.fromkeys(OUTCOMES, 0)
        by_lang: dict[str, dict[str, int]] = {}
        for c in self.constructs:
            by_outcome[c.outcome] += 1
            by_lang.setdefault(c.language, dict.fromkeys(OUTCOMES, 0))[c.outcome] += 1
        for f in self.findings:
            if f.outcome == "info":
                by_outcome["info"] += 1
                by_lang.setdefault(f.language, dict.fromkeys(OUTCOMES, 0))["info"] += 1
        return by_outcome, dict(sorted(by_lang.items()))


def effort(findings: list[Finding], runs: int = EFFORT_RUNS, seed: int = EFFORT_SEED) -> dict[str, Any]:
    """Монте-Карло: сумма треугольных распределений минут по находкам; P50/P90 в часах."""
    params = [f.info.effort for f in findings if f.outcome not in ("auto", "info")]
    params = [p for p in params if p[2] > 0]
    rng = random.Random(seed)
    totals = []
    for _ in range(runs):
        s = 0.0
        for mn, mode, mx in params:
            s += rng.triangular(mn, mx, mode) if mx > mn else mn
        totals.append(s)
    totals.sort()

    def q(p: float) -> float:
        if not totals:
            return 0.0
        idx = min(len(totals) - 1, max(0, round(p * (len(totals) - 1))))
        return round(totals[idx] / 60.0, 2)

    return {
        "model": "triangular-mc",
        "runs": runs,
        "seed": seed,
        "p50_h": q(0.5),
        "p90_h": q(0.9),
        "calibrated": False,
        "calibration": "модель, не калибрована",
    }


def render_md() -> str:
    """docs/RULES.md из реестра (тест проверяет совпадение)."""
    lines = [
        "# Правила C2S7-*",
        "",
        "Документ печатается из `src/c2s7/rules/registry.yaml` (тест `tests/unit/test_rules_mapping.py`).",
        "У каждого правила есть корпус `tests/corpus/<id>/{pos,neg}` и `expected.json`; минуты — треугольное",
        "распределение (min, mode, max) на",
        "находку, задано автором по описанию правила, не калибровано. Итог по проекту — Монте-Карло, 10 000 проб,",
        f"seed {EFFORT_SEED}, находки независимы; P50/P90 в отчёте подписаны «модель, не калибрована».",
        "",
        "| Правило | Класс | Что | Минуты (min/mode/max) |",
        "|---|---|---|---|",
    ]
    reg = registry()
    for rid in sorted(reg):
        r = reg[rid]
        lines.append(
            f"| [{rid}](#{rid.lower()}) | {r.outcome} | {r.title} | {r.effort[0]:g}/{r.effort[1]:g}/{r.effort[2]:g} |"
        )
    lines.append("")
    for rid in sorted(reg):
        r = reg[rid]
        lines += [
            f"## {rid}",
            "",
            f"**{r.title}** — класс `{r.outcome}`.",
            "",
            r.why,
            "",
            f"Что сделать: {r.fix}",
            "",
            f"Источник: {r.source}",
            "",
        ]
    return "\n".join(lines)
