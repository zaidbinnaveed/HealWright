"""Flow 9: product search."""

from playwright.sync_api import Page, expect


def test_search_by_button(page: Page) -> None:
    page.goto("/")
    page.fill("#search", "jacket")
    page.click("#search-btn")
    expect(page.locator("#search-results > li")).to_have_text(["Waterproof Jacket $129.50"])


def test_search_by_enter(page: Page) -> None:
    page.goto("/")
    page.fill("[data-testid='search-input']", "socks")
    page.press("[data-testid='search-input']", "Enter")
    expect(page.locator("#search-results > li")).to_have_count(1)


def test_search_category(page: Page) -> None:
    page.goto("/")
    page.fill("#search", "gear")
    page.click("text=Search")
    expect(page.locator("#search-results > li")).to_have_count(4)


def test_search_no_results(page: Page) -> None:
    page.goto("/")
    page.fill("#search", "zzz")
    page.locator("#search-form .btn-secondary").click()
    expect(page.locator("#search-results")).to_have_text("No products found")
