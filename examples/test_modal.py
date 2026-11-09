"""Flow 3: the "Item added" dialog."""

from playwright.sync_api import Page, expect


def test_modal_appears_after_add(page: Page) -> None:
    page.goto("/product/1")
    page.click("#add-to-cart")
    expect(page.locator("#added-modal")).to_be_visible()


def test_continue_shopping_closes_modal(page: Page) -> None:
    page.goto("/product/2")
    page.click("#add-to-cart")
    page.click("#continue-shopping")
    expect(page.locator("#added-modal")).to_be_hidden()


def test_view_cart_from_modal(page: Page) -> None:
    page.goto("/product/3")
    page.click("#add-to-cart")
    page.click("[data-testid='view-cart']")
    expect(page).to_have_url("/cart")
    expect(page.locator("#cart-items > li")).to_have_count(1)


def test_continue_shopping_by_text(page: Page) -> None:
    page.goto("/product/4")
    page.click("#add-to-cart")
    page.click("text=Continue shopping")
    expect(page.locator("#added-modal")).to_be_hidden()
