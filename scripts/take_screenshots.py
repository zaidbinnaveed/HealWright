"""Full-page screenshots of every app page, light + dark, at 1366 and 1920 px wide.

    uv run healwright serve                    # in another terminal, http://127.0.0.1:8000
    uv run python scripts/take_screenshots.py  # -> docs/screenshots/<page>-<theme>-<width>.png

Run and heal-event pages use the newest add-to-cart heal in the app's data (the dev-01 story).
The demo verdict shots run one real replay demo (dev-01) per theme, about 30 s each.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Literal

from playwright.sync_api import Page, ViewportSize, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"
WIDTHS = (1366, 1920)
THEMES: tuple[Literal["light", "dark"], ...] = ("light", "dark")


def get_json(url: str) -> dict:  # type: ignore[type-arg]
    with urllib.request.urlopen(url, timeout=30) as res:
        data: dict = json.loads(res.read())  # type: ignore[type-arg]
        return data


def settle(page: Page) -> None:
    page.wait_for_load_state("networkidle")
    # Scroll through once so scroll-triggered sections render, then back to the top.
    height = page.evaluate("document.body.scrollHeight")
    for y in range(0, height, 600):
        page.evaluate("y => window.scrollTo(0, y)", y)
        page.wait_for_timeout(120)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(800)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    base = ap.parse_args().base.rstrip("/")

    runs = get_json(base + "/api/v1/runs")["items"]
    run_id = next(r["run_id"] for r in runs if any("test_add_to_cart" in t for t in r["tests"]))
    event_id = get_json(f"{base}/api/v1/runs/{run_id}")["events"][0]["id"]
    pages = {
        "landing": "/",
        "runs": "/runs",
        "run-detail": f"/runs/{run_id}",
        "heal-event": f"/events/{event_id}",
        "benchmark": "/benchmarks",
        "demo": "/demo",
    }

    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for theme in THEMES:
            for width in WIDTHS:
                size: ViewportSize = {"width": width, "height": 900}
                context = browser.new_context(viewport=size, color_scheme=theme)
                context.add_init_script(
                    f"try {{ localStorage.setItem('hw-theme', '{theme}'); }} catch (e) {{}}"
                )
                page = context.new_page()
                for name, path in pages.items():
                    page.goto(base + path)
                    settle(page)
                    page.screenshot(path=str(OUT / f"{name}-{theme}-{width}.png"), full_page=True)
                    print("shot", name, theme, width)
                if width == WIDTHS[0]:
                    page.goto(base + "/demo")
                    page.get_by_role("radio").filter(has_text="dev-01-id-rename").click()
                    button = page.get_by_role("button", name="2. Break it and run the test")
                    button.click()
                    page.wait_for_timeout(1500)
                    expect(button).to_be_enabled(timeout=240_000)
                    # Let the "Demo finished" toast close so it does not cover the shots.
                    toast = page.get_by_text("Demo finished")
                    try:
                        expect(toast).to_be_hidden(timeout=20_000)
                    except AssertionError:
                        page.mouse.click(5, 5)
                    page.wait_for_timeout(1000)
                    page.screenshot(
                        path=str(OUT / f"demo-verdict-{theme}-{width}.png"), full_page=True
                    )
                    print("shot demo-verdict", theme, width)
                context.close()
        browser.close()


if __name__ == "__main__":
    main()
