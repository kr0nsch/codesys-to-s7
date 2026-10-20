"""`--io-map`: «Export mappings to CSV» устройства CODESYS.

По справке CODESYS (_cds_cmd_export_io_mapping_csv): разделитель — системный разделитель списков
(в русской Windows — «;»), у неуникальных имён суффикс `@<n>`. Колонки справка не описывает [L]:
читаются колонки переменной и адреса по заголовку (Variable/Переменная, Address/Адрес, без учёта
регистра); строки без переменной или адреса пропускаются.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from c2s7.ingest.common import IngestError, read_text
from c2s7.model import IoChannel

_VAR = ("variable", "переменная", "var")
_ADDR = ("address", "адрес", "iec address")
_ADDR_RE = re.compile(r"%[IQM][XBWDL]?\d+(\.\d+)?", re.IGNORECASE)


def load_io_map(path: Path) -> list[IoChannel]:
    text = read_text(path)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        delim = dialect.delimiter
    except csv.Error:
        delim = ";" if sample.count(";") >= sample.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows:
        raise IngestError(f"{path}: пустой CSV")
    head = [h.strip().lower() for h in rows[0]]
    vi = next((i for i, h in enumerate(head) if any(h.startswith(v) for v in _VAR)), None)
    ai = next((i for i, h in enumerate(head) if any(h.startswith(a) for a in _ADDR)), None)
    if vi is None or ai is None:
        raise IngestError(f"{path}: нет колонок переменной и адреса (заголовок: {', '.join(rows[0])})")
    out: list[IoChannel] = []
    for r in rows[1:]:
        if len(r) <= max(vi, ai):
            continue
        var, addr = r[vi].strip(), r[ai].strip()
        if not var or not _ADDR_RE.fullmatch(addr):
            continue
        var = re.sub(r"@\d+$", "", var)
        out.append(IoChannel(variable=var, address=addr.upper(), channel=r[0].strip()))
    return out
