"""Public-safe mode for a hosted demo (``HEALWRIGHT_PUBLIC=1``).

Anyone on the internet can reach a public deployment, so:

- nothing that edits files or records a decision is offered (triage, patch apply), and the
  headed "watch" mode is off (there is no display on a server);
- demo runs stay one at a time (``DEMO_BUSY``) and each visitor waits ``cooldown_s``
  between starts (``DEMO_COOLDOWN``, with ``Retry-After``);
- the Chaos Store for "Open the broken shop" runs as a separate internal process
  (``HEALWRIGHT_SHOP_URL``) and is reached only through ``/shop``: its root-relative
  links, scripts and redirects are rewritten to stay under ``/shop``, and its control
  routes are not reachable except ``/__chaos/enter`` (binds a browser to its session).

Demo test runs never go through the proxy: they keep using their own internal store.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
from fastapi import APIRouter, Request, Response

from healwright.api.errors import ApiError

SHOP_PREFIX = "/shop"
# Root-relative URLs in the store's HTML attributes ("/cart", but not "//cdn").
_HTML_URL = re.compile(r'\b(href|src|action)="/(?!/)')
# Root-relative paths inside the store's JavaScript string and template literals.
_JS_URL = re.compile(r"""(["'`])/(?=(?:api|order|product|cart|checkout|static|__chaos)\b)""")
_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "transfer-encoding",
    "te",
    "trailer",
    "upgrade",
    "content-length",
    "content-encoding",
    "host",
}


def rewrite_html(text: str) -> str:
    return _HTML_URL.sub(rf'\1="{SHOP_PREFIX}/', text)


def rewrite_js(text: str) -> str:
    return _JS_URL.sub(rf"\1{SHOP_PREFIX}/", text)


def rewrite_location(location: str) -> str:
    if location.startswith("/") and not location.startswith("//"):
        return SHOP_PREFIX + location
    return location


def visitor_id(request: Request) -> str:
    """The client address; behind a proxy (Hugging Face) the first X-Forwarded-For hop."""
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    return request.client.host if request.client else "unknown"


@dataclass
class Cooldown:
    """Per-visitor wait between demo starts."""

    seconds: float
    clock: Callable[[], float] = time.monotonic
    _last: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def check(self, visitor: str) -> None:
        if self.seconds <= 0:
            return
        now = self.clock()
        with self._lock:
            last = self._last.get(visitor)
        if last is not None and now - last < self.seconds:
            wait = int(self.seconds - (now - last)) + 1
            raise ApiError(
                429,
                "DEMO_COOLDOWN",
                f"You just ran a demo. You can start the next one in {wait} s.",
                {"retry_after_s": wait},
                headers={"Retry-After": str(wait)},
            )

    def mark(self, visitor: str) -> None:
        now = self.clock()
        with self._lock:
            self._last[visitor] = now
            if len(self._last) > 10_000:  # bounded: drop the oldest half
                for key, _ in sorted(self._last.items(), key=lambda kv: kv[1])[:5_000]:
                    del self._last[key]


VERCEL_SITE = "https://healwright.vercel.app"


@dataclass(frozen=True)
class PublicOptions:
    """What create_app needs to know about public mode (from Settings)."""

    public: bool = False
    cooldown_s: float = 60.0
    shop_url: str | None = None
    cors_origins: tuple[str, ...] = ()

    def origins(self) -> tuple[str, ...]:
        if self.cors_origins:
            return self.cors_origins
        return (VERCEL_SITE,) if self.public else ()


def read_only() -> ApiError:
    return ApiError(
        403,
        "PUBLIC_READ_ONLY",
        "Reviewing and applying patches is turned off on the public demo. "
        "Run HealWright locally to review heals and apply patches.",
    )


def shop_router(shop_url: str) -> APIRouter:
    """``/shop/...`` -> the internal Chaos Store, with URLs kept under ``/shop``."""
    r = APIRouter()
    base = shop_url.rstrip("/")

    @r.api_route(
        SHOP_PREFIX + "/{path:path}", methods=["GET", "POST", "DELETE"], include_in_schema=False
    )
    async def shop(path: str, request: Request) -> Response:
        if path.startswith("__chaos") and path != "__chaos/enter":
            raise ApiError(404, "NOT_FOUND", "not found")
        headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP}
        body = await request.body()
        # One client per request: pooled connections are bound to the loop that made them.
        async with httpx.AsyncClient(base_url=base, timeout=15, follow_redirects=False) as client:
            upstream = await client.request(
                request.method,
                "/" + path,
                params=request.query_params,
                headers=headers,
                content=body if body else None,
            )
        out_headers = {
            k: v
            for k, v in upstream.headers.items()
            if k.lower() not in _HOP_BY_HOP | {"set-cookie"}
        }
        if "location" in upstream.headers:
            out_headers["location"] = rewrite_location(upstream.headers["location"])
        media = upstream.headers.get("content-type", "")
        content = upstream.content
        if media.startswith("text/html"):
            content = rewrite_html(upstream.text).encode("utf-8")
        elif "javascript" in media:
            content = rewrite_js(upstream.text).encode("utf-8")
        response = Response(content=content, status_code=upstream.status_code, headers=out_headers)
        for cookie in upstream.headers.get_list("set-cookie"):
            response.headers.append("set-cookie", cookie)
        return response

    return r
