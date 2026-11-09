"""Selectors that depend on POSITION (broken by layout_move: blocks reordered)."""

from playwright.sync_api import Page, expect


def _cart_with(page: Page, product: int) -> None:
    page.goto(f"/product/{product}")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/cart")


def test_position_add_to_cart(page: Page) -> None:
    page.goto("/product/7")
    page.click("#buy-box > button:nth-child(4)")
    expect(page.locator("#cart-status")).to_have_text("Added to cart (1 in cart)")


def test_position_add_two(page: Page) -> None:
    page.goto("/product/5")
    page.fill("#qty", "2")
    page.click("#buy-box > button:nth-child(4)")
    expect(page.locator("#cart-status")).to_have_text("Added to cart (2 in cart)")


def test_position_wishlist(page: Page) -> None:
    page.goto("/product/8")
    page.click("#buy-box > button:nth-child(6)")
    expect(page.locator("#cart-status")).to_have_text("Added to wishlist")


def test_position_search(page: Page) -> None:
    page.goto("/")
    page.fill("#search", "fleece")
    page.click("#search-form > button:nth-child(3)")
    expect(page.locator("#search-results > li")).to_have_count(1)


def test_position_apply_coupon(page: Page) -> None:
    _cart_with(page, 6)
    page.fill("#coupon", "WELCOME5")
    page.click("#coupon-form > button:nth-child(4)")
    expect(page.locator("#cart-discount")).to_have_text("Discount: $2.75")


def test_position_remove_coupon(page: Page) -> None:
    _cart_with(page, 6)
    page.fill("#coupon", "SAVE10")
    page.click("#apply-coupon")
    expect(page.locator("#cart-discount")).to_have_text("Discount: $5.50")
    page.click("#coupon-form > button:nth-child(6)")
    expect(page.locator("#cart-discount")).to_have_text("Discount: $0.00")


def test_position_remove(page: Page) -> None:
    _cart_with(page, 3)
    page.click("#cart-item-1 > button:nth-child(4)")
    expect(page.locator("#cart-empty")).to_be_visible()


def test_position_save_for_later(page: Page) -> None:
    _cart_with(page, 4)
    page.click("#cart-item-1 > button:nth-child(6)")
    expect(page.locator("#cart-empty")).to_be_visible()
