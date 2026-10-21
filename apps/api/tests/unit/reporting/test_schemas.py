"""Response schemas of the reporting module (`app/modules/reporting/schemas.py`), DB-free.

`stock_value` (`MoneyTotal`) has `Money`'s wire form — whole rupees, a decimal string with two
places (D41) — and the same OpenAPI shape, without the 10-digit bound of a stored amount. The
overview's lists are bounded: exactly 17 status counts, at most 5 low-stock parts.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.modules.inventory.schemas import PartRead
from app.modules.reporting.schemas import (
    OverviewInventory,
    OverviewRead,
    OverviewSetup,
    OverviewShop,
    OverviewStatusCount,
    OverviewToday,
    OwnerShopRef,
    OwnerShopSummary,
    OwnerSummaryRead,
)
from app.shared.enums import BookingStatus, StockState


def inventory(stock_value: object) -> OverviewInventory:
    return OverviewInventory(
        parts_count=1,
        low_stock_count=0,
        out_of_stock_count=0,
        stock_value=stock_value,  # type: ignore[arg-type]
        open_purchase_orders=0,
    )


@pytest.mark.parametrize(
    ("value", "wire"),
    [
        (Decimal(0), "0.00"),
        (Decimal("286400"), "286400.00"),
        (Decimal("286400.00"), "286400.00"),
        (Decimal("9999999999"), "9999999999.00"),
        (Decimal("19999999998"), "19999999998.00"),  # beyond one stored amount: still served
        (Decimal("123456789012345678"), "123456789012345678.00"),
    ],
)
def test_stock_value_is_whole_rupees_with_two_places(value: Decimal, wire: str) -> None:
    model = inventory(value)
    assert model.model_dump(mode="json")["stock_value"] == wire
    assert model.stock_value == value
    assert model.stock_value.as_tuple().exponent == -2


@pytest.mark.parametrize("value", [Decimal("1.50"), Decimal("-1"), Decimal("NaN"), "abc"])
def test_stock_value_refuses_paisa_negative_and_garbage(value: object) -> None:
    with pytest.raises(ValidationError):
        inventory(value)


def test_stock_value_is_documented_like_money() -> None:
    stock_value = OverviewInventory.model_json_schema(mode="serialization")["properties"][
        "stock_value"
    ]
    unit_cost = PartRead.model_json_schema(mode="serialization")["properties"]["unit_cost"]
    assert stock_value["type"] == unit_cost["type"] == "string"
    assert set(stock_value) == {"type", "title", "description", "examples"}
    assert stock_value["examples"] == ["286400.00"]


def _overview(**overrides: Any) -> dict[str, Any]:
    now = datetime(2026, 10, 15, 19, 30, tzinfo=UTC)
    part = PartRead(
        id=uuid.uuid4(),
        sku="IGN-COIL-01",
        name="Ignition coil",
        unit_cost=Decimal("6500"),
        is_active=True,
        on_hand=0,
        reserved=0,
        available=0,
        reorder_level=2,
        stock_state=StockState.OUT,
        on_order=1,
        created_at=now,
        updated_at=now,
    )
    values: dict[str, Any] = {
        "shop": OverviewShop(
            id=uuid.uuid4(),
            slug="lahore-auto-care",
            name="Lahore Auto Care",
            city="Lahore",
            is_listed=True,
        ),
        "status_counts": [OverviewStatusCount(status=status, count=0) for status in BookingStatus],
        "today": OverviewToday(
            date=date(2026, 10, 16), bookings=1, ready_for_pickup=0, completed=0
        ),
        "team": [],
        "inventory": inventory(Decimal("286400")),
        "low_stock": [part],
        "setup": OverviewSetup(has_services=True, has_team=True, has_parts=True, is_listed=True),
    }
    values.update(overrides)
    return values


def test_the_overview_serialises_dates_money_and_enums() -> None:
    body = OverviewRead(**_overview()).model_dump(mode="json")
    assert body["today"]["date"] == "2026-10-16"
    assert body["inventory"]["stock_value"] == "286400.00"
    assert body["status_counts"][0] == {"status": "PENDING", "count": 0}
    assert body["low_stock"][0]["unit_cost"] == "6500.00"
    assert body["low_stock"][0]["created_at"] == "2026-10-15T19:30:00Z"


@pytest.mark.parametrize("size", [0, 16, 18])
def test_status_counts_must_list_exactly_17_items(size: int) -> None:
    counts = [OverviewStatusCount(status=BookingStatus.PENDING, count=0)] * size
    with pytest.raises(ValidationError):
        OverviewRead(**_overview(status_counts=counts))


def test_low_stock_lists_at_most_five_parts() -> None:
    part = _overview()["low_stock"][0]
    assert len(OverviewRead(**_overview(low_stock=[part] * 5)).low_stock) == 5
    with pytest.raises(ValidationError):
        OverviewRead(**_overview(low_stock=[part] * 6))


def test_the_owner_summary_shape() -> None:
    shop_id = uuid.uuid4()
    summary = OwnerSummaryRead(
        items=[
            OwnerShopSummary(
                shop=OwnerShopRef(id=shop_id, slug="raza-auto-works", name="Raza", city="Lahore"),
                today_bookings=1,
                needs_sa_action=2,
                in_progress=3,
                ready_for_pickup=1,
                low_stock_count=4,
            )
        ]
    )
    assert summary.model_dump(mode="json") == {
        "items": [
            {
                "shop": {
                    "id": str(shop_id),
                    "slug": "raza-auto-works",
                    "name": "Raza",
                    "city": "Lahore",
                },
                "today_bookings": 1,
                "needs_sa_action": 2,
                "in_progress": 3,
                "ready_for_pickup": 1,
                "low_stock_count": 4,
            }
        ]
    }
    assert OwnerSummaryRead(items=[]).model_dump(mode="json") == {"items": []}
