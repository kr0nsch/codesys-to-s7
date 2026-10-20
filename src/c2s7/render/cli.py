"""`c2s7 render <вход> --pou X --out DIR`: SVG сети POU — источник CODESYS и цель c2s7 (если блок выдан FlgNet)."""

from __future__ import annotations

import argparse
from pathlib import Path

from c2s7.render.svg import render
from c2s7.render.tree import from_flgnet, from_netir

CAPTION = "схема построена c2s7, не снимок TIA"


def render_pou(inp: Path, pou_name: str, cpu: str = "s7-1500", tia: str = "V21") -> dict[str, str]:
    """{'source': svg, 'target': svg?} для POU на LD/FBD/CFC."""
    import copy

    from c2s7.api import load_input, migrate
    from c2s7.convert.core import Options

    proj = load_input(inp)
    pou = next((p for p in proj.pous if p.name.upper() == pou_name.upper()), None)
    if pou is None or pou.net is None:
        raise ValueError(f"{pou_name}: нет POU на LD/FBD/CFC")
    lang = pou.language
    out = {"source": render(from_netir(copy.deepcopy(pou.net)), lang, f"{pou.name} · CODESYS {lang}")}
    res = migrate(proj, Options(cpu=cpu, tia=tia))
    blk = next((b for b in res.blocks if b.source_pou == pou.name and b.flgnet), None)
    if blk is not None and blk.flgnet in res.simaticml:
        tgt_lang = "LAD" if lang == "LD" else "FBD"
        out["target"] = render(
            from_flgnet(res.simaticml[blk.flgnet]), tgt_lang, f"{blk.name} · TIA {tgt_lang} (FlgNet {tia})", CAPTION
        )
    return out


def render_cli(args: argparse.Namespace) -> int:
    svgs = render_pou(Path(args.input), args.pou, args.cpu, args.tia)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for kind, svg in svgs.items():
        (out / f"{args.pou}.{kind}.svg").write_text(svg, encoding="utf-8", newline="\n")
        print(out / f"{args.pou}.{kind}.svg")
    if "target" not in svgs:
        print("цель — SCL (блок вне подмножества FlgNet или --graphics scl)")
    return 0
