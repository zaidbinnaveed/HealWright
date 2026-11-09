"""Page and Locator proxies that intercept an explicit allowlist of actions.

Intercepted (selector form): ``page.click/fill/check/uncheck/press/
select_option/hover`` and the same seven actions on ``page.locator(selector)``.
Everything else is Playwright's own code, untouched.

The proxies SUBCLASS ``Page``/``Locator`` and share the wrapped object's
internal state, instead of delegating through ``__getattr__``. Reason:
``expect(page)`` and ``expect(page.locator(...))`` check ``isinstance`` and
reject any other type, so a plain delegating proxy would break every
assertion. Any method not overridden here is the real Playwright method
operating on the same underlying page.

Recording never raises: tracker bookkeeping errors are swallowed, logged and
counted. Errors raised by the user's action itself propagate unchanged (the
heal engine hooks in at Phase 2).
"""

from __future__ import annotations

import logging
import os
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from types import FrameType
from typing import Any, Literal, Protocol, TypeVar

from playwright.sync_api import Locator, Page, Response
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from healwright.locators.synth import SynthesizedLocator
from healwright.models import StepKey

log = logging.getLogger("healwright.plugin")

ALLOWLIST: tuple[str, ...] = (
    "click",
    "fill",
    "check",
    "uncheck",
    "press",
    "select_option",
    "hover",
)
Via = Literal["page", "locator"]
T = TypeVar("T")


@dataclass(frozen=True)
class GotoStep:
    url: str
    kwargs: dict[str, Any]


@dataclass(frozen=True)
class ActionStep:
    """One wrapped action that succeeded, with the selector that worked."""

    key: StepKey
    via: Via
    selector: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    locator: SynthesizedLocator | None = None  # set when the step was healed: replay uses it


PrefixStep = GotoStep | ActionStep


@dataclass
class RunStats:
    """Session-wide counters shown in the terminal summary."""

    wrapped_actions: int = 0
    recording_errors: int = 0
    tests_tracked: int = 0
    baselines_written: int = 0
    heal_status: Counter[str] = field(default_factory=Counter)
    run_dir: str | None = None


class StepObserver(Protocol):
    """Extension point for the recorder (5.4).

    ``before_action`` runs just before each wrapped action (``target`` is a
    plain, non-waiting locator for the step's selector; ``source_line`` is the
    call site in the test file, if found). ``before_goto`` runs just before
    each ``page.goto``. Exceptions raised here are swallowed and counted.
    """

    def before_action(
        self, page: Page, key: StepKey, target: Locator, source_line: int | None
    ) -> None: ...

    def before_goto(self, page: Page) -> None: ...


class StepHealer(Protocol):
    """Extension point for the heal engine (6.2), used only in ``heal`` mode."""

    def probe_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]: ...

    def handle(
        self,
        tracker: ActionTracker,
        page: Page,
        key: StepKey,
        via: Via,
        selector: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        error: PlaywrightTimeoutError,
        retry: Callable[[], Any],
    ) -> Any: ...


def _without_timeout(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in kwargs.items() if k != "timeout"}


@dataclass
class ActionTracker:
    """Per-test state: step identities and the replayable action prefix."""

    test_nodeid: str
    stats: RunStats
    observers: Sequence[StepObserver] = ()
    test_file: str | None = None  # absolute path of the test module, for call-site lines
    healer: StepHealer | None = None
    healed: bool = False  # a heal happened: this run must never update baselines
    heals_used: int = 0
    prefix: list[PrefixStep] = field(default_factory=list)
    _occurrences: Counter[tuple[str, str]] = field(default_factory=Counter)

    def _safe(self, what: str, fn: Callable[[], object]) -> None:
        try:
            fn()
        except Exception:  # recording must never turn a green test red
            self.stats.recording_errors += 1
            log.warning("healwright: recording error during %s", what, exc_info=True)

    def next_key(self, action: str, selector: str) -> StepKey | None:
        n = self._occurrences[(action, selector)]
        self._occurrences[(action, selector)] = n + 1
        try:
            return StepKey.model_validate(
                {
                    "test_nodeid": self.test_nodeid,
                    "action": action,
                    "selector": selector,
                    "occurrence": n,
                }
            )
        except Exception:
            self.stats.recording_errors += 1
            log.warning("healwright: cannot build step key for %r", selector, exc_info=True)
            return None

    def run(
        self,
        page: Page,
        via: Via,
        action: str,
        selector: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        invoke: Callable[[dict[str, Any]], T],
    ) -> T:
        key = self.next_key(action, selector)
        if key is not None and self.observers:
            self._notify_before(page, key, selector, self.call_site_line())
        if self.healer is not None and key is not None:
            try:
                result = invoke(self.healer.probe_kwargs(kwargs))
            except PlaywrightTimeoutError as error:
                # heal, or retry with the user's own timeout, or re-raise with a note;
                # the healer records the prefix step itself when it succeeds
                healed: T = self.healer.handle(
                    self, page, key, via, selector, args, kwargs, error, lambda: invoke(kwargs)
                )
                self.stats.wrapped_actions += 1
                return healed
        else:
            result = invoke(kwargs)  # the user's action: its errors propagate unchanged
        self.stats.wrapped_actions += 1
        if key is not None:
            step = ActionStep(key, via, selector, args, _without_timeout(kwargs))
            self._safe("prefix", lambda: self.prefix.append(step))
        return result

    def call_site_line(self) -> int | None:
        """Line of the innermost frame in the test module (the action's call site)."""
        if not self.test_file:
            return None
        target = os.path.normcase(os.path.abspath(self.test_file))
        frame: FrameType | None = sys._getframe(1)
        while frame is not None:
            if os.path.normcase(os.path.abspath(frame.f_code.co_filename)) == target:
                return frame.f_lineno
            frame = frame.f_back
        return None

    def _notify_before(self, page: Page, key: StepKey, selector: str, line: int | None) -> None:
        for obs in self.observers:

            def call(o: StepObserver = obs) -> None:
                o.before_action(page, key, Page.locator(page, selector), line)

            self._safe("before_action", call)

    def before_goto(self, page: Page) -> None:
        for obs in self.observers:

            def call(o: StepObserver = obs) -> None:
                o.before_goto(page)

            self._safe("before_goto", call)

    def record_goto(self, url: str, kwargs: dict[str, Any]) -> None:
        self._safe("goto", lambda: self.prefix.append(GotoStep(url, _without_timeout(kwargs))))


def _adopt(proxy: Any, original: Any) -> None:
    """Make ``proxy`` share ``original``'s Playwright wrapper state."""
    proxy.__dict__.update(original.__dict__)


class PageProxy(Page):
    """A ``Page`` whose allowlisted selector actions go through the tracker."""

    def __init__(self, page: Page, tracker: ActionTracker) -> None:  # no super().__init__
        _adopt(self, page)
        self._hw_page = page
        self._hw_tracker = tracker

    @property
    def healwright_tracker(self) -> ActionTracker:
        return self._hw_tracker

    # ---------------------------------------------------------------- pass-through + tracking
    def goto(self, url: str, **kwargs: Any) -> Response | None:
        self._hw_tracker.before_goto(self)
        response = Page.goto(self, url, **kwargs)
        self._hw_tracker.record_goto(Page.url.fget(self), kwargs)  # type: ignore[attr-defined]
        return response

    def locator(self, selector: str, **kwargs: Any) -> Locator:
        loc = Page.locator(self, selector, **kwargs)
        if kwargs:  # has=/has_text= etc.: not an intercepted form, return Playwright's own
            return loc
        return LocatorProxy(loc, selector, self, self._hw_tracker)

    # ---------------------------------------------------------------- intercepted actions
    def _run(
        self, action: str, selector: str, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        method = getattr(Page, action)
        return self._hw_tracker.run(
            self,
            "page",
            action,
            selector,
            args,
            kwargs,
            lambda kw: method(self, selector, *args, **kw),
        )

    def click(self, selector: str, **kwargs: Any) -> None:
        self._run("click", selector, (), kwargs)

    def fill(self, selector: str, value: str, **kwargs: Any) -> None:
        self._run("fill", selector, (value,), kwargs)

    def check(self, selector: str, **kwargs: Any) -> None:
        self._run("check", selector, (), kwargs)

    def uncheck(self, selector: str, **kwargs: Any) -> None:
        self._run("uncheck", selector, (), kwargs)

    def press(self, selector: str, key: str, **kwargs: Any) -> None:
        self._run("press", selector, (key,), kwargs)

    def select_option(self, selector: str, value: Any = None, **kwargs: Any) -> list[str]:
        args = () if value is None else (value,)
        result: list[str] = self._run("select_option", selector, args, kwargs)
        return result

    def hover(self, selector: str, **kwargs: Any) -> None:
        self._run("hover", selector, (), kwargs)


class LocatorProxy(Locator):
    """A ``page.locator(selector)`` whose allowlisted actions go through the tracker."""

    def __init__(
        self, locator: Locator, selector: str, page: Page, tracker: ActionTracker
    ) -> None:  # no super().__init__
        _adopt(self, locator)
        self._hw_selector = selector
        self._hw_page = page
        self._hw_tracker = tracker

    def _run(self, action: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        method = getattr(Locator, action)
        return self._hw_tracker.run(
            self._hw_page,
            "locator",
            action,
            self._hw_selector,
            args,
            kwargs,
            lambda kw: method(self, *args, **kw),
        )

    def click(self, **kwargs: Any) -> None:
        self._run("click", (), kwargs)

    def fill(self, value: str, **kwargs: Any) -> None:
        self._run("fill", (value,), kwargs)

    def check(self, **kwargs: Any) -> None:
        self._run("check", (), kwargs)

    def uncheck(self, **kwargs: Any) -> None:
        self._run("uncheck", (), kwargs)

    def press(self, key: str, **kwargs: Any) -> None:
        self._run("press", (key,), kwargs)

    def select_option(self, value: Any = None, **kwargs: Any) -> list[str]:
        args = () if value is None else (value,)
        result: list[str] = self._run("select_option", args, kwargs)
        return result

    def hover(self, **kwargs: Any) -> None:
        self._run("hover", (), kwargs)


__all__ = [
    "ALLOWLIST",
    "ActionStep",
    "ActionTracker",
    "GotoStep",
    "LocatorProxy",
    "PageProxy",
    "PrefixStep",
    "RunStats",
    "StepHealer",
    "StepObserver",
]
