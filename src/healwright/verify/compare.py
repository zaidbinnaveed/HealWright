"""Contract comparison: does the candidate do the same thing?

Rules, applied to the baseline contract (expected) and the sandbox observation:

1. The URL-after route template must match.
2. Every stable API call in the baseline must appear in the observation
   (method, path template and status class).
3. The observation must contain NO extra state-changing call (POST, PUT,
   PATCH, DELETE) whose method and path are absent from the baseline. This is
   the rule that rejects "Cancel order" (``DELETE /api/orders/{id}``) standing
   in for "Confirm order".
4. The modal delta must match.
5. The DOM-delta sign is compared only for ``weak`` contracts, where it is the
   only signal.

A baseline of strength ``none`` (no observable effect, e.g. hover) cannot be
verified, and neither can a missing observation: both are ``inconclusive``,
which the engine turns into ``suggested`` (test stays red).
"""

from __future__ import annotations

from healwright.models import MAX_REASON_LEN, PostConditionSignature, VerificationResult

STATE_CHANGING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
MAX_MISMATCHES = 50


def _fmt(method: str, path: str, status: str | None = None) -> str:
    return f"{method} {path}" + (f" ({status})" if status else "")


def compare(
    expected: PostConditionSignature, observed: PostConditionSignature | None
) -> VerificationResult:
    if observed is None:
        return VerificationResult(
            outcome="inconclusive",
            expected=expected,
            observed=None,
            mismatches=["sandbox produced no observation"],
        )
    if expected.strength == "none":
        return VerificationResult(
            outcome="inconclusive",
            expected=expected,
            observed=observed,
            mismatches=["baseline contract has no observable effect; cannot verify"],
        )

    mismatches: list[str] = []
    if observed.url_after != expected.url_after:
        mismatches.append(f"url after: expected {expected.url_after!r}, got {observed.url_after!r}")

    for call in sorted(
        expected.api_calls - observed.api_calls, key=lambda c: (c.path_template, c.method)
    ):
        mismatches.append(
            "missing call: " + _fmt(call.method, call.path_template, call.status_class)
        )

    baseline_endpoints = {(c.method, c.path_template) for c in expected.api_calls}
    for call in sorted(observed.api_calls, key=lambda c: (c.path_template, c.method)):
        if (
            call.method in STATE_CHANGING
            and (call.method, call.path_template) not in baseline_endpoints
        ):
            mismatches.append("extra state-changing call: " + _fmt(call.method, call.path_template))

    if observed.modal_delta != expected.modal_delta:
        mismatches.append(
            f"modal delta: expected {expected.modal_delta}, got {observed.modal_delta}"
        )

    if expected.strength == "weak" and observed.dom_delta_sign != expected.dom_delta_sign:
        mismatches.append(
            f"DOM change sign: expected {expected.dom_delta_sign}, got {observed.dom_delta_sign}"
        )

    mismatches = [m[:MAX_REASON_LEN] for m in mismatches[:MAX_MISMATCHES]]
    return VerificationResult(
        outcome="fail" if mismatches else "pass",
        expected=expected,
        observed=observed,
        mismatches=mismatches,
    )


__all__ = ["STATE_CHANGING", "compare"]
