"""Smoke test for a public HealWright backend (the Hugging Face Space, or a local public run).

    uv run python scripts/smoke_space.py https://<user>-healwright.hf.space

1. Public mode is on (``/api/v1/features``): no triage, no apply, no watch mode.
2. Every page loads in a browser with no console errors or failed requests.
3. "Open the broken shop" opens the scenario's shop under ``/shop`` with the renamed button.
4. Three real demos give the right verdict: dev-01 (id rename) heals; dev-07 (distractor
   trap) heals to the true target or stays red, never a false heal; dev-09 (regression
   trap) stays red. The per-visitor cooldown is honoured between them (``Retry-After``).
5. The heal event of the first demo opens on its page; review actions are not offered.

Exit code 1 on any failure.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from playwright.sync_api import ConsoleMessage, Page, Request, Response, sync_playwright

DEMOS = [
    ("dev-01-id-rename", {"true_heal"}),
    ("dev-07-distractor", {"true_heal", "red"}),
    ("dev-09-regression", {"red"}),
]
PAGES = ["/", "/runs", "/benchmarks", "/demo"]


def call(
    base: str, path: str, data: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any], Any]:
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        base + "/api/v1" + path,
        data=body,
        method="POST" if body is not None else "GET",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            return res.status, json.loads(res.read()), res.headers
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}"), exc.headers


def watch(page: Page) -> list[str]:
    problems: list[str] = []

    def on_console(m: ConsoleMessage) -> None:
        if m.type == "error":
            problems.append(f"console error: {m.text}")

    def on_response(r: Response) -> None:
        if r.status >= 400:
            problems.append(f"HTTP {r.status}: {r.url}")

    def on_failed(r: Request) -> None:
        problems.append(f"request failed: {r.url} {r.failure}")

    page.on("console", on_console)
    page.on("pageerror", lambda e: problems.append(f"page error: {e}"))
    page.on("requestfailed", on_failed)
    page.on("response", on_response)
    return problems


def run_demo(base: str, scenario: str) -> dict[str, Any]:
    started = time.monotonic()
    while True:
        status, body, headers = call(base, "/demo/runs", {"scenario_id": scenario})
        if status == 202:
            break
        code = body.get("error", {}).get("code")
        if status in (409, 429) and time.monotonic() - started < 600:
            wait = int(headers.get("Retry-After") or 10) if status == 429 else 10
            print(f"     {code}: waiting {wait} s")
            time.sleep(wait)
            continue
        raise RuntimeError(f"start {scenario}: HTTP {status} {body}")
    run_id = body["id"]
    while True:
        status, state, _ = call(base, f"/demo/runs/{run_id}")
        if status != 200:
            raise RuntimeError(f"poll {scenario}: HTTP {status} {state}")
        if not state["running"]:
            return state
        if time.monotonic() - started > 900:
            raise RuntimeError(f"{scenario}: still running after 15 min")
        time.sleep(2)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    base = ap.parse_args().base.rstrip("/")
    failures: list[str] = []

    status, features, _ = call(base, "/features")
    print("features:", status, features)
    if (
        status != 200
        or features.get("public") is not True
        or features.get("watch")
        or features.get("triage")
    ):
        failures.append(f"public mode not active: {status} {features}")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = context.new_page()
        problems = watch(page)
        for path in PAGES:
            problems.clear()
            res = page.goto(base + path, wait_until="networkidle", timeout=90_000)
            title = page.title()
            ok = bool(res and res.status == 200 and "HealWright" in title and not problems)
            print(
                ("ok   " if ok else "FAIL ") + f"{path}: HTTP {res.status if res else 0}, {title!r}"
            )
            if not ok:
                failures.append(f"{path}: {problems}")
        if page.get_by_text("Watch it happen").count():
            failures.append("/demo still offers 'Watch it happen'")

        page.goto(base + "/demo", wait_until="networkidle")
        page.get_by_role("radio").filter(has_text="dev-01-id-rename").click()
        with context.expect_page(timeout=60_000) as shop_info:
            page.get_by_role("button", name="Open the broken shop").click()
        shop = shop_info.value
        shop.wait_for_load_state("networkidle")
        shop.goto(shop.url.split("/shop/")[0] + "/shop/product/1", wait_until="networkidle")
        renamed = shop.locator("#add-to-cart").count() == 0
        button = shop.get_by_role("button", name="Add to cart").count() == 1
        print(f"shop: {shop.url} renamed={renamed} button={button}")
        if not (shop.url.startswith(base + "/shop/") and renamed and button):
            failures.append(f"broken shop not right: {shop.url} renamed={renamed} button={button}")
        shop.close()

        first_event: str | None = None
        for scenario, allowed in DEMOS:
            t0 = time.monotonic()
            state = run_demo(base, scenario)
            outcome, stage = state.get("outcome"), state.get("stage")
            secs = time.monotonic() - t0
            ok = stage == "done" and outcome in allowed
            print(
                ("ok   " if ok else "FAIL ")
                + f"{scenario}: {stage} / {outcome} ({secs:.0f} s incl. waits)"
            )
            if not ok:
                failures.append(
                    f"{scenario}: stage={stage} outcome={outcome} error={state.get('error')}"
                )
            if first_event is None and state.get("heal_event_ids"):
                first_event = state["heal_event_ids"][0]

        if first_event:
            problems.clear()
            page.goto(f"{base}/events/{first_event}", wait_until="networkidle")
            offered = page.get_by_role("button", name="Accept").count()
            print(f"event page: {page.title()!r}, Accept buttons: {offered}, problems: {problems}")
            if offered or problems:
                failures.append(f"event page: accept={offered} problems={problems}")
        else:
            failures.append("no heal event from the dev-01 demo")
        browser.close()

    print("\nRESULT:", "PASS" if not failures else f"FAIL ({len(failures)})")
    for f in failures:
        print(" -", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
