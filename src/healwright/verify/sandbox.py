"""Sandbox replay: observe what a candidate action DOES.

1. A new ``BrowserContext`` in the already-running browser, same viewport, no
   shared cookies or storage. The Chaos Store keys state by session
   cookie, so nothing here can touch the real run's cart or orders.
2. Replay the test's own action prefix: every ``goto`` and wrapped action that
   ran before the failure, with the selectors that worked. Any replay step
   failing makes the result ``inconclusive``.
3. Perform the candidate action, then wait for the settle window: no in-flight
   XHR/fetch for 300 ms, capped at 2,000 ms.
4. Build the observed contract with the recorder's own code.
5. Close the context in ``finally``.

Comparison against the baseline contract lives in ``verify.compare`` (6.1).
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from playwright.sync_api import Browser, BrowserContext, Page

from healwright.models import PostConditionSignature
from healwright.plugin.proxy import ActionStep, GotoStep, PrefixStep
from healwright.recorder.contract import NetworkLog, PageState, observe
from healwright.recorder.recorder import page_state

SETTLE_IDLE_S = 0.3
SETTLE_CAP_S = 2.0
STEP_TIMEOUT_MS = 5_000
CREATE_TIMEOUT_S = 10.0

CandidateAction = Callable[[Page], Any]


@dataclass(frozen=True)
class SandboxRun:
    outcome: Literal["observed", "inconclusive"]
    observed: PostConditionSignature | None
    reason: str
    settle_ms: float = 0.0


def replay_step(page: Page, step: PrefixStep) -> None:
    if isinstance(step, GotoStep):
        page.goto(step.url, **step.kwargs)
        return
    assert isinstance(step, ActionStep)
    if step.locator is not None:  # an earlier heal in this test: replay the healed locator
        getattr(step.locator.build(page), step.key.action)(*step.args, **step.kwargs)
    elif step.via == "page":
        getattr(page, step.key.action)(step.selector, *step.args, **step.kwargs)
    else:
        getattr(page.locator(step.selector), step.key.action)(*step.args, **step.kwargs)


def settle(page: Page, net: NetworkLog, started: float, mark: int | None = None) -> float:
    """Wait until no XHR/fetch has been in flight for 300 ms, at most 2 s.
    ``started`` is a ``perf_counter`` value; ``mark`` the log position at the action."""
    start_mark = net.mark() if mark is None else mark
    last_activity = started
    seen = len(net.calls)
    while True:
        now = time.perf_counter()
        if now - started >= SETTLE_CAP_S:
            break
        in_flight = net.in_flight(start_mark)
        if len(net.calls) != seen:
            seen = len(net.calls)
            last_activity = now
        if not in_flight and now - last_activity >= SETTLE_IDLE_S:
            break
        page.wait_for_timeout(50)  # also lets Playwright dispatch pending events
    return (time.perf_counter() - started) * 1000


def stable_state(page: Page) -> PageState:
    """Page state; if a navigation destroys the execution context mid-read,
    wait for the new document and read again (up to 3 attempts)."""
    for _ in range(2):
        try:
            return page_state(page)
        except Exception:  # noqa: BLE001 - e.g. execution context destroyed by a navigation
            page.wait_for_load_state("load", timeout=STEP_TIMEOUT_MS)
    return page_state(page)


def _let_step_finish(page: Page, net: NetworkLog) -> None:
    """After a replayed action: settle its network effect and any navigation it
    caused, as the real test did before its next step (it waited on expect())."""
    settle(page, net, time.perf_counter())
    page.wait_for_load_state("load", timeout=STEP_TIMEOUT_MS)


def run_candidate(
    browser: Browser,
    viewport: dict[str, int] | None,
    prefix: Sequence[PrefixStep],
    action: CandidateAction,
) -> SandboxRun:
    context: BrowserContext | None = None
    try:
        t0 = time.monotonic()
        context = browser.new_context(viewport=viewport, device_scale_factor=1)  # type: ignore[arg-type]
        if time.monotonic() - t0 > CREATE_TIMEOUT_S:
            return SandboxRun("inconclusive", None, "sandbox context took too long to create")
        context.set_default_timeout(STEP_TIMEOUT_MS)
        page = context.new_page()
        net = NetworkLog(page)
        net.attach()
        for i, step in enumerate(prefix):
            try:
                replay_step(page, step)
                if isinstance(step, ActionStep):
                    _let_step_finish(page, net)
            except Exception as exc:  # noqa: BLE001 - any replay failure => inconclusive
                return SandboxRun(
                    "inconclusive", None, f"prefix step {i} failed: {type(exc).__name__}"
                )
        before = stable_state(page)
        mark = net.mark()
        started = time.perf_counter()
        try:
            action(page)
        except Exception as exc:  # noqa: BLE001 - the candidate itself could not be acted on
            return SandboxRun(
                "inconclusive", None, f"candidate action failed: {type(exc).__name__}"
            )
        settle_ms = settle(page, net, started, mark)
        after = stable_state(page)
        calls = net.since(mark, started=started)
        net.detach()
        return SandboxRun("observed", observe(before, after, calls), "observed", settle_ms)
    except Exception as exc:  # noqa: BLE001 - sandbox infrastructure failure => inconclusive
        return SandboxRun("inconclusive", None, f"sandbox error: {type(exc).__name__}")
    finally:
        if context is not None:
            with contextlib.suppress(Exception):  # closing is best effort; the run is over
                context.close()


__all__ = [
    "SETTLE_CAP_S",
    "SETTLE_IDLE_S",
    "CandidateAction",
    "SandboxRun",
    "replay_step",
    "run_candidate",
]
