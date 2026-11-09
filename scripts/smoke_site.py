"""Smoke test for the hosted showcase site (or a local preview of dist-showcase/).

    uv run python scripts/smoke_site.py https://<site>

Every route loads in light and dark theme with no console errors, no page errors and no
failed requests; the page title and favicon are present; the theme class matches; the
demo video actually plays. Uses the installed Google Chrome (``channel="chrome"``):
Playwright's own Chromium cannot decode H.264. Exit code 1 on any failure.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from typing import Literal

from playwright.sync_api import ConsoleMessage, Page, Request, Response, sync_playwright

THEMES: tuple[Literal["light", "dark"], ...] = ("light", "dark")


def get_json(url: str) -> dict:  # type: ignore[type-arg]
    with urllib.request.urlopen(url, timeout=30) as res:
        data: dict = json.loads(res.read())  # type: ignore[type-arg]
        return data


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    base = ap.parse_args().base.rstrip("/")

    runs = get_json(base + "/showcase/data/runs.json")["items"]
    run_id = next(r["run_id"] for r in runs if r["status_counts"]["healed"] > 0)
    event_id = get_json(f"{base}/showcase/data/runs/{run_id}.json")["events"][0]["id"]
    routes = ["/", "/runs", f"/runs/{run_id}", f"/events/{event_id}", "/benchmarks", "/demo"]

    failures: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        for theme in THEMES:
            context = browser.new_context(
                viewport={"width": 1366, "height": 900}, color_scheme=theme
            )
            context.add_init_script(
                f"try {{ localStorage.setItem('hw-theme', '{theme}'); }} catch (e) {{}}"
            )
            page = context.new_page()
            problems = watch(page)
            for route in routes:
                problems.clear()
                res = page.goto(base + route, wait_until="networkidle")
                status = res.status if res else 0
                title = page.title()
                dark = page.evaluate("document.documentElement.classList.contains('dark')")
                icon = page.evaluate("document.querySelector('link[rel=icon]')?.href ?? ''")
                heading = (
                    page.locator("h1").first.inner_text(timeout=10_000)
                    if page.locator("h1").count()
                    else ""
                )
                ok_theme = dark == (theme == "dark")
                line = f"[{theme}] {route}: HTTP {status}, title {title!r}, h1 {heading[:40]!r}"
                bad = status != 200 or "HealWright" not in title or not icon or not ok_theme
                if bad or problems:
                    failures.append(
                        line + f", icon={bool(icon)}, theme_ok={ok_theme}, problems={problems}"
                    )
                print(("FAIL " if bad or problems else "ok   ") + line)
                if route == "/demo":
                    played = play_video(page)
                    print(f"     demo video: {played}")
                    if not played.startswith("playing"):
                        failures.append(f"[{theme}] /demo video: {played}")
            icon_res = page.request.get(base + "/favicon.svg")
            if icon_res.status != 200:
                failures.append(f"[{theme}] /favicon.svg HTTP {icon_res.status}")
            context.close()
        browser.close()

    print("\nRESULT:", "PASS" if not failures else f"FAIL ({len(failures)})")
    for f in failures:
        print(" -", f)
    return 1 if failures else 0


def watch(page: Page) -> list[str]:
    """Collect console errors/warnings, page errors and failed or 4xx/5xx requests."""
    problems: list[str] = []

    def on_console(m: ConsoleMessage) -> None:
        if m.type in ("error", "warning"):
            problems.append(f"console {m.type}: {m.text}")

    def on_response(r: Response) -> None:
        if r.status >= 400:
            problems.append(f"HTTP {r.status}: {r.url}")

    def on_failed(r: Request) -> None:
        # Chrome cancels its preload range request for <video> by design: not an error.
        if r.resource_type == "media" and r.failure == "net::ERR_ABORTED":
            return
        problems.append(f"request failed: {r.url} {r.failure}")

    page.on("console", on_console)
    page.on("pageerror", lambda e: problems.append(f"page error: {e}"))
    page.on("requestfailed", on_failed)
    page.on("response", on_response)
    return problems


def play_video(page: Page) -> str:
    video = page.locator("video")
    if video.count() != 1:
        return f"no single <video> (found {video.count()})"
    state = page.evaluate(
        """async () => {
          const v = document.querySelector('video');
          v.muted = true;
          try { await v.play(); } catch (e) { return 'play() rejected: ' + e; }
          await new Promise(r => setTimeout(r, 2500));
          return {t: v.currentTime, d: v.duration, w: v.videoWidth, h: v.videoHeight, err: v.error && v.error.code};
        }"""
    )
    if isinstance(state, str):
        return state
    if state["err"] or state["t"] <= 0.5 or not state["w"]:
        return f"not playing: {state}"
    return f"playing (t={state['t']:.1f}s of {state['d']:.0f}s, {state['w']}x{state['h']})"


if __name__ == "__main__":
    sys.exit(main())
