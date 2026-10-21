"""The D86 read port `ShopActivityReader` (`modules/shops.md` §5.3, spec 01 rule 3).

Unregistered, it fails loudly (`RuntimeError`), never reporting "no bookings". Registered (by
bookings' `register_ports()` in the app, or a fake here), it feeds `ShopRead.has_future_bookings`
and `MemberRead.open_jobs`.
"""

import httpx
import pytest

from app.core.database import Database
from app.modules.shops import service as shops_service
from app.modules.shops.schemas import ShopUpdate, WorkingHoursUpdate
from app.shared.enums import MembershipRole
from tests.modules.identity.builders import bearer, unit_of_work
from tests.modules.shops.builders import add_member, make_shop, week
from tests.modules.shops.fakes import FakeActivityReader

pytestmark = pytest.mark.db


async def test_an_unregistered_port_raises(db: Database) -> None:
    ctx = await make_shop(db)  # creating a shop needs no reader
    previous = shops_service.register_activity_reader(None)
    try:
        with pytest.raises(RuntimeError, match="no ShopActivityReader is registered"):
            shops_service.get_activity_reader()
        async with db.sessionmaker() as session:
            with pytest.raises(RuntimeError):
                await shops_service.get_shop(session, shop_id=ctx.id)
        async with unit_of_work(db) as uow:
            with pytest.raises(RuntimeError):
                await shops_service.update_shop(
                    uow,
                    shop_id=ctx.id,
                    actor_user_id=ctx.owner.id,
                    data=ShopUpdate(slot_capacity=9),
                )
        async with unit_of_work(db) as uow:
            with pytest.raises(RuntimeError):
                await shops_service.replace_working_hours(
                    uow,
                    shop_id=ctx.id,
                    actor_user_id=ctx.owner.id,
                    data=WorkingHoursUpdate.model_validate({"working_hours": week("10:00")}),
                )
        member = await add_member(db, ctx, MembershipRole.TECHNICIAN)  # needs no reader either
    finally:
        shops_service.register_activity_reader(previous)
    async with db.sessionmaker() as session:
        shop = await shops_service.get_shop(session, shop_id=ctx.id)
    assert shop.slot_capacity == 2  # the failed update committed nothing
    assert shop.working_hours[0].opens_at == "09:00"
    assert member.role is MembershipRole.TECHNICIAN


def test_register_returns_the_previous_reader() -> None:
    first, second = FakeActivityReader(), FakeActivityReader()
    original = shops_service.register_activity_reader(first)
    try:
        assert shops_service.register_activity_reader(second) is first
        assert shops_service.get_activity_reader() is second
    finally:
        shops_service.register_activity_reader(original)


async def test_has_future_bookings_comes_from_the_port(
    db_client: httpx.AsyncClient, db: Database, activity_reader: FakeActivityReader
) -> None:
    ctx = await make_shop(db)
    url = f"/api/v1/shops/{ctx.id}"
    headers = bearer(ctx.owner.id)
    assert (await db_client.get(url, headers=headers)).json()["has_future_bookings"] is False
    activity_reader.future_bookings = True
    assert (await db_client.get(url, headers=headers)).json()["has_future_bookings"] is True
    patched = await db_client.patch(url, json={"slot_capacity": 3}, headers=headers)
    assert patched.json()["has_future_bookings"] is True  # the settings form locks the grid
    hours = await db_client.put(
        f"{url}/working-hours", json={"working_hours": week()}, headers=headers
    )
    assert hours.json()["has_future_bookings"] is True
    assert ("has_future_bookings", ctx.id) in activity_reader.calls


async def test_shop_creation_does_not_ask_the_port(
    db_client: httpx.AsyncClient, db: Database, activity_reader: FakeActivityReader
) -> None:
    ctx = await make_shop(db)
    activity_reader.future_bookings = True
    created = await db_client.post(
        "/api/v1/shops",
        json={
            "name": "Brand New",
            "address": "1 Mall Road",
            "city": "Lahore",
            "phone": "+924200000000",
            "slot_duration_minutes": 60,
            "slot_capacity": 1,
            "working_hours": week(),
        },
        headers=bearer(ctx.owner.id),
    )
    assert created.json()["has_future_bookings"] is False  # a new shop has no bookings
    assert activity_reader.calls == []
