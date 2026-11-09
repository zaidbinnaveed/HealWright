"""OpenAI-compatible chat-completions providers over httpx: Groq and Mistral.

Timeouts: connect 5 s, read 20 s. The API key is sent only as a bearer
header and never logged. Status mapping, shared by every provider:

- 429 -> ProviderRateLimited (Retry-After honoured by the router, capped at 10 s)
- 400/401/403/404 -> ProviderAuthError (bad key, permission or model: no retry,
  provider disabled for the session)
- 5xx / network -> ProviderError, timeouts -> ProviderTimeout (retried)
- malformed envelope -> ProviderBadResponse

Retries, the circuit breaker, the per-run cap and the cache live in the router
and apply to every provider the same way.
"""

from __future__ import annotations

import base64
import logging
import re
import time
from typing import Any

import httpx

from healwright.errors import ProviderAuthError, ProviderBadResponse, ProviderError, ProviderTimeout
from healwright.tier2.providers.base import rate_limited

TIMEOUT = httpx.Timeout(20.0, connect=5.0)
IMAGE_TOKENS_ESTIMATE = 1_500  # rough cost of one SoM image, for token-aware pacing
log = logging.getLogger("healwright.tier2.providers")
_DURATION = re.compile(r"(?:(\d+(?:\.\d+)?)m(?![s]))?(?:(\d+(?:\.\d+)?)s)?(?:(\d+(?:\.\d+)?)ms)?$")


def parse_duration(value: str | None) -> float | None:
    """Groq reset headers: "7.66s", "1m2.5s", "250ms", "2m" -> seconds."""
    if not value:
        return None
    m = _DURATION.match(value.strip())
    if not m or not any(m.groups()):
        return None
    minutes, seconds, millis = (float(g) if g else 0.0 for g in m.groups())
    return minutes * 60 + seconds + millis / 1000


def estimate_tokens(prompt: str, with_image: bool) -> int:
    return len(prompt) // 4 + (IMAGE_TOKENS_ESTIMATE if with_image else 0) + 300


class OpenAICompatProvider:
    """One chat-completions endpoint. Subclasses set ``name``, ``url`` and the image shape."""

    name = "openai-compat"
    url = ""
    image_as_object = True  # OpenAI/Groq: {"url": ...}; Mistral: the data URL string

    def __init__(self, api_key: str, model: str, client: httpx.Client | None = None) -> None:
        self._key = api_key
        self.model = model
        self._client = client or httpx.Client(timeout=TIMEOUT)
        # last rate-limit view from the server (token-aware pacing)
        self._limits_at: float | None = None
        self._remaining_tokens: int | None = None
        self._reset_tokens_s: float | None = None
        self._remaining_requests: int | None = None
        self._reset_requests_s: float | None = None

    def pace_seconds(self, prompt: str, with_image: bool) -> float:
        """Seconds to wait so this call fits the server's remaining token / request budget."""
        if self._limits_at is None:
            return 0.0
        elapsed = time.monotonic() - self._limits_at
        wait = 0.0
        needed = estimate_tokens(prompt, with_image)
        if self._remaining_tokens is not None and self._remaining_tokens < needed:
            wait = max(wait, (self._reset_tokens_s or 0.0) - elapsed)
        if self._remaining_requests is not None and self._remaining_requests < 1:
            wait = max(wait, (self._reset_requests_s or 0.0) - elapsed)
        return max(wait, 0.0)

    def _note_limits(self, headers: httpx.Headers) -> None:
        def as_int(name: str) -> int | None:
            v = headers.get(name)
            return int(v) if v is not None and v.isdigit() else None

        tokens = as_int("x-ratelimit-remaining-tokens")
        requests = as_int("x-ratelimit-remaining-requests")
        if tokens is None and requests is None:
            return
        self._limits_at = time.monotonic()
        self._remaining_tokens = tokens
        self._remaining_requests = requests
        self._reset_tokens_s = parse_duration(headers.get("x-ratelimit-reset-tokens"))
        self._reset_requests_s = parse_duration(headers.get("x-ratelimit-reset-requests"))

    def body(self, prompt: str, image_jpeg: bytes | None) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if image_jpeg is not None:
            data_url = "data:image/jpeg;base64," + base64.b64encode(image_jpeg).decode("ascii")
            image: Any = {"url": data_url} if self.image_as_object else data_url
            content.append({"type": "image_url", "image_url": image})
        return {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": content}],
        }

    def complete(self, prompt: str, image_jpeg: bytes) -> str:
        return self._post(self.body(prompt, image_jpeg))

    def complete_text(self, prompt: str) -> str:
        """Text-only call (raw-HTML baseline): same envelope, no image part."""
        return self._post(self.body(prompt, None))

    def _post(self, body: dict[str, Any]) -> str:
        n = self.name
        t0 = time.perf_counter()
        try:
            res = self._client.post(
                self.url,
                json=body,
                headers={"Authorization": f"Bearer {self._key}"},
                timeout=TIMEOUT,
            )
        except httpx.TimeoutException as exc:
            self._log_call("timeout", t0)
            raise ProviderTimeout(f"{n}: {type(exc).__name__}") from None
        except httpx.HTTPError as exc:
            self._log_call("network", t0)
            raise ProviderError(f"{n}: {type(exc).__name__}") from None
        self._note_limits(res.headers)
        self._log_call(str(res.status_code), t0)
        if res.status_code == 429:
            if res.headers.get("x-ratelimit-limit-req-minute") == "0":
                # A quota of ZERO is not a transient limit (e.g. the account's free plan is
                # not activated): treat it like an auth error, no retry, provider off.
                raise ProviderAuthError(f"{n}: request quota is 0 per minute (plan not active?)")
            header = res.headers.get("retry-after")
            try:
                retry_after = float(header) if header else None
            except ValueError:
                retry_after = None
            raise rate_limited(f"{n}: rate limited (429)", retry_after)
        if res.status_code in (400, 401, 403, 404, 422):
            raise ProviderAuthError(f"{n}: HTTP {res.status_code} (key, permission or model)")
        if res.status_code >= 500:
            raise ProviderError(f"{n}: HTTP {res.status_code}")
        if res.status_code != 200:
            raise ProviderError(f"{n}: unexpected HTTP {res.status_code}")
        try:
            content = res.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderBadResponse(f"{n}: malformed envelope ({type(exc).__name__})") from None
        if not isinstance(content, str) or not content:
            raise ProviderBadResponse(f"{n}: empty content")
        return content

    def _log_call(self, status: str, t0: float) -> None:
        # one line per HTTP call: the benchmark counts calls per provider from these
        log.info(
            "provider call %s %s -> %s",
            self.name,
            self.model,
            status,
            extra={
                "provider": self.name,
                "error_code": status,
                "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
            },
        )


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"


class GroqProvider(OpenAICompatProvider):
    name = "groq"
    url = GROQ_URL
    image_as_object = True


class MistralProvider(OpenAICompatProvider):
    name = "mistral"
    url = MISTRAL_URL
    image_as_object = False  # Mistral's documented vision format: "image_url": "data:..."


__all__ = [
    "GROQ_URL",
    "MISTRAL_URL",
    "GroqProvider",
    "MistralProvider",
    "OpenAICompatProvider",
]
