"""Общие настройки тестов: тесты с CODESYS идут только при явном `-m codesys`."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
for sub in ("src", "tools", "tools/codesys", "tools/corpus", "tools/probes", "scenarios/reference"):
    p = str(REPO / sub)
    if p not in sys.path:
        sys.path.insert(0, p)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    marker_expr = config.getoption("-m") or ""
    if "codesys" in marker_expr:
        return
    skip = pytest.mark.skip(reason="CODESYS: запуск только с -m codesys (локально, под блокировкой рантайма)")
    for item in items:
        if "codesys" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def repo() -> Path:
    return REPO
