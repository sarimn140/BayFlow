"""The three bookings reads the overview and the owner summary compose (`modules/bookings.md`
§5.3, pinned signatures), held to the contract reporting relies on. Each test runs twice: against
the plain-SQL stand-ins of `support.py` (`fake`) and against `bookings.service` itself (`real`),
which is skipped only while the bookings build still raises `NotImplementedError`.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from app.core.database import Database
from app.modules.bookings.service import DayActivity
from app.shared.enums import BookingStatus, MembershipRole
from tests.modules.reporting.support import (
    FAKE_BOOKINGS_READS,
    REAL_BOOKINGS_READS,
    BookingsRead,
    World,
    booking_rows,
)
from tests.rows import add_rows, make_membership, make_user

pytestmark = pytest.mark.db

S = BookingStatus
MICROSECOND = timedelta(microseconds=1)
START = datetime(2026, 10, 15, 19, 0, tzinfo=UTC)  # Fri 16 Oct 2026 00:00 PKT
END = START + timedelta(days=1)


@pytest.fixture(params=["fake", "real"])
def reads(request: pytest.FixtureRequest) -> dict[str, BookingsRead]:
    return FAKE_BOOKINGS_READS if request.param == "fake" else REAL_BOOKINGS_READS


async def call(db: Database, reads: dict[str, BookingsRead], name: str, **arguments: Any) -> Any:
    async with db.sessionmaker() as session:
        try:
            return await reads[name](session, **arguments)
        except NotImplementedError:
            pytest.skip(f"bookings.service.{name} still raises NotImplementedError")


async def test_count_by_status_lists_all_17_statuses_of_one_shop(
    db: Database, world: World, reads: dict[str, BookingsRead]
) -> None:
    rows = [
        row
        for status in (S.PENDING, S.PENDING, S.QC_PENDING, S.CANCELLED)
        for row in booking_rows(world.a, world.customer, status)
    ]
    rows += booking_rows(world.b, world.customer, S.COMPLETED)
    await add_rows(db.sessionmaker, *rows)

    counts = await call(db, reads, "count_by_status", shop_id=world.a.id)

    assert counts == {
        **dict.fromkeys(BookingStatus, 0),
        S.PENDING: 2,
        S.QC_PENDING: 1,
        S.CANCELLED: 1,
    }
    assert all(isinstance(status, BookingStatus) for status in counts)
    empty = await call(db, reads, "count_by_status", shop_id=uuid4())
    assert empty == dict.fromkeys(BookingStatus, 0)


async def test_count_open_jobs_per_requested_user(
    db: Database, world: World, reads: dict[str, BookingsRead]
) -> None:
    a, customer = world.a, world.customer
    both_roles = make_user(full_name="Asad")  # technician and parts person of the same job
    await add_rows(
        db.sessionmaker,
        both_roles,
        make_membership(a.shop, both_roles, MembershipRole.TECHNICIAN, created_by=a.owner),
    )
    rows = [
        *booking_rows(a, customer, S.ASSIGNED),
        *booking_rows(a, customer, S.QC_IN_PROGRESS),  # Imran, Usman and the picker Sara
        *booking_rows(a, customer, S.READY_FOR_PICKUP),  # finished: nobody's open job
        *booking_rows(a, customer, S.COMPLETED),
        *booking_rows(a, customer, S.CANCELLED, technician_user_id=a.technician.id),
        *booking_rows(a, customer, S.INSPECTING, technician_user_id=a.former.id),
        *booking_rows(
            a,
            customer,
            S.PARTS_READY,
            technician_user_id=both_roles.id,
            parts_person_user_id=both_roles.id,
        ),
        *booking_rows(world.b, customer, S.IN_REPAIR),  # another shop
    ]
    await add_rows(db.sessionmaker, *rows)
    stranger = uuid4()
    requested = [
        a.owner.id,
        a.technician.id,
        a.parts.id,
        a.qc.id,
        a.former.id,
        both_roles.id,
        world.b.technician.id,
        stranger,
    ]

    counts = await call(db, reads, "count_open_jobs", shop_id=a.id, user_ids=requested)

    assert counts == {
        a.owner.id: 0,
        a.technician.id: 2,  # ASSIGNED, QC_IN_PROGRESS (not RFP, COMPLETED, CANCELLED)
        a.parts.id: 1,  # QC_IN_PROGRESS
        a.qc.id: 1,  # the current picker; not the finished jobs Sara passed
        a.former.id: 1,  # a deactivated member keeps their assignments (D19)
        both_roles.id: 1,  # one booking, counted once
        world.b.technician.id: 0,  # their job is in Shop B
        stranger: 0,
    }


async def test_count_day_activity_uses_the_half_open_window(
    db: Database, world: World, reads: dict[str, BookingsRead]
) -> None:
    a, customer = world.a, world.customer
    rows: list[object] = []
    for moment in (START - MICROSECOND, START, END - MICROSECOND, END):
        rows += booking_rows(a, customer, S.CONFIRMED, slot_start=moment)
        rows += booking_rows(
            a, customer, S.COMPLETED, slot_start=moment - timedelta(days=4), completed_at=moment
        )
    rows += booking_rows(a, customer, S.CANCELLED, slot_start=START + timedelta(hours=10))
    rows += booking_rows(
        a,
        customer,
        S.COMPLETED,
        slot_start=START + timedelta(hours=1),
        completed_at=START + timedelta(hours=4),
    )  # booked and completed today: both counts
    rows += booking_rows(world.b, customer, S.PENDING, slot_start=START + timedelta(hours=10))
    await add_rows(db.sessionmaker, *rows)

    activity = await call(db, reads, "count_day_activity", shop_id=a.id, start=START, end=END)

    assert isinstance(activity, DayActivity)
    assert (activity.bookings, activity.completed) == (3, 3)
    nothing = await call(db, reads, "count_day_activity", shop_id=uuid4(), start=START, end=END)
    assert (nothing.bookings, nothing.completed) == (0, 0)
