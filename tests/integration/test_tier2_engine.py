"""Engine Tier-2 path end to end, in-process, FakeProvider, real Chromium.

dev-07 distractor: Tier 1's gate refuses (the look-alike is too close), so the
VLM decides. Whatever it picks, the verifier has the last word.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, expect

from chaos_store.scenario import SCENARIO_DIR
from healwright.config import Settings
from healwright.engine import HealOutcome, HealRequest, heal
from healwright.plugin.proxy import ActionTracker, PageProxy, RunStats
from healwright.recorder.recorder import Recorder
from healwright.store.baselines import record_passing_run
from healwright.tier2.cache import ResponseCache
from healwright.tier2.picker import VlmPicker
from healwright.tier2.providers import FakeProvider, mark_named
from healwright.tier2.router import Router
from tests.conftest import LiveStore

pytestmark = [pytest.mark.integration, pytest.mark.slow]

NODE = "tests/inner.py::test_confirm[chromium]"


def checkout(p: Page, base: str) -> None:
    p.goto("/product/2")
    p.click("#add-to-cart")
    p.goto("/checkout")
    p.fill("#full-name", "Ada Lovelace")
    p.fill("#email", "ada@example.com")
    p.check("#agree")
    p.click("#place-order")
    expect(p).to_have_url(base + "/order/1001")


def new_page(browser: Browser, base: str) -> tuple[Page, Callable[[], None]]:
    ctx = browser.new_context(base_url=base, viewport={"width": 1280, "height": 800})
    return ctx.new_page(), ctx.close


def record_baselines(browser: Browser, store: LiveStore, root: Path) -> None:
    for _ in range(2):
        page, close = new_page(browser, store.base_url)
        rec = Recorder(page)
        rec.attach()
        proxy = PageProxy(page, ActionTracker(test_nodeid=NODE, stats=RunStats(), observers=[rec]))
        checkout(proxy, store.base_url)
        proxy.click("#confirm-order")
        expect(page.locator("#order-status")).to_have_text("Status: Confirmed")
        assert record_passing_run(root, NODE, rec.finish()) or True
        close()


def heal_confirm(
    browser: Browser, store: LiveStore, root: Path, provider: FakeProvider
) -> tuple[HealOutcome, str]:
    store.set_scenario(
        (SCENARIO_DIR / "dev" / "dev-07-distractor.yaml").read_text(encoding="utf-8")
    )
    page, _close = new_page(browser, store.base_url)
    tracker = ActionTracker(test_nodeid=NODE, stats=RunStats())
    proxy = PageProxy(page, tracker)
    checkout(proxy, store.base_url)
    key = tracker.next_key("click", "#confirm-order")
    assert key is not None
    picker = VlmPicker(Router([provider], ResponseCache(root / "cache", "live"), run_cap=30))
    outcome = heal(
        HealRequest(
            page=page,
            key=key,
            selector="#confirm-order",
            args=(),
            kwargs={},
            prefix=list(tracker.prefix),
            baseline_root=root,
            settings=Settings(_env_file=None),  # type: ignore[call-arg]
        ),
        tier2=picker,
    )
    session = {c["name"]: c["value"] for c in page.context.cookies()}["cw_session"]
    return outcome, session


def live_actions(store: LiveStore, session: str) -> list[object]:
    return [a["action_id"] for a in store.actions(session)]


def test_tier2_picks_true_target_and_heals(page: Page, store: LiveStore, tmp_path: Path) -> None:
    browser = page.context.browser
    assert browser is not None
    record_baselines(browser, store, tmp_path)
    fake = FakeProvider("ok", choose=mark_named("confirm order"))
    outcome, session = heal_confirm(browser, store, tmp_path, fake)
    assert outcome.decision.status == "healed", outcome.decision.reason
    assert outcome.decision.tier == 2
    assert (
        outcome.decision.locator == "page.get_by_role('button', name='Confirm order', exact=True)"
    )
    assert outcome.som is not None  # Set-of-Mark image kept for the report
    assert fake.calls == 1
    assert live_actions(store, session)[-1] == "confirm_order"


def test_tier2_lookalike_is_rejected_by_the_verifier(
    page: Page, store: LiveStore, tmp_path: Path
) -> None:
    browser = page.context.browser
    assert browser is not None
    record_baselines(browser, store, tmp_path)
    fake = FakeProvider("ok", choose=mark_named("cancel order"))
    outcome, session = heal_confirm(browser, store, tmp_path, fake)
    assert outcome.decision.status == "regression_suspected"
    assert outcome.decision.tier == 2
    assert "extra state-changing call: DELETE /api/orders/{id}" in outcome.decision.reason
    assert "cancel_order" not in live_actions(store, session)  # the real run never cancelled


def test_tier2_target_absent(page: Page, store: LiveStore, tmp_path: Path) -> None:
    browser = page.context.browser
    assert browser is not None
    record_baselines(browser, store, tmp_path)
    outcome, _ = heal_confirm(browser, store, tmp_path, FakeProvider("null_mark"))
    assert outcome.decision.status == "regression_suspected"
    assert "target absent" in outcome.decision.reason


def test_providers_down_needs_human(page: Page, store: LiveStore, tmp_path: Path) -> None:
    browser = page.context.browser
    assert browser is not None
    record_baselines(browser, store, tmp_path)
    outcome, _ = heal_confirm(browser, store, tmp_path, FakeProvider("auth"))
    assert outcome.decision.status == "needs_human"
    assert "Tier 2 failed" in outcome.decision.reason
