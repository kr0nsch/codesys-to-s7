"""Второй оракул кольца: интерпретатор ST s7-to-codesys (`s7conv/tests/stsim.py`) на ST′.

Тесты coUnit строит `s7conv gen-tests <сценарии> --corpus <копия tia/sources с расширением .scl>`
(имена сопоставляются по нашему выходу, ТЗ M10), исполняются наборы `*_ScenarioTest` против
раскладки ST′ (выход `s7conv convert` на наших исходниках TIA). Семантика F_TRIG — как в S7
(так ведёт себя CODESYS 3.5.17.30, проба M0). Это модель, не ПЛК: окончательный результат — CODESYS Control Win (режим R2, extras).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from c2s7.verify import s7conv_clone as SC


def corpus_copy(out: Path, dest: Path) -> Path:
    """Копия `tia/sources` (+ compat) с расширением .scl — корпус имён для gen-tests (ТЗ M10)."""
    corpus = dest / "corpus"
    if corpus.exists():
        shutil.rmtree(corpus)
    corpus.mkdir(parents=True)
    for sub in ("tia/sources", "tia/compat"):
        d = out / sub
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.is_file() and f.suffix in (".scl", ".db", ".udt"):
                    (corpus / (f.stem + ".scl")).write_bytes(f.read_bytes())
    return corpus


def gen_tests(scenarios: Path, dest: Path, clone: Path, corpus: Path | None = None) -> str:
    """`s7conv gen-tests` в каталог dest/tests; возвращает сводку s7conv.

    Рабочий каталог — родитель сценариев: путь в шапке тестов короткий (лимит строки 120 у s7conv).
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(clone) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [
        sys.executable,
        "-m",
        "s7conv",
        "gen-tests",
        scenarios.resolve().name,
        "--out",
        str((dest / "tests").resolve()),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(scenarios.resolve().parent),
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"s7conv gen-tests: код {proc.returncode}\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


def run_stsim(out: Path, st_prime: Path, scenarios: Path, clone: Path) -> dict[str, Any]:
    """Сценарные наборы coUnit на ST′ в stsim: всего/прошло тестов и падения по наборам."""
    SC.import_s7conv(clone)
    from s7conv.layout import L  # type: ignore[import-not-found]
    from s7conv.tests.stsim import F_TRIG_S7, Sim  # type: ignore[import-not-found]

    work = out / "roundtrip" / "stsim"
    summary = gen_tests(scenarios, work, clone, corpus_copy(out, work))
    objects = list(L.scan(str(st_prime), "src").objects) + list(L.scan(str(work), "tests").objects)
    suites = sorted(o.name for o in objects if str(o.name).endswith("_ScenarioTest"))
    total = passed = 0
    failures: dict[str, list[str]] = {}
    for suite in suites:
        res = Sim(objects, f_trig=F_TRIG_S7).run_suite(suite, cycles=3)
        total += len(res.registered)
        passed += len(set(res.finished) - set(res.failures))
        if res.failures:
            failures[suite] = sorted(f"{k}: {v[0]}" for k, v in res.failures.items())
    return {
        "suites": len(suites),
        "total": total,
        "passed": passed,
        "failures": failures,
        "gen_tests": summary,
        "note": "stsim s7-to-codesys @ " + SC.SHA[:8] + ", семантика F_TRIG S7",
    }
