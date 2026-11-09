"""A click wrapped in ``page.expect_response`` must still heal.

The waiter's timeout starts when the ``with`` block is entered, so a heal (3 s probe
plus Tier 1, sandbox and live re-check) must finish before it expires. This runs the
benchmark harness (same 5 s action timeout as every benchmark run) on a FIXTURE
scenario: dev-01's id_rename mutation applied to a test whose Add-to-cart click is
wrapped. No dev or eval scenario file is used or changed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmark.run import run_scenario
from chaos_store.scenario import Scenario
from chaos_store.serve import serve_in_thread

pytestmark = [pytest.mark.integration, pytest.mark.slow]

WRAPPED = Scenario.model_validate(
    {
        "id": "fixture-wrapped-add-to-cart",
        "class": "id_rename",
        "test": "examples/test_checkout.py::test_place_order",
        "mutation": {
            "id_map": {"add_to_cart_btn": "btn-add-basket-x7"},
            "testid_map": {"add_to_cart_btn": "add-basket"},
        },
        "expected": {"outcome": "healed", "action_id": "add_to_cart"},
    }
)


def test_wrapped_test_really_waits_on_the_click() -> None:
    source = Path("examples/test_checkout.py").read_text(encoding="utf-8")
    body = source.split("def test_place_order(", 1)[1].split("\ndef ", 1)[0]
    assert "with page.expect_response(" in body
    assert 'page.click("#add-to-cart")' in body


@pytest.mark.timeout(300)
def test_click_inside_expect_response_heals_under_the_benchmark_timeout(tmp_path: Path) -> None:
    with serve_in_thread(control=True) as store:
        row = run_scenario(WRAPPED, "healwright", store, tmp_path, {}, "replay", 0)
    assert row["outcome"] == "true_heal", row
    healed = [e for e in row["events"] if e["status"] == "healed"]
    assert len(healed) == 1, row
    assert healed[0]["patch"] == "ok", row
