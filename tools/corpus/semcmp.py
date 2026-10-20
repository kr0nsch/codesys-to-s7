"""Семантическое сравнение «spec.py ↔ экспорт CODESYS» (ТЗ M9: обязательное, иначе CODESYS незаметно
перестроит сеть).

Сравниваются: язык и интерфейс; ST — нормализованное тело; LD/FBD — число сетей, метки, по сети —
элементы (вид, операнд, отрицание, фронт, хранение, тип блока, экземпляр) и понижение в ST (порядок,
отрицания, топология); CFC — блоки с executionOrderId и понижение; SFC — шаги, действия с
квалификаторами, переходы (источники, цели, условия) и понижение в автомат. localId, порядок атрибутов
и addData (docs/FORMAT-CODESYS.md) в сравнение не входят.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from c2s7.emit.printer import Printer  # noqa: E402
from c2s7.lower import lower_pou  # noqa: E402
from c2s7.model import Pou  # noqa: E402
from c2s7.st import types as T  # noqa: E402


def _type(tr: Any) -> str:
    return (T.type_name(tr) or type(tr).__name__).upper()


def signature(pou: Pou) -> dict[str, Any]:
    p = copy.deepcopy(pou)
    sig: dict[str, Any] = {
        "language": p.language,
        "kind": p.kind,
        "interface": [(b.kind, d.name, _type(d.type)) for b, d in p.decls()],
        "actions": sorted(a.name for a in p.actions),
    }
    if p.net is not None:
        nets = []
        for n in p.net.networks:
            els = []
            for e in n.elements:
                if e.kind in ("left_rail", "right_rail", "connector", "continuation", "comment"):
                    continue
                els.append(
                    (
                        e.kind,
                        (e.var or "").replace(" ", ""),
                        e.negated,
                        e.edge,
                        e.storage,
                        (e.type_name or "").upper(),
                        e.instance or "",
                        e.order,
                        tuple((pin.name.upper(), pin.negated) for pin in e.inputs),
                    )
                )
            nets.append({"label": n.label, "elements": sorted(els, key=repr)})
        sig["networks"] = nets
    if p.sfc is not None:
        sig["steps"] = [
            (s.name, s.initial, s.step_action, tuple((a.qualifier, a.action) for a in s.actions)) for s in p.sfc.steps
        ]
        sig["transitions"] = sorted(
            (tuple(t.source), tuple(t.target), t.text.replace(" ", "").upper()) for t in p.sfc.transitions
        )
    lowered = lower_pou(p, None)
    body = lowered if lowered is not None else p.text.body
    sig["st"] = "\n".join(Printer("st").stmts(body, 0))
    return sig


def compare(spec: Pou, export: Pou) -> list[str]:
    a, b = signature(spec), signature(export)
    diffs = []
    for key in sorted(set(a) | set(b)):
        if a.get(key) != b.get(key):
            diffs.append(f"{spec.name}: {key}: spec={a.get(key)!r} export={b.get(key)!r}"[:600])
    return diffs
