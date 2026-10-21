"""Database errors mapped by constraint name (spec 02 §7.5-7.6, spec 03 §2.4)."""

import json

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import DbSession
from app.core.db_errors import INVALID_TEXT_DETAIL, error_code_for
from app.core.errors import ErrorCode
from tests.rows import make_part, make_shop, make_user

router = APIRouter(prefix="/api/v1/_dberr", tags=["test"])


class TextIn(BaseModel):
    value: str


@router.post("/text")
async def store_text(body: TextIn, session: DbSession) -> dict[str, str]:
    result = await session.execute(text("SELECT CAST(:v AS text)"), {"v": body.value})
    return {"value": result.scalar_one()}


@router.get("/search")
async def search_text(q: str, session: DbSession) -> dict[str, bool]:
    result = await session.execute(text("SELECT 'Honda Civic' ILIKE :q"), {"q": f"%{q}%"})
    return {"match": result.scalar_one()}


@router.post("/jsonb")
async def store_jsonb(body: TextIn, session: DbSession) -> None:
    await session.execute(text("SELECT CAST(:v AS jsonb)"), {"v": json.dumps({"k": body.value})})


@router.post("/duplicate-email")
async def insert_duplicate_email(session: DbSession) -> None:
    session.add(make_user(email="twice@bayflow.test"))
    await session.flush()
    session.add(make_user(email="twice@bayflow.test"))
    await session.flush()


@router.post("/bad-sku")
async def insert_bad_sku(session: DbSession) -> None:
    shop = make_shop()
    session.add(shop)
    await session.flush()
    session.add(make_part(shop, sku="not a valid sku"))  # ck_parts_sku_format: not mapped
    await session.flush()


class FakeDriverError(Exception):
    def __init__(self, constraint: str | None, state: str | None) -> None:
        super().__init__("driver error")
        self.constraint_name = constraint
        self.sqlstate = state


def wrap(constraint: str | None, state: str | None, *, as_cause: bool = False) -> DBAPIError:
    driver = FakeDriverError(constraint, state)
    if as_cause:  # SQLAlchemy's asyncpg adapter raises its own error *from* asyncpg's
        adapted = Exception("adapted")
        adapted.__cause__ = driver
        return DBAPIError("SQL", {}, adapted)
    return DBAPIError("SQL", {}, driver)


@pytest.mark.parametrize(
    ("constraint", "state", "code"),
    [
        ("uq_users_email", "23505", ErrorCode.EMAIL_ALREADY_REGISTERED),
        ("uq_parts_shop_id_sku", "23505", ErrorCode.CONFLICT),
        ("uq_services_active_name", "23505", ErrorCode.CONFLICT),
        ("uq_qc_inspections_one_open_per_booking", "23505", ErrorCode.ALREADY_PICKED),
        ("uq_estimates_one_open_version_per_booking", "23505", ErrorCode.CONCURRENT_UPDATE),
        ("ck_parts_reserved_lte_on_hand", "23514", ErrorCode.INSUFFICIENT_STOCK),
        ("ck_booking_parts_quantities", "23514", ErrorCode.INSUFFICIENT_STOCK),
        (None, "40P01", ErrorCode.CONCURRENT_UPDATE),
        (None, "55P03", ErrorCode.CONCURRENT_UPDATE),
        ("ck_parts_sku_format", "23514", None),
        (None, "P0001", None),
        (None, None, None),
        (None, "22021", ErrorCode.VALIDATION_ERROR),  # NUL in text
        (None, "22P05", ErrorCode.VALIDATION_ERROR),  # NUL inside JSONB
        (None, "22000", None),  # a generic data error without an encoding cause is a bug
    ],
)
def test_error_codes_by_constraint_name(
    constraint: str | None, state: str | None, code: ErrorCode | None
) -> None:
    assert error_code_for(wrap(constraint, state)) == code
    assert error_code_for(wrap(constraint, state, as_cause=True)) == code


def test_a_lone_surrogate_rejected_by_the_driver_is_a_validation_error() -> None:
    """asyncpg raises DataError (22000) from UnicodeEncodeError before sending anything."""
    encode_error = UnicodeEncodeError("utf-8", "\ud800", 0, 1, "surrogates not allowed")
    driver = FakeDriverError(None, "22000")
    driver.__cause__ = encode_error
    adapted = Exception("adapted")
    adapted.__cause__ = driver
    assert error_code_for(DBAPIError("SQL", {}, adapted)) == ErrorCode.VALIDATION_ERROR


@pytest.fixture
def _routes(db_app: FastAPI) -> None:
    db_app.include_router(router)


@pytest.mark.usefixtures("_routes")
async def test_a_unique_violation_becomes_its_code(db_client: httpx.AsyncClient) -> None:
    response = await db_client.post("/api/v1/_dberr/duplicate-email")
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "EMAIL_ALREADY_REGISTERED"
    assert "uq_users_email" not in response.text
    assert "INSERT" not in response.text


def assert_invalid_text(response: httpx.Response) -> None:
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["detail"] == INVALID_TEXT_DETAIL
    assert body["errors"] == []
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"
    assert "SELECT" not in response.text


@pytest.mark.usefixtures("_routes")
async def test_plain_text_is_stored(db_client: httpx.AsyncClient) -> None:
    response = await db_client.post("/api/v1/_dberr/text", json={"value": "Oil leak — filter"})
    assert response.status_code == 200
    assert response.json() == {"value": "Oil leak — filter"}


@pytest.mark.usefixtures("_routes")
async def test_a_nul_character_in_a_body_is_a_validation_error(
    db_client: httpx.AsyncClient,
) -> None:
    assert_invalid_text(await db_client.post("/api/v1/_dberr/text", json={"value": "a\u0000b"}))


@pytest.mark.usefixtures("_routes")
async def test_a_nul_character_in_a_query_string_is_a_validation_error(
    db_client: httpx.AsyncClient,
) -> None:
    assert_invalid_text(await db_client.get("/api/v1/_dberr/search?q=civ%00ic"))


@pytest.mark.usefixtures("_routes")
async def test_a_nul_character_inside_jsonb_is_a_validation_error(
    db_client: httpx.AsyncClient,
) -> None:
    assert_invalid_text(await db_client.post("/api/v1/_dberr/jsonb", json={"value": "a\u0000b"}))


@pytest.mark.usefixtures("_routes")
async def test_a_lone_surrogate_is_a_validation_error(db_client: httpx.AsyncClient) -> None:
    response = await db_client.post(
        "/api/v1/_dberr/text",
        content=b'{"value": "\\ud800"}',  # valid JSON escape, unpaired surrogate
        headers={"Content-Type": "application/json"},
    )
    assert_invalid_text(response)


@pytest.mark.usefixtures("_routes")
async def test_unmapped_database_errors_stay_internal(db_client: httpx.AsyncClient) -> None:
    response = await db_client.post("/api/v1/_dberr/bad-sku")
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "ck_parts_sku_format" not in response.text
    assert response.headers["cache-control"] == "no-store"
