"""Provider router.

For each provider in ``HEALWRIGHT_PROVIDERS`` order:
  cache hit -> done (does not count against the per-run cap);
  replay mode and a miss -> next provider (a replay miss is an error, never a call);
  circuit open -> next provider;
  call with tenacity: up to ``max_retries`` retries (default 2) on 429 / 5xx /
  timeouts, 1 s, 2 s, 4 s, 8 s plus jitter, honouring Retry-After up to
  ``retry_after_cap`` (default 10 s); every failed attempt counts toward the
  breaker (opens after max(3, retries + 1) consecutive failures for 60 s);
  auth / removed model -> no retry, provider disabled for the session;
  invalid reply -> ONE repair attempt with the validation error appended,
  then a provider failure.
Every real call passes a client-side request bucket, the provider's own
token/request budget from its rate-limit headers (token-aware pacing), and the
per-run call cap;
an exhausted cap raises ``BudgetExhausted`` (the engine returns needs_human).
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from tenacity import RetryCallState, Retrying, retry_if_exception, stop_after_attempt

from healwright.errors import (
    BudgetExhausted,
    ProviderAuthError,
    ProviderBadResponse,
    ProviderError,
)
from healwright.models import Tier2Reply
from healwright.tier2.breaker import CircuitBreaker, TokenBucket
from healwright.tier2.cache import ResponseCache, cache_key
from healwright.tier2.prompt import PROMPT_VERSION, InvalidReply, parse_reply, repair_prompt
from healwright.tier2.providers.base import Provider, is_retryable, retry_after_of

BACKOFF_S = (1.0, 2.0, 4.0, 8.0, 8.0, 8.0)
MAX_RETRY_AFTER_S = 10.0
DEFAULT_RPM = {"gemini": 10.0, "groq": 30.0}


@dataclass(frozen=True)
class RouterResult:
    reply: Tier2Reply
    provider: str
    cached: bool


@dataclass
class Router:
    providers: Sequence[Provider]
    cache: ResponseCache
    run_cap: int
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    jitter: Callable[[], float] = field(default=lambda: random.uniform(0.0, 0.25))
    calls_used: int = 0
    max_retries: int = 2
    retry_after_cap: float = MAX_RETRY_AFTER_S
    breakers: dict[str, CircuitBreaker] = field(default_factory=dict)
    buckets: dict[str, TokenBucket] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for p in self.providers:
            self.breakers.setdefault(
                p.name, CircuitBreaker(threshold=max(3, self.max_retries + 1), clock=self.clock)
            )
            rpm = DEFAULT_RPM.get(p.name, 30.0)
            self.buckets.setdefault(
                p.name, TokenBucket(rpm, capacity=max(1.0, rpm / 6), clock=self.clock)
            )

    # ------------------------------------------------------------------ public
    def ask(self, prompt: str, image: bytes, allowed_ids: set[int], marks: str) -> RouterResult:
        errors: list[str] = []
        for provider in self.providers:
            key = cache_key(provider.model, PROMPT_VERSION, image, marks)
            cached = self.cache.get(key)
            if cached is not None:
                try:
                    return RouterResult(
                        parse_reply(cached, allowed_ids), provider.name, cached=True
                    )
                except InvalidReply as exc:
                    errors.append(f"{provider.name}: cached reply invalid ({exc})")
            if self.cache.mode == "replay":
                errors.append(f"{provider.name}: replay cache miss")
                continue
            breaker = self.breakers[provider.name]
            if not breaker.allow():
                errors.append(f"{provider.name}: circuit open")
                continue
            try:
                raw, reply = self._ask_one(provider, prompt, image, allowed_ids)
            except BudgetExhausted:
                raise
            except ProviderAuthError as exc:
                breaker.disable_for_session()
                errors.append(f"{provider.name}: {exc} (disabled for this session)")
                continue
            except ProviderError as exc:
                errors.append(f"{provider.name}: {exc}")
                continue
            breaker.success()
            self.cache.put(key, raw, provider.name, provider.model)
            return RouterResult(reply, provider.name, cached=False)
        raise ProviderError(
            "all providers failed: " + "; ".join(errors) if errors else "no provider configured"
        )

    # ------------------------------------------------------------------ internals
    def _spend(self, provider: Provider, prompt: str = "") -> None:
        if self.calls_used >= self.run_cap:
            raise BudgetExhausted(f"per-run VLM call cap of {self.run_cap} reached")
        bucket = self.buckets[provider.name]
        wait = bucket.wait_time()
        pace = getattr(provider, "pace_seconds", None)
        if callable(pace):
            wait = max(wait, float(pace(prompt, True)))
        if wait > 0:
            self.sleep(min(wait, self.retry_after_cap))
        bucket.take()
        self.calls_used += 1

    def _wait(self, state: RetryCallState) -> float:
        error = state.outcome.exception() if state.outcome else None
        hinted = retry_after_of(error) if error else None
        if hinted is not None:
            return min(hinted, self.retry_after_cap)
        index = min(state.attempt_number - 1, len(BACKOFF_S) - 1)
        return BACKOFF_S[index] + self.jitter()

    def _call(self, provider: Provider, prompt: str, image: bytes) -> str:
        breaker = self.breakers[provider.name]

        def attempt() -> str:
            self._spend(provider, prompt)
            try:
                return provider.complete(prompt, image)
            except ProviderAuthError:
                raise
            except ProviderError:
                breaker.failure()
                raise

        retrying = Retrying(
            stop=stop_after_attempt(1 + self.max_retries),
            retry=retry_if_exception(lambda e: is_retryable(e) and breaker.state == "closed"),
            wait=self._wait,
            sleep=self.sleep,
            reraise=True,
        )
        result: str = retrying(attempt)
        return result

    def _ask_one(
        self, provider: Provider, prompt: str, image: bytes, allowed_ids: set[int]
    ) -> tuple[str, Tier2Reply]:
        raw = self._call(provider, prompt, image)
        try:
            return raw, parse_reply(raw, allowed_ids)
        except InvalidReply as first:
            raw = self._call(provider, repair_prompt(prompt, str(first)), image)
            try:
                return raw, parse_reply(raw, allowed_ids)
            except InvalidReply as second:
                self.breakers[provider.name].failure()
                raise ProviderBadResponse(f"invalid reply after one repair: {second}") from None


__all__ = ["Router", "RouterResult"]
