"""Понижения в ST AST: IL, LD/FBD/CFC (NetIR), SFC (SfcIR), переходы (jumps.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from c2s7.st import nodes as A

if TYPE_CHECKING:
    from c2s7.convert.core import Converter
    from c2s7.model import Pou


def lower_pou(pou: Pou, conv: Converter | None = None) -> list[A.Stmt] | None:
    """Тело POU в ST AST или None, если POU уже на ST без действий."""
    lang = pou.language
    if lang == "IL" and pou.il is not None:
        from c2s7.lower.il import il_to_st

        return il_to_st(pou.il, pou, conv)
    if lang in ("LD", "FBD", "CFC") and pou.net is not None:
        from c2s7.lower.net import net_to_st

        return net_to_st(pou, conv)
    if lang == "SFC" and pou.sfc is not None:
        from c2s7.lower.sfc import sfc_to_st

        return sfc_to_st(pou, conv)
    return None
