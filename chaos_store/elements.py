"""Default (unmutated) element specs and layout regions, keyed by stable keys.

Placeholders such as ``{pid}`` and ``{name}`` are filled at render time from
server data. Scenario YAML files refer to these keys in their mutation maps.

``action``, ``bind_args``, ``ref`` and ``ref_attrs`` are server-side only: they
decide which JS handler is attached and which attributes point at other
elements' (possibly renamed) ids. They are never rendered as attributes, so
the DOM carries no "answer". The element key is the true
identity of a control; a mutation can restyle, rename, re-tag, move or remove
it, but never change what it does.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ElementSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tag: str = Field(pattern=r"^[a-z][a-z0-9]{0,15}$")
    id: str | None = None
    testid: str | None = None
    classes: str = ""
    text: str | None = None
    attrs: dict[str, str] = Field(default_factory=dict)
    # --- server-side only (never rendered as attributes)
    action: str | None = None  # JS handler bound to this element
    bind_args: tuple[str, ...] = ()  # render-context keys passed to the handler
    ref: str | None = None  # name under which JS can find this element
    ref_attrs: dict[str, str] = Field(default_factory=dict)  # attr -> key whose id it points at


def _e(tag: str, **kw: object) -> ElementSpec:
    return ElementSpec(tag=tag, **kw)  # type: ignore[arg-type]


BTN = {"type": "button"}

DEFAULT_ELEMENTS: dict[str, ElementSpec] = {
    # ------------------------------------------------------------ layout (every page)
    "site_header": _e("header", classes="site-header"),
    "site_brand": _e("a", id="brand", classes="brand", text="Chaos Wear", attrs={"href": "/"}),
    "site_nav": _e("nav", classes="site-nav", attrs={"aria-label": "Main"}),
    "nav_home_link": _e(
        "a", id="nav-home", testid="nav-home", classes="nav-link", text="Shop", attrs={"href": "/"}
    ),
    "nav_cart_link": _e(
        "a",
        id="nav-cart",
        testid="nav-cart",
        classes="nav-link",
        text="Cart",
        attrs={"href": "/cart"},
    ),
    "main": _e("main", id="main", classes="container"),
    # ------------------------------------------------------------ catalog + search
    "catalog_title": _e("h1", classes="page-title", text="Products"),
    "search_form": _e(
        "form",
        id="search-form",
        classes="search",
        attrs={"role": "search", "onsubmit": "return false"},
    ),
    "search_input": _e(
        "input",
        id="search",
        testid="search-input",
        classes="field-input field-input--wide",
        attrs={"type": "search", "name": "q", "placeholder": "Search products"},
        ref="search_q",
    ),
    "search_btn": _e(
        "button",
        id="search-btn",
        testid="search-btn",
        classes="btn btn-secondary",
        text="Search",
        attrs=BTN,
        action="search",
    ),
    "search_results": _e(
        "ul",
        id="search-results",
        classes="search-results",
        attrs={"aria-live": "polite", "aria-label": "Search results"},
        ref="search_results",
    ),
    "product_grid": _e("ul", id="product-grid", classes="product-grid"),
    "product_card": _e(
        "li", id="product-card-{pid}", testid="product-card-{pid}", classes="product-card"
    ),
    "product_card_name": _e("h2", classes="product-card__name", text="{name}"),
    "product_card_price": _e("span", classes="product-card__price price", text="{price}"),
    "product_card_link": _e(
        "a",
        id="view-product-{pid}",
        testid="view-product-{pid}",
        classes="btn btn-secondary",
        text="View details",
        attrs={"href": "/product/{pid}"},
    ),
    # ------------------------------------------------------------ product page
    "product_title": _e("h1", id="product-title", classes="page-title", text="{name}"),
    "product_price": _e("p", id="product-price", classes="price price--large", text="{price}"),
    "product_description": _e("p", classes="product-description", text="{description}"),
    "buy_box": _e("form", id="buy-box", classes="buy-box", attrs={"onsubmit": "return false"}),
    "qty_label": _e(
        "label", classes="field-label", text="Quantity", ref_attrs={"for": "qty_input"}
    ),
    "qty_input": _e(
        "input",
        id="qty",
        testid="qty",
        classes="field-input",
        attrs={"type": "number", "name": "qty", "min": "1", "max": "10", "value": "1"},
        ref="qty",
    ),
    "add_to_cart_btn": _e(
        "button",
        id="add-to-cart",
        testid="add-to-cart",
        classes="btn btn-primary",
        text="Add to cart",
        attrs=BTN,
        action="add_to_cart",
        bind_args=("pid",),
    ),
    "wishlist_btn": _e(
        "button",
        id="add-to-wishlist",
        testid="add-to-wishlist",
        classes="btn btn-secondary",
        text="Add to wishlist",
        attrs=BTN,
        action="add_to_wishlist",
        bind_args=("pid",),
    ),
    "cart_status": _e(
        "p",
        id="cart-status",
        classes="status",
        attrs={"role": "status", "aria-live": "polite"},
        ref="status",
    ),
    "back_link": _e(
        "a", id="back-to-shop", classes="link", text="Back to products", attrs={"href": "/"}
    ),
    # ------------------------------------------------------------ "Item added" modal
    "added_modal": _e(
        "div",
        id="added-modal",
        classes="modal",
        attrs={"role": "dialog", "aria-modal": "true", "hidden": ""},
        ref="modal",
        ref_attrs={"aria-labelledby": "added_modal_title"},
    ),
    "added_modal_title": _e(
        "h2", id="added-modal-title", classes="modal__title", text="Item added"
    ),
    "added_modal_text": _e("p", classes="modal__text", text="The item is in your cart."),
    "modal_continue_btn": _e(
        "button",
        id="continue-shopping",
        testid="continue-shopping",
        classes="btn btn-secondary",
        text="Continue shopping",
        attrs=BTN,
        action="close_modal",
    ),
    "modal_view_cart_link": _e(
        "a",
        id="view-cart",
        testid="view-cart",
        classes="btn btn-primary",
        text="View cart",
        attrs={"href": "/cart"},
    ),
    # ------------------------------------------------------------ cart page
    "cart_title": _e("h1", classes="page-title", text="Your cart"),
    "cart_empty": _e("p", id="cart-empty", classes="muted", text="Your cart is empty."),
    "cart_list": _e("ul", id="cart-items", classes="cart-list"),
    "cart_row": _e("li", id="cart-item-{item}", testid="cart-item-{item}", classes="cart-row"),
    "cart_item_name": _e("span", classes="cart-row__name", text="{name}"),
    "cart_item_qty": _e("span", classes="cart-row__qty", text="Qty {qty}"),
    "cart_item_price": _e("span", classes="cart-row__price price", text="{line_total}"),
    "cart_remove_btn": _e(
        "button",
        id="remove-{item}",
        testid="remove-{item}",
        classes="btn btn-link",
        text="Remove",
        attrs={"type": "button", "aria-label": "Remove {name}"},
        action="remove_from_cart",
        bind_args=("item",),
    ),
    "cart_save_btn": _e(
        "button",
        id="save-{item}",
        testid="save-{item}",
        classes="btn btn-link",
        text="Save for later",
        attrs={"type": "button", "aria-label": "Save {name} for later"},
        action="save_for_later",
        bind_args=("item",),
    ),
    "coupon_form": _e(
        "form", id="coupon-form", classes="coupon", attrs={"onsubmit": "return false"}
    ),
    "coupon_label": _e(
        "label", classes="field-label", text="Coupon code", ref_attrs={"for": "coupon_input"}
    ),
    "coupon_input": _e(
        "input",
        id="coupon",
        testid="coupon",
        classes="field-input field-input--wide",
        attrs={"type": "text", "name": "coupon", "autocomplete": "off"},
        ref="coupon",
    ),
    "coupon_apply_btn": _e(
        "button",
        id="apply-coupon",
        testid="apply-coupon",
        classes="btn btn-secondary",
        text="Apply",
        attrs=BTN,
        action="apply_coupon",
    ),
    "coupon_remove_btn": _e(
        "button",
        id="remove-coupon",
        testid="remove-coupon",
        classes="btn btn-link",
        text="Remove coupon",
        attrs=BTN,
        action="remove_coupon",
    ),
    "coupon_status": _e(
        "p",
        id="coupon-status",
        classes="status",
        attrs={"role": "status", "aria-live": "polite"},
        ref="coupon_status",
    ),
    "cart_subtotal": _e("p", id="cart-subtotal", classes="totals", text="Subtotal: {subtotal}"),
    "cart_discount": _e("p", id="cart-discount", classes="totals", text="Discount: {discount}"),
    "cart_total": _e("p", id="cart-total", classes="totals totals--strong", text="Total: {total}"),
    "checkout_link": _e(
        "a",
        id="checkout-link",
        testid="checkout-link",
        classes="btn btn-primary",
        text="Proceed to checkout",
        attrs={"href": "/checkout"},
    ),
    # ------------------------------------------------------------ checkout page
    "checkout_title": _e("h1", classes="page-title", text="Checkout"),
    "checkout_form": _e(
        "form", id="checkout-form", classes="form-grid", attrs={"onsubmit": "return false"}
    ),
    "name_label": _e(
        "label", classes="field-label", text="Full name", ref_attrs={"for": "name_input"}
    ),
    "name_input": _e(
        "input",
        id="full-name",
        testid="full-name",
        classes="field-input field-input--wide",
        attrs={"type": "text", "name": "name", "autocomplete": "name"},
        ref="ship_name",
    ),
    "email_label": _e(
        "label", classes="field-label", text="Email", ref_attrs={"for": "email_input"}
    ),
    "email_input": _e(
        "input",
        id="email",
        testid="email",
        classes="field-input field-input--wide",
        attrs={"type": "email", "name": "email", "autocomplete": "email"},
        ref="email",
    ),
    "address_label": _e(
        "label", classes="field-label", text="Address", ref_attrs={"for": "address_input"}
    ),
    "address_input": _e(
        "textarea",
        id="address",
        testid="address",
        classes="field-input field-input--wide",
        attrs={"name": "address", "rows": "2"},
        ref="address",
    ),
    "shipping_label": _e(
        "label", classes="field-label", text="Shipping", ref_attrs={"for": "shipping_select"}
    ),
    "shipping_select": _e(
        "select",
        id="shipping",
        testid="shipping",
        classes="field-input",
        attrs={"name": "shipping"},
        ref="shipping",
    ),
    "shipping_opt_standard": _e("option", text="Standard (free)", attrs={"value": "standard"}),
    "shipping_opt_express": _e("option", text="Express ($9.99)", attrs={"value": "express"}),
    "agree_input": _e(
        "input",
        id="agree",
        testid="agree",
        classes="checkbox",
        attrs={"type": "checkbox", "name": "agree"},
        ref="agree",
    ),
    "agree_label": _e(
        "label", classes="field-label", text="I accept the terms", ref_attrs={"for": "agree_input"}
    ),
    "checkout_summary": _e(
        "p", id="checkout-summary", classes="totals", text="Order total: {total}"
    ),
    "place_order_btn": _e(
        "button",
        id="place-order",
        testid="place-order",
        classes="btn btn-primary",
        text="Place order",
        attrs=BTN,
        action="place_order",
    ),
    "checkout_status": _e(
        "p",
        id="checkout-status",
        classes="status status--error",
        attrs={"role": "alert"},
        ref="checkout_status",
    ),
    # ------------------------------------------------------------ order page
    "order_title": _e("h1", id="order-title", classes="page-title", text="Order #{oid}"),
    "order_status": _e(
        "p",
        id="order-status",
        classes="status",
        text="Status: {status}",
        attrs={"role": "status", "aria-live": "polite"},
        ref="order_status",
    ),
    "order_items": _e("ul", id="order-items", classes="order-items"),
    "order_item": _e("li", classes="order-item", text="{qty} x {name}"),
    "order_total": _e(
        "p", id="order-total", classes="totals totals--strong", text="Total: {total}"
    ),
    "order_actions": _e("div", id="order-actions", classes="actions"),
    "confirm_order_btn": _e(
        "button",
        id="confirm-order",
        testid="confirm-order",
        classes="btn btn-primary",
        text="Confirm order",
        attrs=BTN,
        action="confirm_order",
        bind_args=("oid",),
    ),
    "cancel_order_btn": _e(
        "button",
        id="cancel-order",
        testid="cancel-order",
        classes="btn btn-danger",
        text="Cancel order",
        attrs=BTN,
        action="cancel_order",
        bind_args=("oid",),
    ),
    "order_back_link": _e(
        "a", id="order-back", classes="link", text="Continue shopping", attrs={"href": "/"}
    ),
}

# Ordered children of layout regions. ``Mutation.order_map`` may reorder or drop
# keys within a region (layout_move, distractor_trap); it may not add new keys.
DEFAULT_REGIONS: dict[str, tuple[str, ...]] = {
    "nav": ("nav_home_link", "nav_cart_link"),
    "search": ("search_input", "search_btn"),
    "card": ("product_card_name", "product_card_price", "product_card_link"),
    "product_info": ("product_title", "product_price", "product_description"),
    "buy_box": ("qty_label", "qty_input", "add_to_cart_btn", "wishlist_btn"),
    "modal_actions": ("modal_continue_btn", "modal_view_cart_link"),
    "cart_row": (
        "cart_item_name",
        "cart_item_qty",
        "cart_item_price",
        "cart_remove_btn",
        "cart_save_btn",
    ),
    "coupon": ("coupon_label", "coupon_input", "coupon_apply_btn", "coupon_remove_btn"),
    "cart_totals": ("cart_subtotal", "cart_discount", "cart_total"),
    "checkout_fields": (
        "name_label",
        "name_input",
        "email_label",
        "email_input",
        "address_label",
        "address_input",
        "shipping_label",
        "shipping_select",
    ),
    "agree": ("agree_input", "agree_label"),
    "order_actions": ("confirm_order_btn", "cancel_order_btn"),
}
