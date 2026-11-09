"""Log redaction and the JSON log file.

All key-like strings below are FAKE, generated for the test.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from healwright.logs import REDACTED, RedactingFilter, redact, setup_logging

pytestmark = pytest.mark.unit

FAKE_GROQ = "gsk_" + "Ab3" * 17 + "x"  # 56 chars, Groq format
FAKE_MISTRAL = "Zq8" * 10 + "Kp2Lm"  # 35 chars, prefix-less mixed case + digits
FAKE_GEMINI = "AIza" + "Sy" + "B9-c_" * 7
FAKE_SEPARATED = "Qx7-" * 8 + "Rt5_Wv9"  # 39 chars: mixed case, digits, - and _
SHA = "a3f1" * 16  # lower-case hex: must survive
ULID = "01JC8Z6Q8M3V0F1T5C8H2K7N4P"


@pytest.mark.parametrize("secret", [FAKE_GROQ, FAKE_MISTRAL, FAKE_GEMINI, FAKE_SEPARATED])
def test_known_key_formats_are_redacted(secret: str) -> None:
    out = redact(f"calling provider with key={secret} now")
    assert secret not in out
    assert REDACTED in out


def test_bearer_header_is_redacted() -> None:
    out = redact("Authorization: Bearer abc.def-ghi_jkl")
    assert "abc.def" not in out
    assert out == f"Authorization: Bearer {REDACTED}"


def test_exact_configured_value_is_redacted_even_if_unusual() -> None:
    odd = "lowercase-only-secret-value"
    assert odd not in redact(f"x {odd} y", secrets=(odd,))


def test_hashes_ids_and_normal_text_survive() -> None:
    text = (
        f"sha {SHA} run {ULID} selector #add-to-cart POST /api/orders/{{id}}/confirm "
        "examples/test_checkout.py::test_place_order_with_express_shipping[chromium]"
    )
    assert redact(text) == text


def test_filter_redacts_args_and_tracebacks() -> None:
    record = logging.LogRecord(
        "healwright.x", logging.ERROR, __file__, 1, "key %s", (FAKE_GROQ,), None
    )
    try:
        raise RuntimeError(f"bad key {FAKE_MISTRAL}")
    except RuntimeError:
        import sys

        record.exc_info = sys.exc_info()
    assert RedactingFilter().filter(record) is True
    assert FAKE_GROQ not in record.getMessage()
    assert record.exc_text is not None
    assert FAKE_MISTRAL not in record.exc_text


def test_setup_logging_writes_redacted_json_lines(tmp_path: Path) -> None:
    path = setup_logging(tmp_path, secrets=(FAKE_MISTRAL,))
    assert path is not None
    log = logging.getLogger("healwright.test")
    log.warning("provider failed for %s", FAKE_MISTRAL, extra={"provider": "mistral", "tier": 2})
    for handler in logging.getLogger("healwright").handlers:
        handler.flush()
    lines = path.read_text(encoding="utf-8").splitlines()
    data = json.loads(lines[-1])
    assert data["provider"] == "mistral"
    assert data["tier"] == 2
    assert FAKE_MISTRAL not in lines[-1]
    assert REDACTED in data["msg"]
