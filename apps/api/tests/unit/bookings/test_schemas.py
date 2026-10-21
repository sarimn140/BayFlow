"""Request schemas of the bookings module (spec 03 §3.3, §4.6, §5.2): field rules, `extra="forbid"`
(SEC-17), trimming, blank optional text → null, distinct ids, strict `expected_version`."""

from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from app.modules.bookings.schemas import (
    CUSTOMER_ACTION_REQUESTS,
    STAFF_ACTION_REQUESTS,
    ActionRequest,
    BookingCreate,
    CancelRequest,
    ConfirmRequest,
    CustomerCancelRequest,
    DeclineRequest,
    FailQcRequest,
    OrderPartsRequest,
    PassQcRequest,
    RejectEstimateRequest,
    SendToQcRequest,
    SubmitEstimateRequest,
    VehicleWrite,
)


def booking(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "shop_id": str(uuid4()),
        "service_ids": [str(uuid4())],
        "slot_start": "2026-10-16T05:00:00Z",
        "vehicle": {
            "registration_number": "LEA-1234",
            "make": "Honda",
            "model": "Civic",
            "year": 2016,
        },
    }
    body.update(overrides)
    return body


def errors(model: type[BaseModel], data: dict[str, Any]) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(data)
    return [
        (".".join(str(part) for part in error["loc"]), error["type"])
        for error in caught.value.errors()
    ]


@pytest.mark.parametrize("field", ["status", "customer_user_id", "reference", "version", "id"])
def test_sec17_booking_create_refuses_server_owned_fields(field: str) -> None:
    assert (field, "extra_forbidden") in errors(BookingCreate, booking(**{field: "x"}))


def test_service_ids_are_1_to_10_and_distinct() -> None:
    assert ("service_ids", "too_short") in errors(BookingCreate, booking(service_ids=[]))
    eleven = [str(uuid4()) for _ in range(11)]
    assert ("service_ids", "too_long") in errors(BookingCreate, booking(service_ids=eleven))
    same = str(uuid4())
    other = str(uuid4())
    found = errors(BookingCreate, booking(service_ids=[same, other, same, same]))
    assert found == [("service_ids.2", "duplicate"), ("service_ids.3", "duplicate")]


def test_slot_start_must_carry_a_timezone() -> None:
    found = errors(BookingCreate, booking(slot_start="2026-10-16T10:00:00"))
    assert found == [("slot_start", "timezone_aware")]
    parsed = BookingCreate.model_validate(booking(slot_start="2026-10-16T10:00:00+05:00"))
    assert parsed.slot_start.isoformat() == "2026-10-16T05:00:00+00:00"


def test_customer_fields_are_optional_but_validated_when_sent() -> None:
    BookingCreate.model_validate(booking())
    found = errors(
        BookingCreate,
        booking(customer={"full_name": " ", "email": "bad@@x", "password": "short", "phone": "12"}),
    )
    assert {field for field, _ in found} == {
        "customer.full_name",
        "customer.email",
        "customer.password",
        "customer.phone",
    }
    assert ("customer.role", "extra_forbidden") in errors(
        BookingCreate, booking(customer={"role": "OWNER"})
    )


def test_customer_values_are_normalised() -> None:
    data = BookingCreate.model_validate(
        booking(
            customer={
                "full_name": "  Ahmed  ",
                "email": " Ahmed.Raza@BayFlow.TEST ",
                "password": "  twelve chars  ",
                "phone": "+92 300 1234567",
            },
            customer_notes="   ",
        )
    )
    assert data.customer is not None
    assert data.customer.full_name == "Ahmed"
    assert data.customer.email == "ahmed.raza@bayflow.test"
    assert data.customer.password is not None
    assert data.customer.password.get_secret_value() == "  twelve chars  "  # never trimmed
    assert data.customer.phone == "+923001234567"
    assert data.customer_notes is None  # blank optional text is null


@pytest.mark.parametrize(
    ("vehicle", "field", "code"),
    [
        ({"registration_number": "L"}, "vehicle.registration_number", "string_too_short"),
        ({"registration_number": "A" * 21}, "vehicle.registration_number", "string_too_long"),
        ({"registration_number": "LEA_1234"}, "vehicle.registration_number", "value_error"),
        ({"registration_number": "LÉA-1234"}, "vehicle.registration_number", "value_error"),
        ({"registration_number": "- -"}, "vehicle.registration_number", "value_error"),
        ({"make": " "}, "vehicle.make", "string_too_short"),
        ({"model": "M" * 61}, "vehicle.model", "string_too_long"),
        ({"year": 1899}, "vehicle.year", "greater_than_equal"),
        ({"year": 2101}, "vehicle.year", "less_than_equal"),
        ({"year": "2016"}, "vehicle.year", "int_type"),
        ({"color": "C" * 31}, "vehicle.color", "string_too_long"),
        ({"mileage_km": -1}, "vehicle.mileage_km", "greater_than_equal"),
        ({"mileage_km": 2_000_001}, "vehicle.mileage_km", "less_than_equal"),
        ({"colour": "red"}, "vehicle.colour", "extra_forbidden"),
    ],
)
def test_bk20_vehicle_rules(vehicle: dict[str, Any], field: str, code: str) -> None:
    body = booking()
    body["vehicle"] = {**body["vehicle"], **vehicle}
    assert (field, code) in errors(BookingCreate, body)


def test_vehicle_values_are_trimmed_and_keyed() -> None:
    parsed = VehicleWrite.model_validate(
        {
            "registration_number": " lea 1234 ",
            "make": " Honda ",
            "model": "Civic",
            "year": 2016,
            "color": "  ",
            "mileage_km": 0,
        }
    )
    assert parsed.registration_number == "lea 1234"
    assert parsed.registration_key == "LEA1234"
    assert parsed.make == "Honda"
    assert parsed.color is None
    assert parsed.mileage_km == 0


@pytest.mark.parametrize(
    "model", [*STAFF_ACTION_REQUESTS.values(), *CUSTOMER_ACTION_REQUESTS.values()]
)
def test_every_action_body_forbids_extra_fields_and_takes_expected_version(
    model: type[ActionRequest],
) -> None:
    assert issubclass(model, ActionRequest)
    assert model.model_config.get("extra") == "forbid"
    assert ("status", "extra_forbidden") in errors(model, {"status": "COMPLETED"})
    assert ("expected_version", "greater_than_equal") in errors(model, {"expected_version": 0})
    assert ("expected_version", "int_type") in errors(model, {"expected_version": True})
    assert ("expected_version", "int_type") in errors(model, {"expected_version": "3"})


def test_required_reasons_are_trimmed_and_not_blank() -> None:
    for model in (DeclineRequest, CancelRequest):
        assert ("reason", "missing") in errors(model, {})
        assert ("reason", "string_too_short") in errors(model, {"reason": "   "})
        assert ("reason", "string_too_long") in errors(model, {"reason": "r" * 501})
        assert model.model_validate({"reason": "  Car sold  "}).reason == "Car sold"  # type: ignore[attr-defined]


def test_optional_texts_are_null_when_blank_and_bounded() -> None:
    assert CustomerCancelRequest.model_validate({"reason": "  "}).reason is None
    assert ConfirmRequest.model_validate({"note": " ok "}).note == "ok"
    assert ("note", "string_too_long") in errors(ConfirmRequest, {"note": "n" * 501})
    assert SendToQcRequest.model_validate({"repair_notes": "\t"}).repair_notes is None
    assert ("repair_notes", "string_too_long") in errors(
        SendToQcRequest, {"repair_notes": "r" * 2001}
    )
    assert SubmitEstimateRequest.model_validate({"inspection_notes": "  "}).inspection_notes is None
    reject = RejectEstimateRequest.model_validate({"estimate_id": str(uuid4()), "reason": " "})
    assert reject.reason is None


def test_order_parts_items_are_bounded_and_distinct() -> None:
    part = str(uuid4())
    found = errors(
        OrderPartsRequest,
        {"items": [{"part_id": part, "quantity": 1}, {"part_id": part, "quantity": 2}]},
    )
    assert found == [("items.1.part_id", "duplicate")]
    assert ("items", "too_short") in errors(OrderPartsRequest, {"items": []})
    assert ("items.0.quantity", "greater_than_equal") in errors(
        OrderPartsRequest, {"items": [{"part_id": part, "quantity": 0}]}
    )
    assert ("supplier_name", "string_too_short") in errors(
        OrderPartsRequest, {"supplier_name": " "}
    )
    assert OrderPartsRequest.model_validate({}).items is None


def test_qc_bodies_use_the_qc_field_types() -> None:
    assert ("checklist", "missing") in errors(PassQcRequest, {})
    too_many = [{"key": "road_test", "passed": True}] * 21
    assert ("checklist", "too_long") in errors(PassQcRequest, {"checklist": too_many})
    assert ("checklist.0.key", "enum") in errors(
        PassQcRequest, {"checklist": [{"key": "x", "passed": True}]}
    )
    fail = errors(FailQcRequest, {"issue_title": " ", "issue_description": "d" * 2001})
    assert ("issue_title", "string_too_short") in fail
    assert ("issue_description", "string_too_long") in fail
    title = FailQcRequest.model_validate({"issue_title": "  Oil leak  ", "issue_description": "x"})
    assert title.issue_title == "Oil leak"
