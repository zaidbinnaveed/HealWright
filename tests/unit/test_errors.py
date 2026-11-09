"""Tests for the error hierarchy."""

from __future__ import annotations

import pytest

from healwright import errors as e

pytestmark = pytest.mark.unit

EXPECTED: dict[type[e.HealWrightError], tuple[str, type[Exception]]] = {
    e.HealWrightError: ("HEALWRIGHT_ERROR", Exception),
    e.BaselineMissing: ("BASELINE_MISSING", e.HealWrightError),
    e.BaselineCorrupt: ("BASELINE_CORRUPT", e.HealWrightError),
    e.ExtractionError: ("EXTRACTION_FAILED", e.HealWrightError),
    e.ProviderError: ("PROVIDER_ERROR", e.HealWrightError),
    e.ProviderRateLimited: ("PROVIDER_RATE_LIMITED", e.ProviderError),
    e.ProviderTimeout: ("PROVIDER_TIMEOUT", e.ProviderError),
    e.ProviderAuthError: ("PROVIDER_AUTH", e.ProviderError),
    e.ProviderBadResponse: ("PROVIDER_BAD_RESPONSE", e.ProviderError),
    e.BudgetExhausted: ("BUDGET_EXHAUSTED", e.HealWrightError),
    e.SandboxError: ("SANDBOX_FAILED", e.HealWrightError),
    e.PatchError: ("PATCH_ERROR", e.HealWrightError),
    e.UnpatchableCallSite: ("UNPATCHABLE_CALL_SITE", e.PatchError),
    e.SourceChanged: ("SOURCE_CHANGED", e.PatchError),
}


@pytest.mark.parametrize("cls", list(EXPECTED), ids=lambda c: c.__name__)
def test_code_and_parent(cls: type[e.HealWrightError]) -> None:
    code, parent = EXPECTED[cls]
    assert cls.code == code
    assert cls.__bases__ == (parent,)
    assert cls("boom").code == code


def test_hierarchy_is_complete_and_codes_unique() -> None:
    exported = {getattr(e, name) for name in e.__all__}
    assert exported == set(EXPECTED)
    codes = [cls.code for cls in EXPECTED]
    assert len(codes) == len(set(codes))


def test_all_errors_are_exceptions() -> None:
    # Fail-closed rule: the plugin catches Exception, never BaseException.
    for cls in EXPECTED:
        assert issubclass(cls, Exception)


def test_notes_can_be_attached() -> None:
    err = e.BaselineCorrupt("truncated JSON")
    err.add_note("HealWright: baseline corrupt (event 01JC8Z5V7Q2W3E4R5T6Y7U8J9P)")
    assert err.__notes__ == ["HealWright: baseline corrupt (event 01JC8Z5V7Q2W3E4R5T6Y7U8J9P)"]
