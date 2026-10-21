"""Identity request/response schemas and its OpenAPI operations (spec 03 §3.2, §4.3; D81)."""

from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app.modules.identity.schemas import (
    OwnerRegistrationCreate,
    SessionCreate,
    SessionRead,
    UserRead,
    UserRecord,
)


def test_owner_registration_normalises_and_masks() -> None:
    data = OwnerRegistrationCreate.model_validate(
        {
            "full_name": "  Fatima Raza ",
            "email": " Fatima.Owner@BayFlow.TEST ",
            "password": "BayFlow@2026",
            "phone": "+92 300 1234567",
        }
    )
    assert (data.full_name, data.email, data.phone) == (
        "Fatima Raza",
        "fatima.owner@bayflow.test",
        "+923001234567",
    )
    assert data.password.get_secret_value() == "BayFlow@2026"
    assert "BayFlow@2026" not in repr(data)  # masked in reprs and tracebacks (D84)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"password": "A" * 11}, [("password", "string_too_short")]),
        ({"password": "A" * 129}, [("password", "string_too_long")]),
        ({"role": "OWNER"}, [("role", "extra_forbidden")]),
        ({"memberships": []}, [("memberships", "extra_forbidden")]),
        ({"email": "x@localhost"}, [("email", "value_error")]),
    ],
)
def test_owner_registration_rules(body: dict[str, Any], expected: list[tuple[str, str]]) -> None:
    payload = {"full_name": "A", "email": "a@bayflow.test", "password": "BayFlow@2026"} | body
    with pytest.raises(ValidationError) as caught:
        OwnerRegistrationCreate.model_validate(payload)
    assert [(".".join(map(str, e["loc"])), e["type"]) for e in caught.value.errors()] == expected


def test_login_accepts_any_existing_password_length_up_to_128() -> None:
    assert SessionCreate(email="a@bayflow.test", password="x").password.get_secret_value() == "x"
    with pytest.raises(ValidationError):
        SessionCreate(email="a@bayflow.test", password="")
    with pytest.raises(ValidationError):
        SessionCreate(email="a@bayflow.test", password="x" * 129)


def test_session_read_has_no_memberships_and_user_record_extends_user_read() -> None:
    assert set(SessionRead.model_fields) == {"access_token", "token_type", "expires_in", "user"}
    assert set(UserRead.model_fields) == {"id", "email", "full_name", "phone"}
    assert set(UserRecord.model_fields) == {
        "id",
        "email",
        "full_name",
        "phone",
        "is_active",
        "is_platform_admin",  # D94, spec 19
    }
    assert issubclass(UserRecord, UserRead)


async def test_identity_operations(client: httpx.AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()
    operations = {
        (method.upper(), path): operation
        for path, methods in schema["paths"].items()
        for method, operation in methods.items()
        if operation["tags"] == ["identity"]
    }
    expected = {
        ("POST", "/api/v1/auth/register-owner"): ("identity_register_owner", "201"),
        ("POST", "/api/v1/auth/login"): ("identity_login", "200"),
        ("POST", "/api/v1/auth/logout"): ("identity_logout", "204"),
    }
    assert set(operations) == set(expected)
    for key, (operation_id, status) in expected.items():
        assert operations[key]["operationId"] == operation_id
        assert status in operations[key]["responses"]
    assert "429" in operations[("POST", "/api/v1/auth/logout")]["responses"]  # per-IP ceiling
    login_errors = operations[("POST", "/api/v1/auth/login")]["responses"]
    assert login_errors["401"]["content"]["application/problem+json"]["schema"]["$ref"].endswith(
        "/Problem"
    )
    password = schema["components"]["schemas"]["OwnerRegistrationCreate"]["properties"]["password"]
    assert (password["format"], password["writeOnly"], password["minLength"]) == (
        "password",
        True,
        12,
    )
