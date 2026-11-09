"""Flows 2 and 4: adding to the cart and managing cart items."""

from playwright.sync_api import Page, expect


def test_add_to_cart(page: Page) -> None:
    page.goto("/product/1")
    page.click("#add-to-cart")
    expect(page.locator("#cart-status")).to_have_text("Added to cart (1 in cart)")


def test_add_to_cart_with_quantity(page: Page) -> None:
    page.goto("/product/3")
    page.fill("#qty", "4")
    page.click("[data-testid='add-to-cart']")
    expect(page.locator("#cart-status")).to_have_text("Added to cart (4 in cart)")


def test_add_to_cart_by_text(page: Page) -> None:
    page.goto("/product/6")
    page.click("text=Add to cart")
    expect(page.locator("#cart-status")).to_contain_text("1 in cart")


def test_add_to_cart_by_class(page: Page) -> None:
    page.goto("/product/8")
    page.locator(".buy-box .btn-primary").click()
    expect(page.locator("#cart-status")).to_contain_text("1 in cart")


def test_add_two_products_then_view_cart(page: Page) -> None:
    page.goto("/product/2")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/product/7")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/cart")
    expect(page.locator("#cart-items > li")).to_have_count(2)
    expect(page.locator("#cart-total")).to_have_text("Total: $162.49")


def test_remove_item_from_cart(page: Page) -> None:
    page.goto("/product/2")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/product/3")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/cart")
    page.click("#remove-1")
    expect(page.locator("#cart-items > li")).to_have_count(1)
    expect(page.locator("#cart-items")).to_contain_text("Merino Wool Socks")


def test_remove_last_item_empties_cart(page: Page) -> None:
    page.goto("/product/5")
    with page.expect_response(
        lambda r: r.url.endswith("/api/cart") and r.request.method == "POST",
        timeout=30_000,
    ):
        page.click("#add-to-cart")
    page.goto("/cart")
    page.click("//button[normalize-space()='Remove']")
    expect(page.locator("#cart-empty")).to_have_text("Your cart is empty.")


def test_quantity_keyboard_entry(page: Page) -> None:
    page.goto("/product/4")
    page.fill("#qty", "")
    page.press("#qty", "3")
    page.click("#add-to-cart")
    expect(page.locator("#cart-status")).to_have_text("Added to cart (3 in cart)")
