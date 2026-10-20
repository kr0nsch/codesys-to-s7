"""Порядок блоков во внешних исходниках: типы → глобальные DB → FC/FB (по зависимостям) → экземплярные DB."""

from __future__ import annotations

import re

from c2s7.s7 import S7Block
from c2s7.st import nodes as A

_QUOTED = re.compile(r'"([^"]+)"')


def block_deps(b: S7Block, names: set[str]) -> set[str]:
    deps: set[str] = set()
    texts: list[str] = []
    for sec in b.sections:
        for m in sec.members:
            texts.append(m.type)
            if m.struct:
                texts.extend(x.type for x in m.struct)
    texts.extend(m.type for m in b.struct)
    if b.db_of:
        texts.append(b.db_of)
    for t in texts:
        deps.update(n for n in _QUOTED.findall(t) if n in names)
    for s in b.body:
        for node in A.walk(s):
            if isinstance(node, A.SclRef) and node.kind == "global" and node.name in names:
                deps.add(node.name)
    deps.discard(b.name)
    return deps


def order_blocks(blocks: list[S7Block]) -> list[S7Block]:
    names = {b.name for b in blocks}
    for b in blocks:
        b.deps = block_deps(b, names)
    by_name = {b.name: b for b in blocks}
    out: list[S7Block] = []
    done: set[str] = set()
    visiting: set[str] = set()

    def visit(b: S7Block) -> None:
        if b.name in done or b.name in visiting:
            return
        visiting.add(b.name)
        for d in sorted(b.deps):
            dep = by_name.get(d)
            if dep is not None and dep.order <= b.order:
                visit(dep)
        visiting.discard(b.name)
        done.add(b.name)
        out.append(b)

    for level in sorted({b.order for b in blocks}):
        for b in sorted((x for x in blocks if x.order == level), key=lambda x: x.name.lower()):
            visit(b)
    return out
