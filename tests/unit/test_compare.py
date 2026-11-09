"""Contract comparison rules."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from healwright.models import ApiCall, PostConditionSignature
from healwright.verify.compare import compare

pytestmark = pytest.mark.unit

CONFIRM = ApiCall(method="POST", path_template="/api/orders/{id}/confirm", status_class="2xx")
CANCEL = ApiCall(method="DELETE", path_template="/api/orders/{id}", status_class="2xx")
ADD = ApiCall(method="POST", path_template="/api/cart", status_class="2xx")
SEARCH = ApiCall(method="GET", path_template="/api/search", status_class="2xx")
BEACON_GET = ApiCall(method="GET", path_template="/api/ping", status_class="2xx")


def sig(**kw: Any) -> PostConditionSignature:
    base: dict[str, Any] = {
        "url_before": "/order/{id}",
        "url_after": "/order/{id}",
        "api_calls": frozenset({CONFIRM}),
        "modal_delta": 0,
        "dom_delta_sign": 0,
        "strength": "strong",
        "observations": 3,
    }
    return PostConditionSignature.model_validate(base | kw)


def test_identical_effect_passes() -> None:
    result = compare(sig(), sig(observations=1, strength="weak"))
    assert result.outcome == "pass"
    assert result.mismatches == []


def test_dev09_shape_cancel_instead_of_confirm_fails() -> None:
    """G1 found Tier 1 + gate would accept Cancel when Confirm is removed. The verifier must not."""
    result = compare(sig(), sig(api_calls=frozenset({CANCEL})))
    assert result.outcome == "fail"
    assert "missing call: POST /api/orders/{id}/confirm (2xx)" in result.mismatches
    assert "extra state-changing call: DELETE /api/orders/{id}" in result.mismatches


def test_extra_state_changing_call_fails_even_if_expected_calls_present() -> None:
    result = compare(sig(), sig(api_calls=frozenset({CONFIRM, CANCEL})))
    assert result.outcome == "fail"
    assert result.mismatches == ["extra state-changing call: DELETE /api/orders/{id}"]


def test_extra_read_only_call_is_tolerated() -> None:
    assert compare(sig(), sig(api_calls=frozenset({CONFIRM, BEACON_GET}))).outcome == "pass"


def test_same_endpoint_different_status_counts_as_missing() -> None:
    failed = ApiCall(method="POST", path_template="/api/orders/{id}/confirm", status_class="4xx")
    result = compare(sig(), sig(api_calls=frozenset({failed})))
    assert result.outcome == "fail"
    assert result.mismatches == ["missing call: POST /api/orders/{id}/confirm (2xx)"]


def test_url_after_must_match() -> None:
    result = compare(
        sig(url_before="/checkout", url_after="/order/{id}", api_calls=frozenset()),
        sig(url_before="/checkout", url_after="/checkout", api_calls=frozenset()),
    )
    assert result.outcome == "fail"
    assert result.mismatches == ["url after: expected '/order/{id}', got '/checkout'"]


def test_modal_delta_must_match() -> None:
    expected = sig(
        url_before="/product/{id}",
        url_after="/product/{id}",
        api_calls=frozenset({ADD}),
        modal_delta=1,
    )
    assert compare(expected, expected.model_copy(update={"modal_delta": 0})).outcome == "fail"


def test_dom_sign_only_matters_for_weak_contracts() -> None:
    strong = sig(dom_delta_sign=1)
    assert compare(strong, strong.model_copy(update={"dom_delta_sign": -1})).outcome == "pass"
    weak = sig(api_calls=frozenset(), modal_delta=-1, dom_delta_sign=-1, strength="weak")
    assert compare(weak, weak.model_copy(update={"dom_delta_sign": 0})).outcome == "fail"


def test_strength_none_is_inconclusive() -> None:
    none = sig(api_calls=frozenset(), strength="none")
    result = compare(none, none)
    assert result.outcome == "inconclusive"


def test_missing_observation_is_inconclusive() -> None:
    result = compare(sig(), None)
    assert result.outcome == "inconclusive"
    assert result.observed is None


calls = st.frozensets(st.sampled_from([CONFIRM, CANCEL, ADD, SEARCH, BEACON_GET]))
signatures = st.builds(
    lambda c, u, m, d, s: sig(
        api_calls=c, url_after=u, modal_delta=m, dom_delta_sign=d, strength=s
    ),
    calls,
    st.sampled_from(["/order/{id}", "/cart"]),
    st.sampled_from([-1, 0, 1]),
    st.sampled_from([-1, 0, 1]),
    st.sampled_from(["strong", "weak"]),
)


@given(signatures)
def test_comparison_is_reflexive(s: PostConditionSignature) -> None:
    """Property: contract comparison is reflexive."""
    assert compare(s, s).outcome == "pass"


@given(signatures, signatures)
def test_pass_implies_no_extra_state_changing_call(
    e: PostConditionSignature, o: PostConditionSignature
) -> None:
    result = compare(e, o)
    if result.outcome == "pass":
        for c in o.api_calls:
            if c.method in {"POST", "PUT", "PATCH", "DELETE"}:
                assert any(
                    x.method == c.method and x.path_template == c.path_template for x in e.api_calls
                )
        assert e.api_calls <= o.api_calls
