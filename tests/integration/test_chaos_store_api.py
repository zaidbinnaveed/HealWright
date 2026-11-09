"""Chaos Store full: every endpoint, session isolation, pages, mutations."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from chaos_store.app import create_app
from chaos_store.state import SESSION_COOKIE

pytestmark = pytest.mark.integration


@pytest.fixture
def app():  # type: ignore[no-untyped-def]
    return create_app(control=True)


class Shopper:
    """One browser-like session against the TestClient."""

    def __init__(self, app: Any) -> None:
        self.c = TestClient(app)
        self.c.get("/")
        self.sid = self.c.cookies[SESSION_COOKIE]

    def actions(self) -> list[str]:
        res = self.c.get("/__chaos/actions", params={"session": self.sid})
        return [a["action_id"] for a in res.json()["actions"]]

    def order(self, **kw: Any) -> int:
        self.c.post("/api/cart", json={"product_id": 1, "qty": 2})
        body = {"name": "Ada Lovelace", "email": "ada@example.com", **kw}
        res = self.c.post("/api/orders", json=body)
        assert res.status_code == 201, res.text
        oid: int = res.json()["id"]
        return oid


# ------------------------------------------------------------------ cart


def test_remove_from_cart(app: Any) -> None:
    s = Shopper(app)
    s.c.post("/api/cart", json={"product_id": 1})
    s.c.post("/api/cart", json={"product_id": 2})
    res = s.c.delete("/api/cart/1")
    assert res.status_code == 200
    assert [i["product_id"] for i in res.json()["items"]] == [2]
    assert s.c.delete("/api/cart/1").status_code == 404
    assert s.actions() == ["add_to_cart", "add_to_cart", "remove_from_cart"]


def test_coupon_valid_and_invalid(app: Any) -> None:
    s = Shopper(app)
    s.c.post("/api/cart", json={"product_id": 2})  # $129.50
    bad = s.c.post("/api/coupon", json={"code": "NOPE"})
    assert bad.status_code == 400
    assert bad.json()["error"] == "Invalid coupon code"
    ok = s.c.post("/api/coupon", json={"code": " save10 "})
    assert ok.status_code == 200
    assert ok.json()["coupon"] == "SAVE10"
    assert ok.json()["discount"] == "$12.95"
    assert ok.json()["total"] == "$116.55"
    assert s.actions() == ["add_to_cart", "apply_coupon"]


def test_save_for_later_moves_item_out_of_cart(app: Any) -> None:
    s = Shopper(app)
    s.c.post("/api/cart", json={"product_id": 1})
    s.c.post("/api/cart", json={"product_id": 2})
    res = s.c.post("/api/cart/1/save")
    assert res.status_code == 200
    assert [i["product_id"] for i in res.json()["items"]] == [2]
    assert s.c.post("/api/cart/1/save").status_code == 404
    assert s.actions() == ["add_to_cart", "add_to_cart", "save_for_later"]


def test_wishlist(app: Any) -> None:
    s = Shopper(app)
    assert s.c.post("/api/wishlist", json={"product_id": 4}).json() == {"wishlist": [4]}
    assert s.c.post("/api/wishlist", json={"product_id": 4}).json() == {"wishlist": [4]}
    assert s.c.post("/api/wishlist", json={"product_id": 99}).status_code == 404
    assert s.actions() == ["add_to_wishlist", "add_to_wishlist"]


def test_remove_coupon(app: Any) -> None:
    s = Shopper(app)
    s.c.post("/api/cart", json={"product_id": 2})
    assert s.c.delete("/api/coupon").status_code == 409  # nothing to remove: not logged
    s.c.post("/api/coupon", json={"code": "SAVE10"})
    res = s.c.delete("/api/coupon")
    assert res.status_code == 200
    assert res.json()["coupon"] is None
    assert res.json()["discount"] == "$0.00"
    assert s.actions() == ["add_to_cart", "apply_coupon", "remove_coupon"]


def test_lookalike_pairs_fire_different_calls(app: Any) -> None:
    """Each distractor pair in the eval set has two controls with different server effects."""
    s = Shopper(app)
    product = s.c.get("/product/1").text
    assert ">Add to cart</button>" in product
    assert ">Add to wishlist</button>" in product
    s.c.post("/api/cart", json={"product_id": 1})
    cart = s.c.get("/cart").text
    for label in (
        ">Remove</button>",
        ">Save for later</button>",
        ">Apply</button>",
        ">Remove coupon</button>",
    ):
        assert label in cart


# ------------------------------------------------------------------ orders


def test_create_order_empties_cart_and_numbers_from_1001(app: Any) -> None:
    s = Shopper(app)
    oid = s.order(shipping="express")
    assert oid == 1001
    page = s.c.get(f"/order/{oid}")
    assert page.status_code == 200
    assert "Order #1001" in page.text
    assert "Status: Pending" in page.text
    assert "$189.97" in page.text  # 2 x 89.99 + 9.99 express
    assert "Your cart is empty." in s.c.get("/cart").text
    assert s.actions() == ["add_to_cart", "create_order"]


def test_create_order_validation(app: Any) -> None:
    s = Shopper(app)
    empty = s.c.post("/api/orders", json={"name": "A", "email": "a@b.c"})
    assert empty.status_code == 409
    s.c.post("/api/cart", json={"product_id": 1})
    assert s.c.post("/api/orders", json={"name": "", "email": "a@b.c"}).status_code == 422
    assert s.c.post("/api/orders", json={"name": "A", "email": "nope"}).status_code == 422
    assert s.actions() == ["add_to_cart"]


def test_confirm_and_cancel_fire_different_calls(app: Any) -> None:
    s = Shopper(app)
    oid = s.order()
    confirm = s.c.post(f"/api/orders/{oid}/confirm")
    assert confirm.json()["status"] == "confirmed"
    assert s.c.post(f"/api/orders/{oid}/confirm").status_code == 409  # not twice
    cancel = s.c.delete(f"/api/orders/{oid}")
    assert cancel.json()["status"] == "cancelled"
    assert s.c.delete(f"/api/orders/{oid}").status_code == 409
    assert s.c.post(f"/api/orders/{oid}/confirm").status_code == 409
    assert s.actions() == ["add_to_cart", "create_order", "confirm_order", "cancel_order"]


def test_orders_are_private_to_their_session(app: Any) -> None:
    a, b = Shopper(app), Shopper(app)
    oid = a.order()
    assert b.c.get(f"/order/{oid}").status_code == 404
    assert b.c.post(f"/api/orders/{oid}/confirm").status_code == 404
    assert b.c.delete(f"/api/orders/{oid}").status_code == 404
    assert b.actions() == []
    assert a.c.get(f"/order/{oid}").status_code == 200


def test_unknown_order_and_item_are_404(app: Any) -> None:
    s = Shopper(app)
    assert s.c.get("/order/999").status_code == 404
    assert s.c.post("/api/orders/999/confirm").status_code == 404
    assert s.c.delete("/api/cart/42").status_code == 404


# ------------------------------------------------------------------ search


def test_search(app: Any) -> None:
    s = Shopper(app)
    res = s.c.get("/api/search", params={"q": "TREK"})
    assert [r["name"] for r in res.json()["results"]] == ["Trekking Poles"]
    gear = s.c.get("/api/search", params={"q": "gear"}).json()["results"]
    assert len(gear) == 4
    assert s.c.get("/api/search", params={"q": ""}).json()["results"] == []
    assert s.actions() == ["search", "search", "search"]


# ------------------------------------------------------------------ pages


def test_cart_page_renders_rows_coupon_and_totals(app: Any) -> None:
    s = Shopper(app)
    s.c.post("/api/cart", json={"product_id": 3, "qty": 2})
    html = s.c.get("/cart").text
    assert 'id="cart-item-1"' in html
    assert 'aria-label="Remove Merino Wool Socks"' in html
    assert '<label class="field-label" for="coupon">Coupon code</label>' in html
    assert "Total: $36.00" in html
    assert 'href="/checkout"' in html


def test_checkout_page_has_labelled_fields(app: Any) -> None:
    s = Shopper(app)
    s.c.post("/api/cart", json={"product_id": 1})
    html = s.c.get("/checkout").text
    for field_id, label in [
        ("full-name", "Full name"),
        ("email", "Email"),
        ("address", "Address"),
        ("shipping", "Shipping"),
        ("agree", "I accept the terms"),
    ]:
        assert f'for="{field_id}">{label}</label>' in html
    assert '<option value="express">Express ($9.99)</option>' in html
    assert ">Place order</button>" in html


def test_product_page_has_hidden_modal(app: Any) -> None:
    html = Shopper(app).c.get("/product/1").text
    assert 'role="dialog" aria-modal="true" hidden="" aria-labelledby="added-modal-title"' in html
    assert ">Continue shopping</button>" in html
    assert ">View cart</a>" in html


def test_empty_checkout_shows_empty_message(app: Any) -> None:
    html = Shopper(app).c.get("/checkout").text
    assert "Your cart is empty." in html
    assert "Place order" not in html


# ------------------------------------------------------------------ mutations and traps


def _set(s: Shopper, yaml_body: str) -> None:
    res = s.c.post("/__chaos/scenario", params={"session": s.sid}, content=yaml_body)
    assert res.status_code == 200, res.text


def test_order_map_reorders_region_and_scripts_follow(app: Any) -> None:
    s = Shopper(app)
    oid = s.order()
    _set(
        s,
        "id: swap\nmutation:\n  order_map: {order_actions: [cancel_order_btn, confirm_order_btn]}\n",
    )
    html = s.c.get(f"/order/{oid}").text
    assert html.index('id="cancel-order"') < html.index('id="confirm-order"')
    # each element is immediately followed by its own binding script
    cancel_at = html.index('id="cancel-order"')
    assert html.index('"cancel_order"', cancel_at) < html.index('id="confirm-order"')


def test_remove_drops_element_and_its_script(app: Any) -> None:
    s = Shopper(app)
    oid = s.order()
    _set(s, "id: gone\nclass: regression_trap\nmutation:\n  remove: [confirm_order_btn]\n")
    html = s.c.get(f"/order/{oid}").text
    assert "confirm-order" not in html
    assert "Confirm order" not in html
    assert '"confirm_order"' not in html
    assert 'id="cancel-order"' in html


def test_removed_target_of_label_drops_for_attribute(app: Any) -> None:
    s = Shopper(app)
    _set(s, "id: nolabel\nmutation:\n  remove: [qty_input]\n")
    html = s.c.get("/product/1").text
    assert '<label class="field-label">Quantity</label>' in html


def test_distractor_trap_shape(app: Any) -> None:
    """Target renamed; identically styled look-alike that fires a different action sits in its place."""
    s = Shopper(app)
    oid = s.order()
    _set(
        s,
        "id: distractor\nclass: distractor_trap\nmutation:\n"
        "  id_map: {confirm_order_btn: ord-act-b}\n"
        "  testid_map: {confirm_order_btn: null}\n"
        "  class_map: {cancel_order_btn: btn btn-primary}\n"
        "  order_map: {order_actions: [cancel_order_btn, confirm_order_btn]}\n",
    )
    html = s.c.get(f"/order/{oid}").text
    assert 'id="confirm-order"' not in html
    assert '<button id="cancel-order" data-testid="cancel-order" class="btn btn-primary"' in html
    assert '<button id="ord-act-b" class="btn btn-primary"' in html


@pytest.mark.parametrize(
    "bad",
    [
        "id: x\nmutation:\n  order_map: {no_region: []}\n",
        "id: x\nmutation:\n  order_map: {order_actions: [add_to_cart_btn]}\n",
        "id: x\nmutation:\n  order_map: {order_actions: [cancel_order_btn, cancel_order_btn]}\n",
        "id: x\nmutation:\n  remove: [nope]\n",
        "id: x\nmutation:\n  tag_map: {add_to_cart_btn: 'div onclick=x'}\n",
    ],
)
def test_invalid_layout_mutations_rejected(app: Any, bad: str) -> None:
    s = Shopper(app)
    assert s.c.post("/__chaos/scenario", content=bad).status_code == 422


def test_tag_to_aria_keeps_handler_binding(app: Any) -> None:
    s = Shopper(app)
    _set(
        s,
        "id: aria\nclass: tag_to_aria\nmutation:\n  tag_map: {add_to_cart_btn: div}\n"
        "  attr_map: {add_to_cart_btn: {type: null, role: button, tabindex: '0'}}\n",
    )
    html = s.c.get("/product/1").text
    start = html.index('role="button" tabindex="0">Add to cart</div>')
    assert html.index('"add_to_cart"', start) - start < 200


def test_enter_binds_the_browser_to_a_session_and_redirects(app: Any) -> None:
    c = TestClient(app)
    res = c.get(
        "/__chaos/enter",
        params={"session": "abcdefghijklmnopqrstuv", "next": "/product/1"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"] == "/product/1"
    assert "cw_session=abcdefghijklmnopqrstuv" in res.headers["set-cookie"]
    assert (
        c.get(
            "/__chaos/enter",
            params={"session": "abcdefghijklmnopqrstuv", "next": "//evil.example"},
            follow_redirects=False,
        ).status_code
        == 400
    )
    assert (
        c.get(
            "/__chaos/enter", params={"session": "x", "next": "/"}, follow_redirects=False
        ).status_code
        == 400
    )


def test_enter_is_absent_without_control() -> None:
    c = TestClient(create_app(control=False))
    assert (
        c.get(
            "/__chaos/enter", params={"session": "abcdefghijklmnopqrstuv"}, follow_redirects=False
        ).status_code
        == 404
    )
