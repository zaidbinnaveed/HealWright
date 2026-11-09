"""In-memory server state, keyed by session id.

Every session has its own cart, coupon, orders, action log entries and
optional scenario override, so a sandbox replay (its own browser context, its
own cookie) can never change the real run's state. All ids are deterministic
per session (cart items from 1, orders from 1001).
"""

from __future__ import annotations

import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from chaos_store.catalog import Product, get_product
from chaos_store.scenario import DEFAULT_SCENARIO, Scenario

SESSION_COOKIE = "cw_session"
SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
COUPONS: dict[str, int] = {"SAVE10": 10, "WELCOME5": 5}  # code -> percent off
EXPRESS_SHIPPING_CENTS = 999

OrderStatus = Literal["pending", "confirmed", "cancelled"]


def new_session_id() -> str:
    return secrets.token_urlsafe(16)


def valid_session_id(value: str | None) -> bool:
    return value is not None and SESSION_ID.match(value) is not None


def money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100}.{cents % 100:02d}"


@dataclass
class CartItem:
    item_id: int
    product: Product
    qty: int

    @property
    def line_cents(self) -> int:
        return self.product.price_cents * self.qty


@dataclass
class Order:
    id: int
    items: list[CartItem]
    subtotal_cents: int
    discount_cents: int
    shipping_cents: int
    shipping: str
    name: str
    email: str
    status: OrderStatus = "pending"

    @property
    def total_cents(self) -> int:
        return self.subtotal_cents - self.discount_cents + self.shipping_cents


@dataclass
class SessionState:
    cart: list[CartItem] = field(default_factory=list)
    saved: list[CartItem] = field(default_factory=list)  # "save for later"
    wishlist: list[int] = field(default_factory=list)  # product ids
    coupon: str | None = None
    orders: dict[int, Order] = field(default_factory=dict)
    scenario: Scenario | None = None  # None = use the server-wide scenario
    next_item_id: int = 1
    next_order_id: int = 1001

    @property
    def subtotal_cents(self) -> int:
        return sum(i.line_cents for i in self.cart)

    @property
    def discount_cents(self) -> int:
        pct = COUPONS.get(self.coupon or "", 0)
        return self.subtotal_cents * pct // 100

    @property
    def total_cents(self) -> int:
        return self.subtotal_cents - self.discount_cents

    @property
    def count(self) -> int:
        return sum(i.qty for i in self.cart)


class StoreError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, SessionState] = {}
        self._log: list[dict[str, Any]] = []
        self._scenario: Scenario = DEFAULT_SCENARIO

    # ---------------------------------------------------------------- sessions
    def session(self, session_id: str) -> SessionState:
        with self._lock:
            return self._sessions.setdefault(session_id, SessionState())

    def scenario_for(self, session_id: str) -> Scenario:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is not None and state.scenario is not None:
                return state.scenario
            return self._scenario

    def set_scenario(self, scenario: Scenario, session_id: str | None) -> None:
        with self._lock:
            if session_id is None:
                self._scenario = scenario
            else:
                self.session(session_id).scenario = scenario

    # ---------------------------------------------------------------- action log
    def log_action(self, session_id: str, action_id: str) -> None:
        with self._lock:
            self._log.append({"session": session_id, "action_id": action_id, "ts": time.time()})

    def actions(self, session_id: str | None) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(entry)
                for entry in self._log
                if session_id is None or entry["session"] == session_id
            ]

    # ---------------------------------------------------------------- reset
    def reset(self, session_id: str | None) -> None:
        with self._lock:
            if session_id is None:
                self._sessions.clear()
                self._log.clear()
                self._scenario = DEFAULT_SCENARIO
            else:
                self._sessions.pop(session_id, None)
                self._log = [e for e in self._log if e["session"] != session_id]

    # ---------------------------------------------------------------- cart
    def add_to_cart(self, session_id: str, product_id: int, qty: int) -> SessionState:
        product = get_product(product_id)
        if product is None:
            raise StoreError(404, "unknown product")
        with self._lock:
            state = self.session(session_id)
            state.cart.append(CartItem(state.next_item_id, product, qty))
            state.next_item_id += 1
            self.log_action(session_id, "add_to_cart")
            return state

    def remove_from_cart(self, session_id: str, item_id: int) -> SessionState:
        with self._lock:
            state = self.session(session_id)
            kept = [i for i in state.cart if i.item_id != item_id]
            if len(kept) == len(state.cart):
                raise StoreError(404, "unknown cart item")
            state.cart = kept
            self.log_action(session_id, "remove_from_cart")
            return state

    def save_for_later(self, session_id: str, item_id: int) -> SessionState:
        with self._lock:
            state = self.session(session_id)
            item = next((i for i in state.cart if i.item_id == item_id), None)
            if item is None:
                raise StoreError(404, "unknown cart item")
            state.cart.remove(item)
            state.saved.append(item)
            self.log_action(session_id, "save_for_later")
            return state

    def add_to_wishlist(self, session_id: str, product_id: int) -> SessionState:
        if get_product(product_id) is None:
            raise StoreError(404, "unknown product")
        with self._lock:
            state = self.session(session_id)
            if product_id not in state.wishlist:
                state.wishlist.append(product_id)
            self.log_action(session_id, "add_to_wishlist")
            return state

    def remove_coupon(self, session_id: str) -> SessionState:
        with self._lock:
            state = self.session(session_id)
            if state.coupon is None:
                raise StoreError(409, "No coupon applied")
            state.coupon = None
            self.log_action(session_id, "remove_coupon")
            return state

    def apply_coupon(self, session_id: str, code: str) -> SessionState:
        code = code.strip().upper()
        if code not in COUPONS:
            raise StoreError(400, "Invalid coupon code")
        with self._lock:
            state = self.session(session_id)
            state.coupon = code
            self.log_action(session_id, "apply_coupon")
            return state

    # ---------------------------------------------------------------- orders
    def create_order(self, session_id: str, name: str, email: str, shipping: str) -> Order:
        with self._lock:
            state = self.session(session_id)
            if not state.cart:
                raise StoreError(409, "Your cart is empty")
            order = Order(
                id=state.next_order_id,
                items=list(state.cart),
                subtotal_cents=state.subtotal_cents,
                discount_cents=state.discount_cents,
                shipping_cents=EXPRESS_SHIPPING_CENTS if shipping == "express" else 0,
                shipping=shipping,
                name=name,
                email=email,
            )
            state.orders[order.id] = order
            state.next_order_id += 1
            state.cart = []
            state.coupon = None
            self.log_action(session_id, "create_order")
            return order

    def order(self, session_id: str, order_id: int) -> Order:
        with self._lock:
            order = self.session(session_id).orders.get(order_id)
            if order is None:
                raise StoreError(404, "unknown order")
            return order

    def confirm_order(self, session_id: str, order_id: int) -> Order:
        with self._lock:
            order = self.order(session_id, order_id)
            if order.status != "pending":
                raise StoreError(409, f"Order is {order.status}")
            order.status = "confirmed"
            self.log_action(session_id, "confirm_order")
            return order

    def cancel_order(self, session_id: str, order_id: int) -> Order:
        with self._lock:
            order = self.order(session_id, order_id)
            if order.status == "cancelled":
                raise StoreError(409, "Order is cancelled")
            order.status = "cancelled"
            self.log_action(session_id, "cancel_order")
            return order

    # ---------------------------------------------------------------- search
    def search(self, session_id: str, query: str, products: tuple[Product, ...]) -> list[Product]:
        q = query.strip().casefold()
        hits = [p for p in products if q and (q in p.name.casefold() or q in p.category)]
        self.log_action(session_id, "search")
        return hits
