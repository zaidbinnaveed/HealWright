"""Chaos Store: the HealWright testbed (FastAPI + Jinja2 + vanilla JS).

Run: ``uv run uvicorn chaos_store.app:app --port 8001``
Control routes (``/__chaos/*``) are mounted only when ``CHAOS_CONTROL=1``.

Every state-changing API handler appends ``{session, action_id, ts}`` to the
action log when the action takes effect; that log is the benchmark's ground
truth. This package is a black-box testbed: it must never import ``healwright``.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from chaos_store.catalog import PRODUCTS, get_product
from chaos_store.scenario import Renderer, Scenario, load_scenario, parse_scenario_yaml
from chaos_store.state import (
    SESSION_COOKIE,
    Order,
    SessionState,
    Store,
    StoreError,
    money,
    new_session_id,
    valid_session_id,
)

HERE = Path(__file__).parent
UNTRACKED_PREFIXES = ("/__chaos", "/static", "/favicon.ico")


class AddToCart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int
    qty: int = Field(default=1, ge=1, le=10)


class AddToWishlist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int


class ApplyCoupon(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=40)


class CreateOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+$")
    address: str = Field(default="", max_length=500)
    shipping: Literal["standard", "express"] = "standard"


def _session_id(request: Request) -> str:
    sid: str = request.state.session_id
    return sid


def _cart_json(state: SessionState) -> dict[str, Any]:
    return {
        "items": [
            {"item_id": i.item_id, "product_id": i.product.id, "qty": i.qty} for i in state.cart
        ],
        "count": state.count,
        "coupon": state.coupon,
        "subtotal": money(state.subtotal_cents),
        "discount": money(state.discount_cents),
        "total": money(state.total_cents),
    }


def _order_json(order: Order) -> dict[str, Any]:
    return {"id": order.id, "status": order.status, "total": money(order.total_cents)}


def _error(exc: StoreError) -> JSONResponse:
    return JSONResponse({"error": exc.message}, status_code=exc.status)


def _control_router(store: Store) -> APIRouter:
    router = APIRouter(prefix="/__chaos")

    @router.post("/scenario")
    async def set_scenario(request: Request, session: str | None = Query(None)) -> dict[str, Any]:
        if session is not None and not valid_session_id(session):
            raise HTTPException(400, "invalid session id")
        body = (await request.body()).decode("utf-8")
        try:
            data = yaml.safe_load(body) if body.strip() else None
            if isinstance(data, dict) and set(data) == {"id"}:
                scenario = load_scenario(str(data["id"]))
            else:
                scenario = parse_scenario_yaml(body)
        except FileNotFoundError as exc:
            raise HTTPException(404, f"unknown scenario: {exc}") from exc
        except (ValueError, ValidationError, yaml.YAMLError) as exc:
            raise HTTPException(422, f"invalid scenario: {exc}") from exc
        store.set_scenario(scenario, session)
        return {"session": session, "scenario": scenario.id}

    @router.get("/enter")
    def enter(session: str = Query(...), next: str = Query("/")) -> RedirectResponse:
        """Bind this browser to ``session`` (sets the session cookie), then go to ``next``.

        Lets a demo open a new tab on a session that already has a scenario applied.
        Same-site paths only.
        """
        if not valid_session_id(session):
            raise HTTPException(400, "invalid session id")
        if not next.startswith("/") or next.startswith("//"):
            raise HTTPException(400, "next must be a same-site path")
        response = RedirectResponse(next, status_code=303)
        response.set_cookie(SESSION_COOKIE, session, httponly=True, samesite="lax", path="/")
        return response

    @router.get("/actions")
    def actions(session: str | None = Query(None)) -> dict[str, Any]:
        return {"session": session, "actions": store.actions(session)}

    @router.post("/reset")
    def reset(session: str | None = Query(None)) -> dict[str, Any]:
        store.reset(session)
        return {"session": session, "reset": True}

    return router


def create_app(control: bool | None = None, store: Store | None = None) -> FastAPI:
    """Build the app. ``control=None`` reads ``CHAOS_CONTROL`` from the environment."""
    if control is None:
        control = os.environ.get("CHAOS_CONTROL") == "1"
    store = store or Store()

    app = FastAPI(title="Chaos Store", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    templates = Jinja2Templates(directory=HERE / "templates")
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    @app.middleware("http")
    async def session_cookie(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path.startswith(UNTRACKED_PREFIXES):
            return await call_next(request)
        sid = request.cookies.get(SESSION_COOKIE)
        is_new = not valid_session_id(sid)
        if is_new:
            sid = new_session_id()
        request.state.session_id = sid
        response = await call_next(request)
        if is_new:
            response.set_cookie(SESSION_COOKIE, str(sid), httponly=True, samesite="lax", path="/")
        return response

    def render(request: Request, name: str, **context: Any) -> HTMLResponse:
        scenario: Scenario = store.scenario_for(_session_id(request))
        return templates.TemplateResponse(
            request, name, {"ui": Renderer(scenario), "scenario_id": scenario.id, **context}
        )

    # ------------------------------------------------------------------ pages
    @app.get("/", response_class=HTMLResponse)
    def catalog(request: Request) -> HTMLResponse:
        return render(request, "catalog.html", products=PRODUCTS, title="Products")

    @app.get("/product/{product_id}", response_class=HTMLResponse)
    def product(request: Request, product_id: int) -> HTMLResponse:
        item = get_product(product_id)
        if item is None:
            raise HTTPException(404, "product not found")
        return render(request, "product.html", product=item, title=item.name)

    @app.get("/cart", response_class=HTMLResponse)
    def cart(request: Request) -> HTMLResponse:
        state = store.session(_session_id(request))
        return render(request, "cart.html", state=state, money=money, title="Your cart")

    @app.get("/checkout", response_class=HTMLResponse)
    def checkout(request: Request) -> HTMLResponse:
        state = store.session(_session_id(request))
        return render(request, "checkout.html", state=state, money=money, title="Checkout")

    @app.get("/order/{order_id}", response_class=HTMLResponse)
    def order_page(request: Request, order_id: int) -> HTMLResponse:
        try:
            order = store.order(_session_id(request), order_id)
        except StoreError as exc:
            raise HTTPException(exc.status, exc.message) from exc
        return render(request, "order.html", order=order, money=money, title=f"Order {order.id}")

    # ------------------------------------------------------------------ API
    @app.post("/api/cart")
    def add_to_cart(request: Request, body: AddToCart) -> JSONResponse:
        try:
            state = store.add_to_cart(_session_id(request), body.product_id, body.qty)
        except StoreError as exc:
            return _error(exc)
        return JSONResponse(_cart_json(state))

    @app.delete("/api/cart/{item_id}")
    def remove_from_cart(request: Request, item_id: int) -> JSONResponse:
        try:
            state = store.remove_from_cart(_session_id(request), item_id)
        except StoreError as exc:
            return _error(exc)
        return JSONResponse(_cart_json(state))

    @app.post("/api/cart/{item_id}/save")
    def save_for_later(request: Request, item_id: int) -> JSONResponse:
        try:
            state = store.save_for_later(_session_id(request), item_id)
        except StoreError as exc:
            return _error(exc)
        return JSONResponse(_cart_json(state))

    @app.post("/api/wishlist")
    def add_to_wishlist(request: Request, body: AddToWishlist) -> JSONResponse:
        try:
            state = store.add_to_wishlist(_session_id(request), body.product_id)
        except StoreError as exc:
            return _error(exc)
        return JSONResponse({"wishlist": state.wishlist})

    @app.delete("/api/coupon")
    def remove_coupon(request: Request) -> JSONResponse:
        try:
            state = store.remove_coupon(_session_id(request))
        except StoreError as exc:
            return _error(exc)
        return JSONResponse(_cart_json(state))

    @app.post("/api/coupon")
    def apply_coupon(request: Request, body: ApplyCoupon) -> JSONResponse:
        try:
            state = store.apply_coupon(_session_id(request), body.code)
        except StoreError as exc:
            return _error(exc)
        return JSONResponse(_cart_json(state))

    @app.post("/api/orders")
    def create_order(request: Request, body: CreateOrder) -> JSONResponse:
        try:
            order = store.create_order(_session_id(request), body.name, body.email, body.shipping)
        except StoreError as exc:
            return _error(exc)
        return JSONResponse(_order_json(order), status_code=201)

    @app.post("/api/orders/{order_id}/confirm")
    def confirm_order(request: Request, order_id: int) -> JSONResponse:
        try:
            order = store.confirm_order(_session_id(request), order_id)
        except StoreError as exc:
            return _error(exc)
        return JSONResponse(_order_json(order))

    @app.delete("/api/orders/{order_id}")
    def cancel_order(request: Request, order_id: int) -> JSONResponse:
        try:
            order = store.cancel_order(_session_id(request), order_id)
        except StoreError as exc:
            return _error(exc)
        return JSONResponse(_order_json(order))

    @app.get("/api/search")
    def search(request: Request, q: str = Query("", max_length=100)) -> JSONResponse:
        hits = store.search(_session_id(request), q, PRODUCTS)
        return JSONResponse(
            {"query": q, "results": [{"id": p.id, "name": p.name, "price": p.price} for p in hits]}
        )

    if control:
        app.include_router(_control_router(store))

    return app


app = create_app()
