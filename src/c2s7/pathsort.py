"""Порядок путей, одинаковый на Windows и Linux.

`sorted()` по объектам Path зависит от ОС: в Windows сравнение без учёта регистра, в Linux — с учётом
(`F_Convert` и `FB_Latch` меняются местами). Ключ повторяет порядок Windows на любой ОС.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import PurePath
from typing import TypeVar

P = TypeVar("P", bound=PurePath)


def path_key(p: PurePath) -> tuple[tuple[str, ...], str]:
    """Части пути в нижнем регистре; при совпадении — исходное написание."""
    return tuple(s.lower() for s in p.parts), p.as_posix()


def sorted_paths(paths: Iterable[P]) -> list[P]:
    return sorted(paths, key=path_key)
