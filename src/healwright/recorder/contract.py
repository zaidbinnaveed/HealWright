"""Post-condition contracts: observation and merging.

A step's contract is what happened between its action and the next boundary
(next wrapped action, next goto, or test end), capped at 2 s: same-origin
XHR/fetch calls, the URL route before/after, and the sign of the change in
rendered dialogs and DOM node count. Nothing here waits: green runs pay no
settle window.

Merging keeps the STABLE INTERSECTION of the last observations, which filters
analytics and polling noise. A step seen only once is capped at ``weak``.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from playwright.sync_api import Page, Request, Response

from healwright.models import ApiCall, PostConditionSignature
from healwright.verify.normalize import same_origin, template_url

WINDOW_CAP_S = 2.0
MAX_HISTORY = 3
Sign = Literal[-1, 0, 1]
StatusClass = Literal["2xx", "3xx", "4xx", "5xx", "failed", "unknown"]


def sign(value: int) -> Sign:
    return 1 if value > 0 else -1 if value < 0 else 0


def status_class(status: int | None, failed: bool = False) -> StatusClass:
    if failed:
        return "failed"
    if status is None:
        return "unknown"
    if 200 <= status < 300:
        return "2xx"
    if 300 <= status < 400:
        return "3xx"
    if 400 <= status < 500:
        return "4xx"
    if 500 <= status < 600:
        return "5xx"
    return "unknown"


@dataclass(frozen=True)
class PageState:
    url: str
    nodes: int
    modals: int


@dataclass
class _Call:
    t: float
    method: str
    url: str
    status: int | None = None
    failed: bool = False


@dataclass
class NetworkLog:
    """Same-origin XHR/fetch calls, in the order Playwright dispatches them.

    Steps are delimited by POSITIONS in this append-only log (``mark()``), not by
    clock values: Windows' monotonic clock ticks every ~15.6 ms, so two events in
    the same tick compare equal and a call could fall out of its window.
    ``perf_counter`` timestamps are kept only for the 2 s window cap.
    """

    page: Page
    calls: list[_Call] = field(default_factory=list)
    _by_request: dict[int, _Call] = field(default_factory=dict)

    def attach(self) -> None:
        self.page.on("request", self._on_request)
        self.page.on("response", self._on_response)
        self.page.on("requestfailed", self._on_failed)

    def detach(self) -> None:
        for event, fn in (
            ("request", self._on_request),
            ("response", self._on_response),
            ("requestfailed", self._on_failed),
        ):
            with contextlib.suppress(Exception):  # page may already be closed
                self.page.remove_listener(event, fn)

    def _on_request(self, request: Request) -> None:
        if request.resource_type not in ("xhr", "fetch"):
            return
        if not same_origin(request.url, self.page.url):
            return
        call = _Call(time.perf_counter(), request.method.upper(), request.url)
        self.calls.append(call)
        self._by_request[id(request)] = call

    def _on_response(self, response: Response) -> None:
        call = self._by_request.get(id(response.request))
        if call is not None:
            call.status = response.status

    def _on_failed(self, request: Request) -> None:
        call = self._by_request.get(id(request))
        if call is not None:
            call.failed = True

    def mark(self) -> int:
        """Position of the next call; boundaries are positions, not timestamps."""
        return len(self.calls)

    def in_flight(self, start: int) -> bool:
        return any(c.status is None and not c.failed for c in self.calls[start:])

    def since(
        self, start: int, end: int | None = None, started: float | None = None
    ) -> frozenset[ApiCall]:
        """Calls logged between two marks; with ``started`` (a ``perf_counter``
        value), only those dispatched within the 2 s window after it."""
        window = self.calls[start:end]
        if started is not None:
            window = [c for c in window if c.t - started <= WINDOW_CAP_S]
        return frozenset(
            ApiCall(
                method=c.method,
                path_template=template_url(c.url),
                status_class=status_class(c.status, c.failed),
            )
            for c in window
        )


def strength_of(
    url_before: str, url_after: str, api_calls: frozenset[ApiCall], modal_delta: int, dom_sign: int
) -> Literal["strong", "weak", "none"]:
    if url_before != url_after or api_calls:
        return "strong"
    if modal_delta != 0 or dom_sign != 0:
        return "weak"
    return "none"


def observe(
    before: PageState, after: PageState, calls: frozenset[ApiCall]
) -> PostConditionSignature:
    """One raw observation (``observations=1``, so at most ``weak`` after merging)."""
    url_before, url_after = template_url(before.url), template_url(after.url)
    modal_delta = sign(after.modals - before.modals)
    dom_sign = sign(after.nodes - before.nodes)
    return PostConditionSignature(
        url_before=url_before,
        url_after=url_after,
        api_calls=calls,
        modal_delta=modal_delta,
        dom_delta_sign=dom_sign,
        strength=strength_of(url_before, url_after, calls, modal_delta, dom_sign),
        observations=1,
    )


def merge(history: Sequence[PostConditionSignature]) -> PostConditionSignature:
    """Stable intersection of the last ``MAX_HISTORY`` observations.

    - API calls: only those present in every observation.
    - URL after, modal delta, DOM sign: kept only if identical in every
      observation; otherwise they fall back to "no change" so they can never
      be the reason a heal is accepted.
    - Strength recomputed from what is stable, then capped at ``weak`` when
      only one observation exists.
    """
    recent = list(history)[-MAX_HISTORY:]
    if not recent:
        raise ValueError("merge() needs at least one observation")
    first = recent[0]
    calls = frozenset.intersection(*(frozenset(o.api_calls) for o in recent))
    url_before = first.url_before
    stable_urls = all(
        o.url_before == first.url_before and o.url_after == first.url_after for o in recent
    )
    url_after = first.url_after if stable_urls else url_before  # unstable => no URL change
    modal: Sign = (
        first.modal_delta if all(o.modal_delta == first.modal_delta for o in recent) else 0
    )
    dom: Sign = (
        first.dom_delta_sign if all(o.dom_delta_sign == first.dom_delta_sign for o in recent) else 0
    )
    strength = strength_of(url_before, url_after, calls, modal, dom)
    if len(recent) == 1 and strength == "strong":
        strength = "weak"
    return PostConditionSignature(
        url_before=url_before,
        url_after=url_after,
        api_calls=calls,
        modal_delta=modal,
        dom_delta_sign=dom,
        strength=strength,
        observations=len(recent),
    )


def raw_state(data: dict[str, Any], url: str) -> PageState:
    return PageState(url=url, nodes=int(data.get("nodes", 0)), modals=int(data.get("modals", 0)))


__all__ = [
    "MAX_HISTORY",
    "WINDOW_CAP_S",
    "NetworkLog",
    "PageState",
    "merge",
    "observe",
    "raw_state",
    "sign",
    "status_class",
    "strength_of",
]
