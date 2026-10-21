"""Where a request comes from, for the audit log (D95, spec 19 §3.2).

The request-context middleware binds the client IP and the user agent next to the request id
(`app.core.logging.request_id_var`); the audit module's handlers read all three through
`current_request_context()` when they write a row. Scripts, the seed and unit tests run outside a
request, so every field is `None` there.

- **IP:** `app.core.security.client_ip` (the rate limiter's trusted-proxy rule: `X-Real-IP` set by
  Railway's edge, else the socket peer), kept only when it parses as an IPv4 or IPv6 address, so
  the `inet` column never receives a spoofed or malformed header.
- **User agent:** at most 255 characters (`audit_events.user_agent`), without NUL characters
  (PostgreSQL text cannot hold them); blank means `None`.
"""

import ipaddress
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from app.core.logging import request_id_var

USER_AGENT_MAX_LENGTH = 255

client_ip_var: ContextVar[str | None] = ContextVar("client_ip", default=None)
user_agent_var: ContextVar[str | None] = ContextVar("user_agent", default=None)


@dataclass(frozen=True, slots=True)
class RequestContext:
    """The current request's origin as the audit log stores it (all `None` outside a request)."""

    ip: str | None
    user_agent: str | None
    request_id: str | None


def normalised_ip(value: str | None) -> str | None:
    """`value` in canonical form when it is an IPv4 or IPv6 address, else `None`."""
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def truncated_user_agent(value: str | None) -> str | None:
    """The user agent without NUL characters, cut to 255 characters; blank → `None`."""
    if value is None:
        return None
    cleaned = value.replace("\x00", "").strip()
    return cleaned[:USER_AGENT_MAX_LENGTH] or None


@contextmanager
def bind_request_context(*, ip: str | None, user_agent: str | None) -> Iterator[None]:
    """Bind the (already normalised) IP and user agent for the duration of one request."""
    ip_token = client_ip_var.set(ip)
    user_agent_token = user_agent_var.set(user_agent)
    try:
        yield
    finally:
        user_agent_var.reset(user_agent_token)
        client_ip_var.reset(ip_token)


def current_request_context() -> RequestContext:
    """The bound IP, user agent and request id (`None` outside a request)."""
    return RequestContext(
        ip=client_ip_var.get(),
        user_agent=user_agent_var.get(),
        request_id=request_id_var.get(),
    )
