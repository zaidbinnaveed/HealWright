"""Circuit breaker and client-side token bucket. Clock is injected."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

State = Literal["closed", "open", "half_open"]


@dataclass
class CircuitBreaker:
    """Opens after ``threshold`` consecutive failures for ``open_s`` seconds, then
    allows ONE half-open trial. An auth failure opens it for the whole session."""

    threshold: int = 3
    open_s: float = 60.0
    clock: Callable[[], float] = time.monotonic
    failures: int = 0
    opened_at: float | None = None
    permanent: bool = False
    _trial_in_flight: bool = field(default=False, repr=False)

    @property
    def state(self) -> State:
        if self.permanent:
            return "open"
        if self.opened_at is None:
            return "closed"
        if self.clock() - self.opened_at >= self.open_s:
            return "half_open"
        return "open"

    def allow(self) -> bool:
        state = self.state
        if state == "closed":
            return True
        if state == "half_open" and not self._trial_in_flight:
            self._trial_in_flight = True
            return True
        return False

    def success(self) -> None:
        self.failures = 0
        self.opened_at = None
        self._trial_in_flight = False

    def failure(self) -> None:
        self._trial_in_flight = False
        self.failures += 1
        if self.opened_at is not None or self.failures >= self.threshold:
            self.opened_at = self.clock()  # (re)open: a failed half-open trial restarts the wait

    def disable_for_session(self) -> None:
        self.permanent = True


@dataclass
class TokenBucket:
    """``rate_per_min`` requests per minute, bursts up to ``capacity``."""

    rate_per_min: float
    capacity: float
    clock: Callable[[], float] = time.monotonic
    tokens: float = -1.0
    updated: float = -1.0

    def wait_time(self) -> float:
        """Seconds to wait before one request may be sent (0 if a token is available)."""
        now = self.clock()
        if self.tokens < 0:
            self.tokens, self.updated = self.capacity, now
        self.tokens = min(
            self.capacity, self.tokens + (now - self.updated) * self.rate_per_min / 60
        )
        self.updated = now
        if self.tokens >= 1:
            return 0.0
        return (1 - self.tokens) * 60 / self.rate_per_min

    def take(self) -> None:
        self.wait_time()
        self.tokens -= 1


__all__ = ["CircuitBreaker", "TokenBucket"]
