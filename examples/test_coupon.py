"""Flow 5: coupons on the cart page."""

from playwright.sync_api import Page, expect


def test_apply_valid_coupon(page: Page) -> None:
    page.goto("/product/2")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/cart")
    page.fill("#coupon", "SAVE10")
    page.click("#apply-coupon")
    expect(page.locator("#cart-discount")).to_have_text("Discount: $12.95")
    expect(page.locator("#cart-total")).to_have_text("Total: $116.55")


def test_apply_invalid_coupon(page: Page) -> None:
    page.goto("/product/2")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/cart")
    page.fill("[data-testid='coupon']", "NOTREAL")
    page.click("[data-testid='apply-coupon']")
    expect(page.locator("#coupon-status")).to_have_text("Invalid coupon code")


def test_apply_coupon_by_text(page: Page) -> None:
    page.goto("/product/5")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/cart")
    page.fill("#coupon", "welcome5")
    page.click("text=Apply")
    expect(page.locator("#cart-discount")).to_have_text("Discount: $3.20")
