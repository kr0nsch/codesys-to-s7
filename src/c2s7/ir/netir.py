"""NetIR — сети LD/FBD/CFC: элементы, провода, порядок, отрицания, фронты.

Из PLCopen XML CODESYS (docs/FORMAT-CODESYS.md): LD — одна шина, сеть начинается парой comment +
vendorElement networktitle; FBD — сети по `localId div 10^10`; CFC — одна сеть с executionOrderId,
провода через connector. Понижение в ST AST — c2s7.lower.net, в FlgNet — c2s7.emit.simaticml.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Conn:
    ref: str
    formal: str | None = None


@dataclass
class Pin:
    name: str
    conns: list[Conn] = field(default_factory=list)
    negated: bool = False


@dataclass
class Element:
    id: str
    kind: str  # left_rail right_rail contact coil in_var out_var inout_var block jump label return connector comment
    var: str | None = None
    negated: bool = False
    edge: str = "none"  # none | rising | falling
    storage: str = "none"  # none | set | reset
    type_name: str | None = None
    instance: str | None = None
    call_type: str | None = None  # operator | function | functionblock
    inputs: list[Pin] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    order: int | None = None
    label: str | None = None
    line: int | None = None

    @property
    def conns(self) -> list[Conn]:
        """Провода единственного входа (контакт, катушка, выход, переход)."""
        return self.inputs[0].conns if self.inputs else []


@dataclass
class Network:
    index: int
    title: str = ""
    comment: str = ""
    elements: list[Element] = field(default_factory=list)
    label: str | None = None

    def by_id(self) -> dict[str, Element]:
        return {e.id: e for e in self.elements}


@dataclass
class NetBody:
    language: str  # LD | FBD | CFC
    networks: list[Network] = field(default_factory=list)
    pages: int = 0
    meta: Any = None  # c2s7.lower.net.NetMeta после понижения (биты фронтов, обратные связи)

    def all_elements(self) -> dict[str, Element]:
        out: dict[str, Element] = {}
        for n in self.networks:
            out.update(n.by_id())
        return out
