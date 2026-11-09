"""Public-safe mode helpers: shop URL rewriting, visitor ids, the per-visitor cooldown."""

from __future__ import annotations

import pytest
from starlette.requests import Request

from healwright.api.errors import ApiError
from healwright.api.public import (
    VERCEL_SITE,
    Cooldown,
    PublicOptions,
    rewrite_html,
    rewrite_js,
    rewrite_location,
    visitor_id,
)

pytestmark = pytest.mark.unit


def test_html_root_relative_urls_move_under_shop() -> None:
    html = (
        '<link rel="stylesheet" href="/static/store.css"><script src="/static/store.js"></script>'
        '<a href="/cart">Cart</a><a href="//cdn.example/x">cdn</a><a href="https://x.y/">abs</a>'
        '<form action="/search"></form><a href="#top">top</a>'
    )
    out = rewrite_html(html)
    assert 'href="/shop/static/store.css"' in out
    assert 'src="/shop/static/store.js"' in out
    assert 'href="/shop/cart"' in out
    assert 'action="/shop/search"' in out
    assert 'href="//cdn.example/x"' in out  # protocol-relative: untouched
    assert 'href="https://x.y/"' in out
    assert 'href="#top"' in out


def test_js_paths_move_under_shop() -> None:
    js = (
        'api("POST", "/api/cart", {});\n'
        'api("POST", `/api/cart/${id}/save`);\n'
        "window.location.assign(`/order/${r.data.id}`);\n"
        '`<a href="/product/${p.id}">`;\n'
        'const other = "/elsewhere";\n'
    )
    out = rewrite_js(js)
    assert '"/shop/api/cart"' in out
    assert "`/shop/api/cart/${id}/save`" in out
    assert "`/shop/order/${r.data.id}`" in out
    assert 'href="/shop/product/${p.id}"' in out
    assert '"/elsewhere"' in out  # not a store path


def test_redirects_stay_under_shop() -> None:
    assert rewrite_location("/") == "/shop/"
    assert rewrite_location("/product/1") == "/shop/product/1"
    assert rewrite_location("//evil.example/") == "//evil.example/"
    assert rewrite_location("https://x.y/") == "https://x.y/"


def _request(headers: dict[str, str], client: str = "10.0.0.9") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": (client, 1234)})


def test_visitor_id_prefers_the_first_forwarded_hop() -> None:
    assert visitor_id(_request({"X-Forwarded-For": "203.0.113.7, 10.1.1.1"})) == "203.0.113.7"
    assert visitor_id(_request({})) == "10.0.0.9"


def test_cooldown_per_visitor() -> None:
    now = [1000.0]
    cd = Cooldown(60, clock=lambda: now[0])
    cd.check("a")  # never ran: fine
    cd.mark("a")
    with pytest.raises(ApiError) as info:
        cd.check("a")
    assert info.value.status == 429
    assert info.value.code == "DEMO_COOLDOWN"
    assert info.value.headers == {"Retry-After": "61"}
    cd.check("b")  # another visitor is not affected
    now[0] += 59.5
    with pytest.raises(ApiError):
        cd.check("a")
    now[0] += 1
    cd.check("a")  # waited long enough


def test_cooldown_zero_is_off() -> None:
    cd = Cooldown(0)
    cd.mark("a")
    cd.check("a")


def test_public_mode_allows_the_showcase_site_by_default() -> None:
    assert PublicOptions(public=True).origins() == (VERCEL_SITE,)
    assert PublicOptions(public=False).origins() == ()
    assert PublicOptions(public=True, cors_origins=("https://a.example",)).origins() == (
        "https://a.example",
    )
