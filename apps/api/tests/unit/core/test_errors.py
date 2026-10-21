"""`ErrorCode` equals glossary §10 exactly; every code has its `AppError` subclass (D49)."""

import pytest

from app.core import errors
from app.core.errors import AppError, ErrorCode

# Glossary §10, copied verbatim: code -> HTTP status.
GLOSSARY_CODES = {
    "VALIDATION_ERROR": 422,
    "INVALID_SLOT": 422,
    "ESTIMATE_EMPTY": 422,
    "MEMBER_NOT_ELIGIBLE": 422,
    "UNAUTHENTICATED": 401,
    "INVALID_CREDENTIALS": 401,
    "FORBIDDEN": 403,
    "NOT_ASSIGNED": 403,
    "IDENTITY_NOT_VERIFIED": 403,
    "NOT_FOUND": 404,
    "METHOD_NOT_ALLOWED": 405,
    "EMAIL_ALREADY_REGISTERED": 409,
    "INVALID_TRANSITION": 409,
    "CONCURRENT_UPDATE": 409,
    "SLOT_FULL": 409,
    "ALREADY_PICKED": 409,
    "STALE_ESTIMATE": 409,
    "ESTIMATE_LOCKED": 409,
    "INSUFFICIENT_STOCK": 409,
    "CALL_BUSY": 409,
    "CALL_ALREADY_ANSWERED": 409,
    "CALL_NOT_ACTIVE": 409,
    "CONFLICT": 409,
    "PAYLOAD_TOO_LARGE": 413,
    "SHOP_SUSPENDED": 403,
    "RATE_LIMITED": 429,
    "INTERNAL_ERROR": 500,
    "CALLING_DISABLED": 503,
    "AI_DISABLED": 503,
    "AI_LIMIT_REACHED": 429,
    "AI_UNAVAILABLE": 503,
}


def test_error_codes_match_the_glossary_exactly() -> None:
    assert {code.value: code.http_status for code in ErrorCode} == GLOSSARY_CODES
    assert all(code.name == code.value for code in ErrorCode)


def test_every_code_has_a_safe_default_detail() -> None:
    for code in ErrorCode:
        assert code.default_detail.endswith(".")
        assert "Traceback" not in code.default_detail


def test_every_code_has_exactly_one_app_error_subclass() -> None:
    subclasses = [
        value
        for value in vars(errors).values()
        if isinstance(value, type) and issubclass(value, AppError) and value is not AppError
    ]
    assert sorted(cls.code.value for cls in subclasses) == sorted(GLOSSARY_CODES)


def test_app_error_carries_status_detail_headers_and_field_errors() -> None:
    error = errors.RateLimited("Too many attempts.", headers={"Retry-After": "30"})
    assert error.status_code == 429
    assert error.detail == "Too many attempts."
    assert error.headers == {"Retry-After": "30"}
    assert errors.SlotFull().detail == ErrorCode.SLOT_FULL.default_detail

    invalid = errors.InvalidSlot(errors=[{"field": "slot_start", "message": "x", "code": "y"}])
    assert invalid.errors == [{"field": "slot_start", "message": "x", "code": "y"}]
    assert "INVALID_SLOT" in repr(invalid)


def test_app_errors_are_plain_exceptions() -> None:
    with pytest.raises(AppError) as caught:
        raise errors.NotFound
    assert caught.value.code is ErrorCode.NOT_FOUND
