"""Обратная проверка (ТЗ M10): SCL c2s7 → s7conv @ 2285760c → ST′ → c2s7.sim против сценариев.

Вызов s7conv — явным списком файлов (каталог на вход не подаётся: collect_inputs берёт из каталога
только *.scl и пропустил бы .db/.udt); таблица тегов и ob_config — из roundtrip/. Число объектов на
входе s7conv = числу файлов tia/sources (+ tia/compat + roundtrip/ob).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from c2s7.ingest.layout import load_layout
from c2s7.sim.scenarios import RowResult, read_csv, run_block, summarize
from c2s7.verify import astcmp as AC
from c2s7.verify import s7conv_clone as SC


@dataclass
class RoundTrip:
    inputs: list[Path]
    st_prime: Path
    s7conv_stdout: str
    objects_in: int


def s7conv_inputs(out: Path) -> list[Path]:
    files = sorted((out / "tia" / "sources").glob("*"))
    files += sorted((out / "tia" / "compat").glob("*.scl"))
    files += sorted((out / "roundtrip" / "ob").glob("*.scl"))
    return files


def run_s7conv(out: Path, clone: Path, timers: str = "s7compat") -> RoundTrip:
    out = out.resolve()
    files = s7conv_inputs(out)
    dest = out / "roundtrip" / "st_prime"
    cmd = [
        sys.executable,
        "-m",
        "s7conv",
        "convert",
        *[str(f) for f in files],
        "--out",
        str(dest),
        "--clean",
        "--emit-support",
    ]
    tags = out / "roundtrip" / "PlcTags.csv"
    if tags.exists():
        cmd += ["--tags", str(tags)]
    obc = out / "roundtrip" / "ob_config.json"
    if obc.exists():
        cmd += ["--ob-config", str(obc)]
    cmd += ["--timers", timers]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(clone) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=str(clone), check=False
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"s7conv convert: код {proc.returncode}\n{proc.stdout}\n{proc.stderr}")
    return RoundTrip(files, dest, proc.stdout + proc.stderr, len(files))


def behaviour(project_dir: Path, scenarios: Path) -> dict[str, list[RowResult]]:
    proj = load_layout(project_dir)
    out: dict[str, list[RowResult]] = {}
    for csvp in sorted(scenarios.glob("*.csv")):
        out[csvp.stem] = run_block(proj, csvp.stem, read_csv(csvp))
    return out


@dataclass
class RingReport:
    blocks: list[AC.BlockResult] = field(default_factory=list)
    by_kind: dict[str, list[int]] = field(default_factory=dict)
    categories: dict[str, int] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    raw: list[str] = field(default_factory=list)
    source_runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    prime_runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    first_divergence: dict[str, Any] | None = None


LOSSY_ARG = "ring.lossy.arg_dropped"
LOSSY_REF = "s7-to-codesys docs/MAPPING.md, «Не поддерживается»: Variant, Any (параметр не перенесён — MIGRATION-TODO)"


def classify(d: AC.Divergence) -> None:
    """Категория расхождения: norm.* (нормализация не покрыла), ring.lossy.* (известная потеря s7conv), bug."""
    o, n = d.original, d.ours
    if o.startswith("('call', ('call'") and n.startswith("('call', ('call'"):
        # тот же вызов, у нас нет части аргументов — s7conv опустил их с пометкой MIGRATION-TODO
        o_args = o.count("('a', ")
        n_args = n.count("('a', ")
        if n_args < o_args and n.split("(('a',")[0] == o.split("(('a',")[0]:
            d.category, d.rule, d.note = "ring.lossy", LOSSY_ARG, LOSSY_REF
            return
    d.category = "bug"


def compare_ring(out: Path, clone: Path) -> RingReport:
    parser = SC.import_s7conv(clone, "s7conv.parser")
    orig, iss1 = AC.parse_scl_files(parser, sorted((clone / "samples" / "scl").glob("*.scl")))
    files = sorted((out / "tia" / "sources").glob("*")) + sorted((out / "roundtrip" / "ob").glob("*.scl"))
    ours, iss2 = AC.parse_scl_files(parser, files)
    rep = RingReport(issues=[*iss1, *iss2], raw=AC.raw_nodes(ours))
    canon = AC.Canon(AC.load_tag_addresses(clone / "samples" / "scl" / "PlcTags.csv"))
    types = {k: v for k, v in orig.items() if v.kind == "TYPE"}
    for name, b in sorted(orig.items()):
        kind_counts = rep.by_kind.setdefault(b.kind, [0, 0])
        kind_counts[1] += 1
        o = ours.get(name)
        if o is None:
            rep.blocks.append(AC.BlockResult(b.name, b.kind, "missing", [AC.Divergence(b.name, "блок", b.name, "—")]))
            rep.categories["bug"] = rep.categories.get("bug", 0) + 1
            continue
        divs = AC.compare_blocks(b, o, canon, types)
        for d in divs:
            classify(d)
            key = d.rule or d.category
            rep.categories[key] = rep.categories.get(key, 0) + 1
            if rep.first_divergence is None:
                rep.first_divergence = {"block": d.block, "where": d.where, "category": d.category, "rule": d.rule}
        if not divs:
            kind_counts[0] += 1
        rep.blocks.append(AC.BlockResult(b.name, b.kind, "match" if not divs else "diverged", divs))
    for name in sorted(set(ours) - set(orig)):
        rep.blocks.append(AC.BlockResult(ours[name].name, ours[name].kind, "extra"))
    return rep


def ring_summary(rep: RingReport) -> dict[str, Any]:
    lossy = sum(v for k, v in rep.categories.items() if k.startswith("ring.lossy"))
    bugs = rep.categories.get("bug", 0)
    norm = sum(v for k, v in rep.categories.items() if k.startswith("norm."))
    return {
        "by_kind": {k: {"matched": v[0], "total": v[1]} for k, v in sorted(rep.by_kind.items())},
        "categories": dict(sorted(rep.categories.items())),
        "lossy": lossy,
        "bug": bugs,
        "norm": norm,
        "mvp": bugs == 0 and lossy <= 4,
        "normalization_rules": AC.NORM_RULES,
        "issues": rep.issues,
        "raw": rep.raw,
        "blocks": [
            {
                "name": b.name,
                "kind": b.kind,
                "status": b.status,
                "divergences": [
                    {
                        "where": d.where,
                        "category": d.category,
                        "rule": d.rule,
                        "note": d.note,
                        "original": d.original,
                        "ours": d.ours,
                    }
                    for d in b.divergences
                ],
            }
            for b in rep.blocks
        ],
    }


def behaviour_summary(runs: dict[str, list[RowResult]]) -> dict[str, Any]:
    total = {"rows": 0, "rows_ok": 0, "rows_skipped": 0, "scenarios": 0, "scenarios_ok": 0, "scenarios_skipped": 0}
    per: dict[str, Any] = {}
    for blk, res in runs.items():
        s = summarize(res)
        per[blk] = s
        for k in total:
            total[k] += s[k]
    fails = [
        {
            "block": blk,
            "scenario": r.scenario,
            "cycle": r.cycle,
            "mismatches": [list(map(str, m)) for m in r.mismatches],
            "error": r.error,
            "skipped": r.skipped,
        }
        for blk, res in runs.items()
        for r in res
        if not r.ok
    ]
    return {"total": total, "blocks": per, "failures": fails[:50]}


def dump(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
