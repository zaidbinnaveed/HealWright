"""The examples suite is green against the unmutated Chaos Store."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from chaos_store.serve import free_port

pytestmark = [pytest.mark.integration, pytest.mark.slow]

ROOT = Path(__file__).resolve().parents[2]


def run_examples(
    *extra: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    full_env = {**os.environ, "CHAOS_PORT": str(free_port()), **(env or {})}
    full_env.pop("CHAOS_BASE_URL", None)
    full_env.pop("CHAOS_SESSION", None)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "examples", "-q", "-p", "no:cacheprovider", *extra],
        cwd=ROOT,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def passed_count(output: str) -> int:
    match = re.search(r"(\d+) passed", output)
    return int(match.group(1)) if match else 0


def outcomes(output: str) -> dict[str, str]:
    """Per-test outcome from ``-rA`` short summary lines, e.g. 'PASSED examples/x.py::t[chromium]'."""
    found: dict[str, str] = {}
    for line in output.splitlines():
        m = re.match(r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS) (\S+)", line)
        if m:
            found[m.group(2)] = m.group(1)
    return found


@pytest.mark.timeout(320)
def test_examples_suite_is_green_without_healwright() -> None:
    result = run_examples("-p", "no:healwright")
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-2000:]
    assert passed_count(result.stdout) >= 30
    assert " failed" not in result.stdout


@pytest.mark.timeout(600)
def test_examples_identical_with_mode_off_and_record(tmp_path: Path) -> None:
    """Proof: the proxy changes nothing about test outcomes."""
    baselines = tmp_path / "baselines"  # never write into the repo from a test
    off = run_examples("-rA", env={"HEALWRIGHT_MODE": "off"})
    record = run_examples(
        "-rA", env={"HEALWRIGHT_MODE": "record", "HEALWRIGHT_BASELINE_DIR": str(baselines)}
    )
    assert off.returncode == 0, off.stdout[-3000:]
    assert record.returncode == 0, record.stdout[-3000:]
    off_outcomes, record_outcomes = outcomes(off.stdout), outcomes(record.stdout)
    assert len(off_outcomes) >= 30
    assert record_outcomes == off_outcomes
    assert set(off_outcomes.values()) == {"PASSED"}
    # the proxy really was active in record mode, and recorded without errors
    summary = re.search(
        r"HealWright mode=record: (\d+) tests tracked, (\d+) wrapped actions, (\d+) recording errors",
        record.stdout,
    )
    assert summary is not None, record.stdout[-2000:]
    tracked, wrapped, errors = (int(g) for g in summary.groups())
    assert tracked == len(off_outcomes)
    assert wrapped > tracked
    assert errors == 0
    assert "HealWright mode=" not in off.stdout
    # every passing example test got a baseline file (5.4)
    assert len(list(baselines.rglob("*.json"))) == len(off_outcomes)


def test_external_store_and_preassigned_session(store) -> None:  # type: ignore[no-untyped-def]
    """The benchmark runner's hook: use a running store and read ground truth by session."""
    env = {**os.environ, "CHAOS_BASE_URL": store.base_url, "CHAOS_SESSION": "bench-session-0001"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "examples/test_cart.py::test_add_to_cart",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:healwright",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-2000:]
    assert [a["action_id"] for a in store.actions("bench-session-0001")] == ["add_to_cart"]


def test_examples_cover_every_intercepted_action() -> None:
    source = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "examples").glob("test_*.py"))
    for action in ("click", "fill", "check", "uncheck", "press", "select_option", "hover"):
        assert f"page.{action}(" in source, action
    assert ".locator(" in source
    assert 'page.click("//' in source  # XPath selectors
    assert 'page.click("text=' in source  # text selectors
