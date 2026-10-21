"""Request schemas of the shops module (spec 03 §4.9; SEC-15/SEC-17 schema halves, SHP-03)."""

from datetime import time
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.modules.shops.schemas import (
    MemberCreate,
    MemberUpdate,
    ServiceCreate,
    ServiceUpdate,
    ShopCreate,
    ShopUpdate,
    StaffRole,
    WorkingHoursWrite,
    format_wall_clock,
)
from app.shared.enums import MembershipRole


def week() -> list[dict[str, Any]]:
    return [
        {"weekday": day, "is_closed": day == 6, "opens_at": "09:00", "closes_at": "18:00"}
        for day in range(7)
    ]


def shop(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "Lahore Auto Care",
        "address": "Plot 12, Main Boulevard",
        "city": "Lahore",
        "phone": "+92 42 0000 0101",
        "slot_duration_minutes": 60,
        "slot_capacity": 2,
        "working_hours": week(),
    }
    body.update(overrides)
    return body


def errors(model: type[Any], body: dict[str, Any]) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(body)
    return [(".".join(map(str, error["loc"])), error["type"]) for error in caught.value.errors()]


def test_shop_create_defaults_and_normalisation() -> None:
    data = ShopCreate.model_validate(
        shop(name="  Lahore Auto Care ", logo_url="HTTPS://x.io/a.png")
    )
    assert data.name == "Lahore Auto Care"
    assert data.timezone == "Asia/Karachi"  # D38
    assert data.is_listed is True
    assert data.phone == "+924200000101"
    assert data.logo_url == "https://x.io/a.png"
    assert data.working_hours[0].opens_at == time(9)


@pytest.mark.parametrize(
    ("sent", "timezone", "is_listed"),
    [
        ({}, "Asia/Karachi", True),  # omitted → defaults
        ({"timezone": None, "is_listed": None}, "Asia/Karachi", True),  # null → defaults
        ({"timezone": "Europe/London", "is_listed": False}, "Europe/London", False),
        ({"timezone": " Asia/Dubai ", "is_listed": True}, "Asia/Dubai", True),
    ],
)
def test_optional_shop_fields_accept_omitted_null_and_values(
    sent: dict[str, Any], timezone: str, is_listed: bool
) -> None:
    """Spec 03 §1.5: an optional request field may be omitted or sent as `null`."""
    data = ShopCreate.model_validate(shop(**sent))
    assert (data.timezone, data.is_listed) == (timezone, is_listed)


@pytest.mark.parametrize(
    ("sent", "is_active"),
    [({}, True), ({"is_active": None}, True), ({"is_active": False}, False)],
)
def test_service_is_active_accepts_omitted_null_and_values(
    sent: dict[str, Any], is_active: bool
) -> None:
    data = ServiceCreate.model_validate(
        {"name": "Oil change", "estimated_duration_minutes": 45, **sent}
    )
    assert data.is_active is is_active


def test_null_defaults_are_documented_as_nullable() -> None:
    shop_schema = ShopCreate.model_json_schema()["properties"]
    service_schema = ServiceCreate.model_json_schema()["properties"]
    for field, default in (
        (shop_schema["timezone"], "Asia/Karachi"),
        (shop_schema["is_listed"], True),
        (service_schema["is_active"], True),
    ):
        assert {"type": "null"} in field["anyOf"]
        assert field["default"] == default
    assert shop_schema["timezone"]["anyOf"][0]["maxLength"] == 64
    for invalid in ({"timezone": "Mars/Olympus"}, {"is_listed": "maybe"}):
        with pytest.raises(ValidationError):
            ShopCreate.model_validate(shop(**invalid))


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"name": "   "}, [("name", "string_too_short")]),
        ({"name": "x" * 121}, [("name", "string_too_long")]),
        ({"address": "x" * 256}, [("address", "string_too_long")]),
        ({"city": ""}, [("city", "string_too_short")]),
        ({"slot_duration_minutes": 50}, [("slot_duration_minutes", "multiple_of")]),
        ({"slot_duration_minutes": 0}, [("slot_duration_minutes", "greater_than_equal")]),
        ({"slot_duration_minutes": 255}, [("slot_duration_minutes", "less_than_equal")]),
        ({"slot_capacity": 0}, [("slot_capacity", "greater_than_equal")]),
        ({"slot_capacity": 51}, [("slot_capacity", "less_than_equal")]),
        ({"timezone": "Mars/Olympus"}, [("timezone", "value_error")]),
        ({"logo_url": "http://x.io/a.png"}, [("logo_url", "value_error")]),
        ({"logo_url": "https://"}, [("logo_url", "value_error")]),
        ({"logo_url": "https://x.io/" + "a" * 2048}, [("logo_url", "string_too_long")]),
        ({"phone": "12"}, [("phone", "string_too_short")]),
        ({"working_hours": week()[:6]}, [("working_hours", "too_short")]),
        ({"working_hours": [*week(), week()[0]]}, [("working_hours", "too_long")]),
        ({"slug": "chosen-slug"}, [("slug", "extra_forbidden")]),
        ({"rating": 5}, [("rating", "extra_forbidden")]),
    ],
)
def test_shop_create_limits(overrides: dict[str, Any], expected: list[tuple[str, str]]) -> None:
    assert errors(ShopCreate, shop(**overrides)) == expected


@pytest.mark.parametrize("value", ["9:00", "09:00:00", "24:00", "09:60", "nine", "٠٩:٠٠", 900])  # noqa: RUF001 - Arabic-Indic digits on purpose
def test_shp03_working_hours_times_are_hh_mm(value: object) -> None:
    body = {"weekday": 0, "is_closed": False, "opens_at": value, "closes_at": "18:00"}
    assert errors(WorkingHoursWrite, body) == [("opens_at", "value_error")]


def test_working_hours_write_maps_to_a_working_day() -> None:
    open_day = WorkingHoursWrite(weekday=2, is_closed=False, opens_at="08:30", closes_at="17:00")
    assert open_day.to_working_day().opens_at == time(8, 30)
    closed = WorkingHoursWrite.model_validate(
        {"weekday": 6, "is_closed": True, "opens_at": "09:00", "closes_at": "13:00"}
    )
    day = closed.to_working_day()
    assert (day.is_closed, day.opens_at, day.closes_at) == (True, None, None)
    assert errors(WorkingHoursWrite, {"weekday": 7, "is_closed": True}) == [
        ("weekday", "less_than_equal")
    ]
    assert format_wall_clock(time(7, 5)) == "07:05"
    assert format_wall_clock(None) is None


def test_shop_update_needs_one_field_and_refuses_nulls() -> None:
    assert errors(ShopUpdate, {}) == [("", "value_error")]
    for field in ("name", "phone", "slot_capacity", "timezone", "is_listed"):
        assert errors(ShopUpdate, {field: None}) == [(field, "value_error")]
    cleared = ShopUpdate.model_validate({"logo_url": None})  # nullable: clears the logo
    assert cleared.model_fields_set == {"logo_url"}
    assert cleared.logo_url is None
    assert errors(ShopUpdate, {"slug": "x"}) == [("slug", "extra_forbidden")]


def test_sec15_member_create_never_accepts_owner() -> None:
    body = {"email": "x@bayflow.test", "full_name": "X", "role": "OWNER"}
    assert errors(MemberCreate, body) == [("role", "enum")]
    staff = MemberCreate.model_validate({**body, "role": "TECHNICIAN"})
    assert staff.role is StaffRole.TECHNICIAN
    assert staff.role.membership_role is MembershipRole.TECHNICIAN
    assert staff.password is None
    assert errors(MemberCreate, {**body, "role": "TECHNICIAN", "password": "short"}) == [
        ("password", "string_too_short")
    ]


def test_sec15_sec17_member_update() -> None:
    assert errors(MemberUpdate, {}) == [("", "value_error")]
    assert errors(MemberUpdate, {"role": "OWNER"}) == [("role", "enum")]
    assert errors(MemberUpdate, {"role": None}) == [("role", "value_error")]
    assert errors(MemberUpdate, {"is_active": None}) == [("is_active", "value_error")]
    assert errors(MemberUpdate, {"user_id": "x"}) == [("user_id", "extra_forbidden")]
    assert errors(MemberUpdate, {"shop_id": "x"}) == [("shop_id", "extra_forbidden")]
    assert MemberUpdate(is_active=False).model_fields_set == {"is_active"}
    assert set(StaffRole) == {
        StaffRole.SERVICE_ADVISOR,
        StaffRole.TECHNICIAN,
        StaffRole.PARTS_PERSON,
        StaffRole.QC_INSPECTOR,
    }


def test_service_create_and_update() -> None:
    created = ServiceCreate.model_validate(
        {"name": " Oil change ", "description": "   ", "estimated_duration_minutes": 45}
    )
    assert (created.name, created.description, created.base_price, created.is_active) == (
        "Oil change",
        None,  # blank optional text becomes null
        None,
        True,
    )
    priced = ServiceCreate.model_validate(
        {"name": "AC", "estimated_duration_minutes": 90, "base_price": 4500}
    )
    assert priced.base_price == Decimal("4500.00")
    bad = {"name": "x", "estimated_duration_minutes": 4, "base_price": "10.50"}
    assert errors(ServiceCreate, bad) == [
        ("estimated_duration_minutes", "greater_than_equal"),
        ("base_price", "not_whole_rupees"),
    ]
    assert errors(ServiceCreate, {"name": "x", "estimated_duration_minutes": 10_081}) == [
        ("estimated_duration_minutes", "less_than_equal")
    ]
    assert errors(ServiceUpdate, {}) == [("", "value_error")]
    assert errors(ServiceUpdate, {"name": None}) == [("name", "value_error")]
    nulls = ServiceUpdate.model_validate({"description": None, "base_price": None})
    assert nulls.model_fields_set == {"description", "base_price"}
