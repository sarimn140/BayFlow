"""Request ids, standard headers, CORS and the access log (spec 01, spec 03 §1.8, spec 04, D61)."""

import logging
import re
import uuid

import httpx
import pytest
from fastapi import APIRouter, FastAPI

from app.core.logging import bind_log_context

router = APIRouter(prefix="/api/v1/_mw", tags=["test"])


@router.get("/ping")
async def ping() -> dict[str, bool]:
    bind_log_context(user_id="user-42")
    return {"pong": True}


@pytest.fixture(autouse=True)
def _test_routes(app: FastAPI) -> None:
    app.include_router(router)


async def test_request_id_is_generated_when_absent(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/_mw/ping")
    request_id = response.headers["x-request-id"]
    assert uuid.UUID(request_id).version == 4


async def test_safe_incoming_request_id_is_echoed(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/_mw/ping", headers={"X-Request-ID": "abc-123_X.y"})
    assert response.headers["x-request-id"] == "abc-123_X.y"


@pytest.mark.parametrize("unsafe", ["has spaces", "x" * 65, "semi;colon", "<script>"])
async def test_unsafe_incoming_request_id_is_replaced(
    client: httpx.AsyncClient, unsafe: str
) -> None:
    response = await client.get("/api/v1/_mw/ping", headers={"X-Request-ID": unsafe})
    assert response.headers["x-request-id"] != unsafe
    assert re.fullmatch(r"[0-9a-f-]{36}", response.headers["x-request-id"])


@pytest.mark.parametrize("path", ["/api/v1/_mw/ping", "/api/v1/unknown", "/api"])
async def test_every_api_response_is_no_store(client: httpx.AsyncClient, path: str) -> None:
    response = await client.get(path)
    assert response.headers["cache-control"] == "no-store"
    assert "x-request-id" in response.headers


async def test_security_headers_on_every_response(client: httpx.AsyncClient) -> None:
    for path in ("/api/v1/_mw/ping", "/docs", "/openapi.json", "/not-api"):
        response = await client.get(path)
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "x-request-id" in response.headers


async def test_non_api_pages_are_not_forced_to_no_store(client: httpx.AsyncClient) -> None:
    response = await client.get("/docs")
    assert response.status_code == 200
    assert response.headers.get("cache-control") != "no-store"


async def test_cors_allows_only_the_client_url(client: httpx.AsyncClient) -> None:
    preflight = {"Access-Control-Request-Method": "POST"}
    allowed = await client.options(
        "/api/v1/_mw/ping", headers={"Origin": "http://localhost:3000", **preflight}
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "x-request-id" in allowed.headers

    foreign = await client.options(
        "/api/v1/_mw/ping", headers={"Origin": "https://evil.example", **preflight}
    )
    assert "access-control-allow-origin" not in foreign.headers

    simple = await client.get("/api/v1/_mw/ping", headers={"Origin": "http://localhost:3000"})
    assert simple.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "x-request-id" in simple.headers["access-control-expose-headers"].lower()


async def test_one_access_line_per_request_without_query_string(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="app.access")
    response = await client.get(
        "/api/v1/_mw/ping?ticket=eyJ.secret.sig", headers={"X-Request-ID": "access-1"}
    )
    assert response.status_code == 200
    lines = [record for record in caplog.records if record.name == "app.access"]
    assert len(lines) == 1
    record = lines[0]
    assert record.__dict__["method"] == "GET"
    assert record.__dict__["path"] == "/api/v1/_mw/ping"
    assert record.__dict__["status"] == 200
    assert record.__dict__["duration_ms"] >= 0
    assert "ticket" not in record.getMessage()
