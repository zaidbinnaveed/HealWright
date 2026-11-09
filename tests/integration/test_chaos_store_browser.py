"""Chaos Store in a real Chromium: the inline-bound JS handlers work and log actions."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.conftest import LiveStore

pytestmark = pytest.mark.integration


def _session(page: Page) -> str:
    cookies = {c["name"]: c["value"] for c in page.context.cookies()}
    return cookies["cw_session"]


def test_add_to_cart_in_browser_logs_action(page: Page, store: LiveStore) -> None:
    page.goto(f"{store.base_url}/product/2")
    page.fill("#qty", "3")
    page.click("#add-to-cart")
    expect(page.locator("#cart-status")).to_have_text("Added to cart (3 in cart)")
    actions = store.actions(_session(page))
    assert [a["action_id"] for a in actions] == ["add_to_cart"]


def test_handler_survives_tag_and_id_mutation(page: Page, store: LiveStore) -> None:
    store.set_scenario(
        "id: browser-tag-swap\nmutation:\n"
        "  tag_map: {add_to_cart_btn: div}\n"
        "  id_map: {add_to_cart_btn: zz-1, qty_input: null}\n"
        "  attr_map: {add_to_cart_btn: {type: null, role: button, tabindex: '0'}}\n"
    )
    page.goto(f"{store.base_url}/product/1")
    assert page.locator("#add-to-cart").count() == 0
    page.get_by_role("button", name="Add to cart").press("Enter")
    expect(page.get_by_role("status")).to_have_text("Added to cart (1 in cart)")
    assert [a["action_id"] for a in store.actions(_session(page))] == ["add_to_cart"]


def _ids(store: LiveStore, page: Page) -> list[object]:
    return [a["action_id"] for a in store.actions(_session(page))]


def test_item_added_modal_opens_and_closes(page: Page, store: LiveStore) -> None:
    page.goto(f"{store.base_url}/product/3")
    dialog = page.get_by_role("dialog", name="Item added")
    expect(dialog).to_be_hidden()
    page.click("#add-to-cart")
    expect(dialog).to_be_visible()
    page.click("#continue-shopping")
    expect(dialog).to_be_hidden()
    page.click("#add-to-cart")
    page.click("#view-cart")
    expect(page).to_have_url(f"{store.base_url}/cart")
    expect(page.locator("#cart-items li")).to_have_count(2)


def _checkout(page: Page, store: LiveStore) -> None:
    page.goto(f"{store.base_url}/product/1")
    page.click("#add-to-cart")
    page.goto(f"{store.base_url}/checkout")
    page.fill("#full-name", "Ada Lovelace")
    page.fill("#email", "ada@example.com")
    page.select_option("#shipping", "express")
    page.check("#agree")
    page.click("#place-order")
    expect(page).to_have_url(f"{store.base_url}/order/1001")


def test_checkout_requires_terms(page: Page, store: LiveStore) -> None:
    page.goto(f"{store.base_url}/product/1")
    page.click("#add-to-cart")
    page.goto(f"{store.base_url}/checkout")
    page.fill("#full-name", "Ada")
    page.fill("#email", "ada@example.com")
    page.click("#place-order")
    expect(page.get_by_role("alert")).to_have_text("Please accept the terms")
    assert _ids(store, page) == ["add_to_cart"]


def test_place_order_then_confirm(page: Page, store: LiveStore) -> None:
    _checkout(page, store)
    expect(page.locator("#order-total")).to_have_text("Total: $99.98")
    page.click("#confirm-order")
    expect(page.locator("#order-status")).to_have_text("Status: Confirmed")
    assert _ids(store, page) == ["add_to_cart", "create_order", "confirm_order"]


def test_cancel_fires_a_different_call_than_confirm(page: Page, store: LiveStore) -> None:
    _checkout(page, store)
    with page.expect_request(lambda r: r.method == "DELETE") as req:
        page.click("#cancel-order")
    assert req.value.url.endswith("/api/orders/1001")
    expect(page.locator("#order-status")).to_have_text("Status: Cancelled")
    assert _ids(store, page) == ["add_to_cart", "create_order", "cancel_order"]


def test_remove_and_coupon_on_cart_page(page: Page, store: LiveStore) -> None:
    page.goto(f"{store.base_url}/product/2")
    page.click("#add-to-cart")
    page.goto(f"{store.base_url}/product/4")
    page.click("#add-to-cart")
    page.goto(f"{store.base_url}/cart")
    page.fill("#coupon", "BOGUS")
    page.click("#apply-coupon")
    expect(page.locator("#coupon-status")).to_have_text("Invalid coupon code")
    page.fill("#coupon", "SAVE10")
    page.click("#apply-coupon")
    expect(page.locator("#cart-discount")).to_have_text("Discount: $15.40")
    page.click("#remove-1")
    expect(page.locator("#cart-items li")).to_have_count(1)
    expect(page.locator("#cart-total")).to_have_text("Total: $22.05")
    assert _ids(store, page) == ["add_to_cart", "add_to_cart", "apply_coupon", "remove_from_cart"]


def test_search_renders_results(page: Page, store: LiveStore) -> None:
    page.goto(store.base_url + "/")
    page.fill("#search", "jacket")
    page.click("#search-btn")
    expect(page.locator("#search-results li")).to_have_text(["Waterproof Jacket $129.50"])
    page.fill("#search", "zzz")
    page.press("#search", "Enter")
    expect(page.locator("#search-results li")).to_have_text(["No products found"])
    assert _ids(store, page) == ["search", "search"]


def test_two_contexts_have_separate_sessions(page: Page, store: LiveStore) -> None:
    page.goto(f"{store.base_url}/product/1")
    other = page.context.browser.new_context()  # type: ignore[union-attr]
    try:
        other_page = other.new_page()
        other_page.goto(f"{store.base_url}/product/1")
        other_page.click("#add-to-cart")
        expect(other_page.locator("#cart-status")).to_contain_text("1 in cart")
        assert store.actions(_session(page)) == []
        assert len(store.actions(_session(other_page))) == 1
    finally:
        other.close()
