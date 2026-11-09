"""Failure-mode table: the rows not already covered elsewhere.

Every row of the table has a passing test; this file holds rows 5-8. The others are tested where
the fault lives (see docs/BENCHMARK.md "Failure-mode tests" for the full row-to-test map):

  1 429 repeatedly ........ test_tier2.py::test_429_repeatedly_retries_twice_opens_breaker_and_falls_back,
                            test_tier2_engine.py::test_providers_down_needs_human
  2 provider timeout ...... test_tier2.py::test_timeouts_and_5xx_behave_like_429
  3 bad reply / null mark . test_tier2.py::test_invalid_reply_gets_one_repair_then_next_provider,
                            test_tier2_engine.py::test_tier2_target_absent
  4 invalid key (401) ..... test_tier2.py::test_auth_error_is_never_retried_and_disables_provider
  9 corrupt baseline ...... test_engine.py::test_corrupt_baseline_fails_closed
 10 recorder throws ....... test_plugin_proxy.py::test_recording_errors_are_swallowed_and_counted
 11 edited before apply ... test_api.py::test_apply_source_changed_reports_both_hashes,
                            test_api.py::test_cli_apply_shares_the_checks
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from playwright.sync_api import Page

from chaos_store.scenario import SCENARIO_DIR
from healwright.config import Settings
from healwright.engine import HealRequest, heal
from healwright.plugin.proxy import ActionTracker, PageProxy, RunStats
from healwright.tier2.cache import ResponseCache
from healwright.tier2.picker import VlmPicker
from healwright.tier2.providers import FakeProvider
from healwright.tier2.router import Router
from tests.conftest import LiveStore
from tests.integration.test_engine import CONFTEST, events, inner, record_twice, run  # noqa: F401
from tests.integration.test_tier2_engine import NODE, checkout, new_page, record_baselines

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def test_row5_call_cap_reached_skips_tier2_and_needs_human(
    page: Page, store: LiveStore, tmp_path: Path
) -> None:
    """Per-run call cap reached (cap 0): Tier 2 is skipped, the provider is never called."""
    browser = page.context.browser
    assert browser is not None
    record_baselines(browser, store, tmp_path)
    store.set_scenario(
        (SCENARIO_DIR / "dev" / "dev-07-distractor.yaml").read_text(encoding="utf-8")
    )
    live, _close = new_page(browser, store.base_url)
    tracker = ActionTracker(test_nodeid=NODE, stats=RunStats())
    checkout(PageProxy(live, tracker), store.base_url)
    key = tracker.next_key("click", "#confirm-order")
    assert key is not None
    provider = FakeProvider("ok")
    picker = VlmPicker(Router([provider], ResponseCache(tmp_path / "cache", "live"), run_cap=0))
    outcome = heal(
        HealRequest(
            page=live,
            key=key,
            selector="#confirm-order",
            args=(),
            kwargs={},
            prefix=list(tracker.prefix),
            baseline_root=tmp_path,
            settings=Settings(_env_file=None),  # type: ignore[call-arg]
        ),
        tier2=picker,
    )
    assert outcome.decision.status == "needs_human"
    assert provider.calls == 0


FLAKY_PREFIX = """
import healwright.verify.sandbox as sandbox

def _flaky_replay(page, step):
    raise RuntimeError("injected: prefix step flaked")

sandbox.replay_step = _flaky_replay
"""


def test_row6_prefix_replay_fails_is_suggested_and_stays_red(
    inner: pytest.Pytester,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sandbox prefix replay fails: the candidate is inconclusive, the decision is `suggested`,
    and the test stays red with the original Playwright error."""
    record_twice(inner, monkeypatch)
    inner.makeconftest(CONFTEST + FLAKY_PREFIX)
    result = run(inner, monkeypatch, "heal", "dev-02-id-rename")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*TimeoutError*"])
    [event] = events(inner)
    assert event["decision"]["status"] == "suggested"
    assert event["decision"]["verification"]["outcome"] == "inconclusive"


CLOSE_BROWSER = """
import healwright.engine as engine

_original = engine.run_candidate

def _close_then_run(browser, *args, **kwargs):
    browser.close()
    return _original(browser, *args, **kwargs)

engine.run_candidate = _close_then_run
"""


def test_row7_browser_closed_mid_heal_reraises_original_error_without_hanging(
    inner: pytest.Pytester,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The browser closes in the middle of a heal: the original error is re-raised, no hang."""
    monkeypatch.setenv(
        "PYTHONIOENCODING", "utf-8"
    )  # Playwright's closed-target message is not cp1252-safe
    record_twice(inner, monkeypatch)
    inner.makeconftest(CONFTEST + CLOSE_BROWSER)
    t0 = time.monotonic()
    result = run(inner, monkeypatch, "heal", "dev-02-id-rename")
    assert time.monotonic() - t0 < 120  # pytest-timeout (60 s per item) would fire long before
    outcomes = result.parseoutcomes()
    assert outcomes.get("failed") == 1
    assert "passed" not in outcomes
    result.stdout.fnmatch_lines(
        [
            "*TimeoutError: PageProxy.click: Timeout*",
            "*Call log:*",
            '*waiting for locator("#confirm-order")*',
        ]
    )
    assert "TargetClosedError: PageProxy.click" not in result.stdout.str()  # not the retry's error
    assert "Timeout >" not in result.stdout.str()  # pytest-timeout did not have to kill it


def test_row8_run_folder_not_writable_is_logged_and_outcome_unchanged(
    inner: pytest.Pytester,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run folder cannot be written: logged, and the test outcome is what it would be."""
    record_twice(inner, monkeypatch)
    blocked = inner.path / "artifacts-blocked"
    blocked.write_text("a file where the run folder should be", encoding="utf-8")
    monkeypatch.setenv("HEALWRIGHT_ARTIFACT_DIR", str(blocked))
    monkeypatch.setenv("HEALWRIGHT_MODE", "heal")
    monkeypatch.setenv("INNER_SCENARIO", str(SCENARIO_DIR / "dev" / "dev-02-id-rename.yaml"))
    result = inner.runpytest_subprocess(
        "-p", "no:cacheprovider", "-o", "log_cli=true", "--log-cli-level=WARNING", timeout=300
    )
    result.assert_outcomes(passed=1)  # dev-02 heals, exactly as with a writable folder
    result.stdout.fnmatch_lines(["*healwright: could not write*"])
    assert blocked.is_file()
