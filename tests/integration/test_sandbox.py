"""Sandbox replay skeleton: isolated context, prefix replay, contract capture."""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import Page

from healwright.locators import SynthesizedLocator
from healwright.locators.synth import LocatorCall
from healwright.models import ApiCall, StepKey
from healwright.plugin.proxy import ActionStep, GotoStep, PrefixStep
from healwright.verify.sandbox import run_candidate
from tests.conftest import LiveStore

pytestmark = pytest.mark.integration

VIEWPORT = {"width": 1280, "height": 800}


def act(action: str, selector: str, *args: object, via: str = "page") -> ActionStep:
    key = StepKey(test_nodeid="t.py::t", action=action, selector=selector, occurrence=0)  # type: ignore[arg-type]
    return ActionStep(key, via, selector, tuple(args), {})  # type: ignore[arg-type]


def click_by_test_id(tid: str):  # type: ignore[no-untyped-def]
    spec = SynthesizedLocator("test_id", (LocatorCall("get_by_test_id", (tid,)),))
    return lambda p: spec.build(p).click()


def ids(store: LiveStore) -> list[object]:
    return [a["action_id"] for a in store.actions()]


def test_candidate_effect_is_observed_in_isolation(page: Page, store: LiveStore) -> None:
    page.goto(f"{store.base_url}/product/1")  # the "real" run's session
    real_session = {c["name"]: c["value"] for c in page.context.cookies()}["cw_session"]
    contexts_before = len(page.context.browser.contexts)  # type: ignore[union-attr]

    prefix: list[PrefixStep] = [GotoStep(f"{store.base_url}/product/1", {})]
    run = run_candidate(page.context.browser, VIEWPORT, prefix, click_by_test_id("add-to-cart"))  # type: ignore[arg-type]

    assert run.outcome == "observed", run.reason
    assert run.observed is not None
    assert run.observed.api_calls == frozenset(
        {ApiCall(method="POST", path_template="/api/cart", status_class="2xx")}
    )
    assert run.observed.modal_delta == 1
    assert run.observed.url_before == run.observed.url_after == "/product/{id}"
    assert run.settle_ms < 2500
    # isolation: the sandbox used its own session and closed its context
    assert store.actions(real_session) == []
    assert ids(store) == ["add_to_cart"]
    assert len(page.context.browser.contexts) == contexts_before  # type: ignore[union-attr]


def test_prefix_replay_reaches_the_order_page(page: Page, store: LiveStore) -> None:
    b = store.base_url
    prefix: list[PrefixStep] = [
        GotoStep(f"{b}/product/2", {}),
        act("click", "#add-to-cart"),
        GotoStep(f"{b}/checkout", {}),
        act("fill", "#full-name", "Ada"),
        act("fill", "#email", "ada@example.com", via="locator"),
        act("check", "#agree"),
    ]
    run = run_candidate(page.context.browser, VIEWPORT, prefix, click_by_test_id("place-order"))  # type: ignore[arg-type]
    assert run.outcome == "observed", run.reason
    assert run.observed is not None
    assert run.observed.url_before == "/checkout"
    assert run.observed.url_after == "/order/{id}"
    assert (
        ApiCall(method="POST", path_template="/api/orders", status_class="2xx")
        in run.observed.api_calls
    )
    assert ids(store) == ["add_to_cart", "create_order"]


def test_distractor_effect_differs(page: Page, store: LiveStore) -> None:
    """Confirm and Cancel must be distinguishable by their observed calls (input to 6.1)."""
    b = store.base_url
    prefix: list[PrefixStep] = [
        GotoStep(f"{b}/product/2", {}),
        act("click", "#add-to-cart"),
        GotoStep(f"{b}/checkout", {}),
        act("fill", "#full-name", "Ada"),
        act("fill", "#email", "ada@example.com"),
        act("check", "#agree"),
        act("click", "#place-order"),
    ]
    browser = page.context.browser
    confirm = run_candidate(browser, VIEWPORT, prefix, click_by_test_id("confirm-order"))  # type: ignore[arg-type]
    cancel = run_candidate(browser, VIEWPORT, prefix, click_by_test_id("cancel-order"))  # type: ignore[arg-type]
    assert confirm.observed is not None
    assert cancel.observed is not None
    assert confirm.observed.api_calls == frozenset(
        {ApiCall(method="POST", path_template="/api/orders/{id}/confirm", status_class="2xx")}
    )
    assert cancel.observed.api_calls == frozenset(
        {ApiCall(method="DELETE", path_template="/api/orders/{id}", status_class="2xx")}
    )


def test_verifier_rejects_cancel_standing_in_for_confirm(page: Page, store: LiveStore) -> None:
    """End to end for 6.1: baseline = Confirm's recorded effect (2 observations);
    the sandbox runs both buttons; only the true target passes."""
    from healwright.recorder.contract import merge
    from healwright.verify.compare import compare

    b = store.base_url
    prefix: list[PrefixStep] = [
        GotoStep(f"{b}/product/2", {}),
        act("click", "#add-to-cart"),
        GotoStep(f"{b}/checkout", {}),
        act("fill", "#full-name", "Ada"),
        act("fill", "#email", "ada@example.com"),
        act("check", "#agree"),
        act("click", "#place-order"),
    ]
    browser = page.context.browser
    first = run_candidate(browser, VIEWPORT, prefix, click_by_test_id("confirm-order"))  # type: ignore[arg-type]
    second = run_candidate(browser, VIEWPORT, prefix, click_by_test_id("confirm-order"))  # type: ignore[arg-type]
    assert first.observed is not None
    assert second.observed is not None
    baseline = merge([first.observed, second.observed])
    assert baseline.strength == "strong"

    true_target = run_candidate(browser, VIEWPORT, prefix, click_by_test_id("confirm-order"))  # type: ignore[arg-type]
    lookalike = run_candidate(browser, VIEWPORT, prefix, click_by_test_id("cancel-order"))  # type: ignore[arg-type]
    assert compare(baseline, true_target.observed).outcome == "pass"
    rejected = compare(baseline, lookalike.observed)
    assert rejected.outcome == "fail"
    assert "extra state-changing call: DELETE /api/orders/{id}" in rejected.mismatches


def test_failing_prefix_step_is_inconclusive_and_context_closed(
    page: Page, store: LiveStore
) -> None:
    contexts_before = len(page.context.browser.contexts)  # type: ignore[union-attr]
    prefix: list[PrefixStep] = [GotoStep(f"{store.base_url}/product/1", {}), act("click", "#nope")]
    t0 = time.monotonic()
    run = run_candidate(page.context.browser, VIEWPORT, prefix, click_by_test_id("add-to-cart"))  # type: ignore[arg-type]
    assert run.outcome == "inconclusive"
    assert "prefix step 1 failed" in run.reason
    assert time.monotonic() - t0 < 8  # 5 s per-step replay timeout
    assert len(page.context.browser.contexts) == contexts_before  # type: ignore[union-attr]
    assert ids(store) == []


def test_candidate_that_cannot_be_acted_on_is_inconclusive(page: Page, store: LiveStore) -> None:
    prefix: list[PrefixStep] = [GotoStep(f"{store.base_url}/product/1", {})]
    run = run_candidate(page.context.browser, VIEWPORT, prefix, click_by_test_id("missing"))  # type: ignore[arg-type]
    assert run.outcome == "inconclusive"
    assert "candidate action failed" in run.reason


def test_no_effect_action_settles_quickly(page: Page, store: LiveStore) -> None:
    prefix: list[PrefixStep] = [GotoStep(f"{store.base_url}/", {})]
    spec = SynthesizedLocator("test_id", (LocatorCall("get_by_test_id", ("nav-cart",)),))
    run = run_candidate(page.context.browser, VIEWPORT, prefix, lambda p: spec.build(p).hover())  # type: ignore[arg-type]
    assert run.observed is not None
    assert run.observed.strength == "none"
    assert run.settle_ms < 1000
