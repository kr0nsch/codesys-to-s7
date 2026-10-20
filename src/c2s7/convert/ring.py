"""Распознавание выхода s7-to-codesys (s7conv @ 2285760c) — обратные правила кольца S7 → CODESYS → S7.

По MAPPING.md s7conv: шапка POU (TITLE/AUTHOR/VERSION/FAMILY), пометки MIGRATION-TODO с исходным
текстом в комментарии, слой S7Compat, GVL_InstanceDBs/GVL_IO/GVL_Markers, DUT анонимных структур
ST_<блок>_<поле>, эмуляция Initial_Call OB, задачи с полем sources «Имя (OBn)».
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from c2s7.model import Project

S7CONV_MARK = "s7conv"
_SOURCE_OB = re.compile(r"^(?P<name>.+?)\s*\(OB(?P<num>\d+)\)\s*$")


def is_s7conv_project(proj: Project) -> bool:
    names = {p.name.upper() for p in proj.pous} | {g.name.upper() for g in proj.gvls}
    if {"GVL_INSTANCEDBS", "F_S7NOW"} & names:
        return True
    return any(any(S7CONV_MARK in line for line in p.doc) for p in proj.pous[:5])


@dataclass
class HeaderMeta:
    title: str | None = None
    comment: list[str] = field(default_factory=list)
    author: str | None = None
    version: str | None = None
    family: str | None = None
    source_block: str | None = None
    file_comment: list[str] = field(default_factory=list)


def parse_header(doc: list[str]) -> HeaderMeta:
    """Шапка POU s7conv: «Назначение:», «Автор: X (исходный блок S7)», «Версия: 2.1 (...)».

    Строка «Источник: ..., FAMILY F» даёт имя исходного блока и FAMILY.
    """
    meta = HeaderMeta()
    in_file_comment = False
    purpose: list[str] = []
    for line in doc:
        s = line.strip()
        if s.startswith("---- комментарий в начале исходного файла SCL"):
            in_file_comment = True
            continue
        if in_file_comment:
            meta.file_comment.append(line)
            continue
        if s.startswith("Назначение:"):
            purpose.append(s.split(":", 1)[1].strip())
            continue
        if purpose and line.startswith(" " * 6) and not re.match(r"^\s*[А-ЯA-Z][а-яa-z]+:", s):
            purpose.append(s)
            continue
        m = re.match(r"^Автор:\s*(.+?)\s*\(исходный блок S7\)", s)
        if m:
            meta.author = m.group(1)
            continue
        m = re.match(r"^Версия:\s*(\S+)\s*\(исходный блок S7\)", s)
        if m:
            meta.version = m.group(1)
            continue
        m = re.match(
            r"^Источник:.*?(FUNCTION_BLOCK|FUNCTION|ORGANIZATION_BLOCK|DATA_BLOCK|TYPE)\s+\"([^\"]+)\"(?:.*FAMILY\s+(\S+))?",
            s,
        )
        if m:
            meta.source_block = m.group(2)
            meta.family = m.group(3)
            continue
    if purpose:
        meta.title = purpose[0] or None
        meta.comment = purpose[1:]
    return meta


def ob_source(sources: list[str], pou: str, tasks_pous: list[str]) -> tuple[str, int] | None:
    """`sources` задачи («Main (OB1)») → имя и номер OB для программы с тем же индексом."""
    if pou not in tasks_pous:
        return None
    idx = tasks_pous.index(pou)
    if idx >= len(sources):
        return None
    m = _SOURCE_OB.match(sources[idx])
    if not m:
        return None
    return m.group("name"), int(m.group("num"))


TODO_RE = re.compile(r"^MIGRATION-TODO:\s*(?P<reason>.*)$")
CHECK_RE = re.compile(r"^MIGRATION-CHECK:\s*(?P<reason>.*)$")
INITIAL_CALL_VAR = "xS7convFirstCycleDone"
STARTUP_VAR = "xS7convStartupDone"


@dataclass
class TodoBlock:
    line: int  # строка пометки (от 1)
    reason: str
    code: list[str]  # исходный текст SCL из комментария
    next_line: int  # первая строка после блока комментариев


_TODO_LINE = re.compile(r"^\s*// MIGRATION-TODO:\s*(.*)$")
_CHECK_LINE = re.compile(r"^\s*// MIGRATION-CHECK:\s*(.*)$")
_CONT_LINE = re.compile(r"^\s*//\s{6,}(\S.*)$")
_COMMENT_LINE = re.compile(r"^\s*// ?(.*)$")


def scan_todos(text: str) -> list[TodoBlock]:
    """Пометки MIGRATION-TODO s7conv и закомментированный исходный текст SCL под ними."""
    lines = text.split("\n")
    out: list[TodoBlock] = []
    i = 0
    while i < len(lines):
        m = _TODO_LINE.match(lines[i])
        if not m:
            i += 1
            continue
        start = i + 1
        reason = m.group(1).strip()
        i += 1
        while i < len(lines) and _CONT_LINE.match(lines[i]):
            reason += " " + _CONT_LINE.match(lines[i]).group(1).strip()  # type: ignore[union-attr]
            i += 1
        code: list[str] = []
        while i < len(lines):
            cm = _COMMENT_LINE.match(lines[i])
            if not cm:
                break
            body = cm.group(1)
            if not body.strip() or body.startswith(("MIGRATION-", "REGION ", "END_REGION")):
                break
            code.append(body.rstrip())
            i += 1
        out.append(TodoBlock(start, reason, code, i + 1))
    return out


@dataclass
class CheckMarker:
    line: int
    reason: str
    next_line: int


def scan_checks(text: str) -> list[CheckMarker]:
    """Пометки MIGRATION-CHECK s7conv: строка, причина, первая строка кода после пометки."""
    lines = text.split("\n")
    out: list[CheckMarker] = []
    i = 0
    while i < len(lines):
        m = _CHECK_LINE.match(lines[i])
        if not m:
            i += 1
            continue
        start = i + 1
        reason = m.group(1).strip()
        i += 1
        while i < len(lines) and _CONT_LINE.match(lines[i]):
            reason += " " + _CONT_LINE.match(lines[i]).group(1).strip()  # type: ignore[union-attr]
            i += 1
        j = i
        while j < len(lines) and lines[j].strip().startswith("//"):
            j += 1
        out.append(CheckMarker(start, reason, j + 1))
    return out


_RENAME = re.compile(r"имя «(?P<old>[^»]+)» переименовано в «(?P<new>[^»]+)»")


def renames(checks: list[CheckMarker]) -> dict[str, str]:
    """Переименования s7conv (name.renamed): новое имя → исходное."""
    out: dict[str, str] = {}
    for c in checks:
        m = _RENAME.search(c.reason)
        if m:
            out[m.group("new").upper()] = m.group("old")
    return out


def non_optimized(checks: list[CheckMarker], header_line: int) -> bool:
    return any("неоптимизированный" in c.reason and c.line < header_line for c in checks)


def s5time_lines(checks: list[CheckMarker]) -> set[int]:
    return {c.next_line for c in checks if c.reason.startswith("S5Time → TIME")}


def s5ti_tim_lines(checks: list[CheckMarker]) -> set[int]:
    return {c.next_line for c in checks if c.reason.startswith("S5TI_TIM")}
