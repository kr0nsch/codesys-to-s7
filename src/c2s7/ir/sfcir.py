"""SfcIR — шаги, переходы, ветвления, действия SFC CODESYS → автомат SCL (c2s7.lower.sfc) или GRAPH (P1)."""

from __future__ import annotations

from dataclasses import dataclass, field

from c2s7.st import nodes as A


@dataclass
class ActionAssoc:
    qualifier: str  # N S R P P0 P1 L D SD DS SL
    action: str
    duration: str = ""
    indicator: str = ""


@dataclass
class SfcStep:
    name: str
    initial: bool = False
    actions: list[ActionAssoc] = field(default_factory=list)
    step_action: str | None = None  # действие шага (не IEC)
    entry: str | None = None
    exit: str | None = None
    min_time: str | None = None
    max_time: str | None = None
    local_id: str | None = None


@dataclass
class SfcTransition:
    id: str
    condition: A.Expr
    source: list[str]  # шаги, которые должны быть активны
    target: list[str]  # шаги, которые активируются
    order: int = 0  # порядок проверки (слева направо)
    text: str = ""


@dataclass
class SfcBody:
    steps: list[SfcStep] = field(default_factory=list)
    transitions: list[SfcTransition] = field(default_factory=list)

    def step(self, name: str) -> SfcStep:
        return next(s for s in self.steps if s.name.upper() == name.upper())

    @property
    def initial(self) -> list[SfcStep]:
        return [s for s in self.steps if s.initial]

    def iec_actions(self) -> list[str]:
        """IEC-действия по алфавиту (порядок исполнения CODESYS, п. 5)."""
        names = {a.action for s in self.steps for a in s.actions}
        return sorted(names, key=str.upper)
