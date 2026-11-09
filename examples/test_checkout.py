"""Flow 6: checkout."""

from playwright.sync_api import Page, expect


def test_proceed_to_checkout(page: Page) -> None:
    page.goto("/product/1")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/cart")
    page.click("#checkout-link")
    expect(page).to_have_url("/checkout")
    expect(page.locator("#checkout-summary")).to_have_text("Order total: $89.99")


def test_place_order(page: Page) -> None:
    page.goto("/product/1")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/checkout")
    page.fill("#full-name", "Ada Lovelace")
    page.fill("#email", "ada@example.com")
    page.fill("#address", "12 Analytical Way")
    page.check("#agree")
    page.click("#place-order")
    expect(page).to_have_url("/order/1001")
    expect(page.locator("#order-status")).to_have_text("Status: Pending")


def test_place_order_with_express_shipping(page: Page) -> None:
    page.goto("/product/3")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/checkout")
    page.fill("[data-testid='full-name']", "Grace Hopper")
    page.fill("[data-testid='email']", "grace@example.com")
    page.select_option("#shipping", "express")
    page.check("[data-testid='agree']")
    page.click("[data-testid='place-order']")
    expect(page.locator("#order-total")).to_have_text("Total: $27.99")


def test_checkout_requires_terms(page: Page) -> None:
    page.goto("/product/1")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/checkout")
    page.fill("#full-name", "Alan Turing")
    page.fill("#email", "alan@example.com")
    page.click("text=Place order")
    expect(page.locator("#checkout-status")).to_have_text("Please accept the terms")


def test_checkout_rejects_bad_email(page: Page) -> None:
    page.goto("/product/1")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/checkout")
    page.fill("#full-name", "Alan Turing")
    page.fill("#email", "not-an-email")
    page.check("#agree")
    page.click("#place-order")
    expect(page.locator("#checkout-status")).to_have_text(
        "Please enter your name and a valid email"
    )


def test_uncheck_terms_blocks_order(page: Page) -> None:
    page.goto("/product/1")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/checkout")
    page.fill("#full-name", "Ada Lovelace")
    page.fill("#email", "ada@example.com")
    page.check("#agree")
    page.uncheck("#agree")
    page.click("#place-order")
    expect(page.locator("#checkout-status")).to_have_text("Please accept the terms")
