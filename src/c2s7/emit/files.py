"""Запись результата `c2s7 migrate`: tia/, roundtrip/, отчёт, трасса, zip.

Файлы TIA (`tia/sources`, `tia/ob`, `tia/compat`, `roundtrip/ob`) — UTF-8 с BOM и CRLF (формат
экспорта TIA); остальное — UTF-8 без BOM, LF. Всё детерминировано: сортировка, без меток времени.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from importlib import resources
from pathlib import Path

from c2s7 import TOOL
from c2s7.convert.core import Result
from c2s7.emit.printer import Printer
from c2s7.emit.scl import block_text, header_comment
from c2s7.s7 import ObPlan, S7Block

FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def write_tia(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = "﻿" + text.replace("\r\n", "\n").replace("\n", "\r\n")
    path.write_bytes(data.encode("utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))


def safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", name).strip("_") or "x"


def source_files(res: Result) -> list[tuple[str, str]]:
    """[(относительный путь, текст)] внешних исходников tia/sources в порядке зависимостей."""
    head = header_comment(TOOL, res.project.path, res.project.sha256)
    out = []
    n = 0
    for b in res.blocks:
        if b.kind == "ORGANIZATION_BLOCK" or b.flgnet:
            continue
        n += 1
        out.append((f"tia/sources/{n:03d}_{safe(b.name)}.{b.ext}", block_text(b, head)))
    return out


def ob_files(res: Result) -> list[tuple[str, str]]:
    head = header_comment(TOOL, res.project.path, res.project.sha256)
    p = Printer("scl", indent="\t")
    out = []
    for o in res.obs:
        lines = [
            head,
            f"// Тело OB для задачи {o.task}: {o.kind}"
            + (f", OB{o.number}" if o.number is not None else "")
            + (f", период {o.interval_ms:g} мс" if o.interval_ms else "")
            + (f", приоритет {o.priority}" if o.priority is not None else ""),
            "// OB создаётся в TIA вручную (TASKS.md); вставьте строки ниже между BEGIN и END_ORGANIZATION_BLOCK.",
        ]
        lines.extend(p.stmts(o.body, 0))
        out.append((f"tia/ob/OB_{safe(o.task if not o.full_block else o.name)}.body.scl", "\n".join(lines) + "\n"))
    return out


def ring_ob_files(res: Result) -> list[tuple[str, str]]:
    """Кольцо (--ob-from-tasks): OB целиком — вход s7conv и сравнения, в TIA не импортируются."""
    head = header_comment(TOOL, res.project.path, res.project.sha256)
    out = []
    for i, o in enumerate(sorted((o for o in res.obs if o.full_block is not None), key=lambda x: x.number or 0)):
        assert o.full_block is not None
        out.append((f"roundtrip/ob/{i + 1:03d}_{safe(o.name)}.scl", block_text(o.full_block, head)))
    return out


def compat_files(res: Result) -> list[tuple[str, str]]:
    out = []
    root = resources.files("c2s7.compat").joinpath("CodesysCompat")
    for name in res.compat:
        text = root.joinpath(f"{name}.scl").read_text(encoding="utf-8")
        out.append((f"tia/compat/{name}.scl", text))
    return out


def plctags_csv(res: Result) -> str:
    """Таблица тегов в формате s7conv (`--tags`): Name, Path, Data Type, Logical Address, Comment, Value."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Name", "Path", "Data Type", "Logical Address", "Comment", "Value"])
    for t in res.tags:
        w.writerow([t.name, t.table, t.type, t.address, t.comment, ""])
    for c in res.constants:
        w.writerow([c.name, c.table, c.type, "", c.comment, c.value or ""])
    return buf.getvalue()


def ob_config(res: Result) -> str:
    """Номера и периоды OB в формате --ob-config s7conv."""
    data: dict[str, dict[str, object]] = {}
    for o in res.obs:
        if o.number is None:
            continue
        kind = {"ProgramCycle": "main", "CyclicInterrupt": "cyclic", "Startup": "startup"}.get(o.kind, "event")
        entry: dict[str, object] = {"number": o.number, "kind": kind}
        if o.interval_ms:
            entry["interval_ms"] = int(o.interval_ms)
        data[o.name] = entry
    return json.dumps(dict(sorted(data.items())), indent=2, ensure_ascii=False) + "\n"


def block_properties(res: Result) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(
        ["Block", "Kind", "Number", "Source", "Optimized", "Event", "CycleTime_ms", "Phase_ms", "Priority", "Comment"]
    )
    src = {
        b.name: path for path, _ in source_files(res) for b in res.blocks if path.endswith(f"_{safe(b.name)}.{b.ext}")
    }
    for o in res.obs:
        w.writerow(
            [
                o.name,
                "OB",
                o.number or "",
                "",
                "TRUE",
                o.kind,
                int(o.interval_ms) if o.interval_ms else "",
                "",
                o.priority or "",
                o.task,
            ]
        )
    for b in res.blocks:
        if b.kind == "ORGANIZATION_BLOCK":
            continue
        kind = {"FUNCTION_BLOCK": "FB", "FUNCTION": "FC", "DATA_BLOCK": "DB", "TYPE": "UDT"}[b.kind]
        w.writerow(
            [b.name, kind, "", src.get(b.name, ""), "TRUE" if b.optimized else "FALSE", "", "", "", "", b.source_pou]
        )
    return buf.getvalue()


def tasks_md(res: Result) -> str:
    lines = [
        "# Задачи → OB",
        "",
        f"Создано {TOOL} для {res.profile.title}. Тип, номер и период OB внешний исходник не задаёт — "
        "OB создаёт инженер",
        "в TIA Portal (Program blocks → Add new block → Organization block) и вставляет тело из `tia/ob/`.",
        "",
        "| Задача CODESYS | Приоритет CODESYS | OB | Тип | Период, мс | Приоритет OB | Вызовы |",
        "|---|---|---|---|---|---|---|",
    ]
    for o in res.obs:
        lines.append(
            f"| {o.task} | {o.cds_priority if o.cds_priority is not None else ''} | {o.name}"
            + (f" (OB{o.number})" if o.number is not None else " (вручную)")
            + f" | {o.kind} | {o.interval_ms:g} | "
            if o.interval_ms
            else f" | {o.kind} |  | "
        )
        lines[-1] += f"{o.priority if o.priority is not None else ''} | {', '.join(o.calls)} |"
    lines += [
        "",
        "Приоритеты: шкала S7 обратная CODESYS (1 — низший, 26 — высший; связь — на 15). Ранги различных приоритетов",
        f"циклических задач переведены формулой ТЗ M5 с P_max = {res.options.max_ob_priority}; программы задачи",
        "вызываются в порядке pouInstance. Многозадачность проверяется только структурно.",
        "",
    ]
    return "\n".join(lines)


def io_map_csv(res: Result) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Variable", "CODESYS address", "S7 tag", "S7 address", "Comment"])
    for t in res.tags:
        src = t.source
        cds = src.split(" AT ", 1)[1] if " AT " in src else ""
        w.writerow([src.split(" AT ")[0], cds, t.name, t.address, t.comment])
    return buf.getvalue()


def manual_steps_md(res: Result) -> str:
    lines = [
        "# Ручные шаги после c2s7",
        "",
        "Импорт в TIA Portal автором не проверялся (у автора TIA нет) — процедура в docs/HARDWARE_VALIDATION.md.",
        "",
        "## 1. Импорт",
        "",
        "1. External source files → Add new external file → все файлы `tia/sources/` (и `tia/compat/`) "
        "по порядку номеров.",
        "2. Generate blocks from source для каждого файла; ошибки компиляции — в VALIDATION_LOG.md дословно.",
        "3. PLC tags → Import → `tia/tags/PLCTags.xlsx` (листы PLC Tags и User Constants).",
        "4. OB по TASKS.md; тела — из `tia/ob/`.",
        "",
        "## 2. Находки manual и impossible",
        "",
        "| Правило | POU | Место | Что | Что сделать | Минуты (min/mode/max) |",
        "|---|---|---|---|---|---|",
    ]
    for f in res.collector.sorted_findings():
        if f.outcome not in ("manual", "impossible"):
            continue
        r = f.info
        where = f"{f.origin.file}:{f.origin.line or ''}"
        frag = f.fragment.replace("|", "\\|")
        lines.append(
            f"| {f.rule} | {f.pou} | {where} | `{frag}` | {r.fix} | {r.effort[0]:g}/{r.effort[1]:g}/{r.effort[2]:g} |"
        )
    if res.manual_steps:
        lines += ["", "## 3. Прочее", ""]
        for s in res.manual_steps:
            lines.append(f"- {s['step']}: {s['do']} (≈ {s['minutes']} мин)")
    return "\n".join(lines) + "\n"


def write_zip(out: Path, root: Path, files: list[str]) -> None:
    """ZIP_STORED, имена по порядку, фиксированные дата и атрибуты (00-INDEX §4.10)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as z:
        for rel in sorted(files):
            info = zipfile.ZipInfo(rel, date_time=FIXED_ZIP_TIME)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_STORED
            z.writestr(info, (root / rel).read_bytes())


def all_outputs(res: Result) -> dict[str, tuple[str, bool]]:
    """Все текстовые файлы результата: путь → (текст, формат TIA)."""
    files: dict[str, tuple[str, bool]] = {}
    for rel, text in source_files(res):
        files[rel] = (text, True)
    for rel, text in ob_files(res):
        files[rel] = (text, True)
    for rel, text in compat_files(res):
        files[rel] = (text, True)
    for rel, text in ring_ob_files(res):
        files[rel] = (text, True)
    files["roundtrip/PlcTags.csv"] = (plctags_csv(res), False)
    files["roundtrip/ob_config.json"] = (ob_config(res), False)
    files["roundtrip/BlockProperties.csv"] = (block_properties(res), False)
    files["roundtrip/TASKS.md"] = (tasks_md(res), False)
    files["roundtrip/IO_MAP.csv"] = (io_map_csv(res), False)
    files["roundtrip/MANUAL_STEPS.md"] = (manual_steps_md(res), False)
    for path, text in res.simaticml.items():
        files[path] = (text, False)
    return files


def write_all(res: Result, out: Path) -> list[str]:
    from c2s7.emit import report as R
    from c2s7.emit import tags as TG

    written: list[str] = []
    for rel, (text, tia) in sorted(all_outputs(res).items()):
        (write_tia if tia else write_text)(out / rel, text)
        written.append(rel)
    TG.write_xlsx(res, out / "tia/tags/PLCTags.xlsx")
    written.append("tia/tags/PLCTags.xlsx")
    for rel, text in R.reports(res, written).items():
        write_text(out / rel, text)
        written.append(rel)
    return sorted(written)


def ob_plan_dict(o: ObPlan) -> dict[str, object]:
    return {
        "task": o.task,
        "ob": o.name,
        "number": o.number,
        "kind": o.kind,
        "interval_ms": o.interval_ms,
        "priority": o.priority,
        "cds_priority": o.cds_priority,
        "calls": o.calls,
    }


def block_dict(b: S7Block) -> dict[str, object]:
    return {"kind": b.kind, "name": b.name, "source": b.source_pou, "language": b.language}
