"""Кейс 2 — корпус «все языки» ВОС «Заречная» (ТЗ M9, M12): без CODESYS, по закоммиченным экспортам и трассам.

- spec.py ↔ source.cds.xml (экспорт CODESYS 3.5.17.30): семантика совпадает;
- R1 «строка = вызов»: c2s7.sim(экспорт) и c2s7.sim(выход c2s7: SCL → s7conv → ST′ или FlgNet → reader)
  против сценариев из эталонных моделей — на S7-1500/V21 и S7-1200/V19;
- R2 «фиксированный цикл»: те же оракулы против трасс Control Win (oracle-codesys.csv, повтор по t_ms).
Нужен клон s7-to-codesys @ 2285760c (без него — skip).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (REPO / "tools" / "corpus", REPO, REPO / "scenarios" / "reference"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from c2s7.verify import s7conv_clone as SC  # noqa: E402

EXPECTED = {
    "F_Convert": "scl",
    "FB_Latch": "scl",
    "FB_TimeIdioms": "scl",
    "FB_LevelAlarm": "simaticml",
    "FB_ValveCmd": "scl",
    "PRG_Permissives": "simaticml",
    "PRG_PumpInterlock": "simaticml",
    "FB_PiCfc": "scl",
    "FB_RatioCfc": "scl",
    "PRG_Backwash": "scl",
    "PRG_FilterAlt": "scl",
    "FB_PulseCountIL": "scl",
    "F_ScaleIL": "scl",
}


def test_thirteen_pous_and_exports() -> None:
    from corpus.common import load_specs

    specs = load_specs()
    assert set(specs) == set(EXPECTED)
    langs = sorted(s.lang for s in specs.values())
    assert {lang: langs.count(lang) for lang in set(langs)} == {"st": 3, "fbd": 2, "ld": 2, "cfc": 2, "sfc": 2, "il": 2}
    for name, cs in specs.items():
        has = (cs.path / "source.cds.xml").exists()
        assert has == cs.in_codesys, name  # IL (M0: N) — без экспорта
        if cs.in_codesys:
            meta = json.loads((cs.path / "oracle-codesys.json").read_text(encoding="utf-8"))
            assert meta["format"] == "oracle-codesys/1" and meta["codesys"] == "3.5.17.30" and meta["period_ms"] == 10


def test_spec_equals_codesys_export() -> None:
    from build_corpus import compare_all

    assert compare_all() == []


def test_scenarios_up_to_date() -> None:
    import gen_scenarios

    assert gen_scenarios.main(["--check"]) == 0


@pytest.fixture(scope="module", params=[("s7-1500", "V21"), ("s7-1200", "V19")], ids=["1500", "1200"])
def results(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    try:
        SC.check(SC.default_dir(REPO))
    except SC.CloneError as exc:
        pytest.skip(f"клон s7-to-codesys: {exc}")
    from corpus_check import check

    cpu, tia = request.param
    rs = check(cpu, tia, "export", tmp_path_factory.mktemp(cpu))
    return {r.name: r for r in rs}


def test_r1_source_and_target(results: dict[str, object]) -> None:
    for name, r in results.items():
        assert r.failures == [], (name, r.failures[:5])  # type: ignore[attr-defined]
        assert r.source["scenarios_ok"] == r.source["scenarios"] > 0  # type: ignore[attr-defined]
        assert r.target["scenarios_ok"] == r.target["scenarios"]  # type: ignore[attr-defined]
        assert r.target_path == EXPECTED[name]  # type: ignore[attr-defined]


def test_r2_traces(results: dict[str, object]) -> None:
    total = 0
    for name, r in results.items():
        if EXPECTED[name] and r.lang != "il":  # type: ignore[attr-defined]
            ts, tt = r.trace_source, r.trace_target  # type: ignore[attr-defined]
            assert ts["rows_ok"] == ts["rows"] > 0, name
            assert tt["rows_ok"] == tt["rows"], name
            total += ts["rows"]
    assert total == 2227
