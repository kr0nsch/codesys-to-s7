"""Проба M0: импорт PLCopen по языкам в CODESYS 3.5.17.30 → сборка → экспорт → сравнение.

    python tools/probes/run_probes.py import     # импорт/сборка/экспорт (нужен CODESYS)
    python tools/probes/run_probes.py compare    # сравнение входа и экспорта (без CODESYS)

Входы — build/probes/in/*.xml, экспорты — build/probes/out/*.xml, итог — build/probes/import.json.
Сводка G/N переносится вручную в docs/FORMAT-CODESYS.md и docs/PROBES.md (с датой прогона).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(HERE), str(REPO / "tools" / "corpus"), str(REPO / "src")]

import builder as B  # noqa: E402
import cdsrun  # noqa: E402
import probe_specs as PS  # noqa: E402

WORK = REPO / "build" / "probes"


def write_inputs() -> list[dict[str, object]]:
    case = PS.probe_case()
    inp = WORK / "in"
    out = WORK / "out"
    inp.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, object]] = []
    for d in case.duts:
        sub = B.Case(d.name, duts=[d])
        path = inp / f"{d.name}.xml"
        path.write_text(B.pretty(B.project_xml(sub)), encoding="utf-8")
        items.append({"name": d.name, "path": str(path), "export": str(out / f"{d.name}.xml"), "objects": [d.name]})
    for g in case.gvls:
        sub = B.Case(g.name, gvls=[g])
        path = inp / f"{g.name}.xml"
        path.write_text(B.pretty(B.project_xml(sub)), encoding="utf-8")
        items.append({"name": g.name, "path": str(path), "export": str(out / f"{g.name}.xml"), "objects": [g.name]})
    for p in case.pous:
        sub = B.Case(p.name, pous=[p])
        path = inp / f"{p.name}.xml"
        path.write_text(B.pretty(B.project_xml(sub)), encoding="utf-8")
        items.append({"name": p.name, "path": str(path), "export": str(out / f"{p.name}.xml"), "objects": [p.name]})
    return items


def cmd_import() -> int:
    items = write_inputs()
    case = PS.probe_case()
    job = {
        "project": str(WORK / "probe.project"),
        "device": cdsrun.CONTROL_WIN,
        "imports": items,
        "tasks": [
            {"name": t.name, "interval_ms": t.interval_ms, "priority": t.priority, "pous": t.pous} for t in case.tasks
        ],
        "build": True,
    }
    res = cdsrun.run(REPO / "tools" / "codesys" / "c2s7_probe.py", job, WORK, "import", 900)
    (WORK / "import.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {k: res.get(k) for k in ("ok", "error", "imports", "build", "exports")}, indent=1, ensure_ascii=False
        )
    )
    return 0 if res.get("ok") else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=["import", "inputs"])
    args = ap.parse_args(argv)
    if args.action == "inputs":
        for it in write_inputs():
            print(it["path"])
        return 0
    return cmd_import()


if __name__ == "__main__":
    sys.exit(main())
