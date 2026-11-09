"""Selectors that depend on the TAG (broken by tag_to_aria: <button> -> <div role=button>)."""

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
    page.goto("/product/3")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/checkout")
    page.fill("#full-name", "Ada Lovelace")
    page.fill("#email", "ada@example.com")
    page.check("#agree")
    page.click("#place-order")
    expect(page).to_have_url("/order/1001")


def test_tag_add_to_cart(page: Page) -> None:
    page.goto("/product/1")
    page.click("button:has-text('Add to cart')")
    expect(page.locator("#cart-status")).to_have_text("Added to cart (1 in cart)")


def test_tag_add_to_wishlist(page: Page) -> None:
    page.goto("/product/2")
    page.click("#buy-box button:has-text('Add to wishlist')")
    expect(page.locator("#cart-status")).to_have_text("Added to wishlist")


def test_tag_remove(page: Page) -> None:
    _cart_with(page, 4)
    page.click("#cart-item-1 button:has-text('Remove')")
    expect(page.locator("#cart-empty")).to_be_visible()


def test_tag_save_for_later(page: Page) -> None:
    _cart_with(page, 5)
    page.click("#cart-item-1 button:has-text('Save for later')")
    expect(page.locator("#cart-empty")).to_be_visible()


def test_tag_apply_coupon(page: Page) -> None:
    _cart_with(page, 2)
    page.fill("#coupon", "SAVE10")
    page.click("#coupon-form button:has-text('Apply')")
    expect(page.locator("#cart-discount")).to_have_text("Discount: $12.95")


def test_tag_place_order(page: Page) -> None:
    page.goto("/product/1")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/checkout")
    page.fill("#full-name", "Grace Hopper")
    page.fill("#email", "grace@example.com")
    page.check("#agree")
    page.click("#checkout-form button")
    expect(page).to_have_url("/order/1001")


def test_tag_confirm(page: Page) -> None:
    _order(page)
    page.click("#order-actions button:has-text('Confirm order')")
    expect(page.locator("#order-status")).to_have_text("Status: Confirmed")


def test_tag_cancel(page: Page) -> None:
    _order(page)
    page.click("#order-actions button:has-text('Cancel order')")
    expect(page.locator("#order-status")).to_have_text("Status: Cancelled")


def test_tag_search(page: Page) -> None:
    page.goto("/")
    page.fill("#search", "poles")
    page.click("#search-form button")
    expect(page.locator("#search-results > li")).to_have_count(1)
