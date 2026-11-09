"""Flow 10: site navigation."""

from playwright.sync_api import Page, expect


def test_nav_to_cart(page: Page) -> None:
    page.goto("/product/1")
    page.click("#nav-cart")
    expect(page).to_have_url("/cart")
    expect(page.locator("#cart-empty")).to_be_visible()


def test_nav_home_from_cart(page: Page) -> None:
    page.goto("/cart")
    page.click("[data-testid='nav-home']")
    expect(page).to_have_url("/")


def test_brand_link_goes_home(page: Page) -> None:
    page.goto("/product/3")
    page.click("#brand")
    expect(page.locator("h1")).to_have_text("Products")


def test_nav_by_text_after_hover(page: Page) -> None:
    page.goto("/")
    page.hover("text=Cart")
    page.click("text=Cart")
    expect(page).to_have_url("/cart")
