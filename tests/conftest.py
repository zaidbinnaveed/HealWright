"""Shared fixtures: a live Chaos Store served by uvicorn in a background thread.

HealWright's own test suite runs with the plugin OFF by default, so our tests
see plain pytest-playwright. Plugin behaviour is tested explicitly (direct
proxy tests, pytester sessions, and examples runs with an explicit mode).
"""

from __future__ import annotations

import os

os.environ.setdefault("HEALWRIGHT_MODE", "off")

from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import pytest

from chaos_store.serve import serve_in_thread


@dataclass(frozen=True)
class LiveStore:
    base_url: str

    def _params(self, session: str | None) -> dict[str, str]:
        return {"session": session} if session else {}

    def actions(self, session: str | None = None) -> list[dict[str, object]]:
        res = httpx.get(f"{self.base_url}/__chaos/actions", params=self._params(session), timeout=5)
        res.raise_for_status()
        actions: list[dict[str, object]] = res.json()["actions"]
        return actions

    def reset(self, session: str | None = None) -> None:
        httpx.post(
            f"{self.base_url}/__chaos/reset", params=self._params(session), timeout=5
        ).raise_for_status()

    def set_scenario(self, yaml_text: str, session: str | None = None) -> None:
        httpx.post(
            f"{self.base_url}/__chaos/scenario",
            params=self._params(session),
            content=yaml_text,
            timeout=5,
        ).raise_for_status()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-timing",
        action="store_true",
        default=False,
        help="run wall-clock timing tests (marker 'timing'); CI and gate checks pass this",
    )
    parser.addoption(
        "--run-release-gate",
        action="store_true",
        default=False,
        help="run release-gate invariants 2 and 3 (marker 'release_gate'; takes minutes)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Timing tests are deselected from the default run (machine load makes
    them flaky on the dev laptop) but still run in CI and before gates."""
    for marker, option in (("timing", "--run-timing"), ("release_gate", "--run-release-gate")):
        if config.getoption(option):
            continue
        skipped = [item for item in items if item.get_closest_marker(marker)]
        if skipped:
            config.hook.pytest_deselected(items=skipped)
            items[:] = [item for item in items if not item.get_closest_marker(marker)]


@pytest.fixture(scope="session")
def live_store() -> Iterator[LiveStore]:
    with serve_in_thread() as base_url:
        yield LiveStore(base_url)


@pytest.fixture
def store(live_store: LiveStore) -> Iterator[LiveStore]:
    """A live store reset to the unmutated scenario before and after the test."""
    live_store.reset()
    yield live_store
    live_store.reset()
