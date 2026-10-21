"""What bookings offers other modules (`modules/bookings.md` §5.3, §5.4, §7.9, §7.11; D86, D89).

The pinned reads (`get_booking_refs`, `list_booking_viewer_ids` — NOT-12's and SEC-33's data half,
`count_by_status`, `count_open_jobs` — SHP-07's `open_jobs`, `count_day_activity`,
`has_future_bookings`), the real wiring of the app (`register_ports()` and `handlers.register`),
and the grid veto over HTTP (BK-29, BK-41).
"""

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI

from app.core.database import Database
from app.modules.bookings import handlers as bookings_handlers
from app.modules.bookings import service as bookings_service
from app.modules.bookings.models import Booking
from app.modules.identity import service as identity_service
from app.modules.inventory import service as inventory_service
from app.modules.inventory.events import PurchaseOrderReceived, PurchaseOrderReceiving
from app.modules.shops import service as shops_service
from app.modules.shops.events import ShopGridChanging
from app.modules.shops.schemas import MemberUpdate, StaffRole
from app.shared.clock import SimulatedClock
from app.shared.enums import BookingStatus, MembershipRole
from tests.modules.bookings.conftest import InvariantCheck
from tests.modules.bookings.support import (
    FRIDAY_1000,
    THURSDAY_0900,
    Desk,
    Journey,
    World,
    drive_booking_to,
    new_customer,
    problem,
)
from tests.modules.identity.builders import bearer, unit_of_work
from tests.modules.shops.builders import set_member_active

pytestmark = pytest.mark.db

S = BookingStatus


async def shop_b_booking(desk: Desk, db: Database) -> uuid.UUID:
    """A booking at the second tenant, by a customer of its own."""
    world = desk.world
    body = desk.booking_body(shop_id=world.other.id, services=world.other_services)
    customer = await new_customer(db, full_name="Shop B customer")
    response = await desk.wizard(body, headers=customer.headers)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["booking"]["id"])


# --- Wiring (D86, D89) ----------------------------------------------------------------------------


async def test_the_app_wires_the_bookings_ports_and_handlers(db_app: FastAPI) -> None:
    assert shops_service.get_activity_reader() is bookings_service.shop_activity_reader
    assert inventory_service.booking_ref_reader() is bookings_service.get_booking_refs
    bus = db_app.state.event_bus
    assert bookings_handlers.on_shop_grid_changing in bus.handlers_for(ShopGridChanging)
    receiving = bus.handlers_for(PurchaseOrderReceiving)
    assert bookings_handlers.on_purchase_order_receiving in receiving
    assert bookings_handlers.on_purchase_order_received in bus.handlers_for(PurchaseOrderReceived)


# --- get_booking_refs -----------------------------------------------------------------------------


async def test_get_booking_refs_reads_this_shops_bookings_on_the_callers_session(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, S.CONFIRMED)
    mine, theirs = uuid.UUID(journey.id), await shop_b_booking(desk, db)
    async with db.sessionmaker() as session:
        none = await bookings_service.get_booking_refs(
            session, shop_id=world.shop_id, booking_ids=[]
        )
        assert none == {}
        refs = await bookings_service.get_booking_refs(
            session, shop_id=world.shop_id, booking_ids=[mine, theirs, uuid.uuid4(), mine]
        )
        assert list(refs) == [mine]  # another shop's and unknown ids are absent
        ref = refs[mine]
        assert (ref.id, ref.reference, ref.status, ref.version) == (
            mine,
            journey.reference,
            S.CONFIRMED,
            2,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            ref.version = 99  # type: ignore[misc]
        row = await session.get(Booking, mine)
        assert row is not None
        row.version = 42  # an uncommitted write of the caller's own transaction
        await session.flush()
        seen = await bookings_service.get_booking_refs(
            session, shop_id=world.shop_id, booking_ids=[mine]
        )
        assert seen[mine].version == 42
        assert ref.version == 2  # the earlier value is a snapshot, never a live row
        await session.rollback()
    async with db.sessionmaker() as session:
        theirs_refs = await bookings_service.get_booking_refs(
            session, shop_id=world.other.id, booking_ids=[mine, theirs]
        )
    assert list(theirs_refs) == [theirs]


# --- list_booking_viewer_ids (NOT-12 / SEC-33 data half) ------------------------------------------


async def viewers(db: Database, journey: Journey) -> list[uuid.UUID]:
    async with db.sessionmaker() as session:
        return await bookings_service.list_booking_viewer_ids(
            session, booking_id=uuid.UUID(journey.id)
        )


async def test_viewer_ids_follow_d21_with_live_memberships(
    desk: Desk, world: World, db: Database
) -> None:
    owner, bilal = world.owner.id, world.advisor.id
    imran, hamza = world.technician.id, world.technician2.id
    usman, sara, hina = world.parts.id, world.qc.id, world.qc2.id
    desk_staff = {owner, bilal}

    pending = await desk.book()
    assert await viewers(db, pending) == sorted({pending.customer.user_id, *desk_staff})
    inspecting = await drive_booking_to(desk, S.INSPECTING)
    assert set(await viewers(db, inspecting)) == {inspecting.customer.user_id, *desk_staff, imran}
    reassign = {"technician_user_id": str(hamza)}
    await desk.act(world.advisor, inspecting.id, "reassign-technician", reassign)
    assert set(await viewers(db, inspecting)) == {inspecting.customer.user_id, *desk_staff, hamza}
    parts = await drive_booking_to(desk, S.PARTS_PENDING)
    assert set(await viewers(db, parts)) == {parts.customer.user_id, *desk_staff, imran, usman}
    queued = await drive_booking_to(desk, S.QC_PENDING)
    expected = {queued.customer.user_id, *desk_staff, imran, usman, sara, hina}
    assert set(await viewers(db, queued)) == expected
    passed = await drive_booking_to(desk, S.READY_FOR_PICKUP)  # Sara inspected it, Hina did not
    expected = {passed.customer.user_id, *desk_staff, imran, usman, sara}
    assert set(await viewers(db, passed)) == expected
    assert world.other.owner.id not in expected
    async with db.sessionmaker() as session:
        unknown = await bookings_service.list_booking_viewer_ids(session, booking_id=uuid.uuid4())
    assert unknown == []
    result = await viewers(db, passed)
    assert result == sorted(result)


async def test_viewer_ids_drop_deactivated_and_changed_members(
    desk: Desk, world: World, db: Database, invariants: InvariantCheck
) -> None:
    invariants.allow_inactive_recipients = True  # their notifications predate the deactivation
    passed = await drive_booking_to(desk, S.READY_FOR_PICKUP)
    customer = passed.customer.user_id
    await set_member_active(db, world.shop, world.advisor.membership_id, active=False)
    await set_member_active(db, world.shop, world.qc.membership_id, active=False)
    async with unit_of_work(db) as uow:  # an inactive account with an active membership
        await identity_service.set_user_active(uow, user_id=world.parts.id, is_active=False)
    async with unit_of_work(db) as uow:  # judged by the role held now
        await shops_service.update_member(
            uow,
            shop_id=world.shop_id,
            actor_user_id=world.owner.id,
            membership_id=world.technician.membership_id,
            data=MemberUpdate(role=StaffRole(MembershipRole.QC_INSPECTOR.value)),
        )
    assert set(await viewers(db, passed)) == {customer, world.owner.id}


# --- count_by_status, count_open_jobs (SHP-07), count_day_activity, has_future_bookings -----------


async def test_count_by_status_counts_every_booking_of_the_shop(
    desk: Desk, world: World, db: Database
) -> None:
    await desk.book()
    await drive_booking_to(desk, S.INSPECTING)
    await drive_booking_to(desk, S.CANCELLED)
    await shop_b_booking(desk, db)
    async with db.sessionmaker() as session:
        counts = await bookings_service.count_by_status(session, shop_id=world.shop_id)
        empty = await bookings_service.count_by_status(session, shop_id=uuid.uuid4())
    assert list(counts) == list(BookingStatus)
    assert counts == dict.fromkeys(BookingStatus, 0) | {
        S.PENDING: 1,
        S.INSPECTING: 1,
        S.CANCELLED: 1,
    }
    assert empty == dict.fromkeys(BookingStatus, 0)


async def test_count_open_jobs_counts_distinct_open_assignments(
    desk: Desk, world: World, db: Database
) -> None:
    await drive_booking_to(desk, S.INSPECTING)  # Imran
    await drive_booking_to(desk, S.PARTS_ORDERED)  # Imran, Usman
    await drive_booking_to(desk, S.QC_IN_PROGRESS)  # Imran, Usman, Sara (picker)
    await drive_booking_to(desk, S.READY_FOR_PICKUP)  # not open
    await drive_booking_to(desk, S.COMPLETED)  # not open
    cancelled = await drive_booking_to(desk, S.ASSIGNED)
    await desk.act(world.advisor, cancelled.id, "cancel", {"reason": "Sold"})  # not open
    ids = [
        world.technician.id,
        world.parts.id,
        world.qc.id,
        world.qc2.id,
        world.advisor.id,
        world.technician.id,  # repeated: counted once
        world.other_advisor.id,
    ]
    async with db.sessionmaker() as session:
        counts = await bookings_service.count_open_jobs(
            session, shop_id=world.shop_id, user_ids=ids
        )
        assert (
            await bookings_service.count_open_jobs(session, shop_id=world.shop_id, user_ids=[])
            == {}
        )
    assert counts == {
        world.technician.id: 3,
        world.parts.id: 2,
        world.qc.id: 1,
        world.qc2.id: 0,
        world.advisor.id: 0,
        world.other_advisor.id: 0,
    }
    members = await desk.get(world.owner.id, desk.shop_path("/members"), limit=100)
    open_jobs = {item["user"]["full_name"]: item["open_jobs"] for item in members["items"]}
    assert (open_jobs["Imran"], open_jobs["Usman"], open_jobs["Sara"], open_jobs["Hina"]) == (
        3,
        2,
        1,
        0,
    )


async def test_count_day_activity_uses_the_half_open_window(
    desk: Desk, world: World, db: Database, clock: SimulatedClock
) -> None:
    thursday = (THURSDAY_0900 - timedelta(hours=4), THURSDAY_0900 + timedelta(hours=20))
    first = await desk.book(slot=THURSDAY_0900)
    await desk.book(slot=THURSDAY_0900 + timedelta(hours=8))  # 17:00, same local day
    await desk.book(slot=FRIDAY_1000)  # the next day
    dropped = await desk.book(slot=THURSDAY_0900 + timedelta(hours=1))
    await desk.act(world.advisor, dropped.id, "decline", {"reason": "Bay closed"})
    done = await drive_booking_to(desk, S.READY_FOR_PICKUP, slot=FRIDAY_1000 + timedelta(days=1))
    clock.set(THURSDAY_0900 + timedelta(hours=3))  # completed on Thursday, slot on Saturday
    await desk.act(world.advisor, done.id, "complete")
    async with db.sessionmaker() as session:
        day = await bookings_service.count_day_activity(
            session, shop_id=world.shop_id, start=thursday[0], end=thursday[1]
        )
        boundary = await bookings_service.count_day_activity(
            session, shop_id=world.shop_id, start=THURSDAY_0900, end=THURSDAY_0900
        )
        before = await bookings_service.count_day_activity(
            session,
            shop_id=world.shop_id,
            start=THURSDAY_0900 - timedelta(hours=1),
            end=THURSDAY_0900,  # the 09:00 slot itself is excluded: [start, end)
        )
        other = await bookings_service.count_day_activity(
            session, shop_id=world.other.id, start=thursday[0], end=thursday[1]
        )
    assert (day.bookings, day.completed) == (2, 1)
    assert (boundary.bookings, boundary.completed) == (0, 0)
    assert (before.bookings, before.completed) == (0, 0)
    assert (other.bookings, other.completed) == (0, 0)
    assert first.booking["slot_start"] == "2026-10-15T04:00:00Z"


async def test_has_future_bookings_ignores_started_and_cancelled_ones(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await desk.book(slot=FRIDAY_1000)

    async def future(now: datetime) -> bool:
        async with db.sessionmaker() as session:
            return await bookings_service.has_future_bookings(
                session, shop_id=world.shop_id, now=now
            )

    assert await future(FRIDAY_1000 - timedelta(microseconds=1)) is True
    assert await future(FRIDAY_1000) is False  # a slot that has started is not "future"
    assert await future(datetime(2027, 1, 1, tzinfo=UTC)) is False
    await desk.my_act(journey.customer, journey.id, "cancel")
    assert await future(FRIDAY_1000 - timedelta(days=1)) is False
    async with db.sessionmaker() as session:
        assert not await bookings_service.has_future_bookings(
            session, shop_id=world.other.id, now=FRIDAY_1000 - timedelta(days=2)
        )


# --- BK-29, BK-41: the grid veto over HTTP --------------------------------------------------------


async def patch_shop(desk: Desk, world: World, **changes: object) -> httpx.Response:
    return await desk.api.patch(desk.shop_path(), json=changes, headers=bearer(world.owner.id))


async def test_bk29_bk41_grid_changes_wait_for_the_future_bookings(
    desk: Desk, world: World, db: Database, clock: SimulatedClock
) -> None:
    booked = await desk.book(slot=FRIDAY_1000)
    for change in ({"slot_duration_minutes": 90}, {"timezone": "Asia/Dubai"}):
        response = await patch_shop(desk, world, **change)
        body = problem(response, 409, "CONFLICT")
        assert "upcoming bookings" in body["detail"]
    shop = await desk.get(world.owner.id, desk.shop_path())
    assert (shop["slot_duration_minutes"], shop["timezone"], shop["has_future_bookings"]) == (
        60,
        "Asia/Karachi",
        True,
    )
    capacity = await patch_shop(desk, world, slot_capacity=3)
    assert capacity.status_code == 200, capacity.text
    # BK-41: once the slot has started, the booking is no longer "future".
    clock.set(FRIDAY_1000)
    started = await patch_shop(desk, world, slot_duration_minutes=90)
    assert started.status_code == 200, started.text
    assert (await desk.get(world.owner.id, desk.shop_path()))["slot_duration_minutes"] == 90
    assert booked.booking["slot_start"] == "2026-10-16T05:00:00Z"


async def test_bk41_a_cancelled_future_booking_never_blocks(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await desk.book(slot=FRIDAY_1000)
    problem(await patch_shop(desk, world, slot_duration_minutes=30), 409, "CONFLICT")
    await desk.act(world.advisor, journey.id, "decline", {"reason": "Fully booked"})
    off_grid = await patch_shop(desk, world, slot_duration_minutes=120)  # 18:00 is not on it
    body = problem(off_grid, 422, "VALIDATION_ERROR")
    assert "hours_not_on_grid" in {error["code"] for error in body["errors"]}
    changed = await patch_shop(desk, world, slot_duration_minutes=30)
    assert changed.status_code == 200, changed.text
    shop = await desk.get(world.owner.id, desk.shop_path())
    assert (shop["slot_duration_minutes"], shop["has_future_bookings"]) == (30, False)
