"""Structured, redacted logging.

JSON lines to ``<artifact_dir>/logs/healwright.log`` (rotating, 5 MB x 3). Every
record passes ``RedactingFilter``, which scrubs anything that looks like a secret:

1. the exact values of the configured API keys (strongest: no pattern guessing);
2. known key formats: Groq ``gsk_...``, Google ``AIza...``, ``Bearer <token>``;
3. any 32+ character token mixing upper case, lower case and digits (catches
   prefix-less keys such as Mistral's). Lower-case hex (SHA-256) and ULIDs
   (26 chars) are not touched.

The filter is attached to the HealWright handler and to the ``healwright`` and
``httpx`` loggers, so it also applies when a test harness adds its own handlers.
"""

from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

REDACTED = "[REDACTED]"
# Set by the API middleware: every record logged while a request is handled carries its id.
request_id_var: ContextVar[str | None] = ContextVar("healwright_request_id", default=None)
_PATTERNS = (
    re.compile(r"gsk_[A-Za-z0-9]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-~+/=]{8,}"),
    # generic: 32+ chars of [A-Za-z0-9_-] with upper, lower AND a digit (Mistral-style keys;
    # lower-case hex hashes, ULIDs and snake_case test names never match)
    re.compile(
        r"(?<![A-Za-z0-9_\-])(?=[A-Za-z0-9_\-]*[a-z])(?=[A-Za-z0-9_\-]*[A-Z])"
        r"(?=[A-Za-z0-9_\-]*[0-9])[A-Za-z0-9_\-]{32,}(?![A-Za-z0-9_\-])"
    ),
)
_CONTEXT_FIELDS = (
    "heal_id",
    "run_id",
    "request_id",
    "test",
    "tier",
    "provider",
    "duration_ms",
    "error_code",
)


def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    for secret in secrets:
        if secret and len(secret) >= 8:
            text = text.replace(secret, REDACTED)
    for pattern in _PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda m: m.group(1) + REDACTED, text)
        else:
            text = pattern.sub(REDACTED, text)
    return text


class RedactingFilter(logging.Filter):
    """Rewrites the record's message (and args) with secrets removed. Never drops a record."""

    def __init__(self, secrets: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.secrets = secrets

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - a broken format string must not break logging
            message = str(record.msg)
        record.msg = redact(message, self.secrets)
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text, self.secrets)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for name in _CONTEXT_FIELDS:
            value = getattr(record, name, None)
            if value is not None:
                data[name] = value
        if "request_id" not in data and (rid := request_id_var.get()) is not None:
            data["request_id"] = rid
        if record.exc_text:
            data["exc"] = record.exc_text
        return json.dumps(data, ensure_ascii=False)


_installed: dict[str, RotatingFileHandler] = {}


def configured_secrets() -> tuple[str, ...]:
    """Values of every configured API key (empty strings skipped)."""
    from healwright.config import load_settings

    try:
        settings = load_settings()
    except Exception:  # noqa: BLE001 - bad config is reported elsewhere; logging must still work
        return ()
    out = []
    for name in ("gemini_api_key", "groq_api_key", "mistral_api_key", "api_token"):
        value = getattr(settings, name, None)
        if value is not None:
            out.append(value.get_secret_value())
    return tuple(v for v in out if v)


def setup_logging(artifact_dir: Path, secrets: tuple[str, ...] | None = None) -> Path | None:
    """Install the rotating JSON handler once per log file. Never raises."""
    path = artifact_dir / "logs" / "healwright.log"
    key = str(path.resolve())
    if key in _installed:
        return path
    redactor = RedactingFilter(configured_secrets() if secrets is None else secrets)
    for name in ("healwright", "httpx"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactingFilter) for f in logger.filters):
            logger.addFilter(redactor)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8", delay=True
        )
    except OSError:
        return None
    handler.setFormatter(JsonFormatter())
    handler.addFilter(redactor)
    handler.setLevel(logging.INFO)
    root = logging.getLogger("healwright")
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(logging.INFO)
    _installed[key] = handler
    return path


__all__ = [
    "REDACTED",
    "JsonFormatter",
    "RedactingFilter",
    "redact",
    "request_id_var",
    "setup_logging",
]
