"""Gemini via google-genai: JSON-schema output, temperature 0.

google-genai 3.0.0 sends HTTP through its own ``httpx2`` dependency, which
respx cannot intercept, so the SDK client is injectable: tests pass a fake
client that returns replies or raises the SDK's own ``errors.APIError``.
SDK-side retries are disabled; the router owns retries.
"""

from __future__ import annotations

from typing import Any

from healwright.errors import ProviderAuthError, ProviderBadResponse, ProviderError, ProviderTimeout
from healwright.tier2.prompt import REPLY_SCHEMA
from healwright.tier2.providers.base import rate_limited

TIMEOUT_MS = 20_000


def _default_client(api_key: str) -> Any:
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=1)
        ),
    )


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, client: Any = None) -> None:
        self.model = model
        self._client = client if client is not None else _default_client(api_key)

    def complete(self, prompt: str, image_jpeg: bytes) -> str:
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_json_schema=REPLY_SCHEMA,
        )
        contents = [types.Part.from_bytes(data=image_jpeg, mime_type="image/jpeg"), prompt]
        try:
            response = self._client.models.generate_content(
                model=self.model, contents=contents, config=config
            )
        except errors.APIError as exc:
            code = int(getattr(exc, "code", 0) or 0)
            if code == 429:
                raise rate_limited("gemini: rate limited (429)", None) from None
            if code in (400, 401, 403, 404):
                raise ProviderAuthError(f"gemini: HTTP {code} (key, permission or model)") from None
            raise ProviderError(f"gemini: HTTP {code}") from None
        except TimeoutError:
            raise ProviderTimeout("gemini: timeout") from None
        except Exception as exc:  # noqa: BLE001 - SDK transport errors vary by version
            if "timeout" in type(exc).__name__.lower():
                raise ProviderTimeout(f"gemini: {type(exc).__name__}") from None
            raise ProviderError(f"gemini: {type(exc).__name__}") from None
        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise ProviderBadResponse("gemini: empty response")
        return text


__all__ = ["GeminiProvider"]
