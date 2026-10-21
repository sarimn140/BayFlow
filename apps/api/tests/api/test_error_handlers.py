"""RFC 9457 problem responses (D49; spec 03 §2; spec 12 API-01..API-04, SEC-28..SEC-30)."""

import logging
import uuid
from typing import Any

import httpx
import pytest
from fastapi import APIRouter, Body, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request as StarletteRequest

from app.core.error_handlers import (
    PROBLEM_JSON,
    unhandled_exception_handler,
    validation_field_errors,
)
from app.core.errors import SlotFull, Unauthenticated, ValidationFailed
from app.core.middleware import LARGE_BODY_ROUTES, MAX_REQUEST_BODY_BYTES, body_limit_for
from app.core.security import Password, limiter
from app.shared.email import Email
from app.shared.pagination import Page, PageParamsDep

SECRET_MARKER = "secret-internals-password-hunter2"


class CustomerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: Email
    password: Password


class BookingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shop_id: uuid.UUID
    customer: CustomerIn
    service_ids: list[uuid.UUID] = Field(min_length=1)


router = APIRouter(prefix="/api/v1/_test", tags=["test"])


@router.post("/bookings")
async def create_test_booking(body: BookingIn) -> dict[str, str]:
    return {"shop_id": str(body.shop_id)}


@router.get("/items")
async def list_test_items(page: PageParamsDep) -> Page[int]:
    return Page[int].build([1, 2], total=2, params=page)


@router.get("/slot-full")
async def raise_slot_full() -> None:
    raise SlotFull


@router.get("/unauthenticated")
async def raise_unauthenticated() -> None:
    raise Unauthenticated


@router.get("/service-validation")
async def raise_service_validation() -> None:
    raise ValidationFailed(errors=[{"field": "slot_start", "message": "Off grid.", "code": "x"}])


@router.get("/boom")
async def explode() -> None:
    raise RuntimeError(SECRET_MARKER)


@router.post("/echo")
async def echo(payload: dict[str, Any] = Body(...)) -> dict[str, int]:  # noqa: B008, FAST002
    return {"keys": len(payload)}


@router.get("/limited")
@limiter.limit("2/minute")
async def limited(request: Request) -> dict[str, bool]:
    return {"ok": True}


@pytest.fixture(autouse=True)
def _test_routes(app: FastAPI) -> None:
    app.include_router(router)


def assert_problem(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM_JSON
    body: dict[str, Any] = response.json()
    assert body["type"] == "about:blank"
    assert body["status"] == status
    assert body["code"] == code
    assert isinstance(body["title"], str)
    assert isinstance(body["detail"], str)
    assert body["instance"] == response.request.url.path
    assert "Traceback" not in response.text
    return body


async def test_unknown_route_is_a_not_found_problem(client: httpx.AsyncClient) -> None:
    body = assert_problem(await client.get("/api/v1/nothing-here?x=1"), 404, "NOT_FOUND")
    assert body["title"] == "Not Found"
    assert body["detail"] == "The requested resource was not found."
    assert body["instance"] == "/api/v1/nothing-here"


async def test_trailing_slash_is_a_404_not_a_redirect(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/_test/items/")
    assert_problem(response, 404, "NOT_FOUND")
    assert "location" not in response.headers


async def test_wrong_method_is_405_with_allow(client: httpx.AsyncClient) -> None:
    response = await client.delete("/api/v1/_test/items")
    body = assert_problem(response, 405, "METHOD_NOT_ALLOWED")
    assert body["title"] == "Method Not Allowed"
    assert response.headers["allow"] == "GET"


async def test_validation_errors_list_every_field_without_echoing_input(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/_test/bookings",
        json={
            "shop_id": "not-a-uuid",
            "customer": {"email": "Fatima.Owner@BayFlow.TEST", "password": "short-pass1"},
            "service_ids": [],
            "status": "COMPLETED",
        },
    )
    body = assert_problem(response, 422, "VALIDATION_ERROR")
    assert body["title"] == "Unprocessable Content"
    errors = {error["field"]: error for error in body["errors"]}
    assert set(errors) == {"shop_id", "customer.password", "service_ids", "status"}
    assert errors["shop_id"]["code"] == "uuid_parsing"
    assert errors["customer.password"]["code"] == "string_too_short"
    assert errors["service_ids"]["code"] == "too_short"
    assert errors["status"]["code"] == "extra_forbidden"
    assert all(set(error) == {"field", "message", "code"} for error in body["errors"])
    assert "short-pass1" not in response.text  # pydantic's `input` is never returned


async def test_query_parameter_errors_keep_their_location(client: httpx.AsyncClient) -> None:
    body = assert_problem(
        await client.get("/api/v1/_test/items?limit=101&offset=-1"), 422, "VALIDATION_ERROR"
    )
    assert {error["field"] for error in body["errors"]} == {"query.limit", "query.offset"}


async def test_pagination_defaults(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/_test/items")
    assert response.json() == {"items": [1, 2], "total": 2, "limit": 20, "offset": 0}


async def test_malformed_json_is_a_whole_body_error(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/_test/bookings",
        content=b'{"shop_id": ',
        headers={"Content-Type": "application/json"},
    )
    body = assert_problem(response, 422, "VALIDATION_ERROR")
    assert [error["field"] for error in body["errors"]] == [""]
    assert body["errors"][0]["code"] == "json_invalid"


@pytest.mark.parametrize(
    "headers",
    [{"Content-Type": "text/plain"}, {"Content-Type": "application/x-www-form-urlencoded"}, {}],
)
async def test_non_json_bodies_are_refused(
    client: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    # spec 04 SEC-30: strict JSON content type is part of the CSRF defence.
    response = await client.post("/api/v1/_test/echo", content=b'{"a": 1}', headers=headers)
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_app_errors_render_their_code_and_status(client: httpx.AsyncClient) -> None:
    body = assert_problem(await client.get("/api/v1/_test/slot-full"), 409, "SLOT_FULL")
    assert body["title"] == "Conflict"
    assert body["detail"] == "This time slot is fully booked. Please choose another slot."
    assert "errors" not in body


async def test_service_validation_errors_carry_field_errors(client: httpx.AsyncClient) -> None:
    body = assert_problem(
        await client.get("/api/v1/_test/service-validation"), 422, "VALIDATION_ERROR"
    )
    assert body["errors"] == [{"field": "slot_start", "message": "Off grid.", "code": "x"}]


async def test_every_401_carries_a_bearer_challenge(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/_test/unauthenticated")
    body = assert_problem(response, 401, "UNAUTHENTICATED")
    assert body["detail"] == "Authentication required."
    assert response.headers["www-authenticate"] == "Bearer"


async def test_unhandled_errors_are_a_bare_500_with_request_id_and_no_store(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR, logger="app.errors")
    response = await client.get("/api/v1/_test/boom", headers={"X-Request-ID": "req-500-test"})
    body = assert_problem(response, 500, "INTERNAL_ERROR")
    assert body["detail"] == "An unexpected error occurred. Please try again."
    assert SECRET_MARKER not in response.text
    assert "RuntimeError" not in response.text
    assert response.headers["x-request-id"] == "req-500-test"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    logged = [record for record in caplog.records if record.getMessage() == "unhandled error"]
    assert logged
    assert logged[0].exc_info is not None


async def test_last_resort_500_handler_sets_the_standard_headers() -> None:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/anything",
        "raw_path": b"/api/v1/anything",
        "query_string": b"",
        "headers": [(b"x-request-id", b"backstop-1")],
    }
    response = await unhandled_exception_handler(StarletteRequest(scope), RuntimeError("x"))
    assert response.status_code == 500
    assert response.headers["x-request-id"] == "backstop-1"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"


async def test_too_large_body_with_content_length_is_413(client: httpx.AsyncClient) -> None:
    payload = b'{"blob": "' + b"x" * MAX_REQUEST_BODY_BYTES + b'"}'
    response = await client.post(
        "/api/v1/_test/echo", content=payload, headers={"Content-Type": "application/json"}
    )
    body = assert_problem(response, 413, "PAYLOAD_TOO_LARGE")
    assert body["title"] == "Content Too Large"


async def test_too_large_streamed_body_is_413(client: httpx.AsyncClient) -> None:
    async def chunks():  # no Content-Length: the middleware counts the bytes it reads
        yield b'{"blob": "'
        for _ in range(80):
            yield b"x" * 1024
        yield b'"}'

    response = await client.post(
        "/api/v1/_test/echo", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert "content-length" not in response.request.headers
    assert_problem(response, 413, "PAYLOAD_TOO_LARGE")


async def test_bodies_under_the_limit_pass(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/_test/echo", json={"blob": "x" * 60_000})
    assert response.status_code == 200
    assert response.json() == {"keys": 1}


def test_the_agent_summary_route_gets_a_larger_limit() -> None:
    assert MAX_REQUEST_BODY_BYTES == 64 * 1024
    assert body_limit_for("/api/v1/internal/calls/3f2c9a1e/summary") == 256 * 1024
    assert body_limit_for("/api/v1/bookings") == MAX_REQUEST_BODY_BYTES
    assert len(LARGE_BODY_ROUTES) == 1


async def test_per_ip_rate_limit_is_a_429_problem_with_retry_after(
    client: httpx.AsyncClient,
) -> None:
    assert (await client.get("/api/v1/_test/limited")).status_code == 200
    assert (await client.get("/api/v1/_test/limited")).status_code == 200
    response = await client.get("/api/v1/_test/limited")
    body = assert_problem(response, 429, "RATE_LIMITED")
    retry_after = int(response.headers["retry-after"])
    assert 0 < retry_after <= 60
    assert body["detail"] == f"Too many attempts. Try again in {retry_after} seconds."
    # Another client IP (Railway's X-Real-IP) has its own budget.
    other = await client.get("/api/v1/_test/limited", headers={"X-Real-IP": "203.0.113.9"})
    assert other.status_code == 200


async def test_openapi_documents_problem_responses(client: httpx.AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()
    assert schema["info"]["version"] == "1.0.0"
    assert schema["paths"]["/health"]["get"]["operationId"] == "system_health"
    create = schema["paths"]["/api/v1/_test/bookings"]["post"]
    assert create["operationId"] == "test_create_test_booking"
    unprocessable = create["responses"]["422"]["content"]
    assert set(unprocessable) == {PROBLEM_JSON}
    assert unprocessable[PROBLEM_JSON]["schema"]["$ref"] == "#/components/schemas/ValidationProblem"
    components = schema["components"]["schemas"]
    assert {"Problem", "ValidationProblem", "FieldError", "ErrorCode"} <= set(components)
    assert "HTTPValidationError" not in components
    health_503 = schema["paths"]["/health"]["get"]["responses"]["503"]["content"]
    assert set(health_503) == {"application/json"}  # infrastructure body, not a problem


def test_identical_field_errors_are_reported_once() -> None:
    """FastAPI re-solves a failed dependency: one bad path parameter can arrive twice."""
    bad_uuid = {"type": "uuid_parsing", "loc": ("path", "shop_id"), "msg": "Input should be a UUID"}
    missing = {"type": "missing", "loc": ("body", "name"), "msg": "Field required"}
    errors = validation_field_errors(RequestValidationError([bad_uuid, missing, bad_uuid, missing]))
    assert [(e["field"], e["code"]) for e in errors] == [
        ("path.shop_id", "uuid_parsing"),
        ("name", "missing"),
    ]


@pytest.mark.parametrize("offset", ["2147483648", "9223372036854775808", "-1"])
async def test_offsets_outside_the_supported_range_are_422(
    client: httpx.AsyncClient, offset: str
) -> None:
    """A huge offset once overflowed asyncpg's int64 encoder and became a 500 on every list."""
    response = await client.get(f"/api/v1/_test/items?offset={offset}")
    assert response.status_code == 422
    assert [error["field"] for error in response.json()["errors"]] == ["query.offset"]


async def test_the_largest_supported_offset_is_accepted(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/_test/items?offset=2147483647")
    assert response.status_code == 200
    assert response.json()["offset"] == 2147483647
