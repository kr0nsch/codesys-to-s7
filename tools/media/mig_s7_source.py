"""Текст функции пиктограммы `mig_s7` для `_shared/media-kit/pictograms.py` (вставляет add_pictogram.py)."""

SOURCE = '''

def mig_s7(g: G) -> None:
    """Перенос CODESYS -> Siemens S7 (codesys-to-s7): проект CODESYS слева (было), блок TIA Portal справа.

    Справа вверху — сеть LAD (SimaticML FlgNet), внизу — отчёт о переносе по языкам: доли классов
    auto/review/verify/manual корпуса «Заречная» на S7-1500 (вывод `c2s7 analyze`, 20.10.2026).
    """
    t = g.t
    rows = [(0, 66, "kw"), (12, 88, "id"), (12, 58, "id"), (0, 48, "kw"), (12, 80, "id"), (24, 54, "lit")]
    col = {"kw": t["process"], "id": t["line"], "lit": t["accent"]}
    # было: проект CODESYS (приглушён — исходник): ST и ступень LD
    _window(g, 6, 34, 150, 186, "CODESYS 3.5", dim=True)
    for i, (ind, ln, kind) in enumerate(rows):
        g.rect(20 + ind, 70 + i * 14, ln, 5, 2.5, None, col[kind], opacity=0.85 if kind != "id" else 0.55)
    g.line(20, 168, 20, 196, t["line_dim"], 1.4)
    g.path("M20 182H36M44 182H70M78 182H100", t["line_dim"], 1.4)
    for x in (36, 70):
        g.path(f"M{x} 175V189M{x + 8} 175V189", t["line_dim"], 1.4)
    g.path("M106 175Q101 182 106 189M114 175Q119 182 114 189", t["line_dim"], 1.4)
    g.text("ST LD FBD CFC SFC IL", 81, 212, "mono", LABEL["minor"], t["text_dim"], "middle")
    # стрелка переноса
    g.path("M162 110H184", t["accent"], 3, cls="flow", cap="butt")
    g.arrow_head(193, 110, 0, 9, t["accent"])
    g.text("c2s7", 178, 96, "mono_semibold", LABEL["label"], t["accent"], "middle")
    # стало: блок TIA Portal с сетью LAD
    _window(g, 202, 14, 192, 112, "TIA Portal", accent=True)
    g.text('FB "PRG_X"', 214, 56, "mono_semibold", LABEL["minor"], t["text"])
    g.line(214, 66, 214, 106, t["line"], 1.6)
    g.path("M214 86H238M248 86H282M292 86H330M346 86H372", t["line"], 1.6)
    for x in (238, 282):
        g.path(f"M{x} 77V95M{x + 10} 77V95", t["line"], 1.6)
    g.path("M334 77Q327 86 334 95M342 77Q349 86 342 95", t["accent"], 2)
    g.text("LAD · SCL", 382, 116, "mono", LABEL["minor"], t["text_dim"], "end")
    # отчёт по языкам: доли классов
    g.rect(202, 134, 192, 96, 6, t["line"], t["surface"], 1.5)
    g.text("отчёт по языкам", 212, 150, "mono_semibold", LABEL["title"], t["text"])
    shares = [("ST", 25, 3, 4, 0), ("LD", 15, 0, 0, 0), ("FBD", 7, 0, 1, 0),
              ("CFC", 11, 0, 1, 0), ("SFC", 125, 16, 0, 0), ("IL", 9, 0, 0, 0)]
    colors = (t["process"], t["line"], t["violet"], t["warn"])
    for i, (lang, *parts) in enumerate(shares):
        cx = 212 + (i // 3) * 92
        cy = 164 + (i % 3) * 21
        g.text(lang, cx, cy + 8, "mono", LABEL["minor"], t["text_muted"])
        total = sum(parts)
        x = cx + 30
        for n, c in zip(parts, colors):
            if n:
                w = 50 * n / total
                g.rect(x, cy, w, 9, 1.5, None, c)
                x += w
    g.text("проект CODESYS", 81, 247, "mono", LABEL["label"], t["text_dim"], "middle")
    g.text("S7-1200/1500 + отчёт", 298, 247, "mono", LABEL["label"], t["text_dim"], "middle")


REGISTRY["mig_s7"] = mig_s7
'''
