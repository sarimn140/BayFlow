"""Request and response schemas of the estimates module (spec 03 §1.5, §2.3, §3.4, §5.3):
EST-06, EST-08, EST-19, EST-20, EST-24 (schema halves), SEC-12 and SEC-17, and the event-metadata
shapes bookings records (spec 08; `modules/bookings.md` §7.6).

The last test proves the wire shape bookings will serve: the project's 422 handler turns the
schema's errors into `{field: "lines.N.<field>", code}` items, all in one response."""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.core.error_handlers import register_error_handlers
from app.modules.estimates.schemas import (
    CustomerEstimateLineRead,
    CustomerEstimateRead,
    CustomerEstimateView,
    EstimateEdit,
    EstimateEditRead,
    EstimateLineWrite,
    EstimateRead,
    EstimateSnapshot,
    EstimateSummary,
    EstimateUpdate,
)
from app.modules.identity.schemas import UserRef
from app.shared.enums import EstimateLineType, EstimateStatus

PART_ID = uuid.uuid4()


def part_line(**overrides: Any) -> dict[str, Any]:
    return {"line_type": "PART", "part_id": str(PART_ID), "quantity": "1", **overrides}


def labour_line(**overrides: Any) -> dict[str, Any]:
    line = {"line_type": "LABOUR", "description": "Labour", "quantity": "1", "unit_price": "4000"}
    return {**line, **overrides}


def errors_of(body: dict[str, Any]) -> list[tuple[str, str]]:
    """`(field path, code)` of every error `EstimateUpdate` reports for `body`."""
    with pytest.raises(ValidationError) as caught:
        EstimateUpdate.model_validate(body)
    return [
        (".".join(str(part) for part in error["loc"]), error["type"])
        for error in caught.value.errors()
    ]


def single_line_errors(line: dict[str, Any]) -> list[tuple[str, str]]:
    return errors_of({"lines": [line]})


def test_valid_body_is_parsed_into_typed_lines() -> None:
    update = EstimateUpdate.model_validate(
        {
            "lines": [part_line(), part_line(unit_price=850), labour_line(quantity=1.5)],
            "inspection_notes": "  Faulty ignition coil  ",
            "expected_version": 4,
        }
    )
    first, second, third = update.lines
    assert first.line_type is EstimateLineType.PART
    assert first.part_id == PART_ID
    assert first.unit_price is None  # the service applies parts.unit_cost (EST-09)
    assert first.quantity == Decimal("1.00")
    assert second.unit_price == Decimal("850.00")
    assert third.quantity == Decimal("1.50")
    assert update.inspection_notes == "Faulty ignition coil"
    assert update.expected_version == 4


def test_est_08_one_to_fifty_lines() -> None:
    """EST-08: 1-50 lines (spec 03 §1.10)."""
    assert errors_of({"lines": []}) == [("lines", "too_short")]
    assert errors_of({"lines": [labour_line()] * 51}) == [("lines", "too_long")]
    assert len(EstimateUpdate.model_validate({"lines": [labour_line()] * 50}).lines) == 50
    assert errors_of({}) == [("lines", "missing")]


@pytest.mark.parametrize(
    ("quantity", "code"),
    [
        ("1.5", "value_error"),  # PART quantities are whole numbers
        ("0", "greater_than"),
        ("-2", "greater_than"),
        ("10000", "less_than_equal"),
        ("1.234", "decimal_max_places"),
        ("NaN", "finite_number"),
        (True, "decimal_type"),
        ("two", "decimal_parsing"),
    ],
)
def test_est_08_part_quantity_is_a_whole_number_from_1_to_9999(quantity: object, code: str) -> None:
    assert single_line_errors(part_line(quantity=quantity)) == [("lines.0.quantity", code)]


def test_est_08_part_quantity_bounds_are_inclusive() -> None:
    for quantity in ("1", "9999", 9999, "2.00", "1e2"):
        EstimateUpdate.model_validate({"lines": [part_line(quantity=quantity)]})


@pytest.mark.parametrize(
    ("quantity", "code"),
    [
        ("0", "greater_than"),
        ("0.001", "decimal_max_places"),
        ("1000", "value_error"),  # LABOUR max is 999.99
        ("999.999", "decimal_max_places"),
    ],
)
def test_est_08_labour_quantity_is_0_01_to_999_99(quantity: str, code: str) -> None:
    assert single_line_errors(labour_line(quantity=quantity)) == [("lines.0.quantity", code)]


def test_est_08_labour_quantity_bounds_are_inclusive() -> None:
    for quantity in ("0.01", "999.99", 0.5, "1"):
        EstimateUpdate.model_validate({"lines": [labour_line(quantity=quantity)]})


def test_est_08_type_specific_fields_get_documented_codes_on_their_own_field() -> None:
    """`missing` / `not_allowed` on the field itself, never a generic `extra_forbidden` or an
    error on the whole line (`modules/estimates.md` §7.4)."""
    assert single_line_errors({"line_type": "PART", "quantity": "1"}) == [
        ("lines.0.part_id", "missing")
    ]
    assert single_line_errors(part_line(description="Coil")) == [
        ("lines.0.description", "not_allowed")
    ]
    assert single_line_errors(part_line(description="")) == [("lines.0.description", "not_allowed")]
    assert single_line_errors(labour_line(part_id=str(PART_ID))) == [
        ("lines.0.part_id", "not_allowed")
    ]
    no_description = labour_line()
    del no_description["description"]
    assert single_line_errors(no_description) == [("lines.0.description", "missing")]
    assert single_line_errors(labour_line(description="   ")) == [
        ("lines.0.description", "string_too_short")
    ]
    assert single_line_errors(labour_line(description="x" * 256)) == [
        ("lines.0.description", "string_too_long")
    ]
    no_price = labour_line()
    del no_price["unit_price"]
    assert single_line_errors(no_price) == [("lines.0.unit_price", "missing")]
    assert single_line_errors(labour_line(unit_price=None)) == [("lines.0.unit_price", "missing")]


def test_null_type_specific_fields_count_as_absent() -> None:
    """Optional request fields may be omitted or sent as null (spec 03 §1.5)."""
    line = EstimateLineWrite.model_validate(part_line(description=None, unit_price=None))
    assert line.description is None
    assert line.unit_price is None
    labour = EstimateLineWrite.model_validate(labour_line(part_id=None, description=" Fit "))
    assert labour.part_id is None
    assert labour.description == "Fit"


def test_est_08_line_type_must_be_part_or_labour() -> None:
    assert single_line_errors({"line_type": "SERVICE", "quantity": "1"}) == [
        ("lines.0.line_type", "enum")
    ]


@pytest.mark.parametrize(
    ("unit_price", "code"),
    [
        ("900.50", "not_whole_rupees"),  # EST-20: paisa
        (900.0, "not_whole_rupees"),  # JSON floats are refused for money (spec 03 §1.5)
        (True, "not_whole_rupees"),
        ("-1", "greater_than_equal"),
        ("10000000000", "less_than_equal"),
        ("900.123", "decimal_max_places"),
    ],
)
def test_est_20_unit_price_is_a_whole_rupee_amount(unit_price: object, code: str) -> None:
    """EST-20: `unit_price` with paisa -> 422 `not_whole_rupees`, on either line type."""
    assert single_line_errors(part_line(unit_price=unit_price)) == [("lines.0.unit_price", code)]
    assert single_line_errors(labour_line(unit_price=unit_price)) == [("lines.0.unit_price", code)]


@pytest.mark.parametrize("field", ["line_total", "parts_total", "labour_total", "grand_total"])
def test_sec_17_client_totals_are_refused_on_a_line(field: str) -> None:
    """SEC-17: totals are never accepted from a client (`extra_forbidden`)."""
    assert single_line_errors(labour_line(**{field: "1.00"})) == [
        (f"lines.0.{field}", "extra_forbidden")
    ]


@pytest.mark.parametrize(
    "field",
    ["grand_total", "parts_total", "labour_total", "shop_id", "booking_id", "status", "version"],
)
def test_sec_17_mass_assignment_on_the_body_is_refused(field: str) -> None:
    """SEC-17: `grand_total` (or any unknown field) on `PUT …/estimate` -> 422."""
    assert errors_of({"lines": [labour_line()], field: "1"}) == [(field, "extra_forbidden")]


def test_inspection_notes_and_expected_version_limits() -> None:
    assert errors_of({"lines": [labour_line()], "inspection_notes": "x" * 4001}) == [
        ("inspection_notes", "string_too_long")
    ]
    assert errors_of({"lines": [labour_line()], "expected_version": 0}) == [
        ("expected_version", "greater_than_equal")
    ]
    update = EstimateUpdate.model_validate({"lines": [labour_line()], "inspection_notes": None})
    assert update.inspection_notes is None
    assert update.expected_version is None


@pytest.mark.parametrize(
    ("notes", "stored"),
    [
        ("   ", None),
        ("\xa0", None),  # NO-BREAK SPACE is whitespace too
        ("\u2003\t\n", None),
        ("", None),
        (None, None),
        ("  Faulty ignition coil \xa0", "Faulty ignition coil"),
    ],
)
def test_blank_inspection_notes_are_none(notes: str | None, stored: str | None) -> None:
    """Spec 03 §1.5: after trimming, an empty optional text means "no value" - the same as
    leaving `inspection_notes` out (as shops and qc do)."""
    update = EstimateUpdate.model_validate({"lines": [labour_line()], "inspection_notes": notes})
    assert update.inspection_notes == stored


def test_a_negative_zero_price_is_plain_zero() -> None:
    """`"-0"` passes as zero and is stored and answered as `0.00`, never `-0.00` (the shared
    `Money` normalises the sign)."""
    line = EstimateLineWrite.model_validate(labour_line(unit_price="-0"))
    assert line.unit_price == Decimal("0.00")
    assert line.unit_price is not None
    assert not line.unit_price.is_signed()


def test_est_24_one_validation_lists_every_invalid_line() -> None:
    """EST-24 (schema half): every line's errors come back together."""
    body = {
        "lines": [
            part_line(description="x"),
            labour_line(),
            labour_line(unit_price="10.50"),
            part_line(quantity="0.5", grand_total="1"),
        ]
    }
    assert errors_of(body) == [
        ("lines.0.description", "not_allowed"),
        ("lines.2.unit_price", "not_whole_rupees"),
        ("lines.3.grand_total", "extra_forbidden"),
    ]


SENT_AT = datetime(2026, 10, 16, 9, 40, tzinfo=UTC)
DECIDED_AT = datetime(2026, 10, 16, 10, 5, 12, 345000, tzinfo=UTC)


def customer_read(status: EstimateStatus) -> CustomerEstimateRead:
    return CustomerEstimateRead(
        id=uuid.uuid4(),
        version=2,
        status=status,
        lines=[
            CustomerEstimateLineRead(
                id=uuid.uuid4(),
                position=1,
                line_type=EstimateLineType.LABOUR,
                description="Wheel alignment",
                quantity=Decimal("1.5"),
                unit_price=Decimal("3500"),
                line_total=Decimal("5250.00"),
            )
        ],
        parts_total=Decimal("12600.00"),
        labour_total=Decimal("3500"),
        grand_total=Decimal("16100.00"),
        sent_at=SENT_AT,
        decided_at=DECIDED_AT,
        customer_note=None,
    )


def test_est_06_money_and_quantities_serialise_as_two_place_strings() -> None:
    """EST-06: money `"16100.00"`, quantities `"1.50"`, timestamps UTC with `Z`."""
    body = customer_read(EstimateStatus.APPROVED).model_dump(mode="json")
    assert body["grand_total"] == "16100.00"
    assert body["labour_total"] == "3500.00"
    assert body["lines"][0]["quantity"] == "1.50"
    assert body["lines"][0]["unit_price"] == "3500.00"
    assert body["lines"][0]["line_total"] == "5250.00"
    assert body["sent_at"] == "2026-10-16T09:40:00Z"
    assert body["decided_at"] == "2026-10-16T10:05:12.345Z"
    assert "part" not in body["lines"][0]  # customers never get SKU or stock
    summary = EstimateSummary(
        estimate_id=uuid.uuid4(),
        version=2,
        status=EstimateStatus.SENT,
        grand_total=Decimal("16100"),
        line_count=4,
    )
    assert summary.model_dump(mode="json")["grand_total"] == "16100.00"


@pytest.mark.parametrize(
    "status", [EstimateStatus.DRAFT, EstimateStatus.SUBMITTED, EstimateStatus.SUPERSEDED]
)
def test_sec_12_a_customer_projection_of_an_unsent_version_cannot_be_built(
    status: EstimateStatus,
) -> None:
    """SEC-12 defence in depth: a customer projection of a draft, submitted or superseded
    version fails instead of leaking."""
    with pytest.raises(ValidationError):
        customer_read(status)


@pytest.mark.parametrize(
    "status", [EstimateStatus.SENT, EstimateStatus.APPROVED, EstimateStatus.REJECTED]
)
def test_customer_projection_of_visible_versions(status: EstimateStatus) -> None:
    view = CustomerEstimateView(estimate=customer_read(status), revision_in_progress=False)
    assert view.estimate is not None
    assert view.estimate.status is status


def test_est_19_snapshot_event_metadata_is_json_ready() -> None:
    """EST-19 (P1, the estimates half): `SUBMIT_ESTIMATE`, `SEND_ESTIMATE`, `APPROVE_ESTIMATE`,
    `REJECT_ESTIMATE` record `{estimate_id, version, grand_total}` with JSON values."""
    estimate_id = uuid.uuid4()
    snapshot = EstimateSnapshot(
        estimate_id=estimate_id, version=2, status=EstimateStatus.SENT, grand_total=Decimal("16100")
    )
    metadata = snapshot.event_metadata()
    assert metadata == {"estimate_id": str(estimate_id), "version": 2, "grand_total": "16100.00"}
    assert [type(value) for value in metadata.values()] == [str, int, str]
    assert json.loads(json.dumps(metadata)) == metadata


def test_snapshot_event_ref_is_id_and_version_only() -> None:
    """`START_INSPECTION`, `REVISE_ESTIMATE`, `RETURN_TO_TECHNICIAN` record `{estimate_id,
    version}` (`modules/bookings.md` §7.6) - no total."""
    estimate_id = uuid.uuid4()
    snapshot = EstimateSnapshot(
        estimate_id=estimate_id, version=3, status=EstimateStatus.DRAFT, grand_total=Decimal("0")
    )
    reference = snapshot.event_ref()
    assert reference == {"estimate_id": str(estimate_id), "version": 3}
    assert [type(value) for value in reference.values()] == [str, int]
    assert json.loads(json.dumps(reference)) == reference


def staff_read(estimate_id: uuid.UUID, *, version: int, grand_total: str) -> EstimateRead:
    author = UserRef(user_id=uuid.uuid4(), full_name="Bilal")
    return EstimateRead(
        id=estimate_id,
        booking_id=uuid.uuid4(),
        version=version,
        status=EstimateStatus.DRAFT,
        lines=[],
        parts_total=Decimal("12600"),
        labour_total=Decimal(grand_total) - Decimal("12600"),
        grand_total=Decimal(grand_total),
        created_by=author,
        created_at=SENT_AT,
        submitted_at=None,
        sent_at=None,
        sent_by=None,
        decided_at=None,
        decided_by=None,
        customer_note=None,
    )


def test_edit_event_metadata_for_edit_estimate() -> None:
    """`EDIT_ESTIMATE` (written when an edit creates a version) records
    `{estimate_id, version, grand_total}` (spec 03 §5.3)."""
    estimate_id = uuid.uuid4()
    edit = EstimateEdit(
        estimate=staff_read(estimate_id, version=2, grand_total="16100"), created_new_version=True
    )
    metadata = edit.event_metadata()
    assert metadata == {"estimate_id": str(estimate_id), "version": 2, "grand_total": "16100.00"}
    assert [type(value) for value in metadata.values()] == [str, int, str]
    assert json.loads(json.dumps(metadata)) == metadata


def test_event_metadata_never_shows_negative_zero() -> None:
    snapshot = EstimateSnapshot(
        estimate_id=uuid.uuid4(), version=1, status=EstimateStatus.DRAFT, grand_total=Decimal("-0")
    )
    assert snapshot.event_metadata()["grand_total"] == "0.00"


async def test_est_24_wire_errors_name_each_line_field_in_one_problem() -> None:
    """EST-08 / EST-24 / SEC-17 on the wire: through the project's 422 handler, as bookings will
    serve `PUT …/estimate`, every bad field of every line is one `{field, message, code}` item."""
    app = FastAPI()
    register_error_handlers(app)

    @app.put("/estimate")
    async def edit(body: EstimateUpdate) -> dict[str, int]:
        return {"lines": len(body.lines)}

    payload = {
        "lines": [
            part_line(description="Coil"),
            labour_line(part_id=str(PART_ID), unit_price="99.5"),
            part_line(quantity="2.5"),
            labour_line(grand_total="1"),
        ]
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put("/estimate", json=payload)
        ok = await client.put("/estimate", json={"lines": [part_line(), labour_line()]})
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    problem = response.json()
    assert problem["code"] == "VALIDATION_ERROR"
    assert [(error["field"], error["code"]) for error in problem["errors"]] == [
        ("lines.0.description", "not_allowed"),
        ("lines.1.unit_price", "not_whole_rupees"),
        ("lines.2.quantity", "value_error"),
        ("lines.3.grand_total", "extra_forbidden"),
    ]
    assert all(set(error) == {"field", "message", "code"} for error in problem["errors"])
    assert ok.status_code == 200
    assert ok.json() == {"lines": 2}


def test_openapi_components_follow_spec_03() -> None:
    """Spec 03 §1.11, §3.4: separate request/response models (no `-Input`/`-Output` variants),
    enums as components, money and quantities as strings in responses, number-or-string in
    requests."""
    app = FastAPI()

    @app.put("/estimate")
    async def edit(body: EstimateUpdate) -> EstimateEditRead:
        raise NotImplementedError

    @app.get("/estimates")
    async def versions() -> list[EstimateRead]:
        raise NotImplementedError

    @app.get("/me")
    async def mine() -> CustomerEstimateView:
        raise NotImplementedError

    @app.get("/summary")
    async def summary() -> EstimateSummary:
        raise NotImplementedError

    components = app.openapi()["components"]["schemas"]
    expected = {
        "CustomerEstimateLineRead",
        "CustomerEstimateRead",
        "EstimateEditRead",
        "EstimateLineRead",
        "EstimateLineType",
        "EstimateLineWrite",
        "EstimateRead",
        "EstimateStatus",
        "EstimateSummary",
        "EstimateUpdate",
        "PartStockRef",
        "StockState",
        "UserRef",
    }
    assert expected <= set(components)
    assert not [name for name in components if name.endswith(("-Input", "-Output"))]
    request_quantity = components["EstimateLineWrite"]["properties"]["quantity"]
    assert {option["type"] for option in request_quantity["anyOf"]} == {"number", "string"}
    assert components["EstimateLineRead"]["properties"]["quantity"]["type"] == "string"
    assert components["EstimateRead"]["properties"]["grand_total"]["type"] == "string"
    assert components["CustomerEstimateRead"]["properties"]["status"] == {
        "$ref": "#/components/schemas/EstimateStatus"
    }
    assert "part" not in components["CustomerEstimateLineRead"]["properties"]


def test_nul_characters_are_refused_before_they_reach_postgresql() -> None:
    """PostgreSQL text cannot hold U+0000 (SQLSTATE 22021): a 422, never a 500."""
    assert single_line_errors(labour_line(description="Fit\u0000coil")) == [
        ("lines.0.description", "value_error")
    ]
    assert errors_of({"lines": [labour_line()], "inspection_notes": "Coil\u0000"}) == [
        ("inspection_notes", "value_error")
    ]


@pytest.mark.parametrize("version", ["3", 3.0, True])
def test_expected_version_is_a_strict_integer_like_the_action_bodies(version: object) -> None:
    with pytest.raises(ValidationError) as caught:
        EstimateUpdate.model_validate({"lines": [labour_line()], "expected_version": version})
    assert caught.value.errors()[0]["loc"] == ("expected_version",)


def test_expected_version_accepts_a_plain_integer() -> None:
    update = EstimateUpdate.model_validate({"lines": [labour_line()], "expected_version": 3})
    assert update.expected_version == 3
