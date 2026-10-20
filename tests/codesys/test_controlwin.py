"""Прогоны в CODESYS 3.5.17.30 и Control Win (только `pytest -m codesys`, локально; итоги — docs/TEST_REPORT.md).

- корпус: import_xml → сборка без ошибок → export_xml → семантика экспорта = spec.py;
- CDS_SR/CDS_RS (обратный перевод s7conv) = Standard.SR/RS на последовательности с SET = RESET = 1;
- кейс 1, R1: ST′ + coUnit из `s7conv gen-tests` — 39/39.
Рантайм общий: занят дольше CDS_LOCK_TIMEOUT_S или близок к концу демо-режима — skip «runtime busy».
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (REPO / "tools" / "codesys", REPO / "tools" / "corpus", REPO / "tools" / "probes", REPO):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

pytestmark = pytest.mark.codesys


def test_corpus_builds_and_export_matches_spec(tmp_path: Path) -> None:
    from build_corpus import build, compare_all

    res = build(tmp_path)
    assert res.get("ok"), res.get("error")
    assert res["build"]["errors"] == 0  # type: ignore[index]
    assert compare_all(tmp_path) == []


def test_compat_sr_rs_against_standard() -> None:
    import check_compat

    code = check_compat.main()
    if code == 3:
        pytest.skip("runtime busy")
    data = json.loads(check_compat.OUT.read_text(encoding="utf-8"))
    assert code == 0 and data["sr_equal"] and data["rs_equal"]


@pytest.mark.slow
def test_ring_r1_in_controlwin() -> None:
    import ring_controlwin

    code = ring_controlwin.main()
    if code == 3:
        pytest.skip("runtime busy")
    data = json.loads(ring_controlwin.OUT.read_text(encoding="utf-8"))
    assert code == 0 and data["totals"]["passed"] == data["totals"]["tests"] == 39
