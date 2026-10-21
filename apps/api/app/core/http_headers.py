"""Response headers every response carries (spec 03 §1.8, spec 01, spec 04, D61).

Shared by the request-context middleware and the last-resort 500 handler, which runs outside the
middleware stack (Starlette's `ServerErrorMiddleware` is always outermost) and therefore sets the
same headers itself.
"""

import re
import uuid

REQUEST_ID_HEADER = "X-Request-ID"

# spec 04 "Security headers (Tier 1 values)", API side.
SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
)
NO_STORE = ("Cache-Control", "no-store")

_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


def needs_no_store(path: str) -> bool:
    """D61 / spec 03 §1.8: every `/api/*` response and `/health` are `Cache-Control: no-store`."""
    return path in {"/api", "/health"} or path.startswith("/api/")


def resolve_request_id(incoming: str | None) -> str:
    """Reuse an incoming `X-Request-ID` matching `^[A-Za-z0-9._-]{1,64}$`, else a new UUID4."""
    if incoming is not None and _SAFE_REQUEST_ID.fullmatch(incoming):
        return incoming
    return str(uuid.uuid4())


def standard_headers(path: str, request_id: str) -> list[tuple[str, str]]:
    """The headers added to every response of `path`."""
    headers = [(REQUEST_ID_HEADER, request_id), *SECURITY_HEADERS]
    if needs_no_store(path):
        headers.append(NO_STORE)
    return headers
