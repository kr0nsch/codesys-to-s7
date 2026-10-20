"""Медиа README (docs/media) из реальных прогонов: GIF терминала, GIF просмотрщика, скриншоты, график.

Снимается в чистом клоне репозитория (`C:\\Users\\hello\\work\\codesys-to-s7`) с медиа-китом серии
(`domestic-plc-gaps/_shared/media-kit`, путь — MEDIA_KIT_DIR или --kit):

    python tools/make_media.py all            # всё
    python tools/make_media.py term           # GIF 1: inventory → analyze → migrate → verify → pytest -m codesys
    python tools/make_media.py viewer         # GIF 2 и скриншоты просмотрщика (dark/light)
    python tools/make_media.py chart          # доли классов по языкам (dark/light)

Числа в подписях — из этих же прогонов. GIF терминала — запись настоящих команд (term2gif), паузы
сокращены при рендере; кадры просмотрщика — Playwright по сайту `c2s7 site`.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MEDIA = REPO / "docs" / "media"
DEFAULT_KIT = REPO.parent / "asu_TP" / "domestic-plc-gaps" / "_shared" / "media-kit"  # рядом с клоном


def kit_dir(arg: str | None) -> Path:
    kit = Path(arg or os.environ.get("MEDIA_KIT_DIR") or DEFAULT_KIT)
    if str(kit) not in sys.path:
        sys.path.insert(0, str(kit))
    return kit


def run(cmd: list[str], **kw: Any) -> None:
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=str(REPO), **kw)


def term(kit: Path) -> None:
    session = REPO / "build" / "media" / "session-cli.json"
    session.parent.mkdir(parents=True, exist_ok=True)
    venv = REPO / ".venv" / "Scripts"
    env = dict(os.environ, PATH=str(venv) + os.pathsep + os.environ.get("PATH", ""), PYTHONIOENCODING="utf-8")
    cmds = [
        "c2s7 inventory corpus/zarechnaya.xml",
        "c2s7 analyze corpus/zarechnaya.xml --cpu s7-1200 --tia V19 --fail-on never",
        "c2s7 migrate corpus/zarechnaya.xml --out out/zar --cpu s7-1500 --tia V21",
        "c2s7 migrate tests/fixtures/s7-to-codesys --out out/ring",
        "c2s7 verify out/ring --roundtrip",
        "python -m pytest -m codesys tests/codesys/test_controlwin.py -k compat -q -p no:randomly",
    ]
    subprocess.run(
        [
            sys.executable,
            str(kit / "term2gif.py"),
            "capture",
            "-o",
            str(session),
            "--shell",
            "powershell",
            "--cwd",
            str(REPO),
            "--title",
            "codesys-to-s7",
            "--prompt",
            "PS codesys-to-s7> ",
            "--cols",
            "110",
            "--pause",
            "0.6",
            *cmds,
        ],
        check=True,
        env=env,
    )
    subprocess.run(
        [
            sys.executable,
            str(kit / "term2gif.py"),
            "render",
            str(session),
            str(MEDIA / "demo-cli.gif"),
            "--speed",
            "1.4",
        ],
        check=True,
    )


def _serve(site: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a: Any) -> None:
            pass

    handler = functools.partial(Quiet, directory=str(site))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/"


def viewer(kit: Path) -> None:
    import shot
    from playwright.sync_api import sync_playwright

    site = REPO / "build" / "media" / "site"
    run([sys.executable, "-m", "c2s7", "site", "--out", str(site)])
    httpd, url = _serve(site)
    frames: list[Any] = []
    durations: list[int] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for scheme in ("dark", "light"):
                page = browser.new_page(
                    viewport={"width": 1440, "height": 900}, color_scheme=scheme, device_scale_factor=1
                )
                page.goto(url)
                page.wait_for_selector(".counter")
                page.click("button[data-case='corpus']")
                page.click("li[data-pou='PRG_PumpInterlock']")
                page.wait_for_timeout(400)
                page.screenshot(path=str(MEDIA / f"shot-viewer-{scheme}.png"))
                page.click("button[data-tab='traps']")
                page.wait_for_timeout(300)
                page.locator("#tab .trap").first.screenshot(path=str(MEDIA / f"shot-trap-srrs-{scheme}.png"))
                page.click("button[data-tab='tags']")
                page.wait_for_timeout(300)
                page.locator("#tab").screenshot(path=str(MEDIA / f"shot-tags-{scheme}.png"))
                page.click("button[data-case='ring']")
                page.click("button[data-tab='equiv']")
                page.wait_for_timeout(300)
                page.locator("#tab").screenshot(path=str(MEDIA / f"shot-ring-{scheme}.png"))
                if scheme == "dark":
                    # GIF 2: LD → LAD, переключение на S7-1200, эквивалентность корпуса
                    page.set_viewport_size({"width": 1200, "height": 760})
                    steps = [
                        ("button[data-case='corpus']", 1400),
                        ("li[data-pou='PRG_Permissives']", 2200),
                        ("li[data-pou='FB_LevelAlarm']", 2200),
                        ("button[data-cpu='s7-1200']", 2000),
                        ("button[data-tab='equiv']", 600),
                    ]
                    for sel, ms in steps:
                        page.click(sel)
                        page.wait_for_timeout(350)
                        if sel.endswith("'equiv']"):
                            page.locator("#tab").scroll_into_view_if_needed()
                            page.wait_for_timeout(200)
                        img = REPO / "build" / "media" / f"frame-{len(frames):02d}.png"
                        page.screenshot(path=str(img))
                        frames.append(img)
                        durations.append(ms)
                    durations[-1] = 2600
                page.close()
            browser.close()
            report = REPO / "out" / "zar" / "MIGRATION_REPORT.html"
            if report.exists():
                b = p.chromium.launch()
                for scheme in ("dark", "light"):
                    pg = b.new_page(viewport={"width": 1200, "height": 900}, color_scheme=scheme)
                    pg.goto(report.resolve().as_uri())
                    pg.screenshot(path=str(MEDIA / f"shot-report-{scheme}.png"))
                    pg.close()
                b.close()
    finally:
        httpd.shutdown()
    shot.frames_to_gif(frames, MEDIA / "demo-viewer.gif", durations=durations, colors=128)


def chart(kit: Path) -> None:
    import charts
    import numpy as np

    out = subprocess.run(
        [sys.executable, "-m", "c2s7", "analyze", "corpus/zarechnaya.xml", "--format", "json", "--fail-on", "never"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    data = json.loads(out.stdout)["totals"]["by_language"]
    langs = [x for x in ("ST", "FBD", "LD", "CFC", "SFC", "IL") if x in data]
    classes = ["auto", "review", "verify", "manual", "impossible"]

    def build(c: dict[str, Any]) -> Any:
        fig, axes = charts.figure(1, size=(10, 4.2))
        ax = axes[0]
        totals = np.array([sum(data[x][k] for k in classes) for x in langs], dtype=float)
        left = np.zeros(len(langs))
        colors = {
            "auto": c["series"][0],
            "review": c["neutral"],
            "verify": c["series"][3],
            "manual": c["warn"],
            "impossible": c["alarm"],
        }
        pos = np.arange(len(langs))
        for k in classes:
            share = np.array([100.0 * data[x][k] / t if t else 0 for x, t in zip(langs, totals, strict=True)])
            if share.sum() == 0:
                continue
            ax.barh(pos, share, left=left, height=0.56, color=colors[k], edgecolor=c["bg"], linewidth=1.5, label=k)
            left += share
        ax.set_yticks(pos, [f"{x} · {int(t)}" for x, t in zip(langs, totals, strict=True)])
        ax.invert_yaxis()
        ax.set_xlim(0, 100)
        ax.grid(axis="x")
        ax.grid(axis="y", visible=False)
        ax.set_xlabel("доля конструкций, %")
        charts.legend_top(ax, c, ncol=4)
        charts.header(
            fig, "Корпус «Заречная» → S7-1500: классы по языкам", "c2s7 analyze, число конструкций после имени языка", c
        )
        return fig

    charts.save_themes(build, MEDIA / "chart-classes")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("what", choices=["all", "term", "viewer", "chart"])
    ap.add_argument("--kit")
    args = ap.parse_args(argv)
    kit = kit_dir(args.kit)
    MEDIA.mkdir(parents=True, exist_ok=True)
    if args.what in ("all", "chart"):
        chart(kit)
    if args.what in ("all", "viewer"):
        if not (REPO / "out" / "zar" / "MIGRATION_REPORT.html").exists():
            run([sys.executable, "-m", "c2s7", "migrate", "corpus/zarechnaya.xml", "--out", "out/zar"])
        viewer(kit)
    if args.what in ("all", "term"):
        term(kit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
