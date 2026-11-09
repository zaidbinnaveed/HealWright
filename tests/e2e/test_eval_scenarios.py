"""Every EVAL scenario really breaks its referenced test natively (slow: ~8 min).

Run: uv run pytest -m e2e tests/e2e/test_eval_scenarios.py
"""

from __future__ import annotations

import pytest

from chaos_store.scenario import Scenario
from tests.conftest import LiveStore
from tests.integration.test_scenarios import EVAL, check_breaks_natively

pytestmark = [pytest.mark.e2e, pytest.mark.slow]


@pytest.mark.timeout(180)
@pytest.mark.parametrize("scenario", EVAL, ids=lambda s: s.id)
def test_eval_scenario_breaks_its_test_natively(store: LiveStore, scenario: Scenario) -> None:
    check_breaks_natively(store, scenario)
