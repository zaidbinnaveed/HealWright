"""Recorder + baselines end to end, in real inner pytest sessions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

ROOT = Path(__file__).resolve().parents[2]

CONFTEST = """
import pytest
from chaos_store.serve import serve_in_thread

@pytest.fixture(scope="session")
def store_url():
    with serve_in_thread() as url:
        yield url

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, store_url):
    return {**browser_context_args, "base_url": store_url,
            "viewport": {"width": 1280, "height": 800}}
"""

TESTS = """
from playwright.sync_api import Page, expect

def test_cart_flow(page: Page) -> None:
    page.goto("/product/1")
    page.click("#add-to-cart")
    expect(page.locator("#added-modal")).to_be_visible()
    page.click("#continue-shopping")
    expect(page.locator("#added-modal")).to_be_hidden()
    page.goto("/cart")
    page.locator("#remove-1").click()
    expect(page.locator("#cart-empty")).to_be_visible()

def test_fails_after_click(page: Page) -> None:
    page.goto("/product/2")
    page.click("#add-to-cart")
    assert False, "deliberate failure"
"""


@pytest.fixture
def inner(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    monkeypatch.setenv("HEALWRIGHT_MODE", "record")
    monkeypatch.setenv("HEALWRIGHT_BASELINE_DIR", str(pytester.path / "baselines"))
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(test_flow=TESTS)
    return pytester


def run(inner: pytest.Pytester) -> pytest.RunResult:
    result = inner.runpytest_subprocess("-p", "no:cacheprovider", timeout=180)
    result.assert_outcomes(passed=1, failed=1)
    return result


def steps(inner: pytest.Pytester) -> list[dict[str, Any]]:
    path = inner.path / "baselines" / "test_flow.py" / "test_cart_flow[chromium].json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["test_nodeid"] == "test_flow.py::test_cart_flow[chromium]"
    return [s["baseline"] for s in data["steps"]]


def summary(result: pytest.RunResult) -> str:
    return next(line for line in result.outlines if "HealWright mode=record" in line)


CLICK_THEN_GOTO = """
from playwright.sync_api import Page, expect

def test_click_then_goto(page: Page) -> None:
    page.goto("/product/3")
    page.click("#add-to-cart")
    page.goto("/cart")  # no wait between: the fetch is still in flight at this boundary
    expect(page.locator("#cart-items > li")).to_have_count(1)
"""


def test_effect_of_click_immediately_followed_by_goto_is_kept(inner: pytest.Pytester) -> None:
    inner.makepyfile(test_flow=CLICK_THEN_GOTO)
    for _ in range(2):
        inner.runpytest_subprocess("-p", "no:cacheprovider", timeout=180).assert_outcomes(passed=1)
    path = inner.path / "baselines" / "test_flow.py" / "test_click_then_goto[chromium].json"
    data = json.loads(path.read_text(encoding="utf-8"))
    [step] = [s["baseline"] for s in data["steps"]]
    assert step["contract"]["api_calls"] == [
        {"method": "POST", "path_template": "/api/cart", "status_class": "2xx"}
    ]
    assert step["contract"]["strength"] == "strong"


def test_baselines_only_for_passing_tests_and_strengthen(inner: pytest.Pytester) -> None:
    first = run(inner)
    assert "0 recording errors, 1 baseline files written" in summary(first)
    files = sorted(p.name for p in (inner.path / "baselines").rglob("*.json"))
    assert files == ["test_cart_flow[chromium].json"]  # the failing test wrote nothing

    b = steps(inner)
    assert [(s["key"]["action"], s["key"]["selector"]) for s in b] == [
        ("click", "#add-to-cart"),
        ("click", "#continue-shopping"),
        ("click", "#remove-1"),
    ]
    add, cont, remove = b
    # fingerprint, normalised
    fp = add["fingerprint"]
    assert (fp["role"], fp["accessible_name"], fp["text"], fp["tag"]) == (
        "button",
        "add to cart",
        "add to cart",
        "button",
    )
    assert fp["attributes"]["id"] == "add-to-cart"
    assert fp["viewport"] == [1280, 800]
    # call site in the inner file (makepyfile strips the leading newline: click is line 5)
    assert add["source_line"] == 5
    # contracts after ONE observation: capped at weak
    assert add["contract"]["api_calls"] == [
        {"method": "POST", "path_template": "/api/cart", "status_class": "2xx"}
    ]
    assert add["contract"]["modal_delta"] == 1
    assert add["contract"]["url_before"] == add["contract"]["url_after"] == "/product/{id}"
    assert add["contract"]["strength"] == "weak"
    assert cont["contract"]["api_calls"] == []
    assert cont["contract"]["modal_delta"] == -1
    assert remove["contract"]["api_calls"] == [
        {"method": "DELETE", "path_template": "/api/cart/{id}", "status_class": "2xx"}
    ]
    assert remove["contract"]["url_before"] == "/cart"

    second = run(inner)
    assert "1 baseline files written" in summary(second)
    add2, cont2, remove2 = steps(inner)
    assert add2["contract"]["strength"] == "strong"
    assert add2["contract"]["observations"] == 2
    assert cont2["contract"]["strength"] == "weak"  # modal only
    assert remove2["contract"]["strength"] == "strong"

    run(inner)  # third observation
    path = inner.path / "baselines" / "test_flow.py" / "test_cart_flow[chromium].json"
    before = path.read_bytes()
    fourth = run(inner)
    assert "0 baseline files written" in summary(fourth)  # stable content: no rewrite
    assert path.read_bytes() == before
