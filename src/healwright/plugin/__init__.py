"""pytest plugin entry point (``-p healwright``; disable with ``-p no:healwright``).

- ``HEALWRIGHT_MODE=off`` (or ``--healwright-mode off``): nothing is registered;
  plain pytest-playwright behaviour.
- ``record`` / ``heal``: the ``page`` fixture is overridden with a proxy that
  intercepts the action allowlist and tracks the replayable action prefix.
- Under pytest-xdist (``PYTEST_XDIST_WORKER`` set) the plugin disables itself
  with a warning: tests must run serially.
- Invalid configuration disables the plugin with a warning rather than
  breaking the test session (it must never turn green tests red).
"""

from __future__ import annotations

import logging
import os
import warnings
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page

from healwright.config import Settings, load_settings
from healwright.plugin.healer import Healer
from healwright.plugin.proxy import ActionTracker, PageProxy, RunStats
from healwright.recorder.recorder import Recorder
from healwright.store.baselines import record_passing_run
from healwright.store.runs import RunStore

log = logging.getLogger("healwright.plugin")

SETTINGS_KEY = pytest.StashKey[Settings]()
STATS_KEY = pytest.StashKey[RunStats]()
TRACKER_KEY = pytest.StashKey[ActionTracker]()
REPORTS_KEY = pytest.StashKey[dict[str, pytest.TestReport]]()
FIXTURES_PLUGIN_NAME = "healwright-fixtures"


class HealWrightWarning(UserWarning):
    """Configuration-time warnings from HealWright."""


class HealWrightFixtures:
    """Registered at configure time, i.e. after pytest-playwright, so this
    ``page`` overrides pytest-playwright's and receives it as its argument."""

    def __init__(
        self,
        settings: Settings,
        stats: RunStats,
        baseline_root: Path,
        healer: Healer | None = None,
    ) -> None:
        self.settings = settings
        self.stats = stats
        self.baseline_root = baseline_root
        self.healer = healer  # only in heal mode

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_makereport(
        self, item: pytest.Item, call: pytest.CallInfo[None]
    ) -> Generator[None, pytest.TestReport, pytest.TestReport]:
        report = yield
        item.stash.setdefault(REPORTS_KEY, {})[report.when] = report
        return report

    @pytest.fixture
    def page(self, page: Page, request: pytest.FixtureRequest) -> Iterator[Page]:
        node = request.node
        recorder = self._start_recorder(page)
        tracker = ActionTracker(
            test_nodeid=node.nodeid,
            stats=self.stats,
            observers=[recorder] if recorder else (),
            test_file=str(node.path),
            healer=self.healer,
        )
        self.stats.tests_tracked += 1
        node.stash[TRACKER_KEY] = tracker
        yield PageProxy(page, tracker)
        if recorder is not None:
            self._finish_recorder(recorder, node, healed=tracker.healed)

    def _start_recorder(self, page: Page) -> Recorder | None:
        try:
            recorder = Recorder(page)
            recorder.attach()
            return recorder
        except Exception:
            self.stats.recording_errors += 1
            log.warning("healwright: recorder could not start", exc_info=True)
            return None

    def _finish_recorder(self, recorder: Recorder, node: pytest.Item, healed: bool) -> None:
        """Runs in fixture teardown: the call-phase report already exists.
        A healed run NEVER updates baselines (blocks baseline poisoning)."""
        try:
            steps = recorder.finish()
            reports = node.stash.get(REPORTS_KEY, {})
            call = reports.get("call")
            passed = call is not None and call.passed and reports["setup"].passed
            if (
                passed
                and not healed
                and not recorder.incomplete
                and record_passing_run(self.baseline_root, node.nodeid, steps)
            ):
                self.stats.baselines_written += 1
        except Exception:
            self.stats.recording_errors += 1
            log.warning("healwright: could not write baseline for %s", node.nodeid, exc_info=True)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("healwright", "HealWright self-healing selectors")
    group.addoption(
        "--healwright-mode",
        choices=("off", "record", "heal"),
        default=None,
        help="Override HEALWRIGHT_MODE for this run.",
    )


def _warn(config: pytest.Config, message: str) -> None:
    config.issue_config_time_warning(HealWrightWarning(message), stacklevel=2)


def pytest_configure(config: pytest.Config) -> None:
    if os.environ.get("PYTEST_XDIST_WORKER"):
        _warn(config, "HealWright disabled: pytest-xdist workers are not supported; run serially.")
        return
    overrides: dict[str, Any] = {}
    cli_mode = config.getoption("--healwright-mode", default=None)
    if cli_mode:
        overrides["mode"] = cli_mode
    try:
        settings = load_settings(**overrides)
    except Exception as exc:  # noqa: BLE001 - fail closed: bad config disables us, never breaks the run
        _warn(config, f"HealWright disabled: invalid configuration ({type(exc).__name__}).")
        return
    config.stash[SETTINGS_KEY] = settings
    stats = RunStats()
    config.stash[STATS_KEY] = stats
    if settings.mode == "off":
        return
    baseline_root = settings.baseline_dir or (config.rootpath / ".healwright" / "baselines")
    artifact_root = settings.artifact_dir
    if not artifact_root.is_absolute():
        artifact_root = config.rootpath / artifact_root
    from healwright.logs import setup_logging

    setup_logging(artifact_root)  # redacted JSON log; never raises
    healer = None
    if settings.mode == "heal":
        from healwright.tier2.factory import build_picker

        healer = Healer(
            settings,
            Path(baseline_root),
            RunStore(artifact_root),
            stats,
            tier2=build_picker(settings, settings.vlm_cache_dir or (artifact_root / "cache")),
            repo_root=config.rootpath,
        )
    config.pluginmanager.register(
        HealWrightFixtures(settings, stats, Path(baseline_root), healer), FIXTURES_PLUGIN_NAME
    )


def active_settings(config: pytest.Config) -> Settings | None:
    return config.stash.get(SETTINGS_KEY, None)


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: pytest.Config) -> None:
    """Recording counters; in heal mode also heal counts per status and the run folder."""
    settings = config.stash.get(SETTINGS_KEY, None)
    stats = config.stash.get(STATS_KEY, None)
    if settings is None or stats is None or settings.mode == "off":
        return
    terminalreporter.write_sep("-", "HealWright")
    terminalreporter.write_line(
        f"HealWright mode={settings.mode}: {stats.tests_tracked} tests tracked, "
        f"{stats.wrapped_actions} wrapped actions, {stats.recording_errors} recording errors, "
        f"{stats.baselines_written} baseline files written"
    )
    if settings.mode == "heal":
        counts = ", ".join(f"{n} {s}" for s, n in sorted(stats.heal_status.items())) or "none"
        terminalreporter.write_line(f"HealWright heals: {counts}")
        if stats.run_dir:
            terminalreporter.write_line(f"HealWright run folder: {stats.run_dir}")
            report = _write_report(Path(stats.run_dir))
            if report is not None:
                terminalreporter.write_line(f"HealWright report: {report}")


def _write_report(run_dir: Path) -> Path | None:
    """Render the run's HTML report; any failure skips it (never changes an outcome)."""
    try:
        from healwright.report import write_report
        from healwright.store.index import load_run

        info = load_run(run_dir.parent.parent, run_dir.name)
        return write_report(info) if info is not None else None
    except Exception:
        log.warning("healwright: HTML report skipped for %s", run_dir, exc_info=True)
        return None


__all__ = [
    "FIXTURES_PLUGIN_NAME",
    "HealWrightFixtures",
    "HealWrightWarning",
    "active_settings",
    "pytest_addoption",
    "pytest_configure",
    "pytest_terminal_summary",
]

warnings.filterwarnings("default", category=HealWrightWarning)
