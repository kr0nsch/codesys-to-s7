"""Пороги покрытия (ТЗ §8): строки ≥ 85 %, ветви ≥ 75 % — всего и отдельно для c2s7/emit/simaticml и c2s7/sim.

    python -m pytest --cov=c2s7 --cov-branch --cov-report=json:build/coverage.json
    python tools/check_coverage.py build/coverage.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LINES, BRANCHES = 85.0, 75.0
PACKAGES = ("c2s7/emit/simaticml/", "c2s7/sim/")


def _pct(summaries: list[dict[str, int]]) -> tuple[float, float]:
    cl = sum(s["covered_lines"] for s in summaries)
    ns = sum(s["num_statements"] for s in summaries)
    cb = sum(s["covered_branches"] for s in summaries)
    nb = sum(s["num_branches"] for s in summaries)
    return 100.0 * cl / max(ns, 1), 100.0 * cb / max(nb, 1)


def main(argv: list[str] | None = None) -> int:
    path = Path((argv or sys.argv[1:] or ["build/coverage.json"])[0])
    data = json.loads(path.read_text(encoding="utf-8"))
    files = {f.replace("\\", "/"): v["summary"] for f, v in data["files"].items()}
    rows = [("всего", *_pct(list(files.values())))]
    for pkg in PACKAGES:
        rows.append((pkg, *_pct([s for f, s in files.items() if pkg in f])))
    ok = True
    for name, lines, branches in rows:
        good = lines >= LINES and branches >= BRANCHES
        ok = ok and good
        print(f"{name:24} строки {lines:5.1f} % ветви {branches:5.1f} % {'OK' if good else 'НИЖЕ ПОРОГА'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
