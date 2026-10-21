"""Inventory request schemas (spec 03 §4.10, §5.3): limits, normalisation and SEC-17 mass
assignment. The same rules are exercised over HTTP in `tests/modules/inventory`."""

import json
import uuid
from decimal import Decimal
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.modules.inventory.schemas import (
    PartCreate,
    PartUpdate,
    PurchaseOrderCreate,
    PurchaseOrderReceive,
    StockAdjustmentCreate,
)


def errors_of(model: type[BaseModel], payload: dict[str, Any]) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as caught:
        model.model_validate_json(json.dumps(payload))
    return [
        (".".join(str(part) for part in error["loc"]), error["type"])
        for error in caught.value.errors()
    ]


PART = {"sku": "OIL-FLT-01", "name": "Oil filter", "unit_cost": "900"}


def test_sku_is_trimmed_and_upper_cased_before_the_format_check() -> None:
    part = PartCreate.model_validate({**PART, "sku": "  ign/coil.01_x "})
    assert part.sku == "IGN/COIL.01_X"
    assert part.unit_cost == Decimal("900.00")
    assert (part.reorder_level, part.is_active) == (0, True)


@pytest.mark.parametrize(
    ("sku", "code"),
    [
        ("", "string_too_short"),
        ("   ", "string_too_short"),
        ("A" * 41, "string_too_long"),
        ("-LEADING-DASH", "string_pattern_mismatch"),
        ("WITH SPACE", "string_pattern_mismatch"),
        ("BAD#CHAR", "string_pattern_mismatch"),
    ],
)
def test_sku_format_is_enforced(sku: str, code: str) -> None:
    assert errors_of(PartCreate, {**PART, "sku": sku}) == [("sku", code)]


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("name", "   ", "string_too_short"),
        ("name", "x" * 121, "string_too_long"),
        ("unit_cost", "900.50", "not_whole_rupees"),
        ("unit_cost", 900.5, "not_whole_rupees"),
        ("unit_cost", "-1", "greater_than_equal"),
        ("reorder_level", -1, "greater_than_equal"),
        ("reorder_level", 100_001, "less_than_equal"),
        ("reorder_level", "5", "int_type"),
        ("is_active", "maybe", "bool_parsing"),
    ],
)
def test_part_create_limits(field: str, value: object, code: str) -> None:
    assert errors_of(PartCreate, {**PART, field: value}) == [(field, code)]


@pytest.mark.parametrize("field", ["on_hand", "reserved", "available", "shop_id", "id", "stock"])
def test_sec17_part_create_has_no_stock_or_tenant_fields(field: str) -> None:
    assert errors_of(PartCreate, {**PART, field: 5}) == [(field, "extra_forbidden")]


@pytest.mark.parametrize("field", ["on_hand", "reserved", "shop_id"])
def test_sec17_part_update_has_no_stock_or_tenant_fields(field: str) -> None:
    assert (field, "extra_forbidden") in errors_of(PartUpdate, {"name": "x", field: 5})


def test_part_update_needs_at_least_one_field() -> None:
    assert errors_of(PartUpdate, {}) == [("", "value_error")]


@pytest.mark.parametrize("field", ["sku", "name", "unit_cost", "reorder_level", "is_active"])
def test_part_update_refuses_null_for_non_nullable_fields(field: str) -> None:
    assert errors_of(PartUpdate, {field: None}) == [(field, "value_error")]


def test_part_update_keeps_track_of_what_was_sent() -> None:
    update = PartUpdate.model_validate({"sku": " new-sku ", "is_active": False})
    assert update.sku == "NEW-SKU"
    assert update.model_fields_set == {"sku", "is_active"}
    assert update.name is None


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"quantity_delta": 0, "reason": "count"}, [("quantity_delta", "value_error")]),
        ({"quantity_delta": 100_001, "reason": "x"}, [("quantity_delta", "less_than_equal")]),
        ({"quantity_delta": -100_001, "reason": "x"}, [("quantity_delta", "greater_than_equal")]),
        ({"quantity_delta": "5", "reason": "x"}, [("quantity_delta", "int_type")]),
        ({"quantity_delta": 1.0, "reason": "x"}, [("quantity_delta", "int_type")]),
        ({"quantity_delta": True, "reason": "x"}, [("quantity_delta", "int_type")]),
        ({"quantity_delta": 5}, [("reason", "missing")]),
        ({"quantity_delta": 5, "reason": "  "}, [("reason", "string_too_short")]),
        ({"quantity_delta": 5, "reason": "r" * 501}, [("reason", "string_too_long")]),
        ({"quantity_delta": 5, "reason": "x", "note": "y"}, [("note", "extra_forbidden")]),
    ],
)
def test_adjustment_limits(payload: dict[str, Any], expected: list[tuple[str, str]]) -> None:
    assert errors_of(StockAdjustmentCreate, payload) == expected


def test_adjustment_accepts_the_extremes_and_trims_the_reason() -> None:
    low = StockAdjustmentCreate.model_validate({"quantity_delta": -100_000, "reason": " count "})
    assert (low.quantity_delta, low.reason) == (-100_000, "count")
    assert StockAdjustmentCreate.model_validate({"quantity_delta": 100_000, "reason": "x"})


def po_item(**overrides: object) -> dict[str, object]:
    return {"part_id": str(uuid.uuid4()), "quantity": 1, **overrides}


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"items": []}, [("items", "too_short")]),
        ({"items": [po_item() for _ in range(51)]}, [("items", "too_long")]),
        ({"items": [po_item(quantity=0)]}, [("items.0.quantity", "greater_than_equal")]),
        ({"items": [po_item(quantity=10_001)]}, [("items.0.quantity", "less_than_equal")]),
        ({"items": [po_item(unit_cost="1.50")]}, [("items.0.unit_cost", "not_whole_rupees")]),
        ({"items": [po_item(part_id="nope")]}, [("items.0.part_id", "uuid_parsing")]),
        ({"items": [po_item()], "supplier_name": " "}, [("supplier_name", "string_too_short")]),
        (
            {"items": [po_item()], "booking_id": str(uuid.uuid4())},
            [("booking_id", "extra_forbidden")],
        ),
        ({"items": [po_item(status="RECEIVED")]}, [("items.0.status", "extra_forbidden")]),
    ],
)
def test_purchase_order_create_limits(
    payload: dict[str, Any], expected: list[tuple[str, str]]
) -> None:
    assert errors_of(PurchaseOrderCreate, payload) == expected


def test_purchase_order_create_accepts_fifty_items_and_an_optional_supplier() -> None:
    order = PurchaseOrderCreate.model_validate(
        {"items": [po_item(quantity=10_000) for _ in range(50)], "supplier_name": " City Auto "}
    )
    assert order.supplier_name == "City Auto"
    assert order.items[0].unit_cost is None


def receive_line(**overrides: object) -> dict[str, object]:
    return {"item_id": str(uuid.uuid4()), "quantity": 1, **overrides}


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"items": []}, [("items", "too_short")]),
        ({"items": [receive_line(quantity=-1)]}, [("items.0.quantity", "greater_than_equal")]),
        ({"items": [receive_line(quantity=10_001)]}, [("items.0.quantity", "less_than_equal")]),
        (
            {"items": [receive_line(expected_received_qty=-1)]},
            [("items.0.expected_received_qty", "greater_than_equal")],
        ),
        (
            {"items": [receive_line(expected_received_qty="0")]},
            [("items.0.expected_received_qty", "int_type")],
        ),
        ({"items": [receive_line()], "received_at": "now"}, [("received_at", "extra_forbidden")]),
    ],
)
def test_receipt_limits(payload: dict[str, Any], expected: list[tuple[str, str]]) -> None:
    assert errors_of(PurchaseOrderReceive, payload) == expected


def test_receipt_accepts_zero_quantities_and_null_expectations() -> None:
    receipt = PurchaseOrderReceive.model_validate(
        {"items": [receive_line(quantity=0, expected_received_qty=None)]}
    )
    assert receipt.items[0].quantity == 0
    assert receipt.items[0].expected_received_qty is None
