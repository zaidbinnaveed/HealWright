"""Flow 1: browsing the catalog and product pages."""

from playwright.sync_api import Page, expect


def test_open_product_from_catalog(page: Page) -> None:
    page.goto("/")
    page.click("#view-product-2")
    expect(page).to_have_url("/product/2")
    expect(page.locator("#product-title")).to_have_text("Waterproof Jacket")


def test_open_product_by_card_link(page: Page) -> None:
    page.goto("/")
    page.locator("[data-testid='product-card-5'] a.btn-secondary").click()
    expect(page.locator("h1")).to_have_text("Daypack 20L")


def test_open_product_by_xpath(page: Page) -> None:
    page.goto("/")
    page.click("//li[@id='product-card-7']//a[normalize-space()='View details']")
    expect(page.locator("#product-price")).to_have_text("$32.99")


def test_back_to_products(page: Page) -> None:
    page.goto("/product/4")
    page.click("text=Back to products")
    expect(page).to_have_url("/")
    expect(page.locator("#product-grid > li")).to_have_count(8)


def test_hover_product_card_link(page: Page) -> None:
    page.goto("/")
    page.hover("#view-product-1")
    page.click("#view-product-1")
    expect(page.locator("#product-title")).to_have_text("Trail Running Shoes")
