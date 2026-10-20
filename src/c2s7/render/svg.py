"""SVG сетей в стиле портфолио (brand.md: «инженерный чертёж», нейтральные линии, один акцент).

Цвета — классы CSS (`ln`, `tx`, `dim`, `acc`); у отдельного файла свои стили с тёмной и светлой темой
(prefers-color-scheme), на сайте их переопределяет страница. Схема цели подписана «схема построена
c2s7, не снимок TIA».
"""

from __future__ import annotations

from typing import Any
from xml.sax.saxutils import escape

from c2s7.render.tree import Box, Coil, Contact, NetView, Par, Series, Sink, Var

CW, CH = 74, 44  # контакт
GAP = 8
COIL_W = 96
FONT = "11px 'Cascadia Mono', Consolas, monospace"
STYLE = (
    "<style>"
    ".ln{stroke:#8FA3BA;fill:none;stroke-width:1.5}.tx{fill:#E6EDF3;font:" + FONT + "}"
    ".dim{fill:#7F90A6;font:" + FONT + "}.acc{stroke:#FF7A1A}.acct{fill:#FF7A1A;font:" + FONT + "}"
    ".bx{fill:#141E2B;stroke:#8FA3BA;stroke-width:1.5}.bg{fill:#0E1621}"
    "@media (prefers-color-scheme: light){.ln{stroke:#4A5B70}.tx{fill:#0F1923}.dim{fill:#5B6B7E}"
    ".acc{stroke:#C2410C}.acct{fill:#C2410C}.bx{fill:#FFFFFF;stroke:#4A5B70}.bg{fill:#F4F6F9}}"
    "</style>"
)


def _t(x: float, y: float, s: str, cls: str = "tx", anchor: str = "middle") -> str:
    return f'<text x="{x:.0f}" y="{y:.0f}" class="{cls}" text-anchor="{anchor}">{escape(s)}</text>'


# ---------------------------------------------------------------- LD / LAD
def _size(n: Any) -> tuple[int, int]:
    if n is None:
        return 20, CH
    if isinstance(n, Contact):
        return CW, CH
    if isinstance(n, Series):
        if not n.items:
            return 20, CH
        sizes = [_size(i) for i in n.items]
        return sum(w for w, _ in sizes), max(h for _, h in sizes)
    if isinstance(n, Par):
        sizes = [_size(i) for i in n.items]
        return max(w for w, _ in sizes) + 2 * GAP, sum(h for _, h in sizes)
    return CW, CH


def _draw(n: Any, x: float, y: float, out: list[str]) -> float:
    """Рисует узел; (x, y) — вход на линии потока; возвращает x выхода."""
    w, _ = _size(n)
    if n is None or (isinstance(n, Series) and not n.items):
        out.append(f'<path class="ln" d="M{x:.0f} {y:.0f}h{w}"/>')
        return x + w
    if isinstance(n, Contact):
        cx = x + CW / 2
        out.append(f'<path class="ln" d="M{x:.0f} {y:.0f}h{CW / 2 - 7:.0f}M{cx + 7:.0f} {y:.0f}h{CW / 2 - 7:.0f}"/>')
        out.append(f'<path class="ln" d="M{cx - 7:.0f} {y - 9:.0f}v18M{cx + 7:.0f} {y - 9:.0f}v18"/>')
        if n.neg:
            out.append(f'<path class="ln" d="M{cx - 5:.0f} {y + 8:.0f}l10 -16"/>')
        if n.edge:
            out.append(_t(cx, y + 4, n.edge, "acct"))
        out.append(_t(cx, y - 14, n.label[:12]))
        return x + CW
    if isinstance(n, Series):
        cur = x
        for it in n.items:
            cur = _draw(it, cur, y, out)
        return cur
    if isinstance(n, Par):
        top = y
        xe = x + w
        out.append(f'<path class="ln" d="M{x:.0f} {y:.0f}h{GAP}"/>')
        last_y = y
        for i, it in enumerate(n.items):
            _, h = _size(it)
            if i:
                out.append(
                    f'<path class="ln" d="M{x + GAP:.0f} {last_y:.0f}V{top:.0f}M{xe - GAP:.0f} {last_y:.0f}V{top:.0f}"/>'
                )
            end = _draw(it, x + GAP, top, out)
            out.append(f'<path class="ln" d="M{end:.0f} {top:.0f}H{xe - GAP:.0f}"/>')
            last_y = top
            top += h
        out.append(f'<path class="ln" d="M{xe - GAP:.0f} {y:.0f}h{GAP}"/>')
        return xe
    return x


def _coil(c: Coil, x: float, y: float, out: list[str]) -> None:
    cx = x + COIL_W / 2
    if c.kind in ("JMP", "RET"):
        out.append(f'<path class="ln" d="M{x:.0f} {y:.0f}h{COIL_W / 2 - 10:.0f}"/>')
        out.append(_t(cx + 4, y + 4, f"»{c.kind} {c.label}", "tx", "middle"))
        return
    out.append(
        f'<path class="ln" d="M{x:.0f} {y:.0f}h{COIL_W / 2 - 10:.0f}M{cx + 10:.0f} {y:.0f}h{COIL_W / 2 - 10:.0f}"/>'
    )
    out.append(f'<path class="ln acc" d="M{cx - 6:.0f} {y - 9:.0f}q-6 9 0 18M{cx + 6:.0f} {y - 9:.0f}q6 9 0 18"/>')
    if c.kind:
        out.append(_t(cx, y + 4, c.kind, "acct"))
    out.append(_t(cx, y - 14, c.label[:14]))


def _ld_rung(r: Any, x0: float, y0: float, out: list[str]) -> tuple[float, float]:
    _w, h = _size(r.flow)
    y = y0 + 26
    end = _draw(r.flow, x0, y, out)
    total_h = max(h, CH * len(r.coils))
    for i, c in enumerate(r.coils):
        cy = y + i * CH
        if i:
            out.append(f'<path class="ln" d="M{end:.0f} {y:.0f}V{cy:.0f}"/>')
        _coil(c, end, cy, out)
    return end + COIL_W, y0 + total_h + 10


# ---------------------------------------------------------------- FBD
BOX_W = 70
ROW = 22


def _fsize(n: Any) -> tuple[int, int]:
    if isinstance(n, Var):
        return 90, ROW
    if isinstance(n, Box):
        kids = [_fsize(k) for _, k, _ in n.inputs] or [(0, ROW)]
        return BOX_W + 20 + max(w for w, _ in kids), max(sum(h for _, h in kids), ROW * 2)
    return 90, ROW


def _fdraw(n: Any, xr: float, y: float, out: list[str]) -> None:
    """Рисует узел так, что его выход — в точке (xr, y)."""
    if isinstance(n, Var):
        out.append(_t(xr - 4, y + 4, ("NOT " if n.neg else "") + n.text[:14], "tx", "end"))
        return
    if isinstance(n, Box):
        _, h = _fsize(n)
        bx = xr - BOX_W
        top = y - h / 2
        out.append(f'<rect class="bx" x="{bx:.0f}" y="{top:.0f}" width="{BOX_W}" height="{h:.0f}" rx="3"/>')
        out.append(_t(bx + BOX_W / 2, top + 14, n.type[:10]))
        if n.instance:
            out.append(_t(bx + BOX_W / 2, top - 4, n.instance[:14], "dim"))
        cy = top
        for pin, kid, neg in n.inputs:
            _, kh = _fsize(kid)
            py = cy + kh / 2
            out.append(f'<path class="ln" d="M{bx - 20:.0f} {py:.0f}h20"/>')
            if neg:
                out.append(f'<circle class="ln" cx="{bx - 3:.0f}" cy="{py:.0f}" r="3"/>')
            out.append(_t(bx + 4, py + 4, pin, "dim", "start"))
            _fdraw(kid, bx - 20, py, out)
            cy += kh


def _fbd_sink(s: Sink, x0: float, y0: float, out: list[str]) -> tuple[float, float]:
    w, h = _fsize(s.node)
    y = y0 + h / 2 + 8
    xr = x0 + w
    _fdraw(s.node, xr, y, out)
    out.append(f'<path class="ln acc" d="M{xr:.0f} {y:.0f}h28"/>')
    if s.neg:
        out.append(f'<circle class="ln acc" cx="{xr + 4:.0f}" cy="{y:.0f}" r="3"/>')
    label = {"JMP": "» ", "RET": "RET ", "CALL": "вызов "}.get(s.kind, "")
    out.append(_t(xr + 32, y + 4, label + s.label[:16], "tx", "start"))
    return xr + 150, y0 + h + 16


# ---------------------------------------------------------------- документ
def render(views: list[NetView], language: str, title: str, caption: str = "") -> str:
    out: list[str] = []
    y = 34.0
    width = 360.0
    for i, v in enumerate(views, start=1):
        head = f"Сеть {i}" + (f" · {v.title}" if v.title else "") + (f" · метка {v.label}" if v.label else "")
        out.append(_t(12, y, head, "dim", "start"))
        y += 8
        if language in ("LD", "LAD"):
            out.append(f'<path class="ln" d="M12 {y:.0f}v{max(CH, 1):.0f}"/>')
            for r in v.rungs:
                xe, y2 = _ld_rung(r, 12, y, out)
                width = max(width, xe + 20)
                out.append(f'<path class="ln" d="M12 {y:.0f}V{y2 - 10:.0f}"/>')
                y = y2
        else:
            for s in v.sinks:
                xe, y2 = _fbd_sink(s, 12, y, out)
                width = max(width, xe + 20)
                y = y2
        y += 14
    if caption:
        out.append(_t(12, y + 4, caption, "dim", "start"))
        y += 14
    h = y + 10
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {h:.0f}" width="{width:.0f}" '
        f'height="{h:.0f}" role="img" aria-label="{escape(title)}">{STYLE}'
        f'<rect class="bg" width="100%" height="100%"/>' + _t(12, 18, title, "tx", "start")
    )
    return head + "".join(out) + "</svg>\n"
