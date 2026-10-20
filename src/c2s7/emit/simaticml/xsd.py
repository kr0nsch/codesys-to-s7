"""Проверка фрагментов SimaticML по XSD Siemens V19/V21 (ТЗ §8.3: «фрагменты после снятия пространства имён»).

XSD в репозиторий не кладутся: `tools/fetch_xsd.py` скачивает их в `.cache/xsd/<версия>/` по SHA-256
(или каталог задаёт C2S7_XSD_DIR). Оболочки `Document/SW.Blocks.*` в XSD нет, поэтому проверяются
элементы `FlgNet` (SW.PlcBlocks.LADFBD_v5.xsd) и `Sections` интерфейса (SW.InterfaceSections_v5.xsd).
Прохождение XSD подтверждением формата не считается.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from lxml import etree

FILES = {"FlgNet": "SW.PlcBlocks.LADFBD_v5.xsd", "Sections": "SW.InterfaceSections_v5.xsd"}


def xsd_dir(tia: str, base: Path | None = None) -> Path | None:
    env = os.environ.get("C2S7_XSD_DIR")
    root = Path(env) if env else (base or Path.cwd()) / ".cache" / "xsd"
    d = root / tia if (root / tia).is_dir() else root
    return d if all((d / f).exists() for f in FILES.values()) else None


@lru_cache(maxsize=8)
def _schema(path: str) -> Any:
    return etree.XMLSchema(etree.parse(path))


def _strip_ns(el: Any) -> Any:
    el = etree.fromstring(etree.tostring(el))
    for e in el.iter():
        if isinstance(e.tag, str) and e.tag.startswith("{"):
            e.tag = e.tag.split("}", 1)[1]
    etree.cleanup_namespaces(el)
    return el


def validate_xsd(xml: str, tia: str, base: Path | None = None) -> list[str]:
    """Ошибки XSD по фрагментам; без схем — исключение FileNotFoundError."""
    d = xsd_dir(tia, base)
    if d is None:
        raise FileNotFoundError(f"нет XSD {tia}: python tools/fetch_xsd.py (или C2S7_XSD_DIR)")
    root = etree.fromstring(xml.encode("utf-8"))
    errors: list[str] = []
    for local, fname in FILES.items():
        schema = _schema(str(d / fname))
        for el in root.iter():
            if isinstance(el.tag, str) and etree.QName(el).localname == local:
                frag = _strip_ns(el)
                if not schema.validate(frag):
                    for e in schema.error_log:
                        errors.append(f"{local}: строка {e.line}: {e.message}")
    return errors
