"""SimaticML (TIA Portal Openness XML): сети LAD/FBD (FlgNet) для V19/V21."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from c2s7.convert.core import Result


def emit_simaticml(res: Result) -> dict[str, str]:
    """Файлы tia/simaticml/*.xml для POU на LD/FBD из подмножества P0 (путь → текст)."""
    from c2s7.emit.simaticml.flgnet import emit_all

    return emit_all(res)
