"""API-11 (P1): the inventory lists issue the same number of SQL statements for 1 and for 20 items
(no N+1: users, booking references, PO totals and on-order figures are read in batches)."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
from sqlalchemy import event

from app.core.database import Database
from tests.modules.inventory.support import (
    World,
    bearer,
    new_part,
    order_parts,
    reserve_for_booking,
    url,
)

pytestmark = pytest.mark.db


@contextmanager
def statements(db: Database) -> Iterator[list[str]]:
    """Every SQL statement sent through the test engine inside the block."""
    seen: list[str] = []

    def record(*args: Any) -> None:
        seen.append(str(args[2]))

    event.listen(db.engine.sync_engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(db.engine.sync_engine, "before_cursor_execute", record)


async def count_get(db: Database, api: httpx.AsyncClient, path: str, user: Any) -> int:
    with statements(db) as seen:
        response = await api.get(path, headers=bearer(user))
    assert response.status_code == 200, response.text
    return len(seen)


async def test_api11_parts_list_is_batched(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    first = await new_part(api, world.a, "P00", stock=3)
    await api.post(
        url(world.a.id, "/purchase-orders"),
        json={"items": [{"part_id": first["id"], "quantity": 1}]},
        headers=bearer(world.a.parts),
    )
    path = url(world.a.id, "/parts")
    one = await count_get(db, api, path, world.a.parts)
    for index in range(1, 20):
        await new_part(api, world.a, f"P{index:02d}", stock=index)
    twenty = await count_get(db, api, path, world.a.parts)
    assert one == twenty


async def test_api11_purchase_order_list_is_batched(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "COIL")
    await order_parts(db, world.a, world.customer, {part["id"]: 1})  # booking-linked
    path = url(world.a.id, "/purchase-orders")
    one = await count_get(db, api, path, world.a.owner)
    for _ in range(10):
        await order_parts(db, world.a, world.customer, {part["id"]: 1})
    for user in (world.a.parts, world.a.parts2) * 5:
        response = await api.post(
            url(world.a.id, "/purchase-orders"),
            json={"items": [{"part_id": part["id"], "quantity": 2}]},
            headers=bearer(user),
        )
        assert response.status_code == 201
    listing = await api.get(path, params={"limit": 50}, headers=bearer(world.a.owner))
    assert listing.json()["total"] == 21
    twenty = await count_get(db, api, path, world.a.owner)
    assert one == twenty


async def test_api11_movement_ledger_is_batched(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "OIL", stock=50)  # ADJUST
    order = await api.post(
        url(world.a.id, "/purchase-orders"),
        json={"items": [{"part_id": part["id"], "quantity": 30}]},
        headers=bearer(world.a.parts),
    )
    item_id = order.json()["items"][0]["id"]

    async def receive_one() -> None:  # RECEIVE, linked to the PO
        response = await api.post(
            url(world.a.id, f"/purchase-orders/{order.json()['id']}/receive"),
            json={"items": [{"item_id": item_id, "quantity": 1}]},
            headers=bearer(world.a.parts2),
        )
        assert response.status_code == 200, response.text

    await receive_one()
    await reserve_for_booking(db, world.a, world.customer, {part["id"]: 1})  # RESERVE + booking
    path = url(world.a.id, f"/parts/{part['id']}/movements")
    three = await count_get(db, api, path, world.a.owner)  # one row of each kind
    for index in range(6):
        await receive_one()
        await reserve_for_booking(db, world.a, world.customer, {part["id"]: 1})
        await new_part(api, world.a, f"X{index}")  # unrelated noise
    fifteen = await count_get(db, api, path, world.a.owner)
    page = await api.get(path, headers=bearer(world.a.owner))
    assert page.json()["total"] == 15
    assert one_of_each(page.json()["items"])
    assert three == fifteen


def one_of_each(items: list[dict[str, Any]]) -> bool:
    kinds = {item["movement_type"] for item in items}
    return {"ADJUST", "RECEIVE", "RESERVE"} <= kinds
