"""Flows 7 and 8: confirming and cancelling an order."""

from playwright.sync_api import Page, expect


def test_confirm_order(page: Page) -> None:
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
    page.click("#place-order")
    expect(page).to_have_url("/order/1001")
    page.click("#confirm-order")
    expect(page.locator("#order-status")).to_have_text("Status: Confirmed")


def test_cancel_order(page: Page) -> None:
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
    page.click("#place-order")
    expect(page).to_have_url("/order/1001")
    page.click("#cancel-order")
    expect(page.locator("#order-status")).to_have_text("Status: Cancelled")


def test_confirm_order_by_xpath(page: Page) -> None:
    page.goto("/product/4")
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
    page.click("//button[normalize-space()='Confirm order']")
    expect(page.locator("#order-status")).to_have_text("Status: Confirmed")


def test_confirm_order_by_class(page: Page) -> None:
    page.goto("/product/5")
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
    page.locator("#order-actions .btn-primary").click()
    expect(page.locator("#order-status")).to_have_text("Status: Confirmed")


def test_cancel_after_confirm(page: Page) -> None:
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
    page.click("[data-testid='confirm-order']")
    expect(page.locator("#order-status")).to_have_text("Status: Confirmed")
    page.click("[data-testid='cancel-order']")
    expect(page.locator("#order-status")).to_have_text("Status: Cancelled")
