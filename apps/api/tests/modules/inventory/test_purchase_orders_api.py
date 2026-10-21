"""General purchase orders over HTTP (spec 03 §4.10; D43, D44): create, list, detail. INV-20,
INV-29, INV-33, SEC-06 (PO half) and the PO-number savepoint retry of spec 02 §7.6."""

import re
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.core.database import Database
from app.core.errors import Conflict
from app.modules.inventory import service as inventory_service
from app.modules.inventory.models import PurchaseOrder, PurchaseOrderItem
from app.modules.inventory.schemas import PurchaseOrderCreate
from app.shared.clock import SimulatedClock
from app.shared.enums import MembershipRole
from app.shared.event_bus import EventBus
from app.shared.uow import UnitOfWork
from tests.modules.inventory.support import (
    Team,
    World,
    assert_ledger_invariants,
    assert_problem,
    bearer,
    field_codes,
    new_part,
    shop_context,
    url,
)

pytestmark = pytest.mark.db

PO_FORMAT = re.compile(r"^PO-[0-9A-HJKMNP-TV-Z]{6}$")


async def create_po(
    api: httpx.AsyncClient, team: Team, items: list[dict[str, Any]], **extra: Any
) -> httpx.Response:
    return await api.post(
        url(team.id, "/purchase-orders"), json={"items": items, **extra}, headers=bearer(team.parts)
    )


async def po_count(db: Database) -> tuple[int, int]:
    async with db.sessionmaker() as session:
        orders = (
            await session.execute(select(func.count()).select_from(PurchaseOrder))
        ).scalar_one()
        items = (
            await session.execute(select(func.count()).select_from(PurchaseOrderItem))
        ).scalar_one()
        return int(orders), int(items)


async def test_inv20_create_a_general_restock_order(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    tire = await new_part(api, world.a, "TIR-185-65-R15", name="Tire 185/65 R15", unit_cost="16000")
    wiper = await new_part(api, world.a, "WPR-PAIR", name="Wiper blades (pair)", unit_cost="2200")
    response = await create_po(
        api,
        world.a,
        [
            {"part_id": wiper["id"], "quantity": 4},
            {"part_id": tire["id"], "quantity": 4, "unit_cost": "15500"},
        ],
        supplier_name="  City Auto Parts ",
    )
    assert response.status_code == 201, response.text
    order = response.json()
    assert PO_FORMAT.fullmatch(order["po_number"])
    assert not order["po_number"].startswith("PO-SEED")
    items = order.pop("items")
    assert order == {
        "id": order["id"],
        "po_number": order["po_number"],
        "status": "ORDERED",
        "supplier_name": "City Auto Parts",
        "booking": None,
        "item_count": 2,
        "ordered_qty_total": 8,
        "received_qty_total": 0,
        "total_cost": "70800.00",
        "created_by": {"user_id": str(world.a.parts.id), "full_name": world.a.parts.full_name},
        "created_at": "2026-10-14T04:00:00Z",
        "received_at": None,
        "updated_at": "2026-10-14T04:00:00Z",
    }
    assert items == [  # by SKU
        {
            "id": items[0]["id"],
            "part": {"id": tire["id"], "sku": "TIR-185-65-R15", "name": "Tire 185/65 R15"},
            "ordered_qty": 4,
            "received_qty": 0,
            "outstanding_qty": 4,
            "unit_cost": "15500.00",
            "line_cost": "62000.00",
        },
        {
            "id": items[1]["id"],
            "part": {"id": wiper["id"], "sku": "WPR-PAIR", "name": "Wiper blades (pair)"},
            "ordered_qty": 4,
            "received_qty": 0,
            "outstanding_qty": 4,
            "unit_cost": "2200.00",
            "line_cost": "8800.00",
        },
    ]
    detail = await api.get(
        url(world.a.id, f"/purchase-orders/{order['id']}"), headers=bearer(world.a.owner)
    )
    assert detail.status_code == 200
    assert detail.json()["items"] == items
    await assert_ledger_invariants(db)  # creating a PO never changes stock


async def test_inv20_numbers_are_unique_per_order(api: httpx.AsyncClient, world: World) -> None:
    part = await new_part(api, world.a, "X1")
    numbers = set()
    for _ in range(5):
        response = await create_po(api, world.a, [{"part_id": part["id"], "quantity": 1}])
        assert response.status_code == 201
        numbers.add(response.json()["po_number"])
    assert len(numbers) == 5
    assert all(PO_FORMAT.fullmatch(number) for number in numbers)


async def test_inv29_items_must_be_active_parts_of_this_shop(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    active = await new_part(api, world.a, "ACTIVE")
    inactive = await new_part(api, world.a, "INACTIVE")
    await api.patch(
        url(world.a.id, f"/parts/{inactive['id']}"),
        json={"is_active": False},
        headers=bearer(world.a.owner),
    )
    theirs = await new_part(api, world.b, "THEIRS")
    response = await create_po(
        api,
        world.a,
        [
            {"part_id": active["id"], "quantity": 1},
            {"part_id": inactive["id"], "quantity": 1},
            {"part_id": theirs["id"], "quantity": 1},
            {"part_id": str(uuid4()), "quantity": 1},
        ],
    )
    assert field_codes(response) == [
        ("items.1.part_id", "invalid_reference"),
        ("items.2.part_id", "invalid_reference"),
        ("items.3.part_id", "invalid_reference"),
    ]
    assert await po_count(db) == (0, 0)


async def test_inv29_a_booking_id_in_the_body_is_refused(
    api: httpx.AsyncClient, world: World
) -> None:
    part = await new_part(api, world.a, "X1")
    response = await create_po(
        api, world.a, [{"part_id": part["id"], "quantity": 1}], booking_id=str(uuid4())
    )
    assert field_codes(response) == [("booking_id", "extra_forbidden")]


async def test_each_part_may_appear_once(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "X1")
    other = await new_part(api, world.a, "X2")
    response = await create_po(
        api,
        world.a,
        [
            {"part_id": part["id"], "quantity": 1},
            {"part_id": other["id"], "quantity": 1},
            {"part_id": part["id"], "quantity": 2},
        ],
    )
    assert field_codes(response) == [("items.2.part_id", "duplicate")]
    assert await po_count(db) == (0, 0)


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([], [("items", "too_short")]),
        ([{"quantity": 1}], [("items.0.part_id", "missing")]),
        ([{"part_id": "PLACEHOLDER", "quantity": 0}], [("items.0.quantity", "greater_than_equal")]),
        (
            [{"part_id": "PLACEHOLDER", "quantity": 10_001}],
            [("items.0.quantity", "less_than_equal")],
        ),
        (
            [{"part_id": "PLACEHOLDER", "quantity": 1, "unit_cost": "1.5"}],
            [("items.0.unit_cost", "not_whole_rupees")],
        ),
    ],
)
async def test_purchase_order_validation(
    api: httpx.AsyncClient,
    world: World,
    items: list[dict[str, Any]],
    expected: list[tuple[str, str]],
) -> None:
    part = await new_part(api, world.a, "X1")
    for item in items:
        if item.get("part_id") == "PLACEHOLDER":
            item["part_id"] = part["id"]
    assert field_codes(await create_po(api, world.a, items)) == expected


async def test_an_order_too_large_for_money_is_422_not_500(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "BIG", unit_cost="9999999999")
    one = await create_po(api, world.a, [{"part_id": part["id"], "quantity": 2}])
    assert field_codes(one) == [("items.0.quantity", "value_error")]
    small = await new_part(api, world.a, "SMALL", unit_cost="5000000000")
    total = await create_po(
        api,
        world.a,
        [{"part_id": small["id"], "quantity": 1}, {"part_id": part["id"], "quantity": 1}],
    )
    assert field_codes(total) == [("items", "value_error")]
    assert await po_count(db) == (0, 0)


async def test_inv18_sec06_only_the_parts_person_creates_purchase_orders(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "X1")
    for user in (world.a.owner, world.a.advisor, world.a.technician, world.a.qc):
        response = await api.post(
            url(world.a.id, "/purchase-orders"),
            json={"items": [{"part_id": part["id"], "quantity": 1}]},
            headers=bearer(user),
        )
        assert_problem(response, 403, "FORBIDDEN")
    for user in (world.b.parts, world.a.former_parts, world.customer):
        response = await api.post(
            url(world.a.id, "/purchase-orders"),
            json={"items": [{"part_id": part["id"], "quantity": 1}]},
            headers=bearer(user),
        )
        assert_problem(response, 404, "NOT_FOUND")
    assert await po_count(db) == (0, 0)


# --- INV-33: PO-number collisions retry inside a savepoint ---------------------------------------


async def test_inv33_a_taken_number_is_drawn_again(
    api: httpx.AsyncClient, world: World, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    part = await new_part(api, world.a, "X1", stock=2)
    first = await create_po(api, world.a, [{"part_id": part["id"], "quantity": 1}])
    taken = first.json()["po_number"]
    draws = iter([taken, taken, "PO-NEW001"])
    monkeypatch.setattr(inventory_service, "po_number_factory", lambda: next(draws))
    second = await create_po(
        api, world.a, [{"part_id": part["id"], "quantity": 3}], supplier_name="Retry"
    )
    assert second.status_code == 201, second.text
    assert second.json()["po_number"] == "PO-NEW001"
    assert second.json()["items"][0]["ordered_qty"] == 3
    assert await po_count(db) == (2, 2)
    # Another shop may hold the same number: uniqueness is per shop.
    monkeypatch.setattr(inventory_service, "po_number_factory", lambda: taken)
    theirs = await new_part(api, world.b, "X1")
    other_shop = await create_po(api, world.b, [{"part_id": theirs["id"], "quantity": 1}])
    assert other_shop.json()["po_number"] == taken


async def test_inv33_running_out_of_attempts_is_a_clean_500(
    api: httpx.AsyncClient, world: World, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    part = await new_part(api, world.a, "X1")
    taken = (await create_po(api, world.a, [{"part_id": part["id"], "quantity": 1}])).json()[
        "po_number"
    ]
    monkeypatch.setattr(inventory_service, "po_number_factory", lambda: taken)
    response = await create_po(api, world.a, [{"part_id": part["id"], "quantity": 1}])
    assert_problem(response, 500, "INTERNAL_ERROR")
    assert await po_count(db) == (1, 1)


async def test_the_seed_can_create_reserved_numbers_once(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "SPK-PLG-IR")
    data = PurchaseOrderCreate.model_validate(
        {
            "supplier_name": "City Auto Parts (demo)",
            "items": [{"part_id": part["id"], "quantity": 8}],
        }
    )
    ctx = shop_context(world.a, world.a.parts, MembershipRole.PARTS_PERSON)
    async with db.sessionmaker() as session:
        created = await inventory_service.create_purchase_order(
            UnitOfWork(session, EventBus()), ctx, data, po_number="PO-SEED01"
        )
    assert created.po_number == "PO-SEED01"
    async with db.sessionmaker() as session:
        with pytest.raises(Conflict):
            await inventory_service.create_purchase_order(
                UnitOfWork(session, EventBus()), ctx, data, po_number="PO-SEED01"
            )
    async with db.sessionmaker() as session:
        with pytest.raises(ValueError, match="not a PO-XXXXXX number"):
            await inventory_service.create_purchase_order(
                UnitOfWork(session, EventBus()), ctx, data, po_number="PO-SEED1"
            )
    assert await po_count(db) == (1, 1)


async def test_the_seed_finds_its_purchase_orders_by_shop_and_number(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    """Spec 11 keys general POs by `(shop_id, po_number)`: find, else create (D51, idempotent)."""
    data = PurchaseOrderCreate.model_validate(
        {"items": [{"part_id": (await new_part(api, world.a, "SPK-PLG-IR"))["id"], "quantity": 8}]}
    )
    ctx = shop_context(world.a, world.a.parts, MembershipRole.PARTS_PERSON)

    async def find(shop_id: UUID, po_number: str) -> UUID | None:
        async with db.sessionmaker() as session:
            return await inventory_service.find_purchase_order_id(
                session, shop_id=shop_id, po_number=po_number
            )

    assert await find(world.a.id, "PO-SEED01") is None  # first run: not there yet → create it
    async with db.sessionmaker() as session:
        seeded = await inventory_service.create_purchase_order(
            UnitOfWork(session, EventBus()), ctx, data, po_number="PO-SEED01"
        )
    assert await find(world.a.id, "PO-SEED01") == seeded.id  # a re-run finds it and skips
    random_po = (
        await create_po(api, world.a, [{"part_id": str(data.items[0].part_id), "quantity": 1}])
    ).json()
    assert await find(world.a.id, random_po["po_number"]) == UUID(random_po["id"])
    assert await find(world.b.id, "PO-SEED01") is None  # another shop's number
    assert await find(world.b.id, random_po["po_number"]) is None
    assert await find(world.a.id, "PO-SEED02") is None
    assert await find(world.a.id, "po-seed01") is None  # exact numbers only
    their_part = await new_part(api, world.b, "SPK-PLG-IR")
    their_data = PurchaseOrderCreate.model_validate(
        {"items": [{"part_id": their_part["id"], "quantity": 1}]}
    )
    async with db.sessionmaker() as session:
        theirs = await inventory_service.create_purchase_order(
            UnitOfWork(session, EventBus()),
            shop_context(world.b, world.b.parts, MembershipRole.PARTS_PERSON),
            their_data,
            po_number="PO-SEED01",
        )
    assert await find(world.b.id, "PO-SEED01") == theirs.id != seeded.id
    assert await find(world.a.id, "PO-SEED01") == seeded.id


# --- List and detail -----------------------------------------------------------------------------


async def test_list_shows_open_orders_first_then_newest(
    api: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    part = await new_part(api, world.a, "X1")
    created = []
    for _ in range(3):
        response = await create_po(api, world.a, [{"part_id": part["id"], "quantity": 2}])
        created.append(response.json())
        clock.advance(timedelta(minutes=10))
    oldest, middle, newest = created
    received = await api.post(
        url(world.a.id, f"/purchase-orders/{newest['id']}/receive"),
        json={"items": [{"item_id": newest["items"][0]["id"], "quantity": 2}]},
        headers=bearer(world.a.parts),
    )
    assert received.status_code == 200
    partial = await api.post(
        url(world.a.id, f"/purchase-orders/{oldest['id']}/receive"),
        json={"items": [{"item_id": oldest["items"][0]["id"], "quantity": 1}]},
        headers=bearer(world.a.parts),
    )
    assert partial.status_code == 200
    listing = await api.get(url(world.a.id, "/purchase-orders"), headers=bearer(world.a.owner))
    assert listing.status_code == 200
    page = listing.json()
    assert [o["id"] for o in page["items"]] == [middle["id"], oldest["id"], newest["id"]]
    assert [o["status"] for o in page["items"]] == ["ORDERED", "PARTIALLY_RECEIVED", "RECEIVED"]
    assert page["total"] == 3
    summary = page["items"][1]
    assert (summary["item_count"], summary["ordered_qty_total"], summary["received_qty_total"]) == (
        1,
        2,
        1,
    )
    assert summary["total_cost"] == "1800.00"
    assert "items" not in summary
    assert page["items"][2]["received_at"] is not None


async def test_list_filters_by_status_and_booking_and_paginates(
    api: httpx.AsyncClient, world: World
) -> None:
    part = await new_part(api, world.a, "X1")
    first = (await create_po(api, world.a, [{"part_id": part["id"], "quantity": 1}])).json()
    await create_po(api, world.a, [{"part_id": part["id"], "quantity": 1}])
    await api.post(
        url(world.a.id, f"/purchase-orders/{first['id']}/receive"),
        json={"items": [{"item_id": first["items"][0]["id"], "quantity": 1}]},
        headers=bearer(world.a.parts),
    )

    async def ids(**params: Any) -> list[str]:
        response = await api.get(
            url(world.a.id, "/purchase-orders"), params=params, headers=bearer(world.a.parts)
        )
        assert response.status_code == 200, response.text
        return [o["id"] for o in response.json()["items"]]

    assert await ids(status="RECEIVED") == [first["id"]]
    assert len(await ids(status=["ORDERED", "RECEIVED"])) == 2
    assert await ids(status="PARTIALLY_RECEIVED") == []
    assert await ids(booking_id=str(uuid4())) == []
    assert len(await ids(limit=1)) == 1
    assert len(await ids(limit=1, offset=1)) == 1
    bad = await api.get(
        url(world.a.id, "/purchase-orders"),
        params={"status": "CANCELLED"},
        headers=bearer(world.a.parts),
    )
    assert field_codes(bad) == [("query.status.0", "enum")]


async def test_purchase_orders_are_read_by_owner_and_parts_person_only(
    api: httpx.AsyncClient, world: World
) -> None:
    part = await new_part(api, world.a, "X1")
    order = (await create_po(api, world.a, [{"part_id": part["id"], "quantity": 1}])).json()
    for path in ("/purchase-orders", f"/purchase-orders/{order['id']}"):
        for user in (world.a.owner, world.a.parts, world.a.parts2):
            assert (await api.get(url(world.a.id, path), headers=bearer(user))).status_code == 200
        for user in (world.a.advisor, world.a.technician, world.a.qc):
            assert_problem(
                await api.get(url(world.a.id, path), headers=bearer(user)), 403, "FORBIDDEN"
            )
        assert_problem(
            await api.get(url(world.a.id, path), headers=bearer(world.b.owner)), 404, "NOT_FOUND"
        )


async def test_another_shops_purchase_orders_are_invisible(
    api: httpx.AsyncClient, world: World
) -> None:
    theirs = await new_part(api, world.b, "THEIRS")
    order = (await create_po(api, world.b, [{"part_id": theirs["id"], "quantity": 1}])).json()
    listing = await api.get(url(world.a.id, "/purchase-orders"), headers=bearer(world.a.parts))
    assert listing.json()["items"] == []
    for po_id in (order["id"], str(uuid4())):
        detail = await api.get(
            url(world.a.id, f"/purchase-orders/{po_id}"), headers=bearer(world.a.parts)
        )
        assert_problem(detail, 404, "NOT_FOUND")
    assert UUID(order["id"])
