"""HTTP middleware (spec 01 "Logging and request IDs", spec 04 "Security headers", D61).

Order, outermost first: request context (request id, client IP and user agent for the audit log,
security headers, `Cache-Control: no-store` on `/api/*`, one access-log line, a problem+json 500
for unhandled errors) -> CORS for `CLIENT_URL` -> request-body size limit. All three are pure ASGI
middleware (no `BaseHTTPMiddleware`), so context variables and streaming behave normally.
"""

import logging
import re
import time

from fastapi import FastAPI
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.error_handlers import internal_error_response, problem_response
from app.core.errors import ErrorCode
from app.core.http_headers import REQUEST_ID_HEADER, resolve_request_id, standard_headers
from app.core.logging import request_log_context
from app.core.request_context import bind_request_context, normalised_ip, truncated_user_agent
from app.core.security import client_ip

access_logger = logging.getLogger("app.access")
error_logger = logging.getLogger("app.errors")

# spec 03 §1.10: 64 KiB per request body; the agent's call-summary post may carry a transcript.
MAX_REQUEST_BODY_BYTES = 64 * 1024
LARGE_BODY_ROUTES: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"/api/v1/internal/calls/[^/]+/summary"), 256 * 1024),
)

CORS_ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CORS_ALLOWED_HEADERS = ["Content-Type", "Authorization", REQUEST_ID_HEADER]
CORS_EXPOSED_HEADERS = [REQUEST_ID_HEADER, "Retry-After"]


class RequestContextMiddleware:
    """Request id, standard response headers, one access-log line per request, last-resort 500.

    It also binds the request's client IP (`client_ip`, the rate limiter's trusted-proxy rule; kept
    only when it is a valid address) and user agent (at most 255 characters) next to the request id,
    so the audit log records where every action came from (D95, spec 19 §3.2).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]
        request_headers = Headers(scope=scope)
        request_id = resolve_request_id(request_headers.get(REQUEST_ID_HEADER))
        ip = normalised_ip(client_ip(Request(scope)))
        user_agent = truncated_user_agent(request_headers.get("user-agent"))
        extra_headers = standard_headers(path, request_id)
        started_at = time.perf_counter()
        response_status = 500
        response_started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal response_status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                response_status = message["status"]
                headers = MutableHeaders(scope=message)
                for name, value in extra_headers:
                    headers[name] = value
            await send(message)

        with request_log_context(request_id), bind_request_context(ip=ip, user_agent=user_agent):
            try:
                await self.app(scope, receive, send_with_headers)
            except Exception:
                error_logger.exception("unhandled error")
                if response_started:
                    raise
                await internal_error_response(path)(scope, receive, send_with_headers)
            finally:
                access_logger.info(
                    "%s %s %s",
                    scope["method"],
                    path,
                    response_status,
                    extra={
                        "method": scope["method"],
                        "path": path,  # never the query string (it may carry a ticket)
                        "status": response_status,
                        "duration_ms": round((time.perf_counter() - started_at) * 1000, 1),
                    },
                )


class _BodyTooLarge(StarletteHTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=413)


def body_limit_for(path: str, default: int = MAX_REQUEST_BODY_BYTES) -> int:
    for pattern, limit in LARGE_BODY_ROUTES:
        if pattern.fullmatch(path):
            return limit
    return default


class BodySizeLimitMiddleware:
    """Rejects request bodies over the limit with 413 `PAYLOAD_TOO_LARGE` (spec 03 §1.10).

    A too-large `Content-Length` is refused before the app runs. Bodies without a length (chunked)
    are counted while the app reads them; the overflow raises an HTTP 413 exception, which FastAPI
    re-raises from body parsing and the error handlers render as problem+json.
    """

    def __init__(self, app: ASGIApp, max_body_bytes: int = MAX_REQUEST_BODY_BYTES) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        limit = body_limit_for(path, self.max_body_bytes)
        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None and content_length.isdigit() and int(content_length) > limit:
            await self._reject(path, scope, receive, send)
            return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if response_started:
                raise
            await self._reject(path, scope, receive, send)

    @staticmethod
    async def _reject(path: str, scope: Scope, receive: Receive, send: Send) -> None:
        response = problem_response(
            ErrorCode.PAYLOAD_TOO_LARGE, instance=path, headers={"Connection": "close"}
        )
        await response(scope, receive, send)


def install_middleware(app: FastAPI, settings: Settings) -> None:
    """Add the middleware stack; the last one added runs outermost."""
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.client_url],
        allow_credentials=True,
        allow_methods=CORS_ALLOWED_METHODS,
        allow_headers=CORS_ALLOWED_HEADERS,
        expose_headers=CORS_EXPOSED_HEADERS,
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware)
