"""Таблицы соответствия CODESYS → S7 (`mapping/*.yaml`) и их печать в docs/MAPPING.md."""

from __future__ import annotations

from importlib import resources
from typing import Any

import yaml

TABLES = ("common", "st", "graphics")


def load(name: str) -> dict[str, Any]:
    text = resources.files("c2s7.mapping").joinpath(f"{name}.yaml").read_text(encoding="utf-8")
    data: dict[str, Any] = yaml.safe_load(text)
    return data


def reverse_rules() -> list[dict[str, Any]]:
    text = resources.files("c2s7.mapping").joinpath("reverse.yaml").read_text(encoding="utf-8")
    data: list[dict[str, Any]] = yaml.safe_load(text)
    return data


def render_md() -> str:
    lines = [
        "# Таблицы соответствия CODESYS 3.5 → S7-1200/1500",
        "",
        "Документ печатается из `src/c2s7/mapping/*.yaml` (тест `tests/unit/test_mapping.py` проверяет совпадение).",
        "Классы — опорный словарь семейства: `auto` (без потерь, есть тест), `review` (адаптер или описанное",
        "расхождение), `verify` (поведение S7 не подтверждено, есть проба), `manual` (заготовка и шаг в MANUAL_STEPS.md),",
        "`impossible` (в профиле CPU нет средства). Источники — в docs/SOURCES.md; что проверено, а что нет — в",
        "docs/PROBES.md и docs/HARDWARE_VALIDATION.md. Импорт в TIA Portal автором не проверялся.",
        "",
    ]
    for name in TABLES:
        t = load(name)
        lines += [
            f"## {t['title']}",
            "",
            "| CODESYS | S7 (TIA Portal) | Класс | Источник | Тест |",
            "|---|---|---|---|---|",
        ]
        for r in t["rows"]:
            lines.append(f"| {r['cds']} | {r['s7']} | {r['class']} | {r['source']} | `{r['test']}` |")
        lines.append("")
    rev = reverse_rules()
    lines += [
        "## Обратные правила к строкам «авто» s7-to-codesys",
        "",
        "Каждой строке «авто» таблицы s7-to-codesys `docs/MAPPING.md` @ `2285760c` соответствует обратное правило c2s7;",
        "пример и ожидаемый фрагмент SCL проверяет `tests/unit/test_reverse_rules.py`, всё вместе — кольцо (`tests/ring`).",
        "Строки «проверка»/TODO не зеркалируются. Известный дефект 1.0.0 — одноимённые SR/RS (их стр. 93) — не копируется.",
        "",
        "| Стр. | S7 | Выход s7conv | Обратно (c2s7) |",
        "|---|---|---|---|",
    ]
    for r in rev:
        exp = f"`{r['expect']}`" if r["expect"] else f"— ({r['cds']})"
        cds = r["cds"] if r["kind"] != "note" else "—"
        lines.append(f"| {r['line']} | `{r['s7']}` | {cds} | {exp} |")
    lines.append("")
    return "\n".join(lines)
