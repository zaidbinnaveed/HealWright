"""Recorder: fingerprints and non-blocking contracts.

At each boundary (before a wrapped action, before a ``goto``, at test end) the
recorder makes ONE evaluate that returns the page state and, before an
action, the target element's fingerprint. Step *i*'s contract is built from
the state at its own boundary, the state at the next boundary, and the
same-origin XHR/fetch calls dispatched in between (capped at 2 s).

The boundary timestamp is taken AFTER that evaluate: Playwright dispatches
pending network events during the call, so calls caused by step *i* land in
step *i*'s window, not the next one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from playwright.sync_api import Locator, Page

from healwright.models import ElementFingerprint, StepKey
from healwright.recorder.contract import WINDOW_CAP_S, NetworkLog, PageState, observe, raw_state
from healwright.recorder.extract import extract_js, target_expression
from healwright.recorder.fingerprint import fingerprint_from_row
from healwright.store.baselines import ObservedStep

STATE_ONLY = "() => (\n{js}\n)({{ target: null }})"


def page_state(page: Page) -> PageState:
    """URL, rendered-dialog count and DOM node count, exactly as the recorder sees them.

    Shared with the sandbox verifier so record time and verify time measure state
    with the same code.
    """
    result: dict[str, Any] = page.evaluate(STATE_ONLY.format(js=extract_js()))
    return raw_state(result["state"], page.url)


@dataclass
class _OpenStep:
    key: StepKey
    fingerprint: ElementFingerprint | None
    source_line: int | None
    before: PageState
    started: float  # perf_counter, for the 2 s cap only
    mark: int  # position in the network log where this step began


class Recorder:
    """A ``StepObserver`` that buffers observed steps for one test."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.net = NetworkLog(page)
        self.steps: list[ObservedStep] = []
        self.incomplete = False  # any internal error => this test's run is not written
        self._open: _OpenStep | None = None
        self._state_js = STATE_ONLY.format(js=extract_js())
        self._target_js = target_expression()

    # ------------------------------------------------------------------ lifecycle
    def attach(self) -> None:
        self.net.attach()

    def finish(self) -> list[ObservedStep]:
        """Flush the last step (state at test end) and stop listening."""
        try:
            if self._open is not None and not self.page.is_closed():
                state = self._boundary_state(None)[0]
                self._close(state, self.net.mark())
        except Exception:
            self.incomplete = True
            raise
        finally:
            self.net.detach()
        return list(self.steps)

    # ------------------------------------------------------------------ StepObserver
    def before_action(
        self, page: Page, key: StepKey, target: Locator, source_line: int | None
    ) -> None:
        try:
            state, fingerprint = self._boundary_state(target)
            mark = self.net.mark()  # after the evaluate: pending events are dispatched
            self._close(state, mark)
            self._open = _OpenStep(key, fingerprint, source_line, state, time.perf_counter(), mark)
        except Exception:
            self.incomplete = True
            self._open = None
            raise

    def before_goto(self, page: Page) -> None:
        try:
            if self._open is not None:
                state = self._boundary_state(None)[0]
                self._close(state, self.net.mark())
        except Exception:
            self.incomplete = True
            self._open = None
            raise

    # ------------------------------------------------------------------ internals
    def _in_flight(self) -> bool:
        step = self._open
        return step is not None and self.net.in_flight(step.mark)

    def _boundary_state(
        self, target: Locator | None
    ) -> tuple[PageState, ElementFingerprint | None]:
        """Snapshot at a boundary. If the open step still has XHR/fetch in flight
        (e.g. a click immediately followed by ``goto``), let those calls finish
        first, capped at the 2 s window, so the step's effect is not lost. Green
        runs only pay this when a request is actually in flight."""
        snapshot = self._snapshot(target)  # also dispatches pending network events
        if not self._in_flight():
            return snapshot
        deadline = time.perf_counter() + WINDOW_CAP_S
        while self._in_flight() and time.perf_counter() < deadline:
            self.page.wait_for_timeout(20)
        return self._snapshot(target)

    def _snapshot(self, target: Locator | None) -> tuple[PageState, ElementFingerprint | None]:
        result: dict[str, Any]
        if target is None:
            result = self.page.evaluate(self._state_js)
        else:
            result = target.evaluate_all(self._target_js)
        state = raw_state(result["state"], self.page.url)
        fingerprint = None
        if result["rows"]:
            fingerprint = fingerprint_from_row(result["rows"][0], result["viewport"])
        return state, fingerprint

    def _close(self, after: PageState, end_mark: int) -> None:
        step = self._open
        if step is None:
            return
        self._open = None
        calls = self.net.since(step.mark, end_mark, started=step.started)
        self.steps.append(
            ObservedStep(
                key=step.key,
                fingerprint=step.fingerprint,
                observation=observe(step.before, after, calls),
                source_line=step.source_line,
            )
        )


__all__ = ["Recorder", "page_state"]
