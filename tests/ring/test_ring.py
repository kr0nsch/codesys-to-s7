"""Кейс 1 «Кольцо S7 → CODESYS → S7» @ 2285760c (ТЗ M12): AST по категориям и 39 сценариев R1 в c2s7.sim.

Нужен клон s7-to-codesys @ 2285760c в .cache/ (CI клонирует его с GitHub); без клона — skip.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from c2s7.api import run_migrate
from c2s7.convert.core import Options
from c2s7.verify import roundtrip as RT
from c2s7.verify import s7conv_clone as SC
from c2s7.verify.run import verify

REPO = Path(__file__).resolve().parents[2]
RING = REPO / "tests" / "fixtures" / "s7-to-codesys"


@pytest.fixture(scope="module")
def clone() -> Path:
    path = SC.default_dir(REPO)
    try:
        return SC.check(path)
    except SC.CloneError as exc:
        pytest.skip(f"клон s7-to-codesys: {exc}")


@pytest.fixture(scope="module")
def out(tmp_path_factory: pytest.TempPathFactory, clone: Path) -> Path:
    o = tmp_path_factory.mktemp("ring") / "out"
    run_migrate(RING.relative_to(REPO) if Path.cwd() == REPO else RING, o, Options())
    return o


def test_objects_in_equals_files(out: Path, clone: Path) -> None:
    rt = RT.run_s7conv(out, clone)
    n_files = (
        len(list((out / "tia" / "sources").glob("*")))
        + len(list((out / "tia" / "compat").glob("*.scl")))
        + len(list((out / "roundtrip" / "ob").glob("*.scl")))
    )
    assert rt.objects_in == n_files
    assert "без ошибок" in rt.s7conv_stdout or "записано" in rt.s7conv_stdout


def test_ring_ast_categories(out: Path, clone: Path) -> None:
    rep = RT.compare_ring(out, clone)
    s = RT.ring_summary(rep)
    assert s["issues"] == []
    assert s["raw"] == []  # s7conv разобрал все объекты без RawStmt/RawDecl
    assert s["bug"] == 0
    assert s["lossy"] <= 4
    kinds = {k: (v["matched"], v["total"]) for k, v in s["by_kind"].items()}
    assert kinds["FUNCTION_BLOCK"] == (14, 14)
    assert kinds["FUNCTION"] == (1, 1)
    assert kinds["TYPE"] == (3, 3)
    assert kinds["DATA_BLOCK"] == (22, 22)
    assert kinds["ORGANIZATION_BLOCK"][1] == 4
    for b in s["blocks"]:
        for d in b["divergences"]:
            assert d["category"] == "ring.lossy" and d["note"], d


def test_ring_behaviour_39_of_39(out: Path, clone: Path) -> None:
    args = argparse.Namespace(s7conv=str(clone), oracle="sim", regime="r1", scenarios=str(RING / "scenarios"))
    code = verify(out, args)
    eq = json.loads((out / "EQUIVALENCE.json").read_text(encoding="utf-8"))
    assert code == 0
    assert eq["source"]["total"] == {
        "rows": 263,
        "rows_ok": 263,
        "rows_skipped": 0,
        "scenarios": 39,
        "scenarios_ok": 39,
        "scenarios_skipped": 0,
    }
    assert eq["st_prime"]["total"] == {
        "rows": 263,
        "rows_ok": 263,
        "rows_skipped": 0,
        "scenarios": 39,
        "scenarios_ok": 39,
        "scenarios_skipped": 0,
    }
    rep = json.loads((out / "MIGRATION_REPORT.json").read_text(encoding="utf-8"))
    assert rep["equivalence"]["passed"] == 39 and rep["equivalence"]["oracles"] == ["c2s7.sim"]


def test_ring_stsim_second_oracle(out: Path, clone: Path) -> None:
    from c2s7.verify.stsim_adapter import run_stsim

    rt = RT.run_s7conv(out, clone)
    res = run_stsim(out, rt.st_prime, RING / "scenarios", clone)
    assert res["suites"] == 6 and res["total"] == 39 and res["passed"] == 39 and res["failures"] == {}
