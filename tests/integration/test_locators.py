"""Locator synthesis: each strategy, duplicates, quotes, identity."""

from __future__ import annotations

import ast
from typing import Any

import pytest
from playwright.sync_api import ElementHandle, Page

from healwright.locators import SynthesizedLocator, css_escape_id, synthesize
from healwright.recorder.extract import extract, row_as_dict

pytestmark = pytest.mark.integration


def raw_of(page: Page, selector: str) -> tuple[ElementHandle, dict[str, Any]]:
    handle = page.query_selector(selector)
    assert handle is not None, selector
    snap = extract(page, target=handle)
    return handle, row_as_dict(snap["rows"][0])


def check(page: Page, selector: str) -> SynthesizedLocator:
    handle, raw = raw_of(page, selector)
    spec = synthesize(page, handle, raw)
    assert spec is not None, selector
    loc = spec.build(page)
    assert loc.count() == 1
    assert loc.evaluate("(el, t) => el === t", handle)
    ast.parse(spec.code())  # valid Python
    return spec


def test_test_id_strategy(page: Page) -> None:
    page.set_content('<button data-testid="place-order">Place order</button>')
    spec = check(page, "button")
    assert spec.strategy == "test_id"
    assert spec.code() == "page.get_by_test_id('place-order')"
    assert not spec.fragile


def test_duplicate_test_id_falls_back_to_role(page: Page) -> None:
    page.set_content(
        '<button data-testid="act">Place order</button><button data-testid="act">Cancel</button>'
    )
    spec = check(page, "text=Place order")
    assert spec.strategy == "role"
    assert spec.code() == "page.get_by_role('button', name='Place order', exact=True)"


def test_role_strategy_uses_raw_casing(page: Page) -> None:
    page.set_content("<a href='/cart'>View Cart</a>")
    spec = check(page, "a")
    assert spec.strategy == "role"
    assert "name='View Cart'" in spec.code()


def test_label_strategy_when_role_is_unknown(page: Page) -> None:
    page.set_content('<label for="d">Birthday</label><input id="d" type="date">')
    spec = check(page, "#d")
    assert spec.strategy == "label"
    assert spec.code() == "page.get_by_label('Birthday', exact=True)"


def test_scoped_role_for_duplicate_names(page: Page) -> None:
    page.set_content(
        "<ul>"
        "<li id='card-1'><h2>Shoes</h2><a href='/p/1'>View details</a></li>"
        "<li id='card-2'><h2>Jacket</h2><a href='/p/2'>View details</a></li>"
        "</ul>"
    )
    spec = check(page, "#card-2 a")
    assert spec.strategy == "scoped_role"
    assert spec.code() == (
        "page.locator('#card-2').get_by_role('link', name='View details', exact=True)"
    )
    assert not spec.fragile


def test_scope_prefers_test_id_ancestor(page: Page) -> None:
    page.set_content(
        "<div data-testid='a'><button>Remove</button></div>"
        "<div data-testid='b'><button>Remove</button></div>"
    )
    spec = check(page, "[data-testid=b] button")
    assert (
        spec.code() == "page.get_by_test_id('b').get_by_role('button', name='Remove', exact=True)"
    )


def test_nth_fallback_is_marked_fragile(page: Page) -> None:
    page.set_content(
        "<div><button>Remove</button><button>Remove</button><button>Remove</button></div>"
    )
    spec = check(page, "button >> nth=1")
    assert spec.fragile
    assert spec.code().endswith(".nth(1)")


@pytest.mark.parametrize(
    "name",
    ['Say "hi"', "It's here", "a\\b", "x'); import os; ('", "Ünïcödé ✓"],
)
def test_names_with_quotes_are_safe(page: Page, name: str) -> None:
    page.evaluate(
        "(n) => { document.body.innerHTML = ''; const b = document.createElement('button');"
        " b.textContent = n; document.body.appendChild(b); }",
        name,
    )
    spec = check(page, "button")
    tree = ast.parse(spec.code(), mode="eval")
    # the only call arguments are literals: page text cannot become code
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for arg in [*node.args, *(k.value for k in node.keywords)]:
                assert isinstance(arg, ast.Constant)
    assert any(isinstance(n, ast.Constant) and n.value == name for n in ast.walk(tree))


def test_identity_mismatch_is_rejected(page: Page) -> None:
    page.set_content("<button id='a'>Save</button><button id='b'>Cancel</button>")
    handle_b = page.query_selector("#b")
    assert handle_b is not None
    _, raw_a = raw_of(page, "#a")
    raw_a["attrs"] = {}  # pretend: chosen element is B but the row describes A
    spec = synthesize(page, handle_b, raw_a)
    assert spec is None or spec.build(page).evaluate("(el, t) => el === t", handle_b)


def test_no_role_no_name_no_testid_gives_none(page: Page) -> None:
    page.set_content("<div tabindex='0'></div>")
    handle, raw = raw_of(page, "div")
    assert synthesize(page, handle, raw) is None


def test_chaos_like_page(page: Page) -> None:
    page.set_content(
        "<div id='order-actions'><button id='ord-act-b' class='btn btn-primary'>Confirm order</button>"
        "<button id='cancel-order' data-testid='cancel-order'>Cancel order</button></div>"
    )
    spec = check(page, "#ord-act-b")
    assert spec.code() == "page.get_by_role('button', name='Confirm order', exact=True)"


@pytest.mark.parametrize(
    ("value", "escaped"), [("card-2", "#card-2"), ("1st", "#\\31 st"), ("a.b", "#a\\2e b")]
)
def test_css_escape_id(page: Page, value: str, escaped: str) -> None:
    assert css_escape_id(value) == escaped
    page.evaluate(
        "(v) => { document.body.innerHTML = ''; const d = document.createElement('div'); d.id = v; document.body.appendChild(d); }",
        value,
    )
    assert page.locator(css_escape_id(value)).count() == 1
