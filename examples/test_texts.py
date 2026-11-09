"""Selectors that depend on visible TEXT (broken by copy_drift and i18n)."""

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
    page.goto("/product/8")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/checkout")
    page.fill("#full-name", "Grace Hopper")
    page.fill("#email", "grace@example.com")
    page.check("#agree")
    page.click("#place-order")
    expect(page).to_have_url("/order/1001")


def test_text_wishlist(page: Page) -> None:
    page.goto("/product/6")
    page.click("text=Add to wishlist")
    expect(page.locator("#cart-status")).to_have_text("Added to wishlist")


def test_text_save_for_later(page: Page) -> None:
    _cart_with(page, 2)
    page.click("text=Save for later")
    expect(page.locator("#cart-empty")).to_be_visible()


def test_text_remove_coupon(page: Page) -> None:
    _cart_with(page, 5)
    page.fill("#coupon", "SAVE10")
    page.click("#apply-coupon")
    expect(page.locator("#cart-discount")).to_have_text("Discount: $6.40")
    page.click("text=Remove coupon")
    expect(page.locator("#cart-discount")).to_have_text("Discount: $0.00")


def test_text_cancel(page: Page) -> None:
    _order(page)
    page.click("text=Cancel order")
    expect(page.locator("#order-status")).to_have_text("Status: Cancelled")


def test_text_confirm(page: Page) -> None:
    _order(page)
    page.click("text=Confirm order")
    expect(page.locator("#order-status")).to_have_text("Status: Confirmed")


def test_text_place_order(page: Page) -> None:
    page.goto("/product/4")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/checkout")
    page.fill("#full-name", "Ada Lovelace")
    page.fill("#email", "ada@example.com")
    page.check("#agree")
    page.click("//button[normalize-space()='Place order']")
    expect(page).to_have_url("/order/1001")
