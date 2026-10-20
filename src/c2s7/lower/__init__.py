"""Понижения в ST AST: IL, LD/FBD/CFC (NetIR), SFC (SfcIR), переходы (jumps.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from c2s7.st import nodes as A

if TYPE_CHECKING:
    from c2s7.convert.core import Converter
    from c2s7.model import Pou, Project


def lower_pou(pou: Pou, conv: Converter | None = None) -> list[A.Stmt] | None:
    """Тело POU в ST AST или None, если POU уже на ST без действий."""
    lang = pou.language
    for act in pou.actions:
        if act.language == "IL" and act.il is not None:
            from c2s7.lower.il import il_to_st

            act.body = il_to_st(act.il, pou, conv)
            act.language = "ST"
        elif act.language not in ("ST", "IL") and conv is not None:
            conv.add(
                "C2S7-LIB", act.origin or pou.origin, f"действие {act.name}: графический язык действия не переводится"
            )
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


def lower_project(project: Project) -> Project:
    """Понижает графику и IL всех POU проекта на месте (для c2s7.sim источника); возвращает проект."""
    from c2s7.lower.jumps import remove_jumps

    for pou in project.pous:
        if pou.language != "ST" or pou.actions:
            stmts = lower_pou(pou, None)
            if stmts is not None:
                pou.text.body = stmts
        elif any(isinstance(s, A.Jump | A.Label) for s in pou.text.body):
            pou.text.body = remove_jumps(pou.text.body).stmts
    return project
