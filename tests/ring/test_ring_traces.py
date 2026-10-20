"""Кейс 1, R2 «фиксированный цикл»: трассы CODESYS Control Win 3.5.17.30 (tests/oracle/ring) против c2s7.sim.

Источник — ST s7-to-codesys (фикстура, таймеры S7Compat), ST′ — `s7conv convert --timers standard` из
tia/sources c2s7. Строки сценариев держатся до t_ms следующей (цикл 10 мс), выходы записаны на первом и
последнем цикле каждой строки; c2s7.sim повторяет все циклы по записанным отметкам TIME().
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from c2s7.api import run_migrate
from c2s7.convert.core import Options
from c2s7.ingest.layout import load_layout
from c2s7.sim.scenarios import read_trace, run_block
from c2s7.verify import s7conv_clone as SC
from c2s7.verify.roundtrip import run_s7conv

REPO = Path(__file__).resolve().parents[2]
ORACLE = REPO / "tests" / "oracle" / "ring"
BLOCKS = ["FB_AlarmDelay", "FB_AnalogIn", "FB_Motor", "FB_PumpAlternation", "FB_Sequencer", "FB_Totalizer"]


def _check(proj: object, label: str) -> tuple[int, int]:
    compared = cycles = 0
    for b in BLOCKS:
        rows = read_trace(ORACLE / label / b / "oracle-codesys.csv", tol=1e-3)
        meta = json.loads((ORACLE / label / b / "oracle-codesys.json").read_text(encoding="utf-8"))
        assert meta["format"] == "oracle-codesys/1" and meta["period_ms"] == 10 and meta["cycles"] == len(rows)
        res = run_block(proj, b, rows)  # type: ignore[arg-type]
        bad = [r for r in res if not r.ok]
        assert bad == [], (label, b, [(r.cycle, r.error, r.mismatches) for r in bad[:3]])
        compared += sum(1 for r in rows if r.outputs)
        cycles += len(rows)
    return compared, cycles


def test_source_trace() -> None:
    compared, cycles = _check(load_layout(REPO / "tests" / "fixtures" / "s7-to-codesys"), "source")
    assert (compared, cycles) == (487, 50739)


def test_st_prime_trace(tmp_path: Path) -> None:
    try:
        clone = SC.check(SC.default_dir(REPO))
    except SC.CloneError as exc:
        pytest.skip(f"клон s7-to-codesys: {exc}")
    out = tmp_path / "ring"
    run_migrate(REPO / "tests" / "fixtures" / "s7-to-codesys", out, Options())
    rt = run_s7conv(out, clone, timers="standard")
    compared, cycles = _check(load_layout(rt.st_prime), "st_prime")
    assert (compared, cycles) == (487, 50739)
