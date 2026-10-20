"""`c2s7 site --out site-out`: данные просмотрщика (JSON, SVG, zip tia/) и статические файлы `site/assets`.

Кейсы: «Кольцо S7 → CODESYS → S7» (tests/fixtures/s7-to-codesys) и «Все языки» (corpus/zarechnaya.xml),
каждый — для S7-1500/V21 и S7-1200/V19. Эквивалентность берётся из закоммиченных прогонов
`docs/data/*.json` (tools/make_data.py) — сайт сам ничего не исполняет. Чужих доменов нет.
"""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
from importlib import resources
from pathlib import Path
from typing import Any

from c2s7 import TOOL
from c2s7.api import load_input, migrate
from c2s7.convert.core import Options, Result
from c2s7.emit.files import all_outputs, write_all, write_zip
from c2s7.emit.printer import Printer
from c2s7.emit.probe import probes_for
from c2s7.emit.scl import block_text
from c2s7.model import Pou
from c2s7.render.svg import render
from c2s7.render.tree import from_flgnet, from_netir
from c2s7.st import types as T

CASES = [
    {
        "id": "ring",
        "title": "Кольцо S7 → CODESYS → S7",
        "input": "tests/fixtures/s7-to-codesys",
        "about": "Выход s7-to-codesys @ 2285760c (19 POU, S7Compat, GVL, DUT) переведён обратно в SCL и сверен "
        "с исходным SCL по нормализованному AST и 39 сценариям.",
    },
    {
        "id": "corpus",
        "title": "Все языки — ВОС «Заречная»",
        "input": "corpus/zarechnaya.xml",
        "about": "13 POU на ST, FBD, LD, CFC, SFC и IL; 11 собраны в CODESYS 3.5.17.30 и сняты трассами Control Win.",
    },
]
PROFILES = [("s7-1500", "V21"), ("s7-1200", "V19")]
CAPTION = "схема построена c2s7, не снимок TIA"


def _type_text(tr: Any) -> str:
    name = T.type_name(tr)
    if name:
        return name
    return type(tr).__name__.replace("Type", "").upper()


def source_text(pou: Pou, lowered: bool) -> str:
    head = {"FUNCTION_BLOCK": "FUNCTION_BLOCK", "PROGRAM": "PROGRAM", "FUNCTION": "FUNCTION"}.get(pou.kind, pou.kind)
    rt = f" : {_type_text(pou.return_type)}" if pou.return_type is not None else ""
    lines = [f"{head} {pou.name}{rt}"]
    for b in pou.text.var_blocks:
        if any(d.name.startswith("_c2s7_") for d in b.decls) and lowered:
            decls = [d for d in b.decls if not d.name.startswith("_c2s7_")]
        else:
            decls = b.decls
        if not decls:
            continue
        lines.append(" ".join([b.kind, *b.qualifiers]))
        for d in decls:
            init = f" := {Printer('st').expr(d.init)}" if d.init is not None else ""
            at = f" AT {d.address}" if d.address else ""
            lines.append(f"    {d.name}{at} : {_type_text(d.type)}{init};")
        lines.append("END_VAR")
    if lowered:
        lines.append(f"(* {pou.language}: тело показано схемой; ниже — понижение c2s7 в ST *)")
    lines.extend(Printer("st").stmts(pou.text.body, 0))
    return "\n".join(lines) + "\n"


def _findings(res: Result, pou: str) -> list[dict[str, Any]]:
    out = []
    for f in res.collector.findings:
        if f.pou != pou:
            continue
        d = f.as_dict()
        out.append(
            {
                "rule": d["rule"],
                "outcome": d["outcome"],
                "title": d.get("title", ""),
                "why": d.get("why", ""),
                "fix": d.get("fix", ""),
                "line": d["origin"].get("line"),
                "fragment": d.get("fragment", ""),
            }
        )
    return out


def case_data(case: dict[str, str], cpu: str, tia: str, root: Path, out: Path) -> dict[str, Any]:
    src_proj = load_input(root / case["input"], root)
    pristine = {p.name: copy.deepcopy(p) for p in src_proj.pous}
    res = migrate(src_proj, Options(cpu=cpu, tia=tia))
    data_dir = out / "svg" / case["id"] / cpu
    data_dir.mkdir(parents=True, exist_ok=True)
    report = _report(res)
    pous = []
    outcome_of = {p["pou"]: p["outcome"] for p in report["c2s7"]["pous"]}
    ob_of = {o.full_block.source_pou if o.full_block else "": o for o in res.obs}
    for pou in res.project.pous:
        orig = pristine.get(pou.name, pou)
        graphic = pou.language in ("LD", "FBD", "CFC")
        entry: dict[str, Any] = {
            "name": pou.name,
            "language": pou.language,
            "outcome": outcome_of.get(pou.name, "auto"),
            "findings": _findings(res, pou.name),
            "source": source_text(pou, pou.language != "ST"),
        }
        if graphic and orig.net is not None:
            svg = render(from_netir(orig.net), pou.language, f"{pou.name} · CODESYS {pou.language}")
            (data_dir / f"{pou.name}.source.svg").write_text(svg, encoding="utf-8", newline="\n")
            entry["svg_source"] = f"svg/{case['id']}/{cpu}/{pou.name}.source.svg"
        blk = next(
            (b for b in res.blocks if b.source_pou == pou.name and b.kind in ("FUNCTION_BLOCK", "FUNCTION")), None
        )
        if blk is not None and blk.flgnet:
            lang = "LAD" if pou.language == "LD" else "FBD"
            svg = render(
                from_flgnet(res.simaticml[blk.flgnet]), lang, f"{blk.name} · TIA {lang} (FlgNet {tia})", CAPTION
            )
            (data_dir / f"{pou.name}.target.svg").write_text(svg, encoding="utf-8", newline="\n")
            entry["svg_target"] = f"svg/{case['id']}/{cpu}/{pou.name}.target.svg"
            entry["target_kind"] = "simaticml"
            entry["target"] = res.simaticml[blk.flgnet][:6000]
        elif blk is not None:
            entry["target_kind"] = "scl"
            entry["target"] = block_text(blk)
        elif pou.name in ob_of:
            o = ob_of[pou.name]
            entry["target_kind"] = "ob"
            entry["target"] = "\n".join(Printer("scl", indent="\t").stmts(o.body, 1)) + "\n"
        else:
            entry["target_kind"] = "none"
            entry["target"] = ""
        pous.append(entry)
    # zip tia/
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp) / "out"
        files = write_all(res, t)
        dl = out / "downloads"
        dl.mkdir(parents=True, exist_ok=True)
        write_zip(dl / f"{case['id']}-{cpu}-tia.zip", t, [f for f in files if f.startswith("tia/")])
    rules = {f.rule for f in res.collector.findings} | {r for f in res.collector.findings for r in f.related}
    return {
        "case": case["id"],
        "cpu": cpu,
        "tia": tia,
        "profile": res.profile.title,
        "verdict": report["c2s7"]["verdict"],
        "totals": report["totals"],
        "effort": report["effort"],
        "pous": pous,
        "obs": report["c2s7"]["obs"],
        "tags": [
            {"name": t.name, "table": t.table, "type": t.type, "address": t.address, "comment": t.comment}
            for t in res.tags
        ],
        "constants": [{"name": c.name, "type": c.type, "value": c.value, "comment": c.comment} for c in res.constants],
        "probes": [
            {"id": p.id, "rule": p.rule, "construct": p.construct, "expected": p.expected} for p in probes_for(rules)
        ],
        "files": sorted(all_outputs(res)),
        "zip": f"downloads/{case['id']}-{cpu}-tia.zip",
    }


def _report(res: Result) -> dict[str, Any]:
    from c2s7.emit.report import report_json

    return report_json(res, [])


def traps_data() -> list[dict[str, Any]]:
    from c2s7.ingest.layout import load_single_st
    from c2s7.site.traps import TRAPS

    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for t in TRAPS:
            f = Path(tmp) / f"{t.id}.st"
            f.write_text(t.codesys, encoding="utf-8")
            res = migrate(load_single_st(f), Options(cpu=t.profile, tia="V21"))
            blk = next(b for b in res.blocks if b.source_pou == "FB_Trap")
            scl = block_text(blk)
            compat = list(res.compat)
            out.append(
                {
                    "id": t.id,
                    "title": t.title,
                    "codesys": t.codesys,
                    "scl": scl,
                    "compat": compat,
                    "s7_fact": t.s7_fact,
                    "s7_source": t.s7_source,
                    "evidence": t.evidence,
                    "verdict": t.verdict,
                    "rules": sorted({fd.rule for fd in res.collector.findings}),
                }
            )
    return out


def _data_file(root: Path, name: str) -> Any:
    p = root / "docs" / "data" / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def build_site(out: Path, cases: list[Path] | None = None, root: Path | None = None) -> int:
    root = (root or Path.cwd()).resolve()
    if out.exists():
        shutil.rmtree(out)
    (out / "data").mkdir(parents=True)
    assets = resources.files("c2s7.site") / "assets"
    for name in ("index.html", "app.js", "style.css"):
        target = out / ("index.html" if name == "index.html" else f"assets/{name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((assets / name).read_bytes())
    index: dict[str, Any] = {"tool": TOOL, "cases": [], "profiles": [p for p, _ in PROFILES]}
    for case in CASES:
        entry: dict[str, Any] = dict(case)
        entry["data"], entry["totals"] = {}, {}
        for cpu, tia in PROFILES:
            data = case_data(case, cpu, tia, root, out)
            name = f"{case['id']}.{cpu}.json"
            (out / "data" / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            entry["data"][cpu] = f"data/{name}"
            entry["totals"][cpu] = data["totals"]["by_outcome"]
        index["cases"].append(entry)
    index["cases"].append(
        {
            "id": "process-lib",
            "title": "plc-process-lib: ООП",
            "about": "Кейс 3 (уплощение FB_Motor с METHOD/PROPERTY) — P1, в версию 0.1.0 не входит (docs/ROADMAP.md).",
            "planned": True,
        }
    )
    index["traps"] = traps_data()
    index["equivalence"] = {
        "ring": _data_file(root, "ring-verify.json"),
        "ring_controlwin": _data_file(root, "ring-controlwin-r1.json"),
        "corpus": _data_file(root, "corpus.json"),
        "compat": _data_file(root, "compat-controlwin.json"),
    }
    (out / "data" / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"сайт: {out} (кейсов {len(CASES)}, профилей {len(PROFILES)}, ловушек {len(index['traps'])})")
    return 0
