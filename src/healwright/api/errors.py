"""Error envelope, request ids, auth, body limit and exception handlers.

Every error response has this shape and never contains a stack trace::

    {"error": {"code": "SOURCE_CHANGED",
               "message": "tests/test_checkout.py changed after the patch was generated",
               "details": {"expected_sha256": "...", "actual_sha256": "..."},
               "request_id": "01JC8Z..."}}

``details`` is present only when there is something structured to say (validation
errors, SHA mismatches). ``X-Request-ID`` is echoed when the client sends a safe value,
otherwise a new ULID is generated; it is set on every response and attached to every
log record written while the request is handled (``healwright.logs.request_id_var``).

Codes: VALIDATION_ERROR 422, UNAUTHORIZED 401, NOT_FOUND 404, NO_PATCH 404,
METHOD_NOT_ALLOWED 405, ALREADY_TRIAGED 409, NOT_ACCEPTED 409, SOURCE_CHANGED 409,
DEMO_BUSY 409, PAYLOAD_TOO_LARGE 413, PATCH_INVALID 422, STORAGE_UNAVAILABLE 503,
INTERNAL_ERROR 500.
"""

from __future__ import annotations

import hmac
import logging
import re
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp
from ulid import ULID

from healwright.logs import request_id_var

log = logging.getLogger("healwright.api")
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MAX_BODY_BYTES = 64 * 1024  # triage notes are <= 1000 chars; nothing legitimate is larger

HTTP_CODES = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHORIZED",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    500: "INTERNAL_ERROR",
    503: "STORAGE_UNAVAILABLE",
}


class ApiError(Exception):
    def __init__(
        self, status: int, code: str, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def request_id(request: Request) -> str:
    rid: str = getattr(request.state, "request_id", "") or ""
    return rid


def envelope(
    request: Request,
    status: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = details
    error["request_id"] = request_id(request)
    return JSONResponse({"error": error}, status_code=status, headers=headers)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Request id + access log + bearer token + body size limit, in that order."""

    def __init__(self, app: ASGIApp, api_token: str | None = None) -> None:
        super().__init__(app)
        self.api_token = api_token

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-request-id", "")
        rid = incoming if SAFE_REQUEST_ID.match(incoming) else str(ULID())
        request.state.request_id = rid
        token = request_id_var.set(rid)
        t0 = time.perf_counter()
        try:
            response = await self._guarded(request, call_next)
        except Exception:
            log.exception(
                "api: unhandled error (request %s) on %s %s", rid, request.method, request.url.path
            )
            response = envelope(request, 500, "INTERNAL_ERROR", "internal error")
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        log.info(
            "api %s %s -> %d",
            request.method,
            request.url.path,
            response.status_code,
            extra={"request_id": rid, "duration_ms": round((time.perf_counter() - t0) * 1000, 1)},
        )
        return response

    async def _guarded(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        is_api = request.url.path.startswith("/api/")
        if self.api_token and is_api and request.method != "OPTIONS":
            sent = request.headers.get("authorization", "")
            expected = f"Bearer {self.api_token}"
            if not hmac.compare_digest(sent.encode(), expected.encode()):
                return envelope(
                    request,
                    401,
                    "UNAUTHORIZED",
                    "send Authorization: Bearer <HEALWRIGHT_API_TOKEN>",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        if request.method in ("POST", "PUT", "PATCH"):
            declared = request.headers.get("content-length")
            if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
                return _too_large(request)
            if len(await request.body()) > MAX_BODY_BYTES:
                return _too_large(request)
        return await call_next(request)


def _too_large(request: Request) -> JSONResponse:
    return envelope(
        request,
        413,
        "PAYLOAD_TOO_LARGE",
        "request body is too large",
        {"max_bytes": MAX_BODY_BYTES},
    )


def install(app: FastAPI, api_token: str | None = None) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return envelope(request, exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else code.lower()
        return envelope(request, exc.status_code, code, message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": [str(p) for p in err.get("loc", ())], "msg": str(err.get("msg", ""))}
            for err in exc.errors()
        ]
        return envelope(request, 422, "VALIDATION_ERROR", "request is invalid", {"errors": errors})

    @app.exception_handler(OSError)
    async def _storage(request: Request, exc: OSError) -> JSONResponse:
        log.exception("api: storage error (request %s)", request_id(request))
        return envelope(
            request,
            503,
            "STORAGE_UNAVAILABLE",
            "run folders or artifacts are not readable or writable",
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("api: unhandled error (request %s)", request_id(request))
        return envelope(request, 500, "INTERNAL_ERROR", "internal error")

    app.add_middleware(RequestIdMiddleware, api_token=api_token)


__all__ = ["MAX_BODY_BYTES", "ApiError", "envelope", "install", "request_id"]
