"""Contract observation, strength rules and stable-intersection merging."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from healwright.models import ApiCall, PostConditionSignature
from healwright.recorder.contract import (
    PageState,
    merge,
    observe,
    sign,
    status_class,
    strength_of,
)

pytestmark = pytest.mark.unit

POST_CART = ApiCall(method="POST", path_template="/api/cart", status_class="2xx")
ANALYTICS = ApiCall(method="POST", path_template="/api/beacon", status_class="2xx")
DELETE_ORDER = ApiCall(method="DELETE", path_template="/api/orders/{id}", status_class="2xx")


def state(url: str = "http://h/product/1", nodes: int = 100, modals: int = 0) -> PageState:
    return PageState(url=url, nodes=nodes, modals=modals)


def test_status_class() -> None:
    assert [status_class(s) for s in (200, 204, 301, 404, 503)] == [
        "2xx",
        "2xx",
        "3xx",
        "4xx",
        "5xx",
    ]
    assert status_class(None) == "unknown"
    assert status_class(200, failed=True) == "failed"


def test_sign() -> None:
    assert (sign(-5), sign(0), sign(3)) == (-1, 0, 1)


@pytest.mark.parametrize(
    ("before", "after", "calls", "expected"),
    [
        (state(), state(url="http://h/order/1001"), frozenset(), "strong"),  # URL change
        (state(), state(), frozenset({POST_CART}), "strong"),  # API call
        (state(), state(modals=1), frozenset(), "weak"),  # modal only
        (state(), state(nodes=101), frozenset(), "weak"),  # DOM only
        (state(), state(), frozenset(), "none"),  # no observable effect (e.g. hover)
    ],
)
def test_observe_strength(
    before: PageState, after: PageState, calls: frozenset[ApiCall], expected: str
) -> None:
    obs = observe(before, after, calls)
    assert obs.strength == expected
    assert obs.observations == 1


def test_observe_templates_urls_and_signs_deltas() -> None:
    obs = observe(
        state("http://h/checkout?x=1", nodes=200, modals=1),
        state("http://h/order/1001#t", nodes=150, modals=0),
        frozenset(),
    )
    assert (obs.url_before, obs.url_after) == ("/checkout", "/order/{id}")
    assert (obs.modal_delta, obs.dom_delta_sign) == (-1, -1)


def sig(**kw: object) -> PostConditionSignature:
    base: dict[str, object] = {
        "url_before": "/product/{id}",
        "url_after": "/product/{id}",
        "api_calls": frozenset({POST_CART}),
        "modal_delta": 1,
        "dom_delta_sign": 1,
        "strength": "strong",
        "observations": 1,
    }
    return PostConditionSignature.model_validate(base | kw)


def test_single_observation_is_capped_at_weak() -> None:
    merged = merge([sig()])
    assert merged.strength == "weak"
    assert merged.api_calls == frozenset({POST_CART})


def test_two_identical_observations_are_strong() -> None:
    merged = merge([sig(), sig()])
    assert merged.strength == "strong"
    assert merged.observations == 2


def test_intersection_drops_unstable_calls() -> None:
    merged = merge(
        [
            sig(api_calls=frozenset({POST_CART, ANALYTICS})),
            sig(api_calls=frozenset({POST_CART})),
            sig(api_calls=frozenset({POST_CART, ANALYTICS})),
        ]
    )
    assert merged.api_calls == frozenset({POST_CART})


def test_unstable_url_and_deltas_fall_back_to_no_change() -> None:
    merged = merge(
        [
            sig(url_after="/cart", api_calls=frozenset(), modal_delta=1, dom_delta_sign=1),
            sig(url_after="/order/{id}", api_calls=frozenset(), modal_delta=0, dom_delta_sign=-1),
        ]
    )
    assert merged.url_after == merged.url_before
    assert (merged.modal_delta, merged.dom_delta_sign) == (0, 0)
    assert merged.strength == "none"


def test_unstable_url_before_does_not_fake_a_url_change() -> None:
    merged = merge([sig(url_before="/a", url_after="/a"), sig(url_before="/b", url_after="/b")])
    assert merged.url_before == merged.url_after


def test_merge_keeps_only_last_three() -> None:
    old = sig(api_calls=frozenset({DELETE_ORDER}))
    merged = merge([old, sig(), sig(), sig()])
    assert merged.api_calls == frozenset({POST_CART})
    assert merged.observations == 3


def test_merge_requires_observations() -> None:
    with pytest.raises(ValueError, match="at least one"):
        merge([])


calls = st.frozensets(st.sampled_from([POST_CART, ANALYTICS, DELETE_ORDER]))
signs = st.sampled_from([-1, 0, 1])
observations = st.builds(
    lambda c, m, d, u: sig(api_calls=c, modal_delta=m, dom_delta_sign=d, url_after=u),
    calls,
    signs,
    signs,
    st.sampled_from(["/product/{id}", "/cart"]),
)


@given(st.lists(observations, min_size=1, max_size=5))
def test_merge_is_a_subset_of_every_recent_observation(
    history: list[PostConditionSignature],
) -> None:
    merged = merge(history)
    for obs in history[-3:]:
        assert merged.api_calls <= obs.api_calls
    assert merged.strength == strength_of(
        merged.url_before,
        merged.url_after,
        merged.api_calls,
        merged.modal_delta,
        merged.dom_delta_sign,
    ) or (len(history) == 1 and merged.strength == "weak")


@given(observations)
def test_merge_of_identical_observations_is_stable(obs: PostConditionSignature) -> None:
    assert merge([obs, obs]) == merge([obs, obs, obs]).model_copy(update={"observations": 2})


def test_network_log_windows_are_positions_not_clock_ticks() -> None:
    """Windows' monotonic clock ticks every ~15.6 ms: identical timestamps must not drop calls."""
    from healwright.recorder.contract import NetworkLog, _Call

    net = NetworkLog(page=None)  # type: ignore[arg-type]
    start = net.mark()
    net.calls.append(_Call(100.0, "POST", "http://h/api/orders/1001/confirm", status=200))
    end = net.mark()
    net.calls.append(_Call(100.0, "POST", "http://h/api/cart", status=200))  # same tick, next step
    assert net.since(start, end, started=100.0) == frozenset(
        {ApiCall(method="POST", path_template="/api/orders/{id}/confirm", status_class="2xx")}
    )
    assert net.since(end) == frozenset({POST_CART})
    assert not net.in_flight(start)
    net.calls.append(_Call(100.5, "GET", "http://h/api/search", status=None))
    assert net.in_flight(start)


def test_network_log_window_cap_is_two_seconds() -> None:
    from healwright.recorder.contract import NetworkLog, _Call

    net = NetworkLog(page=None)  # type: ignore[arg-type]
    net.calls.append(_Call(10.0, "POST", "http://h/api/cart", status=200))
    net.calls.append(_Call(12.5, "DELETE", "http://h/api/cart/1", status=200))  # polling-like, late
    assert net.since(0, started=10.0) == frozenset({POST_CART})
