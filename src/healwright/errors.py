"""HealWright exception hierarchy.

These errors never reach the user's test as-is: at the plugin boundary any
``Exception`` is logged, recorded as a heal event with status ``error``, and
the ORIGINAL Playwright error is re-raised with an exception note carrying the
code below.
"""

from typing import ClassVar


class HealWrightError(Exception):
    code: ClassVar[str] = "HEALWRIGHT_ERROR"


class BaselineMissing(HealWrightError):
    code: ClassVar[str] = "BASELINE_MISSING"  # no green run recorded


class BaselineCorrupt(HealWrightError):
    code: ClassVar[str] = "BASELINE_CORRUPT"  # unreadable / wrong schema


class ExtractionError(HealWrightError):
    code: ClassVar[str] = "EXTRACTION_FAILED"  # evaluate failed, iframe target


class ProviderError(HealWrightError):
    code: ClassVar[str] = "PROVIDER_ERROR"  # base for VLM failures


class ProviderRateLimited(ProviderError):
    code: ClassVar[str] = "PROVIDER_RATE_LIMITED"


class ProviderTimeout(ProviderError):
    code: ClassVar[str] = "PROVIDER_TIMEOUT"


class ProviderAuthError(ProviderError):
    code: ClassVar[str] = "PROVIDER_AUTH"  # bad key / removed model: no retry


class ProviderBadResponse(ProviderError):
    code: ClassVar[str] = "PROVIDER_BAD_RESPONSE"  # invalid JSON after one repair


class BudgetExhausted(HealWrightError):
    code: ClassVar[str] = "BUDGET_EXHAUSTED"


class SandboxError(HealWrightError):
    code: ClassVar[str] = "SANDBOX_FAILED"  # -> verification inconclusive


class PatchError(HealWrightError):
    code: ClassVar[str] = "PATCH_ERROR"


class UnpatchableCallSite(PatchError):
    code: ClassVar[str] = "UNPATCHABLE_CALL_SITE"  # not a literal at the call site


class SourceChanged(PatchError):
    code: ClassVar[str] = "SOURCE_CHANGED"


__all__ = [
    "BaselineCorrupt",
    "BaselineMissing",
    "BudgetExhausted",
    "ExtractionError",
    "HealWrightError",
    "PatchError",
    "ProviderAuthError",
    "ProviderBadResponse",
    "ProviderError",
    "ProviderRateLimited",
    "ProviderTimeout",
    "SandboxError",
    "SourceChanged",
    "UnpatchableCallSite",
]
