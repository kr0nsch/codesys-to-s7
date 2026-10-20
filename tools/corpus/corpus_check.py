"""Проверка корпуса «Заречная» без CODESYS: источник и выход c2s7 против сценариев в c2s7.sim (R1).

Путь каждого POU:
- источник — PLCopen из `spec.py` (или экспорт CODESYS `source.cds.xml`, если он есть) → c2s7.sim;
- выход — `c2s7 migrate` всего корпуса → SCL → s7conv (клон @ 2285760c) → ST′ → c2s7.sim;
  блоки, выданные FlgNet, — SimaticML → `s7xml_reader` → c2s7.sim (самосогласованность).

    python tools/corpus/corpus_check.py [--cpu s7-1500|s7-1200] [--source spec|export]
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
for p in (REPO / "src", REPO / "tools" / "corpus", REPO):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import builder as B  # noqa: E402

from c2s7.api import migrate  # noqa: E402
from c2s7.convert.core import Options, Result  # noqa: E402
from c2s7.ingest.layout import load_layout  # noqa: E402
from c2s7.ingest.plcopen import load_plcopen  # noqa: E402
from c2s7.lower import lower_project  # noqa: E402
from c2s7.model import Project  # noqa: E402
from c2s7.sim.scenarios import read_csv, read_trace, run_block, summarize  # noqa: E402
from c2s7.st import nodes as A  # noqa: E402
from c2s7.verify import s7conv_clone as SC  # noqa: E402
from c2s7.verify.roundtrip import run_s7conv  # noqa: E402
from c2s7.verify.s7xml_reader import read_flgnet  # noqa: E402

SCEN = REPO / "scenarios"


@dataclass
class CaseResult:
    name: str
    lang: str
    source: dict[str, Any] = field(default_factory=dict)
    target: dict[str, Any] = field(default_factory=dict)
    target_path: str = ""  # scl | simaticml
    trace_source: dict[str, Any] = field(default_factory=dict)  # R2: c2s7.sim(экспорт CODESYS) против трассы
    trace_target: dict[str, Any] = field(default_factory=dict)  # R2: c2s7.sim(выход c2s7) против трассы
    failures: list[str] = field(default_factory=list)


def corpus_xml(work: Path, include_il: bool = True) -> Path:
    from corpus.common import case

    work.mkdir(parents=True, exist_ok=True)
    f = work / "corpus.xml"
    f.write_text(B.pretty(B.project_xml(case(include_il=include_il), "Zarechnaya")), encoding="utf-8")
    return f


def _fails(name: str, results: list[Any]) -> list[str]:
    out = []
    for r in results:
        if not r.ok:
            what = r.error or r.skipped or "; ".join(f"{p}: ожидалось {e}, получено {a}" for p, e, a in r.mismatches)
            out.append(f"{name} {r.scenario}#{r.cycle}: {what}")
    return out


def prune_unknown(proj: Project) -> Project:
    """Убирает POU и переменные GVL, чьи типы ФБ отсутствуют в проекте (ссылки на блоки FlgNet)."""
    from c2s7.sim.stdlib import BUILTINS
    from c2s7.st import types as T

    while True:
        known = {p.name.upper() for p in proj.pous} | {d.name.upper() for d in proj.duts} | set(BUILTINS)

        def bad(tr: A.TypeRef, known: set[str] = known) -> bool:
            n = T.type_name(tr)
            return (
                isinstance(tr, A.NamedType) and n is not None and T.elem(n.upper()) is None and n.upper() not in known
            )

        drop = {p.name for p in proj.pous if any(bad(d.type) for _, d in p.decls())}
        for g in proj.gvls:
            for b in g.text.var_blocks:
                b.decls = [d for d in b.decls if not bad(d.type)]
        if not drop:
            return proj
        proj.pous = [p for p in proj.pous if p.name not in drop]


def check(cpu: str = "s7-1500", tia: str = "V21", source: str = "spec", work: Path | None = None) -> list[CaseResult]:
    from corpus.common import load_specs

    work = work or (REPO / "build" / "corpus" / cpu)
    specs = load_specs()
    src_xml = corpus_xml(work)
    proj = load_plcopen(src_xml)
    results: list[CaseResult] = []
    # источник
    src_projects: dict[str, Project] = {}
    for name, cs in specs.items():
        exp = cs.path / "source.cds.xml"
        if source == "export" and exp.exists():
            src_projects[name] = lower_project(load_plcopen(exp))
        else:
            src_projects[name] = lower_project(load_plcopen(src_xml))
    # выход c2s7
    res: Result = migrate(load_plcopen(src_xml), Options(cpu=cpu, tia=tia))
    out = work / "out"
    import shutil

    from c2s7.emit.files import write_all

    if out.exists():
        shutil.rmtree(out)
    write_all(res, out)
    clone = SC.check(SC.default_dir(REPO))
    rt = run_s7conv(out, clone)
    prime = prune_unknown(load_layout(rt.st_prime))  # блоки FlgNet в ST′ не попадают: обвязка ссылается на них
    flg = {b.source_pou: b.flgnet for b in res.blocks if b.flgnet}
    for name, cs in specs.items():
        csv = SCEN / f"{name}.csv"
        cr = CaseResult(name, cs.lang)
        rows = read_csv(csv)
        sres = run_block(src_projects[name], name, rows)
        cr.source = summarize(sres)
        cr.failures += _fails("источник", sres)
        tgt_project: Project
        if name in flg:
            cr.target_path = "simaticml"
            xml = (out / str(flg[name])).read_text(encoding="utf-8")
            rb = read_flgnet(xml)
            pou = copy.deepcopy(next(p for p in proj.pous if p.name == name))
            pou.text.body = rb.body
            pou.language = "ST"
            pou.net = None
            pou.text.var_blocks.append(
                A.VarBlock("VAR_TEMP", [], [A.VarDecl(t, A.NamedType("BOOL")) for t in rb.temps])
            )
            lowered = res.lowered.get(name)
            if lowered is not None:
                # статика понижения (биты фронтов) объявлена в исходном POU после migrate
                src_pou = next(p for p in res.project.pous if p.name == name)
                pou.text.var_blocks = [*copy.deepcopy(src_pou.text.var_blocks), pou.text.var_blocks[-1]]
            tgt_project = Project("rd", "st", "rd", "-", pous=[pou], duts=proj.duts, gvls=proj.gvls)
        else:
            cr.target_path = "scl"
            tgt_project = prime
        tres = run_block(tgt_project, name, rows)
        cr.target = summarize(tres)
        cr.failures += _fails("выход", tres)
        trace = cs.path / "oracle-codesys.csv"
        exp = cs.path / "source.cds.xml"
        if trace.exists() and exp.exists():
            r2s = run_block(lower_project(load_plcopen(exp)), name, read_trace(trace))
            cr.trace_source = summarize(r2s)
            cr.failures += _fails("R2 источник", r2s)
            r2t = run_block(tgt_project, name, read_trace(trace))
            cr.trace_target = summarize(r2t)
            cr.failures += _fails("R2 выход", r2t)
        results.append(cr)
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cpu", default="s7-1500")
    ap.add_argument("--tia", default="V21")
    ap.add_argument("--source", default="spec", choices=("spec", "export"))
    args = ap.parse_args(argv)
    rs = check(args.cpu, args.tia, args.source)
    for r in rs:
        r2 = ""
        if r.trace_source:
            ts, tt = r.trace_source, r.trace_target
            r2 = f"  R2: источник {ts['rows_ok']}/{ts['rows']}, выход {tt['rows_ok']}/{tt['rows']}"
        src, tgt = r.source, r.target
        r1 = f"R1: источник {src['scenarios_ok']}/{src['scenarios']}, выход ({r.target_path}) "
        print(f"{r.name:18} {r.lang:4} {r1}{tgt['scenarios_ok']}/{tgt['scenarios']}{r2}")
        for f in r.failures[:6]:
            print("    " + f)
    print(json.dumps({"ok": all(not r.failures for r in rs)}))
    return 0 if all(not r.failures for r in rs) else 1


if __name__ == "__main__":
    sys.exit(main())
