"""Page/Locator proxy: every allowlisted method, pass-through, fail-safe recording."""

from __future__ import annotations

from typing import Any

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page, expect

from healwright.models import StepKey
from healwright.plugin.proxy import (
    ALLOWLIST,
    ActionStep,
    ActionTracker,
    GotoStep,
    LocatorProxy,
    PageProxy,
    RunStats,
)

pytestmark = pytest.mark.integration

NODE = "tests/x.py::test_y"

FORM = """
<form onsubmit="return false">
  <label for="name">Name</label><input id="name">
  <input id="agree" type="checkbox">
  <select id="size"><option value="s">S</option><option value="m">M</option></select>
  <button id="go" onclick="document.getElementById('out').textContent = 'clicked ' + (++window.n)">Go</button>
  <span id="hov" onmouseover="this.textContent='hovered'">hover me</span>
  <p id="out"></p>
</form>
<script>window.n = 0;</script>
"""


def make(page: Page, observers: Any = ()) -> tuple[PageProxy, ActionTracker]:
    tracker = ActionTracker(test_nodeid=NODE, stats=RunStats(), observers=observers)
    proxy = PageProxy(page, tracker)
    proxy.set_content(FORM)
    return proxy, tracker


def actions(tracker: ActionTracker) -> list[tuple[str, str, int, str]]:
    return [
        (s.key.action, s.key.selector, s.key.occurrence, s.via)
        for s in tracker.prefix
        if isinstance(s, ActionStep)
    ]


def test_proxies_are_real_playwright_types(page: Page) -> None:
    proxy, _ = make(page)
    assert isinstance(proxy, Page)
    loc = proxy.locator("#go")
    assert isinstance(loc, LocatorProxy)
    assert isinstance(loc, Locator)
    expect(proxy.locator("#go")).to_have_text("Go")  # expect() accepts the proxies
    expect(proxy).to_have_title("")


def test_every_allowlisted_page_method(page: Page) -> None:
    proxy, tracker = make(page)
    proxy.fill("#name", "Ada")
    proxy.press("#name", "End")
    proxy.check("#agree")
    proxy.uncheck("#agree")
    proxy.check("#agree")
    assert proxy.select_option("#size", "m") == ["m"]
    proxy.hover("#hov")
    proxy.click("#go")
    expect(page.locator("#name")).to_have_value("Ada")
    expect(page.locator("#agree")).to_be_checked()
    expect(page.locator("#size")).to_have_value("m")
    expect(page.locator("#hov")).to_have_text("hovered")
    expect(page.locator("#out")).to_have_text("clicked 1")
    assert actions(tracker) == [
        ("fill", "#name", 0, "page"),
        ("press", "#name", 0, "page"),
        ("check", "#agree", 0, "page"),
        ("uncheck", "#agree", 0, "page"),
        ("check", "#agree", 1, "page"),  # occurrence counts repeats of (action, selector)
        ("select_option", "#size", 0, "page"),
        ("hover", "#hov", 0, "page"),
        ("click", "#go", 0, "page"),
    ]
    assert {a for a, *_ in actions(tracker)} == set(ALLOWLIST)
    fill = tracker.prefix[0]
    assert isinstance(fill, ActionStep)
    assert fill.args == ("Ada",)
    assert fill.key == StepKey(test_nodeid=NODE, action="fill", selector="#name", occurrence=0)


def test_every_allowlisted_locator_method(page: Page) -> None:
    proxy, tracker = make(page)
    proxy.locator("#name").fill("Grace")
    proxy.locator("#name").press("End")
    agree = proxy.locator("#agree")
    agree.check()
    agree.uncheck()
    assert proxy.locator("#size").select_option("s") == ["s"]
    proxy.locator("#hov").hover()
    go = proxy.locator("#go")
    go.click()
    go.click()
    expect(page.locator("#out")).to_have_text("clicked 2")
    assert actions(tracker) == [
        ("fill", "#name", 0, "locator"),
        ("press", "#name", 0, "locator"),
        ("check", "#agree", 0, "locator"),
        ("uncheck", "#agree", 0, "locator"),
        ("select_option", "#size", 0, "locator"),
        ("hover", "#hov", 0, "locator"),
        ("click", "#go", 0, "locator"),
        ("click", "#go", 1, "locator"),
    ]


def test_page_and_locator_forms_share_occurrence_counter(page: Page) -> None:
    proxy, tracker = make(page)
    proxy.click("#go")
    proxy.locator("#go").click()
    assert [o for _, _, o, _ in actions(tracker)] == [0, 1]


def test_non_allowlisted_api_passes_through_untracked(page: Page) -> None:
    proxy, tracker = make(page)
    by_role = proxy.get_by_role("button", name="Go")
    assert type(by_role) is Locator  # get_by_* is not intercepted
    by_role.click()
    filtered = proxy.locator("button", has_text="Go")
    assert type(filtered) is Locator  # locator(..., has_text=) is not intercepted
    filtered.click()
    chained = proxy.locator("form").locator("#go")
    assert type(chained) is Locator
    chained.dblclick()
    assert proxy.evaluate("1 + 1") == 2
    assert proxy.locator("#go").text_content() == "Go"
    assert actions(tracker) == []
    expect(page.locator("#out")).to_have_text("clicked 4")


def test_goto_is_tracked_for_replay(page: Page) -> None:
    tracker = ActionTracker(test_nodeid=NODE, stats=RunStats())
    proxy = PageProxy(page, tracker)
    proxy.goto("data:text/html,<button id=b>b</button>", wait_until="load", timeout=5000)
    proxy.click("#b")
    assert isinstance(tracker.prefix[0], GotoStep)
    assert tracker.prefix[0].url.startswith("data:text/html")
    assert tracker.prefix[0].kwargs == {"wait_until": "load"}  # timeout is not replayed
    assert isinstance(tracker.prefix[1], ActionStep)


def test_action_errors_propagate_unchanged_and_are_not_in_prefix(page: Page) -> None:
    proxy, tracker = make(page)
    with pytest.raises(PlaywrightError) as raw:
        page.click("#missing", timeout=300)
    with pytest.raises(PlaywrightError) as proxied:
        proxy.click("#missing", timeout=300)
    assert type(proxied.value) is type(raw.value)
    assert not getattr(proxied.value, "__notes__", None)
    assert actions(tracker) == []
    # the failed attempt still consumed occurrence 0 of (click, #missing)
    following = tracker.next_key("click", "#missing")
    assert following is not None
    assert following.occurrence == 1


class ExplodingObserver:
    def before_action(
        self, page: Page, key: StepKey, target: Locator, source_line: int | None
    ) -> None:
        raise RuntimeError("recorder bug before action")

    def before_goto(self, page: Page) -> None:
        raise RuntimeError("recorder bug before goto")


def test_recording_errors_are_swallowed_and_counted(page: Page) -> None:
    proxy, tracker = make(page, observers=[ExplodingObserver()])
    proxy.goto("data:text/html,<button id=go onclick=\"this.textContent='ok'\">go</button>")
    proxy.click("#go")
    expect(page.locator("#go")).to_have_text("ok")
    assert tracker.stats.recording_errors == 2
    assert tracker.stats.wrapped_actions == 1
    assert len(actions(tracker)) == 1


def test_observer_sees_target_and_call_site_before_action(page: Page) -> None:
    seen: list[tuple[object, ...]] = []

    class Spy:
        def before_action(
            self, page: Page, key: StepKey, target: Locator, source_line: int | None
        ) -> None:
            seen.append(
                ("action", target.count(), page.locator("#out").text_content(), source_line)
            )

        def before_goto(self, page: Page) -> None:
            seen.append(("goto", page.url))

    tracker = ActionTracker(
        test_nodeid=NODE, stats=RunStats(), observers=[Spy()], test_file=__file__
    )
    proxy = PageProxy(page, tracker)
    proxy.set_content(FORM)
    import inspect

    line = inspect.currentframe().f_lineno + 1  # type: ignore[union-attr]
    proxy.click("#go")
    proxy.goto("about:blank")
    assert seen == [("action", 1, "", line), ("goto", page.url)]


def test_unbuildable_step_key_does_not_break_the_action(page: Page) -> None:
    proxy, tracker = make(page)
    long_selector = "#go" + ", #go" * 600  # > 2000 chars: StepKey rejects it
    proxy.click(long_selector)
    expect(page.locator("#out")).to_have_text("clicked 1")
    assert tracker.stats.recording_errors == 1
    assert actions(tracker) == []
