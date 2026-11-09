"""Text normalisation, URL templating and hashed-class filter."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from healwright.verify.normalize import (
    is_hashed_class,
    normalize_text,
    same_origin,
    stable_class_tokens,
    template_path,
    template_url,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Add   to\tCart \n", "add to cart"),
        ("Add​to‍ cart", "addto cart"),
        (
            "\uff21\uff24\uff24 \uff34\uff2f \uff23\uff21\uff32\uff34",
            "add to cart",
        ),  # full-width (NFKC)
        ("Straße", "strasse"),  # casefold, not lower()
        ("ﬁle", "file"),  # ligature (NFKC)
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_text(raw: str | None, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_normalize_truncates_after_normalising() -> None:
    assert normalize_text("\uff21" * 300) == "a" * 200
    assert normalize_text("abc def", limit=4) == "abc"


@given(st.text())
def test_normalize_is_idempotent(s: str) -> None:
    once = normalize_text(s, limit=None)
    assert normalize_text(once, limit=None) == once


@given(st.text())
def test_normalize_respects_limit(s: str) -> None:
    assert len(normalize_text(s)) <= 200


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://127.0.0.1:8001/order/1001?x=1#top", "/order/{id}"),
        ("https://shop.example/api/orders/42/confirm", "/api/orders/{id}/confirm"),
        ("/api/cart/7", "/api/cart/{id}"),
        ("http://h/u/550e8400-e29b-41d4-a716-446655440000/x", "/u/{id}/x"),
        ("http://h/obj/5f2b9c0e1a2b3c4d5e6f7a8b", "/obj/{id}"),
        ("http://h/product/deadbeef", "/product/deadbeef"),  # short hex is a real word
        ("http://h/", "/"),
        ("http://h", "/"),
        ("about:blank", "about:blank"),
        ("data:text/html,<p>secret</p>", "data:"),
    ],
)
def test_template_url(url: str, expected: str) -> None:
    assert template_url(url) == expected


url_paths = st.lists(
    st.one_of(
        st.integers(min_value=0, max_value=10**9).map(str),
        st.uuids().map(str),
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz-_", min_size=1, max_size=12),
        st.just("{id}"),
    ),
    max_size=6,
).map(lambda segs: "/" + "/".join(segs))


@given(url_paths)
def test_template_is_idempotent(path: str) -> None:
    once = template_url("http://h" + path)
    assert template_url("http://h" + once) == once
    assert template_path(template_path(path)) == template_path(path)


def test_same_origin() -> None:
    assert same_origin("http://127.0.0.1:8001/api/x", "http://127.0.0.1:8001/cart")
    assert not same_origin("http://127.0.0.1:8002/api/x", "http://127.0.0.1:8001/cart")
    assert not same_origin("https://analytics.example/collect", "http://127.0.0.1:8001/")
    assert not same_origin("about:blank", "about:blank")


@pytest.mark.parametrize(
    "token", ["css-9f2kq1", "css-1x8b2c", "sc-a81kd2", "_a1b2c3", "Button_root__x7f2a", "a81kd2x"]
)
def test_hashed_classes(token: str) -> None:
    assert is_hashed_class(token)


@pytest.mark.parametrize(
    "token", ["btn", "btn-primary", "px-3.5", "py-2", "rounded-md", "gap-3", "text-base", "h1"]
)
def test_stable_classes(token: str) -> None:
    assert not is_hashed_class(token)


def test_stable_class_tokens_filters_dedupes_and_caps() -> None:
    assert stable_class_tokens(["css-9f2kq1", "btn", "btn", "px-3"]) == ["btn", "px-3"]
    assert len(stable_class_tokens([f"c{i}x" * 2 for i in range(80)])) <= 50
