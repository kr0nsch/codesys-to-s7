"""Общее для разборщиков входа."""

from __future__ import annotations

from pathlib import Path


class IngestError(ValueError):
    """Вход не разобран (код CLI 2)."""


def read_text(path: Path) -> str:
    """UTF-8 (BOM снимается), переводы строк → LF."""
    data = path.read_bytes()
    text = data.decode("utf-8-sig")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_doc(text: str) -> tuple[list[str], str]:
    """Комментарий-заголовок `// ...` в начале текста (до первой значимой строки) и остаток."""
    lines = text.split("\n")
    doc: list[str] = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("//"):
            doc.append(s[2:].strip() if not s.startswith("// ") else s[3:].rstrip())
            i += 1
            continue
        if not s:
            i += 1
            continue
        break
    return doc, "\n".join(lines[i:])
