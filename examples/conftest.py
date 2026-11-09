"""Fixtures for the example suite: a Chaos Store and a browser context pointed at it.

- By default the store runs in a background thread on port 8001 (``CHAOS_PORT``
  overrides the port).
- ``CHAOS_BASE_URL`` makes the suite use an already-running store instead; the
  benchmark runner uses this to control scenarios and read the action log.
- ``CHAOS_SESSION`` pre-assigns the ``cw_session`` cookie of the test's browser
  context, so the runner can read ground truth for the real run only (sandbox
  contexts get their own sessions).

Tests use only normal Playwright: literal selectors at the call site, sync API.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import BrowserContext

from chaos_store.serve import serve_in_thread


@pytest.fixture(scope="session")
def chaos_store_url() -> Iterator[str]:
    external = os.environ.get("CHAOS_BASE_URL")
    if external:
        yield external.rstrip("/")
        return
    port = int(os.environ.get("CHAOS_PORT", "8001"))
    with serve_in_thread(port) as url:
        yield url


@pytest.fixture(scope="session")
def browser_context_args(
    browser_context_args: dict[str, Any], chaos_store_url: str
) -> dict[str, Any]:
    return {
        **browser_context_args,
        "base_url": chaos_store_url,
        "viewport": {"width": 1280, "height": 800},
        "device_scale_factor": 1,
    }


@pytest.fixture(autouse=True)
def _preassigned_session(context: BrowserContext, chaos_store_url: str) -> None:
    session = os.environ.get("CHAOS_SESSION")
    if session:
        context.add_cookies([{"name": "cw_session", "value": session, "url": chaos_store_url}])
    # Optional: shorter Playwright timeouts so harnesses that EXPECT a broken selector
    # (scenario checks, benchmark "native" system) do not wait 30 s per failure.
    timeout_ms = os.environ.get("CHAOS_ACTION_TIMEOUT_MS")
    if timeout_ms:
        context.set_default_timeout(int(timeout_ms))
