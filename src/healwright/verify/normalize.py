"""Text normalisation and URL templating, applied identically at
record time and heal time, plus the hashed-class filter.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit

ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
_WS = re.compile(r"\s+")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_NUMERIC = re.compile(r"^\d+$")
_LONG_HEX = re.compile(r"^[0-9a-fA-F]{16,}$")
ID_TOKEN = "{id}"


def normalize_text(value: str | None, limit: int | None = 200) -> str:
    """NFKC, casefold, zero-width characters stripped, whitespace collapsed.

    Truncation (to ``limit`` characters) happens AFTER normalising, because
    NFKC can change the length. Idempotent.
    """
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value).translate(ZERO_WIDTH)
    text = unicodedata.normalize("NFKC", text.casefold())
    text = _WS.sub(" ", text).strip()
    if limit is not None and len(text) > limit:
        text = text[:limit].rstrip()
    return text


def _template_segment(segment: str) -> str:
    if _NUMERIC.match(segment) or _UUID.match(segment) or _LONG_HEX.match(segment):
        return ID_TOKEN
    return segment


def template_path(path: str) -> str:
    """Numeric, UUID and long-hex path segments become ``{id}``. Idempotent."""
    if not path:
        return "/"
    return "/".join(_template_segment(seg) for seg in path.split("/"))


def template_url(url: str, limit: int = 2048) -> str:
    """Route template of a URL: path only, query and fragment dropped.

    Non-hierarchical URLs (``about:blank``, ``data:``) keep their scheme only,
    so page content can never leak into a contract.
    """
    if not url:
        return ""
    parts = urlsplit(url)
    if parts.scheme in ("http", "https", "file") or (not parts.scheme and url.startswith("/")):
        return template_path(parts.path)[:limit]
    if parts.scheme:
        return f"{parts.scheme}:" + (parts.path if parts.scheme == "about" else "")
    return template_path(parts.path)[:limit]


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""


def same_origin(a: str, b: str) -> bool:
    oa = origin_of(a)
    return bool(oa) and oa == origin_of(b)


# --------------------------------------------------------------------------- classes

_HASHED = (
    re.compile(r"^css-[a-z0-9]{4,}$", re.IGNORECASE),  # emotion
    re.compile(r"^sc-[a-z0-9]+$", re.IGNORECASE),  # styled-components
    re.compile(r"^_[a-z0-9]{5,}$", re.IGNORECASE),  # CSS modules (short form)
    re.compile(r"^[a-z]+_[a-z]+__[a-z0-9]{5}$", re.IGNORECASE),  # CSS modules (long form)
)


def is_hashed_class(token: str) -> bool:
    """True for generated class names that carry no stable meaning."""
    if any(p.match(token) for p in _HASHED):
        return True
    if len(token) >= 5:
        digits = sum(ch.isdigit() for ch in token)
        return digits / len(token) >= 0.4
    return False


def stable_class_tokens(tokens: list[str], limit: int = 50) -> list[str]:
    out: list[str] = []
    for token in tokens:
        if token and not is_hashed_class(token) and token not in out:
            out.append(token[:100])
        if len(out) >= limit:
            break
    return out


__all__ = [
    "ID_TOKEN",
    "is_hashed_class",
    "normalize_text",
    "origin_of",
    "same_origin",
    "stable_class_tokens",
    "template_path",
    "template_url",
]
