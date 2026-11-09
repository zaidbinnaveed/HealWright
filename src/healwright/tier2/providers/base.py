"""Provider interface: one image + one prompt in, raw reply text out.

Providers raise only ``ProviderError`` subclasses (errors.py):
``ProviderRateLimited`` (429; may carry ``retry_after``), ``ProviderTimeout``,
``ProviderAuthError`` (bad key / removed model: never retried), and plain
``ProviderError`` for 5xx and anything else retryable.
"""

from __future__ import annotations

from typing import Protocol

from healwright.errors import ProviderError, ProviderRateLimited


class Provider(Protocol):
    name: str
    model: str

    def complete(self, prompt: str, image_jpeg: bytes) -> str: ...


def rate_limited(message: str, retry_after: float | None) -> ProviderRateLimited:
    err = ProviderRateLimited(message)
    err.retry_after = retry_after  # type: ignore[attr-defined]
    return err


def retry_after_of(error: BaseException) -> float | None:
    value = getattr(error, "retry_after", None)
    return float(value) if isinstance(value, (int, float)) else None


def is_retryable(error: BaseException) -> bool:
    from healwright.errors import ProviderAuthError, ProviderBadResponse

    return isinstance(error, ProviderError) and not isinstance(
        error, (ProviderAuthError, ProviderBadResponse)
    )


__all__ = ["Provider", "is_retryable", "rate_limited", "retry_after_of"]
