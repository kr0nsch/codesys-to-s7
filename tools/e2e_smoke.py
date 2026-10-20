"""Дымовой e2e просмотрщика (ТЗ §8.8): Playwright из Python, ThreadingHTTPServer на порту 0.

Проверки: счётчики на странице = `c2s7 analyze` того же входа; схемы SVG загружаются; запросов к чужим
доменам нет; ошибок в консоли нет. Скриншоты тёмной и светлой темы — build/e2e/*.png.

    python tools/e2e_smoke.py [--site build/site-out] [--shots docs/media]
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]


def cli_totals(inp: str, cpu: str, tia: str) -> dict[str, int]:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "c2s7",
            "analyze",
            inp,
            "--cpu",
            cpu,
            "--tia",
            tia,
            "--format",
            "json",
            "--fail-on",
            "never",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    data = json.loads(proc.stdout)
    return {k: int(v) for k, v in data["totals"]["by_outcome"].items()}


def serve(site: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
    handler.log_message = lambda *a, **k: None  # type: ignore[attr-defined]
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/"


def main(argv: list[str] | None = None) -> int:
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", default=str(REPO / "build" / "site-out"))
    ap.add_argument("--shots", default=str(REPO / "build" / "e2e"))
    args = ap.parse_args(argv)
    site = Path(args.site)
    shots = Path(args.shots)
    shots.mkdir(parents=True, exist_ok=True)
    httpd, url = serve(site)
    problems: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for scheme in ("dark", "light"):
                page = browser.new_page(viewport={"width": 1440, "height": 1000}, color_scheme=scheme)
                foreign: list[str] = []
                errors: list[str] = []
                page.on(
                    "request",
                    lambda r, f=foreign: (
                        f.append(r.url)
                        if urlparse(r.url).hostname not in ("127.0.0.1",) and not r.url.startswith("data:")
                        else None
                    ),
                )
                page.on("console", lambda m, e=errors: e.append(m.text) if m.type == "error" else None)
                page.goto(url)
                page.wait_for_selector(".counter")
                for case, inp in (("ring", "tests/fixtures/s7-to-codesys"), ("corpus", "corpus/zarechnaya.xml")):
                    for cpu, tia in (("s7-1500", "V21"), ("s7-1200", "V19")):
                        page.click(f"button[data-case='{case}']")
                        page.click(f"button[data-cpu='{cpu}']")
                        page.wait_for_timeout(300)
                        shown = {
                            el.get_attribute("data-outcome"): int(el.inner_text().split("\n")[0])
                            for el in page.query_selector_all(".counter")
                        }
                        want = cli_totals(inp, cpu, tia)
                        if any(shown.get(k) != want.get(k, 0) for k in shown):
                            problems.append(f"{scheme} {case} {cpu}: на странице {shown}, CLI {want}")
                page.click("button[data-case='corpus']")
                page.click("button[data-cpu='s7-1500']")
                page.click("li[data-pou='PRG_PumpInterlock']")
                page.wait_for_timeout(300)
                imgs = page.query_selector_all("#src img, #tgt img")
                ok = [i.evaluate("i => i.complete && i.naturalWidth > 0") for i in imgs]
                if len(imgs) != 2 or not all(ok):
                    problems.append(f"{scheme}: схемы LD/LAD не загрузились ({len(imgs)} img, {ok})")
                page.screenshot(path=str(shots / f"viewer-{scheme}.png"), full_page=False)
                page.click("button[data-tab='traps']")
                page.wait_for_timeout(200)
                page.locator("#tab").screenshot(path=str(shots / f"traps-{scheme}.png"))
                page.click("button[data-case='ring']")
                page.click("button[data-tab='equiv']")
                page.wait_for_timeout(200)
                page.locator("#tab").screenshot(path=str(shots / f"ring-{scheme}.png"))
                page.click("button[data-tab='tags']")
                page.click("button[data-case='corpus']")
                page.wait_for_timeout(200)
                page.locator("#tab").screenshot(path=str(shots / f"tags-{scheme}.png"))
                if foreign:
                    problems.append(f"{scheme}: запросы к чужим доменам: {foreign[:3]}")
                if errors:
                    problems.append(f"{scheme}: ошибки консоли: {errors[:3]}")
                page.close()
            browser.close()
    finally:
        httpd.shutdown()
    for pr in problems:
        print("ПРОБЛЕМА:", pr)
    print(json.dumps({"ok": not problems, "shots": str(shots)}, ensure_ascii=False))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
