"""Кейс 1 в CODESYS Control Win, режим R1: ST′ кольца + тесты coUnit из `s7conv gen-tests` (ТЗ M10, M12).

Шаги: `c2s7 migrate tests/fixtures/s7-to-codesys` → `s7conv convert` (ST′, клон @ 2285760c) →
`s7conv gen-tests scenarios --corpus <копия tia/sources как .scl>` → временный репозиторий
build/ring-cw (src = ST′, tests = сгенерированные наборы + рукописные наборы S7Compat клона,
tools/codesys = копия из клона) → `python tools/codesys/cds.py test` (импорт, сборка, прогон coUnit
в рантайме под общей блокировкой). Рантайм, запущенный другим проектом, не перезапускается
(CODESYS_RUNTIME_MAX_AGE_MIN задаётся огромным); если до конца его демо-режима меньше 25 минут —
прогон откладывается (код 3, «runtime busy»). Рантайм, запущенный этим скриптом, после прогона
останавливается.

    python tools/codesys/ring_controlwin.py     → docs/data/ring-controlwin-r1.json
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in (HERE, REPO / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import online  # noqa: E402
from c2s7.api import run_migrate  # noqa: E402
from c2s7.convert.core import Options  # noqa: E402
from c2s7.verify import s7conv_clone as SC  # noqa: E402
from c2s7.verify.roundtrip import run_s7conv  # noqa: E402
from c2s7.verify.stsim_adapter import corpus_copy, gen_tests  # noqa: E402
from cdshost import cli as H  # noqa: E402

WORK = REPO / "build" / "ring-cw"
OUT = REPO / "docs" / "data" / "ring-controlwin-r1.json"


def prepare() -> Path:
    clone = SC.check(SC.default_dir(REPO))
    out = REPO / "build" / "ring-cw-out"
    run_migrate(REPO / "tests" / "fixtures" / "s7-to-codesys", out, Options())
    rt = run_s7conv(out, clone)
    tests_root = out / "roundtrip" / "cw"
    print(gen_tests(REPO / "tests" / "fixtures" / "s7-to-codesys" / "scenarios", tests_root, clone, corpus_copy(out, tests_root)))
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    shutil.copytree(rt.st_prime / "src", WORK / "src")
    shutil.copytree(tests_root / "tests", WORK / "tests")
    shutil.copytree(clone / "tests" / "POUs" / "S7Compat", WORK / "tests" / "POUs" / "S7Compat")
    shutil.copytree(clone / "tools" / "codesys", WORK / "tools" / "codesys", ignore=shutil.ignore_patterns("__pycache__"))
    (WORK / "LICENSE").write_text("Временная сборка c2s7 для прогона в Control Win (не публикуется).\n", encoding="utf-8")
    return WORK


def main() -> int:
    st = online.settings()
    status = H.runtime_status(st)
    left = status.get("demo_left_min")
    if status["running"] and left is not None and left < 25:
        print(f"runtime busy: рантайм другого проекта работает {status['age_min']} мин, до конца демо-режима {left} мин")
        return 3
    started_here = not status["running"] and not status["port_open"]
    work = prepare()
    env = dict(os.environ)
    env["CODESYS_RUNTIME_MAX_AGE_MIN"] = "1000000"  # не перезапускать чужой рантайм
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, str(work / "tools" / "codesys" / "cds.py"), "test", "--no-deps"],
        cwd=str(work),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    (REPO / "build" / "ring-cw.log").write_text(proc.stdout + "\n" + proc.stderr, encoding="utf-8")
    print(proc.stdout[-3000:])
    if started_here:
        with H.runtime_lock(st, "c2s7 ring stop"):
            H.runtime_stop(st)
    res_path = work / "build" / "test-results.json"
    if not res_path.exists():
        print("нет test-results.json:", proc.stderr[-2000:])
        return 1
    return summarize(res_path, started_here, proc.returncode)


def summarize(res_path: Path, started_here: bool, returncode: int = 0) -> int:
    data = json.loads(res_path.read_text(encoding="utf-8"))
    suites = []
    for s in data.get("suites", []):
        cases = s.get("cases", [])
        name = cases[0]["class_name"].rsplit(".", 1)[-1] if cases else s.get("name")
        suites.append({"name": name, "tests": len(cases), "failed": [c["name"] for c in cases if c.get("status") != "PASS"]})
    summary = {
        "what": "кейс 1, R1 в CODESYS Control Win: ST′ (s7conv @ 2285760c из tia/sources c2s7) + coUnit из gen-tests",
        "codesys": data.get("codesys_version"),
        "framework": data.get("framework"),
        "totals": data.get("totals"),
        "suites": suites,
        "build": data.get("build"),
        "date": (data.get("started") or "")[:10],
        "runtime_started_here": started_here,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary["totals"], ensure_ascii=False))
    return 0 if returncode == 0 and data.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
