"""Прямые адреса CODESYS → S7.

CODESYS: номер в %IW/%ID/%IL — номер слова/двойного/четверного слова (%IW5 = байты 10–11), биты
`%IXa.b` — байт a при байтовой адресации (проба M0 на Control Win) или слово a при словной.
S7: номер — номер байта (%IW10 = байты 10–11), порядок байтов big-endian (s7-to-codesys MAPPING.md,
«Адресная модель»).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ADDR = re.compile(r"^%([IQM])([XBWDL]?)(\d+)(?:\.(\d+))?$", re.IGNORECASE)
WIDTH = {"X": 1, "B": 8, "W": 16, "D": 32, "L": 64}
BYTES = {"B": 1, "W": 2, "D": 4, "L": 8}


@dataclass(frozen=True)
class Addr:
    area: str  # I Q M
    size: str  # X B W D L
    number: int
    bit: int | None = None

    def byte_range(self, bit_mode: str = "byte") -> tuple[int, int]:
        """Байты [начало, конец) в адресном пространстве CODESYS."""
        if self.size == "X":
            byte = self.number if bit_mode == "byte" else self.number * 2 + (self.bit or 0) // 8
            return byte, byte + 1
        n = BYTES[self.size]
        return self.number * n, self.number * n + n


def parse(text: str) -> Addr | None:
    m = _ADDR.match(text.strip())
    if not m:
        return None
    area, size, num, bit = m.group(1).upper(), (m.group(2) or "X").upper(), int(m.group(3)), m.group(4)
    if size == "X" and bit is None:
        return None
    return Addr(area, size, num, int(bit) if bit is not None else None)


def to_s7(text: str, bit_mode: str = "byte") -> tuple[str | None, str]:
    """Адрес CODESYS → (адрес S7 или None, пояснение)."""
    a = parse(text)
    if a is None:
        return None, f"адрес {text} не разобран"
    if a.size == "X":
        if bit_mode == "word":
            return None, "словная адресация битов: бит слова не выражается байтовым адресом S7"
        return f"%{a.area}{a.number}.{a.bit}", ""
    n = BYTES[a.size]
    prefix = {"B": "B", "W": "W", "D": "D", "L": "L"}[a.size]
    return f"%{a.area}{prefix}{a.number * n}", ""


def overlaps(addrs: list[tuple[str, Addr]], bit_mode: str = "byte") -> set[str]:
    """Имена переменных %M, чьи байты пересекаются с переменными другой ширины."""
    out: set[str] = set()
    for i, (n1, a1) in enumerate(addrs):
        r1 = a1.byte_range(bit_mode)
        for n2, a2 in addrs[i + 1 :]:
            if a1.area != a2.area or a1.size == a2.size:
                continue
            if {a1.size, a2.size} <= {"X", "B"}:
                continue  # бит и байт адресуются одинаково (байтовая адресация битов)
            r2 = a2.byte_range(bit_mode)
            if r1[0] < r2[1] and r2[0] < r1[1]:
                out.update((n1, n2))
    return out
