"""Engine end to end, in real inner pytest sessions against the Chaos Store."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from chaos_store.scenario import SCENARIO_DIR

pytestmark = [pytest.mark.integration, pytest.mark.slow]

ROOT = Path(__file__).resolve().parents[2]

CONFTEST = """
import os
import httpx
import pytest
from chaos_store.serve import serve_in_thread

@pytest.fixture(scope="session")
def store_url():
    with serve_in_thread() as url:
        scenario = os.environ.get("INNER_SCENARIO")
        if scenario:
            httpx.post(url + "/__chaos/scenario", content=open(scenario, encoding="utf-8").read()).raise_for_status()
        yield url

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, store_url):
    return {**browser_context_args, "base_url": store_url,
            "viewport": {"width": 1280, "height": 800}}

@pytest.fixture(autouse=True)
def _short_default_timeout(context):
    context.set_default_timeout(5000)
"""

TESTS = """
from playwright.sync_api import Page, expect

def test_confirm(page: Page) -> None:
    page.goto("/product/2")
    page.click("#add-to-cart")
    page.goto("/checkout")
    page.fill("#full-name", "Ada Lovelace")
    page.fill("#email", "ada@example.com")
    page.check("#agree")
    page.click("#place-order")
    expect(page).to_have_url("/order/1001")
    page.click("#confirm-order")
    expect(page.locator("#order-status")).to_have_text("Status: Confirmed")
"""

SLOW = """
from playwright.sync_api import Page, expect

def test_slow_button(page: Page) -> None:
    page.set_content(
        "<p id=out></p><script>setTimeout(() => {"
        " const b = document.createElement('button'); b.id = 'late'; b.textContent = 'Late';"
        " b.onclick = () => document.getElementById('out').textContent = 'clicked';"
        " document.body.appendChild(b); }, 3500)</script>"
    )
    page.click("#late")
    expect(page.locator("#out")).to_have_text("clicked")
"""


@pytest.fixture
def inner(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    monkeypatch.setenv("HEALWRIGHT_BASELINE_DIR", str(pytester.path / "baselines"))
    monkeypatch.setenv("HEALWRIGHT_ARTIFACT_DIR", str(pytester.path / "artifacts"))
    monkeypatch.delenv("INNER_SCENARIO", raising=False)
    # Hermetic Tier 2: these sessions run with NO model provider, whatever the outer
    # environment says. CI sets HEALWRIGHT_VLM_MODE=replay, which turns key-less providers
    # into replay stubs (Tier 2 "available", then a cache miss), and a developer may have
    # a key exported. Tier-2 paths are tested in test_tier2_engine.py with a FakeProvider.
    monkeypatch.setenv("HEALWRIGHT_VLM_MODE", "record")
    for key in ("GROQ_API_KEY", "MISTRAL_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(test_flow=TESTS)
    return pytester


def run(
    inner: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, mode: str, scenario: str | None = None
) -> pytest.RunResult:
    monkeypatch.setenv("HEALWRIGHT_MODE", mode)
    if scenario:
        monkeypatch.setenv("INNER_SCENARIO", str(SCENARIO_DIR / "dev" / f"{scenario}.yaml"))
    else:
        monkeypatch.delenv("INNER_SCENARIO", raising=False)
    return inner.runpytest_subprocess("-p", "no:cacheprovider", timeout=300)


def record_twice(inner: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> Path:
    for _ in range(2):
        run(inner, monkeypatch, "record").assert_outcomes(passed=1)
    path = inner.path / "baselines" / "test_flow.py" / "test_confirm[chromium].json"
    assert path.is_file()
    return path


def events(inner: pytest.Pytester) -> list[dict[str, Any]]:
    files = list((inner.path / "artifacts" / "runs").glob("*/events.jsonl"))
    assert len(files) == 1, files
    return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]


def test_heals_id_rename_and_never_touches_the_baseline(
    inner: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = record_twice(inner, monkeypatch)
    before = baseline.read_bytes()
    result = run(inner, monkeypatch, "heal", "dev-02-id-rename")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(
        [
            "*HealWright heals: 1 healed*",
            "*HealWright run folder:*",
            "*HealWright report:*report.html",
        ]
    )
    report_html = next((inner.path / "artifacts" / "runs").iterdir()) / "report.html"
    assert "Healed" in report_html.read_text(encoding="utf-8")
    [event] = events(inner)
    decision = event["decision"]
    assert decision["status"] == "healed"
    assert decision["tier"] == 1
    assert decision["locator"] == "page.get_by_role('button', name='Confirm order', exact=True)"
    assert decision["verification"]["outcome"] == "pass"
    assert event["key"]["selector"] == "#confirm-order"
    assert event["artifacts"] == {
        "before": "before.png",
        "candidates": "candidates.json",
        "patch": "patch.diff",
    }
    run_dir = next((inner.path / "artifacts" / "runs").iterdir())
    report = json.loads(
        (run_dir / "artifacts" / event["id"] / "candidates.json").read_text(encoding="utf-8")
    )
    assert report["gate"]["accepted"] is True
    assert report["gate"]["delta"] == 0.06
    assert 2 <= len(report["candidates"]) <= 5
    assert report["candidates"][0]["fingerprint"]["accessible_name"] == "confirm order"
    assert [a["outcome"] for a in report["attempts"]] == ["pass"]
    assert report["live_check"]["outcome"] == "pass"
    assert len(event["source_sha256"] or "") == 64
    assert '-    page.click("#confirm-order")' in event["diff"]
    assert (
        "+    page.get_by_role('button', name='Confirm order', exact=True).click()" in event["diff"]
    )
    # release-gate invariant 3: the patch is a real fix (applies, then passes natively)
    subprocess.run(
        ["git", "-c", "core.autocrlf=false", "apply", "-"],
        cwd=inner.path,
        input=event["diff"].encode(),
        check=True,
    )
    native = run(inner, monkeypatch, "off", "dev-02-id-rename")
    native.assert_outcomes(passed=1)
    assert set(event["timings_ms"]) >= {
        "classify",
        "baseline",
        "extract",
        "tier1",
        "verify",
        "live",
        "total",
    }
    assert baseline.read_bytes() == before  # a heal never updates a baseline


def test_distractor_without_tier2_stays_red(
    inner: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_twice(inner, monkeypatch)
    result = run(inner, monkeypatch, "heal", "dev-07-distractor")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(
        ["*HealWright: needs human: Tier 1 not confident*Tier 2 unavailable*"]
    )
    [event] = events(inner)
    assert event["decision"]["status"] == "needs_human"


def test_regression_trap_is_rejected_by_the_verifier(
    inner: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G1 showed Tier 1 + gate would accept 'Cancel order' here. The verifier must not."""
    record_twice(inner, monkeypatch)
    result = run(inner, monkeypatch, "heal", "dev-09-regression")
    result.assert_outcomes(failed=1)
    [event] = events(inner)
    decision = event["decision"]
    assert decision["status"] == "regression_suspected"
    assert decision["tier"] == 1
    assert "extra state-changing call: DELETE /api/orders/{id}" in decision["reason"]
    run_dir = next((inner.path / "artifacts" / "runs").iterdir())
    report = json.loads(
        (run_dir / "artifacts" / event["id"] / "candidates.json").read_text(encoding="utf-8")
    )
    # the screen must be able to show the verifier rejecting the look-alike
    assert report["attempts"][0]["label"] == "cancel order"
    assert report["attempts"][0]["outcome"] == "fail"
    assert any("DELETE" in m for m in report["attempts"][0]["mismatches"])
    assert report["live_check"] is None
    result.stdout.fnmatch_lines(["*HealWright: regression suspected*"])


def test_no_baseline_needs_human(inner: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> None:
    result = run(inner, monkeypatch, "heal", "dev-02-id-rename")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*HealWright: needs human: no baseline for this step*"])


def test_corrupt_baseline_fails_closed(
    inner: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = record_twice(inner, monkeypatch)
    baseline.write_text("{truncated", encoding="utf-8")
    result = run(inner, monkeypatch, "heal", "dev-02-id-rename")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*HealWright: error: BASELINE_CORRUPT*"])


def test_green_run_in_heal_mode_has_no_events(
    inner: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_twice(inner, monkeypatch)
    result = run(inner, monkeypatch, "heal")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*HealWright heals: none*"])
    assert not (inner.path / "artifacts" / "runs").exists()


def test_slow_element_is_not_turned_red(
    inner: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 3 s probe expires, but the user's own (5 s) timeout would succeed: so must we."""
    inner.makepyfile(test_flow=SLOW)
    result = run(inner, monkeypatch, "heal")
    result.assert_outcomes(passed=1)
