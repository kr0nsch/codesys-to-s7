"""Корпус в CODESYS 3.5.17.30: spec.py → PLCopen → import_xml → сборка → export_xml → семантическое сравнение.

    python tools/corpus/build_corpus.py            # нужен CODESYS (noUI, без рантайма)
    python tools/corpus/build_corpus.py --compare  # только сравнение spec ↔ закоммиченные source.cds.xml

Экспорт каждого POU — corpus/<язык>/<кейс>/source.cds.xml (эталон; свои экспорты, MIT), экспорт приложения
с задачами — corpus/application.cds.xml. IL (M0: N) в проект не попадает. Итог — build/corpus/build.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
for p in (REPO / "src", REPO / "tools" / "corpus", REPO / "tools" / "probes", REPO / "tools" / "codesys", REPO):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import builder as B  # noqa: E402
from semcmp import compare  # noqa: E402

from c2s7.ingest.plcopen import load_plcopen  # noqa: E402

WORK = REPO / "build" / "corpus"


def compare_all(export_root: Path | None = None) -> list[str]:
    from corpus.common import load_specs

    diffs: list[str] = []
    for name, cs in load_specs().items():
        if not cs.in_codesys:
            continue
        exp = (export_root / cs.lang / name if export_root else cs.path) / "source.cds.xml"
        if not exp.exists():
            diffs.append(f"{name}: нет {exp.relative_to(REPO)}")
            continue
        tmp = WORK / "spec" / f"{name}.xml"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(B.pretty(B.project_xml(B.Case(name, pous=[cs.pou]))), encoding="utf-8")
        spec_pou = load_plcopen(tmp).pous[0]
        exp_pou = next((p for p in load_plcopen(exp).pous if p.name == name), None)
        if exp_pou is None:
            diffs.append(f"{name}: в экспорте нет POU")
            continue
        diffs.extend(compare(spec_pou, exp_pou))
    return diffs


def build(export_root: Path | None = None) -> dict[str, object]:
    """export_root — куда писать экспорты (по умолчанию — закоммиченные corpus/…; тесты пишут во временный каталог)."""
    import cdsrun
    from corpus.common import case, load_specs

    import online

    WORK.mkdir(parents=True, exist_ok=True)
    c = case(include_il=False)
    duts = c.duts
    c.duts = []  # UNION в схеме PLCopen tc6_0200 нет: DUT создаются объектами с текстом объявления
    xml = WORK / "corpus-codesys.xml"
    xml.write_text(B.pretty(B.project_xml(c, "Zarechnaya")), encoding="utf-8")
    specs = load_specs()
    exports: list[dict[str, object]] = [
        {"path": str((export_root / cs.lang / name if export_root else cs.path) / "source.cds.xml"), "objects": [name]}
        for name, cs in specs.items()
        if cs.in_codesys
    ]
    root = export_root or REPO / "corpus"
    for e in exports:
        Path(str(e["path"])).parent.mkdir(parents=True, exist_ok=True)
    (root / "duts").mkdir(parents=True, exist_ok=True)
    exports.append({"path": str(root / "application.cds.xml"), "application": True})
    exports += [{"path": str(root / "duts" / f"{d.name}.cds.xml"), "objects": [d.name]} for d in duts]
    job = {
        "project": str(WORK / "zarechnaya.project"),
        "device": cdsrun.CONTROL_WIN,
        "libraries": [["Standard", "Standard, * (System)"]],
        "imports": [str(xml)],
        "objects": [{"kind": "dut", "name": d.name, "decl": d.text} for d in duts],
        "tasks": [
            {"name": t.name, "interval_ms": t.interval_ms, "priority": t.priority, "pous": t.pous, "kind": t.kind}
            for t in c.tasks
        ],
        "build": True,
        "exports": exports,
    }
    res = online.run_script("c2s7_online.py", job, "corpus-build", timeout_s=900, online=False)
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compare", action="store_true")
    args = ap.parse_args(argv)
    out: dict[str, object] = {}
    if not args.compare:
        res = build()
        b: dict[str, Any] = dict(res.get("build") or {})  # type: ignore[call-overload]
        out["build"] = b
        out["ok"] = res.get("ok")
        out["error"] = res.get("error")
        out["imported"] = res.get("imported")
        print(f"CODESYS: ok={res.get('ok')} ошибок {b.get('errors')} предупреждений {b.get('warnings')}")
        for m in b.get("messages", [])[:40]:
            print(f"  {m['severity']} {m['object']}: {m['text']}")
        if res.get("error"):
            print(res["error"])
    diffs = compare_all()
    out["semantic_diffs"] = diffs
    (WORK / "build.json").write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"семантических расхождений spec ↔ экспорт: {len(diffs)}")
    for d in diffs:
        print("  " + d)
    return 0 if not diffs else 1


if __name__ == "__main__":
    sys.exit(main())
