"""`c2s7 verify <out> --roundtrip`: s7conv → ST′ → оракул; кольцо (AST) для входа из s7-to-codesys.

Результат — EQUIVALENCE.{md,json} в каталоге результата и раздел equivalence в MIGRATION_REPORT.json.
Ограничение (README, EQUIVALENCE.md): кольцо доказывает согласованность c2s7 и s7conv, а не компиляцию
в TIA; общие ошибки одного автора могут погаситься.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from c2s7 import TOOL
from c2s7.api import load_input
from c2s7.pathsort import sorted_paths
from c2s7.sim.scenarios import RowResult, read_csv, run_block
from c2s7.verify import roundtrip as RT
from c2s7.verify import s7conv_clone as SC

LIMITATION = (
    "Кольцо доказывает согласованность c2s7 и s7conv (один автор), а не компиляцию в TIA Portal: общие ошибки "
    "могут погаситься. Противовесы — эталонные модели сценариев, CODESYS Control Win как эталон поведения, XSD и "
    "свой валидатор SimaticML. Импорт в TIA не проверен."
)


def _scenarios_dir(report: dict[str, Any], args: argparse.Namespace) -> Path | None:
    if args.scenarios:
        return Path(args.scenarios)
    inp = Path(report["c2s7"]["input"])
    cand = [inp / "scenarios", inp.parent / "scenarios"]
    return next((c for c in cand if c.is_dir()), None)


def _runs(project_runs: dict[str, list[RowResult]]) -> dict[str, Any]:
    return RT.behaviour_summary(project_runs)


def verify(out: Path, args: argparse.Namespace) -> int:
    rep_path = out / "MIGRATION_REPORT.json"
    if not rep_path.exists():
        raise FileNotFoundError(f"{out}: нет MIGRATION_REPORT.json — сначала c2s7 migrate")
    report = json.loads(rep_path.read_text(encoding="utf-8"))
    clone = SC.check(Path(args.s7conv) if args.s7conv else SC.default_dir())
    if args.oracle not in ("sim", "stsim"):
        print(f"оракул {args.oracle}: запускается отдельно (pytest -m codesys / extras), здесь — c2s7.sim")
    rt = RT.run_s7conv(out, clone)
    result: dict[str, Any] = {
        "tool": TOOL,
        "s7conv": SC.SHA,
        "objects_in": rt.objects_in,
        "regime": args.regime.upper(),
        "oracles": ["c2s7.sim"],
        "limitation": LIMITATION,
    }
    ok = True
    scen = _scenarios_dir(report, args)
    if scen is not None:
        src_proj = load_input(Path(report["c2s7"]["input"]))
        src_runs = {c.stem: run_block(src_proj, c.stem, read_csv(c)) for c in sorted_paths(scen.glob("*.csv"))}
        prime_runs = RT.behaviour(rt.st_prime, scen)
        result["source"] = _runs(src_runs)
        result["st_prime"] = _runs(prime_runs)
        if args.oracle == "stsim":
            from c2s7.verify.stsim_adapter import run_stsim

            result["stsim"] = run_stsim(out, rt.st_prime, scen, clone)
            result["oracles"].append("stsim")
        sp = result["st_prime"]["total"]
        ok = (
            ok
            and sp["scenarios_ok"] == sp["scenarios"]
            and result["source"]["total"]["scenarios_ok"] == sp["scenarios"]
        )
    if report["c2s7"].get("ring"):
        ring = RT.compare_ring(out, clone)
        result["ring"] = RT.ring_summary(ring)
        result["first_divergence"] = ring.first_divergence
        ok = ok and result["ring"]["bug"] == 0
    RT.dump(out / "EQUIVALENCE.json", result)
    (out / "EQUIVALENCE.md").write_text(equivalence_md(result), encoding="utf-8")
    core = {
        "oracles": result["oracles"],
        "regime": result["regime"],
        "scenarios": result.get("st_prime", {}).get("total", {}).get("scenarios", 0),
        "rows": result.get("st_prime", {}).get("total", {}).get("rows", 0),
        "passed": result.get("st_prime", {}).get("total", {}).get("scenarios_ok", 0),
        "skipped": result.get("st_prime", {}).get("total", {}).get("scenarios_skipped", 0),
        "xfail": result.get("ring", {}).get("lossy", 0),
        "first_divergence": result.get("first_divergence"),
    }
    report["equivalence"] = core
    rep_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _print(result)
    return 0 if ok else 1


def _print(r: dict[str, Any]) -> None:
    print(f"{TOOL} verify: s7conv @ {r['s7conv'][:8]}, объектов на входе {r['objects_in']}")
    if "st_prime" in r:
        s, p = r["source"]["total"], r["st_prime"]["total"]
        print(
            f"  сценарии (R1, c2s7.sim): источник {s['scenarios_ok']}/{s['scenarios']}, ST′ {p['scenarios_ok']}/{p['scenarios']}; строк ST′ {p['rows_ok']}/{p['rows']}"
        )
    if "stsim" in r:
        st = r["stsim"]
        print(f"  stsim: {st.get('passed', 0)}/{st.get('total', 0)} ({st.get('note', '')})")
    if "ring" in r:
        ring = r["ring"]
        kinds = ", ".join(f"{k} {v['matched']}/{v['total']}" for k, v in ring["by_kind"].items())
        print(f"  кольцо (AST): {kinds}; bug {ring['bug']}, ring.lossy {ring['lossy']}")


def equivalence_md(r: dict[str, Any]) -> str:
    lines = [
        "# Эквивалентность",
        "",
        f"Создано {r['tool']}; s7conv @ `{r['s7conv']}`; объектов на входе s7conv: {r['objects_in']}.",
        "",
        r["limitation"],
        "",
    ]
    if "st_prime" in r:
        lines += [
            "## Поведение (R1, c2s7.sim)",
            "",
            "| Блок | Источник | ST′ (после s7conv) | Строк ST′ |",
            "|---|---|---|---|",
        ]
        for blk, s in r["st_prime"]["blocks"].items():
            src = r["source"]["blocks"].get(blk, {})
            lines.append(
                f"| {blk} | {src.get('scenarios_ok', 0)}/{src.get('scenarios', 0)} | {s['scenarios_ok']}/{s['scenarios']} | {s['rows_ok']}/{s['rows']} |"
            )
        if r["st_prime"]["failures"]:
            lines += ["", "Первые расхождения:", ""]
            for f in r["st_prime"]["failures"][:10]:
                lines.append(f"- {f['block']}/{f['scenario']}#{f['cycle']}: {f['mismatches'] or f['error']}")
        lines.append("")
    if "stsim" in r:
        st = r["stsim"]
        lines += [
            "## stsim (второе мнение, кейс 1)",
            "",
            f"{st.get('passed', 0)}/{st.get('total', 0)}. {st.get('note', '')}",
            "",
        ]
    if "ring" in r:
        ring = r["ring"]
        lines += ["## Кольцо S7 → CODESYS → S7 (AST)", "", "| Вид | Совпало | Всего |", "|---|---|---|"]
        for k, v in ring["by_kind"].items():
            lines.append(f"| {k} | {v['matched']} | {v['total']} |")
        lines += [
            "",
            f"Категории расхождений: {ring['categories'] or 'нет'}; критерий MVP (bug = 0, ring.lossy ≤ 4): {'выполнен' if ring['mvp'] else 'не выполнен'}.",
            "",
        ]
        for b in ring["blocks"]:
            for d in b["divergences"]:
                lines.append(f"- {b['kind']} {b['name']} — {d['where']}: {d['category']} {d['rule']} {d['note']}")
        lines += ["", "Правила нормализации:", ""]
        for k, v in ring["normalization_rules"].items():
            lines.append(f"- `{k}` — {v}")
        lines.append("")
    return "\n".join(lines)
