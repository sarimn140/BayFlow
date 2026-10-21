"""The request context the audit log records (spec 19 §3.2; D95): the client IP through the rate
limiter's trusted-proxy rule (`client_ip`), the user agent cut to 255 characters and the request
id, bound by the request-context middleware and empty outside a request."""

import httpx
import pytest
from fastapi import APIRouter, FastAPI

from app.core.request_context import (
    USER_AGENT_MAX_LENGTH,
    current_request_context,
    normalised_ip,
    truncated_user_agent,
)
from app.main import create_app
from tests.conftest import make_settings

probe = APIRouter()


@probe.get("/api/v1/_context")
async def read_context() -> dict[str, str | None]:
    context = current_request_context()
    return {"ip": context.ip, "user_agent": context.user_agent, "request_id": context.request_id}


@pytest.fixture
def probe_app() -> FastAPI:
    app = create_app(make_settings())
    app.include_router(probe)
    return app


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("203.0.113.7", "203.0.113.7"),
        (" 203.0.113.7 ", "203.0.113.7"),
        ("2001:DB8::1", "2001:db8::1"),
        ("203.0.113.7, 10.0.0.1", None),
        ("unknown", None),
        ("999.1.1.1", None),
        ("", None),
        (None, None),
    ],
)
def test_only_valid_addresses_are_kept(value: str | None, expected: str | None) -> None:
    assert normalised_ip(value) == expected


def test_user_agents_are_cut_and_cleaned() -> None:
    assert truncated_user_agent("x" * 300) == "x" * USER_AGENT_MAX_LENGTH
    assert truncated_user_agent("Mozi\x00lla") == "Mozilla"
    assert truncated_user_agent("   ") is None
    assert truncated_user_agent(None) is None


def test_outside_a_request_everything_is_empty() -> None:
    context = current_request_context()
    assert (context.ip, context.user_agent, context.request_id) == (None, None, None)


async def test_the_middleware_binds_ip_user_agent_and_request_id(probe_app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=probe_app, client=("198.51.100.4", 4321))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        proxied = await client.get(
            "/api/v1/_context",
            headers={
                "X-Real-IP": "203.0.113.9",
                "User-Agent": "BayFlow-Test/1.0",
                "X-Request-ID": "ctx-1",
            },
        )
        direct = await client.get("/api/v1/_context", headers={"User-Agent": "u" * 400})
        spoofed = await client.get("/api/v1/_context", headers={"X-Real-IP": "<script>"})
    assert proxied.json() == {
        "ip": "203.0.113.9",
        "user_agent": "BayFlow-Test/1.0",
        "request_id": "ctx-1",
    }
    assert direct.json()["ip"] == "198.51.100.4"  # no proxy header: the socket peer
    assert direct.json()["user_agent"] == "u" * USER_AGENT_MAX_LENGTH
    assert direct.json()["request_id"] == direct.headers["x-request-id"]
    assert spoofed.json()["ip"] is None  # a malformed header never reaches the inet column
    assert current_request_context().ip is None  # nothing leaks out of the request
