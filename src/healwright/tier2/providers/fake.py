"""FakeProvider for tests: never touches the network.

Modes: ok, rate_limited, timeout, bad_json, out_of_range, null_mark, auth.
In ``ok`` mode the reply's mark comes from ``choose(prompt)`` (default: mark 1).
``calls`` counts invocations so tests can assert caching and caps.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Literal

from healwright.errors import ProviderAuthError, ProviderError, ProviderTimeout
from healwright.tier2.providers.base import rate_limited

FakeMode = Literal[
    "ok", "rate_limited", "timeout", "bad_json", "out_of_range", "null_mark", "auth", "server_error"
]


def mark_named(name: str) -> Callable[[str], int]:
    """A chooser that picks the mark whose name equals ``name`` (from the marks table)."""

    def choose(prompt: str) -> int:
        table = re.search(r"MARKS: (\[.*?\])\n", prompt)
        assert table, "marks table missing from prompt"
        for row in json.loads(table.group(1)):
            if row["name"] == name:
                return int(row["id"])
        raise AssertionError(f"no mark named {name!r}")

    return choose


class FakeProvider:
    def __init__(
        self,
        mode: FakeMode = "ok",
        name: str = "fake",
        model: str = "fake-1",
        choose: Callable[[str], int] | None = None,
        retry_after: float | None = None,
    ) -> None:
        self.mode = mode
        self.name = name
        self.model = model
        self.choose = choose or (lambda _prompt: 1)
        self.retry_after = retry_after
        self.calls = 0
        self.prompts: list[str] = []

    def complete(self, prompt: str, image_jpeg: bytes) -> str:
        self.calls += 1
        self.prompts.append(prompt)
        if self.mode == "rate_limited":
            raise rate_limited("fake: 429", self.retry_after)
        if self.mode == "timeout":
            raise ProviderTimeout("fake: timeout")
        if self.mode == "auth":
            raise ProviderAuthError("fake: 401")
        if self.mode == "server_error":
            raise ProviderError("fake: 503")
        if self.mode == "bad_json":
            return "this is not json"
        if self.mode == "out_of_range":
            return json.dumps({"mark_id": 999, "confidence": 0.9, "reason": "made up"})
        if self.mode == "null_mark":
            return json.dumps({"mark_id": None, "confidence": 0.8, "reason": "target absent"})
        return json.dumps(
            {"mark_id": self.choose(prompt), "confidence": 0.9, "reason": "same control"}
        )


__all__ = ["FakeMode", "FakeProvider", "mark_named"]
