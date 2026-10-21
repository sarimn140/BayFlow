"""Races through the lock gate (spec 12 §3.5; `modules/bookings.md` §11).

CON-01 (double submit), SM-06 ★ / BK-39 (two QC picks), SM-07 ★ through the wizard (the last place
in a slot), CON-02 (cancel vs allocate-parts), CON-03 (two cancels of one slot), CON-04 (PO
receipt vs cancel, both orders), CON-05 (grid change vs booking creation, both orders) and two
new customers booking with the same new e-mail (case B, D32).

Each race holds the contested row with `hold_row_lock`, starts the requests one at a time, and
starts the next only once the previous one waits on a lock: PostgreSQL then hands the row over in
that order, so "who wins" is chosen by the test instead of by luck. The shared invariants are
checked after every test (conftest), and the 5 s `lock_timeout` of the test database turns any
lock-order bug into a failure instead of a hang.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from app.core.database import Database
from app.modules.bookings.models import Booking, Vehicle
from app.modules.identity.models import User
from app.modules.qc.models import QcInspection
from app.shared.clock import SimulatedClock
from app.shared.enums import BookingAction, BookingStatus
from tests.lockgate import hold_row_lock, wait_for_lock_waiters
from tests.modules.admin.support import audit_rows, make_admin
from tests.modules.bookings.support import (
    FRIDAY_1000,
    Desk,
    World,
    booking_row,
    build_world,
    drive_booking_to,
    events_of,
    next_client_ip,
    problem,
    slot_count,
)
from tests.modules.identity.builders import TEST_PASSWORD, bearer, unique_email

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

S = BookingStatus
Request = Callable[[], Awaitable[httpx.Response]]


@pytest.fixture
async def world(db: Database, clock: SimulatedClock) -> World:
    """Two cars per slot, so SM-07 can race for the last place."""
    return await build_world(db, capacity=2)


async def race(db: Database, table: str, key: dict[str, Any], *requests: Request) -> list[Any]:
    """Run `requests` against the gated row, granting it to them in the order given."""
    tasks: list[asyncio.Task[httpx.Response]] = []
    async with hold_row_lock(db, table, **key):
        for waiting, request in enumerate(requests, start=1):
            tasks.append(asyncio.create_task(request()))
            await wait_for_lock_waiters(db, waiting)
    return [await task for task in tasks]


def post(desk: Desk, user_id: uuid.UUID, booking_id: str, slug: str, body: Any = None) -> Request:
    def request() -> Awaitable[httpx.Response]:
        return desk.act_raw(user_id, booking_id, slug, body)

    return request


# --- CON-01, SM-06 ★ / BK-39 ----------------------------------------------------------------------


async def test_con01_a_double_submit_confirms_once(desk: Desk, world: World, db: Database) -> None:
    journey = await desk.book()
    key = {"id": uuid.UUID(journey.id)}
    first, second = await race(
        db,
        "bookings",
        key,
        post(desk, world.advisor.id, journey.id, "confirm"),
        post(desk, world.owner.id, journey.id, "confirm"),
    )
    assert first.status_code == 200, first.text
    problem(second, 409, "INVALID_TRANSITION")  # the loser re-read the committed row
    events = await events_of(db, journey.id)
    assert [event.action for event in events] == [BookingAction.CREATE, BookingAction.CONFIRM]
    assert events[-1].actor_user_id == world.advisor.id
    row = await booking_row(db, journey.id)
    assert (row.status, row.version) == (S.CONFIRMED, 2)


@pytest.mark.parametrize("sara_first", [True, False])
async def test_sm06_bk39_two_qc_inspectors_pick_at_once(
    desk: Desk, world: World, db: Database, sara_first: bool
) -> None:
    journey = await drive_booking_to(desk, S.QC_PENDING)
    pickers = [world.qc, world.qc2] if sara_first else [world.qc2, world.qc]
    winner, loser = await race(
        db,
        "bookings",
        {"id": uuid.UUID(journey.id)},
        *(post(desk, member.id, journey.id, "pick-qc") for member in pickers),
    )
    assert winner.status_code == 200, winner.text
    assert winner.json()["qc_inspector"]["full_name"] == pickers[0].user.full_name
    body = problem(loser, 409, "ALREADY_PICKED")
    assert body["detail"] == f"Already picked by {pickers[0].user.full_name}."
    picks = [e for e in await events_of(db, journey.id) if e.action == BookingAction.PICK_QC]
    assert len(picks) == 1
    async with db.sessionmaker() as session:
        rounds = (
            (
                await session.execute(
                    select(QcInspection.inspector_user_id).where(
                        QcInspection.booking_id == uuid.UUID(journey.id)
                    )
                )
            )
            .scalars()
            .all()
        )
    assert rounds == [pickers[0].id]


# --- SM-07 ★: the last place in a slot ------------------------------------------------------------


async def test_sm07_two_customers_race_for_the_last_place(
    desk: Desk, world: World, db: Database
) -> None:
    await desk.book(slot=FRIDAY_1000)  # one of the two places is taken
    emails = [unique_email("racer"), unique_email("racer")]

    def wizard(email: str, plate: str) -> Request:
        body = desk.booking_body(slot=FRIDAY_1000, registration=plate)
        body["customer"] = {"full_name": "Racer", "email": email, "password": TEST_PASSWORD}

        def request() -> Awaitable[httpx.Response]:
            return desk.wizard(body, headers={"X-Real-IP": next_client_ip()})

        return request

    key = {"shop_id": world.shop_id, "slot_start": FRIDAY_1000}
    winner, loser = await race(
        db, "slot_counters", key, wizard(emails[0], "AAA-111"), wizard(emails[1], "BBB-222")
    )
    assert winner.status_code == 201, winner.text
    problem(loser, 409, "SLOT_FULL")
    assert await slot_count(db, world.shop_id, FRIDAY_1000) == 2
    async with db.sessionmaker() as session:
        users = (await session.execute(select(User.email).where(User.email.in_(emails)))).all()
        plates = (
            await session.execute(
                select(Vehicle.registration_key).where(Vehicle.registration_key == "BBB222")
            )
        ).all()
    assert [row.email for row in users] == [emails[0]]  # the loser's account was rolled back
    assert plates == []


async def test_case_b_two_new_customers_with_the_same_new_email(
    desk: Desk, world: World, db: Database
) -> None:
    email = unique_email("twin")

    def wizard(name: str, plate: str) -> Request:
        body = desk.booking_body(registration=plate)
        body["customer"] = {"full_name": name, "email": email, "password": TEST_PASSWORD}

        def request() -> Awaitable[httpx.Response]:
            return desk.wizard(body, headers={"X-Real-IP": next_client_ip()})

        return request

    # The first creates the account and waits on the shop row (gated); the second's insert of the
    # same e-mail waits on the first transaction, then loses on the unique index.
    first, second = await race(
        db, "shops", {"id": world.shop_id}, wizard("Ali", "AAA-111"), wizard("Ali Two", "BBB-222")
    )
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [201, 409], (first.text, second.text)
    loser = first if first.status_code == 409 else second
    body = problem(loser, 409, "EMAIL_ALREADY_REGISTERED")
    assert "Log in" in body["detail"]
    async with db.sessionmaker() as session:
        accounts = (
            await session.execute(select(func.count()).select_from(User).where(User.email == email))
        ).scalar_one()
        bookings = (await session.execute(select(func.count()).select_from(Booking))).scalar_one()
    assert (accounts, bookings) == (1, 1)


# --- CON-02, CON-03 -------------------------------------------------------------------------------


@pytest.mark.parametrize("cancel_first", [True, False])
async def test_con02_cancel_racing_allocate_parts(
    desk: Desk, world: World, db: Database, cancel_first: bool
) -> None:
    journey = await drive_booking_to(desk, S.PARTS_READY)
    cancel = post(desk, world.advisor.id, journey.id, "cancel", {"reason": "Customer withdrew"})
    allocate = post(desk, world.parts.id, journey.id, "allocate-parts")
    order = [cancel, allocate] if cancel_first else [allocate, cancel]
    winner, loser = await race(db, "bookings", {"id": uuid.UUID(journey.id)}, *order)
    assert winner.status_code == 200, winner.text
    problem(loser, 409, "INVALID_TRANSITION")
    row = await booking_row(db, journey.id)
    filters = await desk.balance(world.catalogue.oil_filter)
    if cancel_first:
        assert row.status == S.CANCELLED
        assert filters == (100, 0)  # released
        assert await desk.balance(world.catalogue.coil) == (1, 0)
    else:
        assert row.status == S.IN_REPAIR
        assert filters == (99, 0)  # consumed
        assert await desk.balance(world.catalogue.coil) == (0, 0)


async def test_con03_two_cancels_in_one_slot_free_both_places(
    desk: Desk, world: World, db: Database
) -> None:
    first = await desk.book(slot=FRIDAY_1000)
    second = await desk.book(slot=FRIDAY_1000)
    assert await slot_count(db, world.shop_id, FRIDAY_1000) == 2
    one, two = await race(
        db,
        "slot_counters",
        {"shop_id": world.shop_id, "slot_start": FRIDAY_1000},
        post(desk, world.advisor.id, first.id, "decline", {"reason": "Bay closed"}),
        post(desk, world.advisor.id, second.id, "decline", {"reason": "Bay closed"}),
    )
    assert (one.status_code, two.status_code) == (200, 200), (one.text, two.text)
    assert await slot_count(db, world.shop_id, FRIDAY_1000) == 0


# --- CON-04: PO receipt vs cancel -----------------------------------------------------------------


@pytest.mark.parametrize("receipt_first", [True, False])
async def test_con04_a_receipt_racing_a_cancel_of_its_booking(
    desk: Desk, world: World, db: Database, receipt_first: bool
) -> None:
    journey = await drive_booking_to(desk, S.PARTS_ORDERED)
    order_id = str(journey.purchase_order_id)
    order = await desk.get(world.parts.id, desk.shop_path(f"/purchase-orders/{order_id}"))
    items = [
        {"item_id": item["id"], "quantity": item["outstanding_qty"]} for item in order["items"]
    ]

    def receive() -> Awaitable[httpx.Response]:
        return desk.api.post(
            desk.shop_path(f"/purchase-orders/{order_id}/receive"),
            json={"items": items},
            headers=bearer(world.parts.id),
        )

    cancel = post(desk, world.advisor.id, journey.id, "cancel", {"reason": "Customer withdrew"})
    requests = [receive, cancel] if receipt_first else [cancel, receive]
    responses = await race(db, "bookings", {"id": uuid.UUID(journey.id)}, *requests)
    assert [response.status_code for response in responses] == [200, 200], [
        response.text for response in responses
    ]
    receipt = responses[0] if receipt_first else responses[1]
    assert receipt.json()["purchase_order"]["status"] == "RECEIVED"
    assert receipt.json()["receive_parts_applied"] is receipt_first
    actions = [event.action for event in await events_of(db, journey.id)]
    if receipt_first:  # the receipt reserved and moved the booking; the cancel then released it
        assert actions[-2:] == [BookingAction.RECEIVE_PARTS, BookingAction.CANCEL]
    else:  # the cancel won: the receipt reserved nothing (INV-24)
        assert actions[-1] == BookingAction.CANCEL
        assert BookingAction.RECEIVE_PARTS not in actions
    assert (await booking_row(db, journey.id)).status == S.CANCELLED
    assert await desk.balance(world.catalogue.coil) == (1, 0)  # general stock either way
    assert await desk.balance(world.catalogue.oil_filter) == (100, 0)


# --- CON-05: grid change vs booking creation ------------------------------------------------------


@pytest.mark.parametrize("booking_first", [True, False])
async def test_con05_a_grid_change_racing_a_booking(
    desk: Desk, world: World, db: Database, booking_first: bool
) -> None:
    earlier = await desk.book(slot=FRIDAY_1000 + timedelta(days=7))
    await desk.my_act(earlier.customer, earlier.id, "cancel")  # a cancelled booking never blocks
    body = desk.booking_body(slot=FRIDAY_1000)  # Friday 10:00: off a 90-minute grid

    def book() -> Awaitable[httpx.Response]:
        return desk.wizard(body, headers=earlier.customer.headers)

    def change_grid() -> Awaitable[httpx.Response]:
        return desk.api.patch(
            desk.shop_path(),
            json={"slot_duration_minutes": 90},
            headers=bearer(world.owner.id),
        )

    requests = [book, change_grid] if booking_first else [change_grid, book]
    responses = await race(db, "shops", {"id": world.shop_id}, *requests)
    booking, grid = (responses[0], responses[1]) if booking_first else (responses[1], responses[0])
    async with db.sessionmaker() as session:
        live = (
            await session.execute(
                select(func.count()).select_from(Booking).where(Booking.status != S.CANCELLED)
            )
        ).scalar_one()
    if booking_first:
        assert booking.status_code == 201, booking.text
        problem(grid, 409, "CONFLICT")  # the bookings veto saw the new booking (D37)
        shop = await desk.get(world.owner.id, desk.shop_path())
        assert shop["slot_duration_minutes"] == 60
        assert live == 1
    else:
        assert grid.status_code == 200, grid.text
        assert grid.json()["slot_duration_minutes"] == 90
        problem(booking, 422, "INVALID_SLOT")  # checked against the new grid, never the old
        assert live == 0
        assert await slot_count(db, world.shop_id, FRIDAY_1000) is None


# --- Unlisting or suspension vs booking creation (D96; spec 19 §7) -------------------------------


@pytest.mark.parametrize("closing", ["suspend", "unlist"])
async def test_a_booking_waiting_on_the_shop_row_sees_it_closed(
    desk: Desk, world: World, db: Database, closing: str
) -> None:
    """The wizard passed the unlocked "bookable" check, then waits for the shop row `FOR SHARE`
    while a suspension (or an unlisting) holds it `FOR UPDATE`. Once that commits, the booking
    re-reads the shop under its lock and answers 404 like the unlocked check; the case-B account
    and every audit row of the attempt roll back with it."""
    admin = await make_admin(db, full_name="Areeba Hashmi")
    email = unique_email("late")
    body = desk.booking_body(
        customer={"full_name": "Late Customer", "email": email, "password": TEST_PASSWORD}
    )

    def close() -> Awaitable[httpx.Response]:
        if closing == "suspend":
            return desk.api.post(
                f"/api/v1/admin/shops/{world.shop_id}/suspend",
                headers=bearer(admin.id),
                json={"reason": "Closed while a customer was booking"},
            )
        return desk.api.patch(
            desk.shop_path(), json={"is_listed": False}, headers=bearer(world.owner.id)
        )

    def book() -> Awaitable[httpx.Response]:
        return desk.wizard(body, headers={"X-Real-IP": next_client_ip()})

    closed, booking = await race(db, "shops", {"id": world.shop_id}, close, book)
    assert closed.status_code == 200, closed.text
    problem(booking, 404, "NOT_FOUND")
    async with db.sessionmaker() as session:
        assert (await session.execute(select(func.count()).select_from(Booking))).scalar_one() == 0
        account = await session.execute(select(User).where(User.email == email))
        assert account.scalar_one_or_none() is None
    assert await audit_rows(db, action="user.customer_created") == []
    assert await audit_rows(db, action="booking.create") == []
