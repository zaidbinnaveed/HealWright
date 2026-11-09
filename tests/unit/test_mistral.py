"""Mistral provider and the Groq -> Mistral chain, offline via respx. No live calls."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from healwright.errors import (
    ProviderAuthError,
    ProviderBadResponse,
    ProviderError,
    ProviderRateLimited,
    ProviderTimeout,
)
from healwright.tier2.cache import ResponseCache
from healwright.tier2.providers.openai_compat import (
    GROQ_URL,
    MISTRAL_URL,
    GroqProvider,
    MistralProvider,
)
from healwright.tier2.router import Router

pytestmark = pytest.mark.unit

IMAGE = b"\xff\xd8fake-jpeg"
IDS = {1, 2, 3}
MARKS = '[{"id":1,"name":"confirm order"}]'
KEY = "Mx7-fake-mistral-key-Zq81"  # fake


def ok(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


REPLY = '{"mark_id": 2, "confidence": 0.8, "reason": "same label"}'


@respx.mock
def test_mistral_request_shape() -> None:
    route = respx.post(MISTRAL_URL).mock(return_value=ok(REPLY))
    provider = MistralProvider(KEY, "mistral-small-latest", client=httpx.Client())
    assert json.loads(provider.complete("prompt", IMAGE))["mark_id"] == 2
    request = route.calls.last.request
    assert request.headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(request.content)
    assert body["model"] == "mistral-small-latest"
    assert body["temperature"] == 0
    assert body["response_format"] == {"type": "json_object"}
    text, image = body["messages"][0]["content"]
    assert text == {"type": "text", "text": "prompt"}
    # Mistral's documented vision format: image_url is the data URL string itself
    assert image["type"] == "image_url"
    assert image["image_url"].startswith("data:image/jpeg;base64,")


@respx.mock
def test_text_only_call_has_no_image_part() -> None:
    route = respx.post(MISTRAL_URL).mock(return_value=ok('{"selector": "#x"}'))
    MistralProvider(KEY, "m", client=httpx.Client()).complete_text("html prompt")
    body = json.loads(route.calls.last.request.content)
    assert body["messages"][0]["content"] == [{"type": "text", "text": "html prompt"}]


@respx.mock
@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(429, headers={"retry-after": "2"}), ProviderRateLimited),
        (httpx.Response(401), ProviderAuthError),
        (httpx.Response(422), ProviderAuthError),  # Mistral: invalid model / request
        (httpx.Response(500), ProviderError),
        (httpx.Response(200, json={"choices": []}), ProviderBadResponse),
        (ok(""), ProviderBadResponse),
    ],
)
def test_mistral_error_mapping(response: httpx.Response, error: type[Exception]) -> None:
    respx.post(MISTRAL_URL).mock(return_value=response)
    with pytest.raises(error) as exc:
        MistralProvider(KEY, "m", client=httpx.Client()).complete("p", IMAGE)
    assert KEY not in str(exc.value)
    assert str(exc.value).startswith("mistral:")


@respx.mock
def test_zero_quota_is_permanent_not_retried(tmp_path: Path) -> None:
    """Seen live 2026-11-07: Mistral 429 with x-ratelimit-limit-req-minute: 0 (plan not active)."""
    zero = httpx.Response(429, headers={"x-ratelimit-limit-req-minute": "0"})
    route = respx.post(MISTRAL_URL).mock(return_value=zero)
    with pytest.raises(ProviderAuthError, match="quota is 0"):
        MistralProvider(KEY, "m", client=httpx.Client()).complete("p", IMAGE)
    r = _router(tmp_path, MistralProvider(KEY, "m", client=httpx.Client()))
    with pytest.raises(ProviderError):
        r.ask("prompt", IMAGE, IDS, MARKS)
    assert route.call_count == 2  # one direct + one via the router: never retried


@respx.mock
def test_mistral_timeout() -> None:
    respx.post(MISTRAL_URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    with pytest.raises(ProviderTimeout):
        MistralProvider(KEY, "m", client=httpx.Client()).complete("p", IMAGE)


def _router(tmp_path: Path, *providers: object) -> Router:
    return Router(
        list(providers),  # type: ignore[arg-type]
        ResponseCache(tmp_path / "cache", "record"),
        30,
        sleep=lambda s: None,
        jitter=lambda: 0.0,
    )


@respx.mock
def test_groq_auth_failure_falls_back_to_mistral(tmp_path: Path) -> None:
    groq = respx.post(GROQ_URL).mock(return_value=httpx.Response(404))  # removed model
    mistral = respx.post(MISTRAL_URL).mock(return_value=ok(REPLY))
    r = _router(
        tmp_path,
        GroqProvider("gsk_fake", "gone-model", client=httpx.Client()),
        MistralProvider(KEY, "m", client=httpx.Client()),
    )
    result = r.ask("prompt", IMAGE, IDS, MARKS)
    assert result.provider == "mistral"
    assert result.reply.mark_id == 2
    assert groq.call_count == 1  # auth errors are never retried
    assert mistral.call_count == 1
    again = r.ask("prompt", IMAGE, IDS, MARKS)  # cached: zero further calls
    assert again.cached is True
    assert mistral.call_count == 1


@respx.mock
def test_groq_rate_limits_fall_back_to_mistral_after_retries(tmp_path: Path) -> None:
    groq = respx.post(GROQ_URL).mock(return_value=httpx.Response(429))
    respx.post(MISTRAL_URL).mock(return_value=ok(REPLY))
    r = _router(
        tmp_path,
        GroqProvider("gsk_fake", "m", client=httpx.Client()),
        MistralProvider(KEY, "m", client=httpx.Client()),
    )
    assert r.ask("prompt", IMAGE, IDS, MARKS).provider == "mistral"
    assert groq.call_count == 3  # 1 try + 2 retries
