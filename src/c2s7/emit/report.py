"""MIGRATION_REPORT.{md,json,html} и trace.json.

JSON содержит ядро семейства (00-INDEX.md §4.2, schemas/report-core.schema.json) и расширение c2s7
(schemas/report.schema.json). Классы конструкций — опорный словарь семейства; P50/P90 — модель
Монте-Карло, «модель, не калибрована».
"""

from __future__ import annotations

import html
import json
from typing import Any

from c2s7 import TOOL, __version__
from c2s7.convert.core import Result
from c2s7.emit.files import block_dict, ob_plan_dict
from c2s7.rules import OUTCOMES, SEVERITY, effort

OUTCOME_RU = {
    "auto": "автоматически",
    "review": "проверить",
    "verify": "подтвердить пробой",
    "manual": "вручную",
    "impossible": "невозможно",
    "info": "сведения",
}


def pou_verdicts(res: Result) -> list[dict[str, Any]]:
    worst: dict[str, str] = {}
    langs: dict[str, str] = {}
    for c in res.collector.constructs:
        if not c.pou:
            continue
        cur = worst.get(c.pou, "auto")
        if SEVERITY[c.outcome] > SEVERITY[cur]:
            worst[c.pou] = c.outcome
        else:
            worst.setdefault(c.pou, cur)
    for p in res.project.pous:
        langs[p.name] = p.language
    out = []
    for name in sorted(worst, key=str.lower):
        fs = [f for f in res.collector.findings if f.pou == name and f.outcome != "info"]
        out.append(
            {
                "pou": name,
                "language": langs.get(name, "DECL"),
                "outcome": worst[name],
                "findings": len(fs),
                "effort": effort(fs, runs=2000) if fs else None,
            }
        )
    return out


def overall_verdict(by_outcome: dict[str, int]) -> str:
    if by_outcome["impossible"]:
        return "есть конструкции, невозможные на выбранном CPU — сменить CPU или переписать"
    if by_outcome["manual"]:
        return "нужны ручные шаги (MANUAL_STEPS.md) — остальное переносится автоматически или с проверкой"
    if by_outcome["verify"]:
        return "переносится; поведение части конструкций подтвердить пробником на ПЛК (probe/)"
    if by_outcome["review"]:
        return "переносится с проверкой описанных расхождений"
    return "переносится автоматически"


def report_json(res: Result, files: list[str], equivalence: dict[str, Any] | None = None) -> dict[str, Any]:
    by_outcome, by_lang = res.collector.totals()
    findings = [f.as_dict() for f in res.collector.sorted_findings()]
    eff = effort(res.collector.findings)
    data: dict[str, Any] = {
        "format": "plc-migration-report/1",
        "tool": {"name": "c2s7", "version": __version__},
        "source": {
            "kind": res.project.kind,
            "sha256": res.project.sha256,
            "ide": res.project.ide,
            "ide_version": res.project.ide_version or "3.5.17.30",
        },
        "target": {"profile": res.profile.cpu, "version": res.profile.tia},
        "totals": {"by_outcome": by_outcome, "by_language": by_lang},
        "findings": findings,
        "effort": eff,
    }
    if equivalence is not None:
        data["equivalence"] = equivalence
    data["c2s7"] = {
        "input": res.project.path,
        "verdict": overall_verdict(by_outcome),
        "ring": res.ring,
        "options": {
            "cpu": res.options.cpu,
            "tia": res.options.tia,
            "graphics": res.options.graphics or "",
            "sfc": res.options.sfc,
            "timers": res.options.timers,
            "markers": res.options.markers,
            "bit_addressing": res.options.bit_addressing,
            "max_ob_priority": res.options.max_ob_priority,
            "ob_from_tasks": res.options.ob_from_tasks,
        },
        "pous": pou_verdicts(res),
        "blocks": [block_dict(b) for b in res.blocks],
        "obs": [ob_plan_dict(o) for o in res.obs],
        "tags": len(res.tags),
        "constants": len(res.constants),
        "compat": res.compat,
        "files": files,
        "constructs": len(res.collector.constructs),
    }
    return data


def report_md(data: dict[str, Any]) -> str:
    t = data["totals"]
    e = data["effort"]
    c = data["c2s7"]
    lines = [
        "# Отчёт о переносе CODESYS → S7",
        "",
        f"Создано {TOOL} · источник {c['input']} · SHA-256 {data['source']['sha256']}",
        f"Цель: {data['target']['profile']}, TIA Portal {data['target']['version']}. Импорт в TIA автором не проверен.",
        "",
        f"**Вердикт:** {c['verdict']}.",
        "",
        "## Конструкции по классам",
        "",
        "| Класс | Конструкций |",
        "|---|---|",
    ]
    for o in OUTCOMES:
        lines.append(f"| {o} ({OUTCOME_RU[o]}) | {t['by_outcome'][o]} |")
    lines += ["", "## По языкам", "", "| Язык | " + " | ".join(OUTCOMES) + " |", "|---" * (len(OUTCOMES) + 1) + "|"]
    for lang, counts in t["by_language"].items():
        lines.append(f"| {lang} | " + " | ".join(str(counts[o]) for o in OUTCOMES) + " |")
    lines += [
        "",
        "## Трудоёмкость",
        "",
        f"P50 = {e['p50_h']} ч, P90 = {e['p90_h']} ч ({e['model']}, {e['runs']} проб, seed {e['seed']}) — модель, не калибрована.",
        "",
    ]
    if "equivalence" in data:
        eq = data["equivalence"]
        lines += [
            "## Эквивалентность",
            "",
            f"Оракулы: {', '.join(eq['oracles'])}; режим {eq.get('regime', '')}; сценариев {eq['scenarios']}, "
            f"строк {eq.get('rows', 0)}, совпало {eq['passed']}, ожидаемых расхождений {eq.get('xfail', 0)}.",
            "",
        ]
    lines += ["## POU", "", "| POU | Язык | Класс | Находок | P50/P90, ч |", "|---|---|---|---|---|"]
    for p in c["pous"]:
        eff = p["effort"]
        effs = f"{eff['p50_h']}/{eff['p90_h']}" if eff else "—"
        lines.append(f"| {p['pou']} | {p['language']} | {p['outcome']} | {p['findings']} | {effs} |")
    lines += ["", "## Находки", "", "| Правило | Класс | POU | Место | Фрагмент | Что |", "|---|---|---|---|---|---|"]
    for f in data["findings"]:
        o = f["origin"]
        where = f"{o['file']}:{o.get('line', '')}"
        frag = str(f.get("fragment", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {f['rule']} | {f['outcome']} | {f['pou']} | {where} | `{frag}` | {f['title']} |")
    lines += ["", "## OB", "", "| Задача | OB | Номер | Тип | Период, мс | Приоритет |", "|---|---|---|---|---|---|"]
    for o in c["obs"]:
        lines.append(
            f"| {o['task']} | {o['ob']} | {o['number'] or 'вручную'} | {o['kind']} | {o['interval_ms'] or ''} | {o['priority'] or ''} |"
        )
    lines.append("")
    return "\n".join(lines)


def report_html(data: dict[str, Any]) -> str:
    md = report_md(data)
    body = []
    in_table = False
    for line in md.splitlines():
        if line.startswith("|"):
            cells = [html.escape(x.strip()) for x in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-"):
                continue
            if not in_table:
                body.append("<table>")
                in_table = True
                body.append("<tr>" + "".join(f"<th>{x}</th>" for x in cells) + "</tr>")
            else:
                body.append("<tr>" + "".join(f"<td>{x}</td>" for x in cells) + "</tr>")
            continue
        if in_table:
            body.append("</table>")
            in_table = False
        if line.startswith("# "):
            body.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.strip():
            body.append(f"<p>{html.escape(line).replace('**', '')}</p>")
    if in_table:
        body.append("</table>")
    style = (
        ":root{--bg:#14171c;--fg:#e6e8eb;--line:#2b313a;--acc:#ff7a1a}"
        "@media (prefers-color-scheme: light){:root{--bg:#f7f7f5;--fg:#1d2127;--line:#d6d8dc}}"
        "body{background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px}"
        "h1,h2{font-weight:600}h2{border-bottom:1px solid var(--line);padding-bottom:4px}"
        "table{border-collapse:collapse;width:100%;margin:8px 0}td,th{border:1px solid var(--line);padding:4px 6px;text-align:left;vertical-align:top}"
        "th{color:var(--acc)}"
    )
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Отчёт c2s7</title><style>{style}</style></head><body>" + "\n".join(body) + "</body></html>\n"
    )


def trace_json(res: Result) -> str:
    return json.dumps({"tool": TOOL, "entries": res.trace}, indent=2, ensure_ascii=False) + "\n"


def reports(res: Result, files: list[str], equivalence: dict[str, Any] | None = None) -> dict[str, str]:
    data = report_json(
        res,
        sorted([*files, "MIGRATION_REPORT.md", "MIGRATION_REPORT.json", "MIGRATION_REPORT.html", "trace.json"]),
        equivalence,
    )
    return {
        "MIGRATION_REPORT.json": json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        "MIGRATION_REPORT.md": report_md(data),
        "MIGRATION_REPORT.html": report_html(data),
        "trace.json": trace_json(res),
    }
