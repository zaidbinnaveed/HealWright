"""Selectors that depend on CLASS names (broken by css_refactor)."""

from playwright.sync_api import Page, expect


def _cart_with(page: Page, product: int) -> None:
    page.goto(f"/product/{product}")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/cart")


def _order(page: Page) -> None:
    page.goto("/product/6")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/checkout")
    page.fill("#full-name", "Alan Turing")
    page.fill("#email", "alan@example.com")
    page.check("#agree")
    page.click("#place-order")
    expect(page).to_have_url("/order/1001")


def test_class_wishlist(page: Page) -> None:
    page.goto("/product/4")
    page.click(".buy-box .btn-secondary")
    expect(page.locator("#cart-status")).to_have_text("Added to wishlist")


def test_class_remove(page: Page) -> None:
    _cart_with(page, 8)
    page.click(".cart-row .btn-link[aria-label^='Remove']")
    expect(page.locator("#cart-empty")).to_be_visible()


def test_class_save_for_later(page: Page) -> None:
    _cart_with(page, 7)
    page.click(".cart-row .btn-link[aria-label^='Save']")
    expect(page.locator("#cart-empty")).to_be_visible()


def test_class_apply_coupon(page: Page) -> None:
    _cart_with(page, 3)
    page.fill("#coupon", "SAVE10")
    page.click(".coupon .btn-secondary")
    expect(page.locator("#cart-discount")).to_have_text("Discount: $1.80")


def test_class_remove_coupon(page: Page) -> None:
    _cart_with(page, 3)
    page.fill("#coupon", "SAVE10")
    page.click("#apply-coupon")
    expect(page.locator("#cart-discount")).to_have_text("Discount: $1.80")
    page.click(".coupon .btn-link")
    expect(page.locator("#cart-discount")).to_have_text("Discount: $0.00")


def test_class_place_order(page: Page) -> None:
    page.goto("/product/2")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/checkout")
    page.fill("#full-name", "Ada Lovelace")
    page.fill("#email", "ada@example.com")
    page.check("#agree")
    page.click(".form-grid .btn-primary")
    expect(page).to_have_url("/order/1001")


def test_class_cancel(page: Page) -> None:
    _order(page)
    page.click(".actions .btn-danger")
    expect(page.locator("#order-status")).to_have_text("Status: Cancelled")
