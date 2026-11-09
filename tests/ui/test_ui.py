"""UI tests: the BUILT frontend served by FastAPI, driven by pytest-playwright.

One smoke test per screen, plus the accept -> apply flow and the demo flow (e2e).
Data: the throwaway run folders and git repo from the API tests' ``env`` fixture, and
the committed eval-combined benchmark summary. The demo runner is the API tests' fake
(instant), so no Chaos Store or browser-in-browser runs here; the real demo runner is
covered by tests/integration/test_api_demo_live.py.

Skipped when frontend/dist is missing (run `npm run build` in frontend/ first).
Never start the Vite dev server for these.
"""

from __future__ import annotations

import dataclasses
import re
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from playwright.sync_api import Page, expect

from chaos_store.serve import free_port
from healwright.api import create_app
from tests.integration.test_api import HEALED, env  # noqa: F401 - fixture re-export

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "frontend" / "dist"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="frontend not built"),
]


@pytest.fixture
def app_url(env: dict[str, Any]) -> Iterator[str]:  # noqa: F811
    paths = dataclasses.replace(
        env["paths"], frontend_dist=DIST, results_root=ROOT / "benchmark" / "results"
    )
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(paths, env["demo"]), host="127.0.0.1", port=port, log_level="warning"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "API did not start"
        assert thread.is_alive(), "API thread died"
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture
def console_errors(page: Page) -> list[str]:
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    return errors


def test_landing(page: Page, app_url: str, console_errors: list[str]) -> None:
    page.goto(app_url)
    expect(page.get_by_role("heading", level=1)).to_have_text("HealWright")
    expect(page.get_by_text("Never a fake pass.")).to_be_visible()
    # headline metrics come from the committed eval summary (0.9917 -> 99.2%)
    expect(page.get_by_text("true heal rate", exact=True)).to_be_visible()
    expect(page.get_by_text("99.2%", exact=True)).to_be_visible()
    expect(page).to_have_title("HealWright: self-healing tests that never lie")
    assert page.locator('link[rel="icon"][href="/favicon.svg"]').count() == 1
    body = page.locator("body").inner_text()
    for word in (
        "Zaid",
        "Abbas",
        "Sabeeh",
        "FAST",
        "NUCES",
        "University",
        "semester",
        "Illustration",
    ):
        assert word not in body, word
    page.get_by_role("tab", name="Apply").click()
    expect(page.get_by_text("healwright apply <event_id>")).to_be_visible()
    page.get_by_role("link", name="Open dashboard").first.click()
    expect(page).to_have_url(re.compile(r"/runs$"))
    expect(page).to_have_title("Runs · HealWright")
    assert console_errors == []


def test_runs_and_run_detail(page: Page, app_url: str, env: dict[str, Any]) -> None:  # noqa: F811
    page.goto(f"{app_url}/runs")
    expect(page.get_by_role("heading", name="Runs")).to_be_visible()
    page.goto(f"{app_url}/runs/{env['run_a']}")
    expect(page.get_by_text(env["run_a"]).first).to_be_visible()


def test_heal_event_accept_then_apply(
    page: Page,
    app_url: str,
    env: dict[str, Any],  # noqa: F811
    console_errors: list[str],
) -> None:
    page.goto(f"{app_url}/events/{env['ev_patch']}")
    triage = page.locator("section", has=page.get_by_role("heading", name="Triage"))
    triage.get_by_role("button", name="Accept").click()
    page.get_by_role("dialog").get_by_role("button", name="Accept").click()
    expect(triage.get_by_role("button", name="Apply patch")).to_be_enabled()
    triage.get_by_role("button", name="Apply patch").click()
    page.get_by_role("dialog").get_by_role("button", name="Apply patch").click()
    expect(triage.get_by_role("status")).to_be_visible()
    deadline = time.monotonic() + 10
    while env["test_file"].read_text(encoding="utf-8") != HEALED:
        assert time.monotonic() < deadline, "patch was not applied to the file"
        time.sleep(0.1)
    assert console_errors == []


def test_benchmark_page_shows_the_eval_summary(
    page: Page, app_url: str, console_errors: list[str]
) -> None:
    page.goto(f"{app_url}/benchmarks")
    expect(page.get_by_role("heading", name="Benchmark", level=1)).to_be_visible()
    table = page.locator(
        "section", has=page.get_by_role("heading", name="All metrics (table view)")
    )
    raw = table.get_by_role("row").filter(has=page.get_by_role("rowheader", name="Raw-HTML LLM"))
    expect(raw).to_contain_text("95% (92.5% to 97.5%)")  # combined.json: 0.95 (0.925 to 0.975)
    expect(
        page.get_by_role("heading", name=re.compile(r"Scenario table .*50 scenarios"))
    ).to_be_visible()
    assert console_errors == []


def test_benchmark_page_api_down_shows_retry(page: Page, app_url: str) -> None:
    page.route("**/api/v1/benchmarks/combined", lambda route: route.abort())
    page.goto(f"{app_url}/benchmarks")
    expect(page.get_by_role("alert")).to_contain_text("not reachable")
    expect(page.get_by_role("button", name="Retry")).to_be_visible()


@pytest.mark.e2e
def test_demo_flow(page: Page, app_url: str, console_errors: list[str]) -> None:
    page.goto(f"{app_url}/demo")
    page.get_by_role("radio", name=re.compile("dev-07-distractor")).click()
    page.get_by_role("button", name="Break it and run the test").click()
    expect(page.get_by_test_id("verdict")).to_contain_text("Healed", timeout=15_000)
    assert console_errors == []


@pytest.mark.e2e
def test_demo_watch_toggle_and_broken_shop_tab(
    page: Page,
    app_url: str,
    env: dict[str, Any],  # noqa: F811
    console_errors: list[str],
) -> None:
    page.goto(f"{app_url}/demo")
    page.get_by_role("radio", name=re.compile("dev-01-id-rename")).click()
    page.get_by_text("Watch it happen").click()
    expect(page.get_by_role("checkbox", name=re.compile("Watch it happen"))).to_be_checked()
    page.get_by_role("button", name="Break it and run the test").click()
    expect(page.get_by_test_id("verdict")).to_contain_text("Healed", timeout=15_000)
    runs = list(env["demo"]._runs.values())
    assert runs[-1].watch is True
    try:
        with page.context.expect_page() as popup:
            page.get_by_role("button", name="Open the broken shop").click()
        shop = popup.value
        shop.wait_for_load_state()
        expect(shop).to_have_url(re.compile(r"^http://127\.0\.0\.1:\d+/$"))
        shop.goto(shop.url + "product/1")
        expect(shop.locator("#btn-add-basket-x7")).to_have_count(1)
    finally:
        env["demo"].close()
    assert console_errors == []
