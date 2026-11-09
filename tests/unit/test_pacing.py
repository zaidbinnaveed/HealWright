"""Benchmark-mode pacing: retries, Retry-After cap, token-aware waits, live saves."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from healwright.tier2.cache import ResponseCache, cache_key
from healwright.tier2.prompt import PROMPT_VERSION
from healwright.tier2.providers.openai_compat import GROQ_URL, GroqProvider, parse_duration
from healwright.tier2.router import Router

pytestmark = pytest.mark.unit

IMAGE = b"\xff\xd8fake-jpeg"
IDS = {1, 2}
MARKS = '[{"id":1}]'
REPLY = '{"mark_id": 1, "confidence": 0.9, "reason": "x"}'


def ok(headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"content": REPLY}}]}, headers=headers or {}
    )


@pytest.mark.parametrize(
    ("value", "seconds"),
    [("7.66s", 7.66), ("1m2.5s", 62.5), ("250ms", 0.25), ("2m", 120.0), ("", None), ("x", None)],
)
def test_parse_duration(value: str, seconds: float | None) -> None:
    assert parse_duration(value) == seconds


@respx.mock
def test_provider_waits_when_the_token_budget_is_too_small() -> None:
    respx.post(GROQ_URL).mock(
        return_value=ok({"x-ratelimit-remaining-tokens": "100", "x-ratelimit-reset-tokens": "9s"})
    )
    p = GroqProvider("gsk_fake", "m", client=httpx.Client())
    assert p.pace_seconds("p", True) == 0.0  # nothing known yet
    p.complete("prompt", IMAGE)
    wait = p.pace_seconds("prompt " * 100, True)
    assert 8.0 < wait <= 9.0  # 100 tokens left < needed: wait for the reset


@respx.mock
def test_provider_does_not_wait_with_enough_budget() -> None:
    respx.post(GROQ_URL).mock(
        return_value=ok(
            {"x-ratelimit-remaining-tokens": "50000", "x-ratelimit-remaining-requests": "900"}
        )
    )
    p = GroqProvider("gsk_fake", "m", client=httpx.Client())
    p.complete("prompt", IMAGE)
    assert p.pace_seconds("prompt", True) == 0.0


def _router(tmp_path: Path, mode: str, **kw: object) -> tuple[Router, list[float]]:
    slept: list[float] = []
    r = Router(
        [GroqProvider("gsk_fake", "m", client=httpx.Client())],
        ResponseCache(tmp_path / "cache", mode),  # type: ignore[arg-type]
        30,
        sleep=slept.append,
        jitter=lambda: 0.0,
        **kw,  # type: ignore[arg-type]
    )
    return r, slept


@respx.mock
def test_benchmark_mode_retries_four_times_and_honours_long_retry_after(tmp_path: Path) -> None:
    route = respx.post(GROQ_URL).mock(
        side_effect=[httpx.Response(429, headers={"retry-after": "30"})] * 4 + [ok()]
    )
    r, slept = _router(tmp_path, "record", max_retries=4, retry_after_cap=60.0)
    result = r.ask("prompt", IMAGE, IDS, MARKS)
    assert result.reply.mark_id == 1
    assert route.call_count == 5  # 1 try + 4 retries; the breaker did not cut it short
    assert slept.count(30.0) == 4  # Retry-After 30 s honoured (default cap would clip to 10)


@respx.mock
def test_default_policy_still_two_retries_and_ten_second_cap(tmp_path: Path) -> None:
    route = respx.post(GROQ_URL).mock(
        return_value=httpx.Response(429, headers={"retry-after": "30"})
    )
    r, slept = _router(tmp_path, "record")
    with pytest.raises(Exception, match="all providers failed"):
        r.ask("prompt", IMAGE, IDS, MARKS)
    assert route.call_count == 3
    assert slept == [10.0, 10.0]


@respx.mock
def test_live_mode_calls_every_time_but_saves_replies(tmp_path: Path) -> None:
    route = respx.post(GROQ_URL).mock(return_value=ok())
    r, _ = _router(tmp_path, "live")
    r.ask("prompt", IMAGE, IDS, MARKS)
    r.ask("prompt", IMAGE, IDS, MARKS)
    assert route.call_count == 2  # reads bypass the cache
    key = cache_key("m", PROMPT_VERSION, IMAGE, MARKS)
    assert (tmp_path / "cache" / f"{key}.json").is_file()  # but the reply was saved
