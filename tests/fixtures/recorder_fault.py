"""pytest plugin for the release gate: makes the recorder throw on every snapshot.

Loaded with ``-p tests.fixtures.recorder_fault``. HealWright must swallow and count the errors;
every green test stays green (failure-mode row "Recorder throws", release-gate invariant 2).
"""

from __future__ import annotations

from typing import Any


def pytest_configure(config: Any) -> None:
    from healwright.recorder.recorder import Recorder

    def _broken_snapshot(self: Recorder, target: Any) -> Any:
        raise RuntimeError("injected recorder fault")

    Recorder._snapshot = _broken_snapshot  # type: ignore[method-assign]
