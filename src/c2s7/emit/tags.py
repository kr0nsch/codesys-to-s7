"""Таблица тегов `tia/tags/PLCTags.xlsx` для импорта в TIA Portal через GUI.

Колонки листа «PLC Tags» — как в экспорте редактора тегов TIA (R§2.5 [M]: Name, Path, Data Type,
Logical Address, Comment, Hmi Visible, Hmi Accessible, Hmi Writeable, Typeobject ID, Version ID);
лист «User Constants» — Name, Path, Data Type, Value, Comment. Сверка с реальным импортом —
docs/HARDWARE_VALIDATION.md. Файл детерминирован: фиксированные свойства книги, записи zip без
сжатия с фиксированной датой.
"""

from __future__ import annotations

import datetime as dt
import io
import re
import zipfile
from pathlib import Path

from openpyxl import Workbook

from c2s7.convert.core import Result

TAG_COLUMNS = [
    "Name",
    "Path",
    "Data Type",
    "Logical Address",
    "Comment",
    "Hmi Visible",
    "Hmi Accessible",
    "Hmi Writeable",
    "Typeobject ID",
    "Version ID",
]
CONST_COLUMNS = ["Name", "Path", "Data Type", "Value", "Comment"]
FIXED = dt.datetime(2026, 10, 19, 0, 0, 0)
_MODIFIED = re.compile(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)")  # openpyxl ставит «сейчас» при save
_STAMP = rb"\g<1>" + FIXED.strftime("%Y-%m-%dT%H:%M:%SZ").encode() + rb"\g<2>"


def build_xlsx(res: Result) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "PLC Tags"
    ws.append(TAG_COLUMNS)
    for t in res.tags:
        ws.append([t.name, t.table, t.type, t.address, t.comment, "True", "True", "True", "", ""])
    wc = wb.create_sheet("User Constants")
    wc.append(CONST_COLUMNS)
    for c in res.constants:
        wc.append([c.name, c.table, c.type, c.value or "", c.comment])
    wb.properties.creator = "c2s7"
    wb.properties.created = FIXED
    wb.properties.modified = FIXED
    wb.properties.lastModifiedBy = "c2s7"
    raw = io.BytesIO()
    wb.save(raw)
    return _normalize_zip(raw.getvalue())


def _normalize_zip(data: bytes) -> bytes:
    """Записи xlsx без сжатия и с фиксированной датой — одинаковые байты на любой платформе."""
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as z:
        for info in src.infolist():
            body = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                body = _MODIFIED.sub(_STAMP, body.replace(b"\r\n", b"\n"))
            ni = zipfile.ZipInfo(info.filename, date_time=(1980, 1, 1, 0, 0, 0))
            ni.external_attr = 0o644 << 16
            ni.create_system = 3  # одинаково на Windows и Linux
            z.writestr(ni, body)
    return out.getvalue()


def write_xlsx(res: Result, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_xlsx(res))
