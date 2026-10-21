"""`GET /api/v1/shops/{shop_id}/overview` — `reporting_get_overview` (spec 03 §3.7, §4.13;
`modules/reporting.md`).

RPT-01 (the selected shop's data only), RPT-03 (Owner only: 403 for every other role, 404 for
non-members), RPT-04 (all 17 statuses in glossary §3 order, zeros included, summing to the shop's
bookings), RPT-05 (today in the shop's time zone: the spec's frozen-clock case, every window bound,
cancelled bookings, `completed_at`, and DST days of 23 and 25 hours), RPT-06 (inventory over
active parts), RPT-07 (the team with open jobs) and RPT-08 (setup flags of a brand-new shop, then
each flipping after its matching action).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from app.core.database import Database
from app.modules.identity.models import User
from app.shared.clock import SimulatedClock
from app.shared.enums import BookingStatus, MembershipRole, PurchaseOrderStatus
from tests.assertions import assert_problem
from tests.modules.reporting.support import (
    GLOSSARY_STATUS_ORDER,
    LONDON,
    Cast,
    World,
    add_booking,
    add_bookings,
    bearer,
    booking_rows,
    make_cast,
    overview_url,
    part_row,
    purchase_order_rows,
    service_row,
)
from tests.rows import add_rows, make_membership, make_user

pytestmark = pytest.mark.db

S = BookingStatus
OWNER = MembershipRole.OWNER
SA = MembershipRole.SERVICE_ADVISOR
TECH = MembershipRole.TECHNICIAN
PP = MembershipRole.PARTS_PERSON
QC = MembershipRole.QC_INSPECTOR

MICROSECOND = timedelta(microseconds=1)
# RPT-05: Friday 16 Oct 2026 in Asia/Karachi (UTC+5) is [2026-10-15T19:00Z, 2026-10-16T19:00Z).
PKT_FRIDAY_START = datetime(2026, 10, 15, 19, 0, tzinfo=UTC)
PKT_FRIDAY_END = datetime(2026, 10, 16, 19, 0, tzinfo=UTC)
NOT_FOUND_DETAIL = "The requested resource was not found."


async def get_overview(api: httpx.AsyncClient, cast: Cast, user: User | None = None) -> Any:
    response = await api.get(overview_url(cast.id), headers=bearer(user or cast.owner))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"  # API-13 (D61)
    return response.json()


def counts_of(body: dict[str, Any]) -> dict[str, int]:
    return {item["status"]: item["count"] for item in body["status_counts"]}


def zero_counts(**counts: int) -> dict[str, int]:
    return {**dict.fromkeys(GLOSSARY_STATUS_ORDER, 0), **counts}


async def table_counts(db: Database, shop_id: object) -> dict[str, int]:
    """The `bookings` table itself, grouped by status (RPT-01's source of truth)."""
    async with db.sessionmaker() as session:
        rows = await session.execute(
            text("SELECT status, count(*) FROM bookings WHERE shop_id = :id GROUP BY status"),
            {"id": shop_id},
        )
        return zero_counts(**{status: int(count) for status, count in rows.all()})


def team_ids(cast: Cast) -> set[str]:
    members = (
        cast.owner,
        cast.advisor,
        cast.technician,
        cast.technician_2,
        cast.parts,
        cast.qc,
        cast.qc_2,
        cast.former,
    )
    return {str(user.id) for user in members}


# --- RPT-01 ---------------------------------------------------------------------------------------


async def test_rpt01_the_overview_shows_only_the_selected_shop(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    a, b, customer = world.a, world.b, world.customer
    await add_bookings(db, a, customer, [S.PENDING, S.PENDING, S.IN_REPAIR, S.COMPLETED])
    await add_bookings(
        db, b, customer, [S.CONFIRMED, S.QC_PENDING, S.QC_PENDING, S.CANCELLED, S.PARTS_READY]
    )
    await add_rows(
        db.sessionmaker,
        part_row(a, "A-OUT", on_hand=0, reorder_level=2),
        part_row(a, "A-OK", on_hand=10, reorder_level=2, unit_cost="100"),
        part_row(b, "B-LOW", on_hand=1, reorder_level=5),
        part_row(b, "B-OUT", on_hand=0),
        *purchase_order_rows(b, PurchaseOrderStatus.ORDERED),
    )

    body = await get_overview(api, a)

    assert body["shop"] == {
        "id": str(a.id),
        "slug": a.shop.slug,
        "name": a.shop.name,
        "city": "Lahore",
        "is_listed": True,
    }
    assert counts_of(body) == await table_counts(db, a.id)
    assert counts_of(body) == zero_counts(PENDING=2, IN_REPAIR=1, COMPLETED=1)
    assert {member["user_id"] for member in body["team"]} == team_ids(a)
    assert body["inventory"] == {
        "parts_count": 2,
        "low_stock_count": 1,
        "out_of_stock_count": 1,
        "stock_value": "1000.00",
        "open_purchase_orders": 0,
    }
    assert [part["sku"] for part in body["low_stock"]] == ["A-OUT"]

    other = await get_overview(api, b)
    assert other["shop"]["id"] == str(b.id)
    assert counts_of(other) == await table_counts(db, b.id)
    assert {member["user_id"] for member in other["team"]} == team_ids(b)
    assert other["inventory"]["low_stock_count"] == 2
    assert other["inventory"]["open_purchase_orders"] == 1
    assert [part["sku"] for part in other["low_stock"]] == ["B-OUT", "B-LOW"]


async def test_rpt01_an_owner_of_two_shops_sees_each_shop_on_its_own(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    a = world.a
    second = await make_cast(db, owner=a.owner)  # Fatima owns both (glossary §14.1)
    await add_bookings(db, a, world.customer, [S.PENDING])
    await add_bookings(db, second, world.customer, [S.CONFIRMED, S.CONFIRMED])
    await add_rows(db.sessionmaker, part_row(second, "SECOND-OUT", on_hand=0))

    first_body = await get_overview(api, a)
    second_body = await get_overview(api, second)

    assert counts_of(first_body) == zero_counts(PENDING=1)
    assert counts_of(second_body) == zero_counts(CONFIRMED=2)
    assert first_body["low_stock"] == []
    assert [part["sku"] for part in second_body["low_stock"]] == ["SECOND-OUT"]
    assert {member["user_id"] for member in first_body["team"]} == team_ids(a)
    assert {member["user_id"] for member in second_body["team"]} == team_ids(second)


# --- RPT-03 ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("role", [SA, TECH, PP, QC])
async def test_rpt03_every_other_role_gets_403(
    api: httpx.AsyncClient, world: World, role: MembershipRole
) -> None:
    member = world.a.members_by_role()[role]
    response = await api.get(overview_url(world.a.id), headers=bearer(member))
    body = assert_problem(response, 403, "FORBIDDEN")
    assert body["instance"] == overview_url(world.a.id)
    assert response.headers["cache-control"] == "no-store"


async def test_rpt03_the_second_technician_and_inspector_get_403_too(
    api: httpx.AsyncClient, world: World
) -> None:
    for member in (world.a.technician_2, world.a.qc_2):
        response = await api.get(overview_url(world.a.id), headers=bearer(member))
        assert_problem(response, 403, "FORBIDDEN")


async def test_rpt03_non_members_get_the_same_404(api: httpx.AsyncClient, world: World) -> None:
    a = world.a
    callers = {
        "Shop B's owner": (world.b.owner, a.id),
        "a customer": (world.customer, a.id),
        "a deactivated member": (a.former, a.id),
        "the owner, unknown shop": (a.owner, uuid4()),
    }
    for label, (user, shop_id) in callers.items():
        response = await api.get(overview_url(shop_id), headers=bearer(user))
        body = assert_problem(response, 404, "NOT_FOUND")
        assert body["detail"] == NOT_FOUND_DETAIL, label
        assert response.headers["cache-control"] == "no-store", label


async def test_rpt03_the_owner_is_admitted(api: httpx.AsyncClient, world: World) -> None:
    body = await get_overview(api, world.a)
    assert set(body) == {
        "shop",
        "status_counts",
        "today",
        "team",
        "inventory",
        "low_stock",
        "setup",
    }


# --- RPT-04 ---------------------------------------------------------------------------------------


async def test_rpt04_all_17_statuses_in_glossary_order_with_zeros(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    statuses = [S.PENDING] * 3 + [S.ASSIGNED, S.QC_IN_PROGRESS, S.QC_IN_PROGRESS, S.COMPLETED]
    statuses += [S.CANCELLED, S.CANCELLED]
    await add_bookings(db, world.a, world.customer, statuses)

    body = await get_overview(api, world.a)

    assert [item["status"] for item in body["status_counts"]] == GLOSSARY_STATUS_ORDER
    assert counts_of(body) == zero_counts(
        PENDING=3, ASSIGNED=1, QC_IN_PROGRESS=2, COMPLETED=1, CANCELLED=2
    )
    assert sum(counts_of(body).values()) == len(statuses)


async def test_rpt04_one_booking_in_every_status(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    await add_bookings(db, world.a, world.customer, list(BookingStatus))
    body = await get_overview(api, world.a)
    assert body["status_counts"] == [
        {"status": status, "count": 1} for status in GLOSSARY_STATUS_ORDER
    ]
    assert body["today"]["ready_for_pickup"] == 1


async def test_rpt04_a_shop_without_bookings_lists_17_zeros(
    api: httpx.AsyncClient, world: World
) -> None:
    body = await get_overview(api, world.a)
    assert body["status_counts"] == [
        {"status": status, "count": 0} for status in GLOSSARY_STATUS_ORDER
    ]


# --- RPT-05 ---------------------------------------------------------------------------------------


async def test_rpt05_the_spec_case_in_asia_karachi(
    api: httpx.AsyncClient, world: World, db: Database, clock: SimulatedClock
) -> None:
    """Frozen at 2026-10-15T19:30Z (Fri 16 Oct 00:30 PKT): a booking at 2026-10-16T05:00Z counts,
    one at 2026-10-15T18:00Z does not, a cancelled one never counts, `completed` follows
    `completed_at` and `ready_for_pickup` ignores the date."""
    clock.set(datetime(2026, 10, 15, 19, 30, tzinfo=UTC))
    a, customer = world.a, world.customer
    friday_10 = datetime(2026, 10, 16, 5, 0, tzinfo=UTC)
    rows = [
        *booking_rows(a, customer, S.PENDING, slot_start=friday_10),
        *booking_rows(a, customer, S.PENDING, slot_start=datetime(2026, 10, 15, 18, tzinfo=UTC)),
        *booking_rows(
            a,
            customer,
            S.CANCELLED,
            slot_start=friday_10,
            cancelled_at=datetime(2026, 10, 15, 19, 20, tzinfo=UTC),
        ),
        # Completed today, booked last week: completed counts, the slot does not.
        *booking_rows(
            a,
            customer,
            S.COMPLETED,
            slot_start=datetime(2026, 10, 9, 5, tzinfo=UTC),
            completed_at=datetime(2026, 10, 15, 19, 10, tzinfo=UTC),
        ),
        # Completed yesterday: no.
        *booking_rows(
            a,
            customer,
            S.COMPLETED,
            slot_start=datetime(2026, 10, 14, 5, tzinfo=UTC),
            completed_at=datetime(2026, 10, 15, 12, 0, tzinfo=UTC),
        ),
        # Ready for pick-up since last week: counted whatever its date.
        *booking_rows(
            a, customer, S.READY_FOR_PICKUP, slot_start=datetime(2026, 10, 8, 5, tzinfo=UTC)
        ),
    ]
    await add_rows(db.sessionmaker, *rows)
    # Another shop's booking today never counts here.
    await add_booking(db, world.b, customer, S.PENDING, slot_start=friday_10)

    body = await get_overview(api, a)

    assert body["today"] == {
        "date": "2026-10-16",
        "bookings": 1,
        "ready_for_pickup": 1,
        "completed": 1,
    }


async def test_rpt05_window_bounds_are_half_open(
    api: httpx.AsyncClient, world: World, db: Database, clock: SimulatedClock
) -> None:
    clock.set(PKT_FRIDAY_END - MICROSECOND)  # the last instant of Friday in Karachi
    a, customer = world.a, world.customer
    inside = [PKT_FRIDAY_START, PKT_FRIDAY_END - MICROSECOND]
    outside = [PKT_FRIDAY_START - MICROSECOND, PKT_FRIDAY_END]
    rows: list[object] = []
    for moment in inside + outside:
        rows += booking_rows(a, customer, S.CONFIRMED, slot_start=moment)
        rows += booking_rows(
            a,
            customer,
            S.COMPLETED,
            slot_start=moment - timedelta(days=3),
            completed_at=moment,
        )
    await add_rows(db.sessionmaker, *rows)

    body = await get_overview(api, a)
    assert body["today"] == {
        "date": "2026-10-16",
        "bookings": 2,
        "ready_for_pickup": 0,
        "completed": 2,
    }

    clock.set(PKT_FRIDAY_END)  # midnight: Saturday starts, and the window moves with it
    saturday = await get_overview(api, a)
    assert saturday["today"] == {
        "date": "2026-10-17",
        "bookings": 1,
        "ready_for_pickup": 0,
        "completed": 1,
    }


async def test_rpt05_cancelled_bookings_never_count_as_today(
    api: httpx.AsyncClient, world: World, db: Database, clock: SimulatedClock
) -> None:
    clock.set(datetime(2026, 10, 16, 3, 0, tzinfo=UTC))
    for moment in (PKT_FRIDAY_START, datetime(2026, 10, 16, 5, tzinfo=UTC)):
        await add_booking(
            db,
            world.a,
            world.customer,
            S.CANCELLED,
            slot_start=moment,
            cancelled_at=datetime(2026, 10, 16, 1, tzinfo=UTC),
        )
    body = await get_overview(api, world.a)
    assert body["today"]["bookings"] == 0
    assert counts_of(body)["CANCELLED"] == 2


@dataclass(frozen=True)
class DstDay:
    now: datetime
    date: str
    start: datetime  # the local midnight that opens the day, in UTC
    hours: int  # the day's length
    expected: int  # how many of the probe instants fall inside it


DST_DAYS = [
    # 25-hour day: BST ends at 02:00 on Sunday 25 Oct 2026; 23:30 GMT is still the 25th.
    pytest.param(
        DstDay(
            now=datetime(2026, 10, 25, 12, 0, tzinfo=UTC),
            date="2026-10-25",
            start=datetime(2026, 10, 24, 23, 0, tzinfo=UTC),
            hours=25,
            expected=6,
        ),
        id="25-hour-day",
    ),
    # 23-hour day: BST starts at 01:00 on Sunday 29 Mar 2026; 23:00 UTC is already the 30th.
    pytest.param(
        DstDay(
            now=datetime(2026, 3, 29, 12, 0, tzinfo=UTC),
            date="2026-03-29",
            start=datetime(2026, 3, 29, 0, 0, tzinfo=UTC),
            hours=23,
            expected=3,
        ),
        id="23-hour-day",
    ),
]


@pytest.mark.parametrize("day", DST_DAYS)
async def test_rpt05_dst_days_in_europe_london(
    api: httpx.AsyncClient, world: World, db: Database, clock: SimulatedClock, day: DstDay
) -> None:
    """Both midnights are converted on their own: `start + 24 h` would miss the 25th hour of the
    long day and take the first hour of the next day into the short one."""
    clock.set(day.now)
    london = await make_cast(db, timezone=LONDON, city="London")
    start, end = day.start, day.start + timedelta(hours=day.hours)
    offsets = [timedelta(hours=h, minutes=30) for h in (22, 23, 24)] + [timedelta(hours=24)]
    candidates = [start - MICROSECOND, start, end - MICROSECOND, end]
    candidates += [start + offset for offset in offsets]
    rows: list[object] = []
    for moment in candidates:
        rows += booking_rows(london, world.customer, S.PENDING, slot_start=moment)
        rows += booking_rows(
            london,
            world.customer,
            S.COMPLETED,
            slot_start=moment - timedelta(days=2),
            completed_at=moment,
        )
    await add_rows(db.sessionmaker, *rows)

    body = await get_overview(api, london)

    assert sum(start <= moment < end for moment in candidates) == day.expected
    assert body["today"] == {
        "date": day.date,
        "bookings": day.expected,
        "ready_for_pickup": 0,
        "completed": day.expected,
    }


async def test_rpt05_a_new_shop_has_an_empty_today(
    api: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    body = await get_overview(api, world.a)
    assert body["today"] == {
        "date": "2026-10-14",  # the test clock: Wednesday 09:00 PKT
        "bookings": 0,
        "ready_for_pickup": 0,
        "completed": 0,
    }


# --- RPT-06 ---------------------------------------------------------------------------------------


async def test_rpt06_inventory_over_active_parts(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    a, b = world.a, world.b
    out_active = part_row(a, "OUT-ACT", on_hand=0, reorder_level=2, unit_cost="6500")
    out_reserved = part_row(a, "OUT-RES", on_hand=4, reserved=4, reorder_level=1, unit_cost="900")
    low_two = part_row(a, "LOW-TWO", on_hand=3, reserved=1, reorder_level=2, unit_cost="5200")
    low_one = part_row(a, "LOW-ONE", on_hand=1, reorder_level=1, unit_cost="1500")
    ok_part = part_row(a, "OK-PART", on_hand=3, reorder_level=2, unit_cost="1200")
    ok_no_level = part_row(a, "OK-NO-LEVEL", on_hand=1, reorder_level=0, unit_cost="700")
    inactive_out = part_row(a, "INACTIVE-OUT", on_hand=0, reorder_level=5, active=False)
    inactive_stock = part_row(a, "INACTIVE-STOCK", on_hand=100, unit_cost="1000", active=False)
    parts = [out_active, out_reserved, low_two, low_one, ok_part, ok_no_level]
    await add_rows(
        db.sessionmaker,
        *parts,
        inactive_out,
        inactive_stock,
        *purchase_order_rows(a, PurchaseOrderStatus.ORDERED, [(out_active, 5, 0)]),
        *purchase_order_rows(a, PurchaseOrderStatus.PARTIALLY_RECEIVED, [(out_active, 4, 1)]),
        *purchase_order_rows(a, PurchaseOrderStatus.RECEIVED, [(low_one, 2, 2)]),
        *purchase_order_rows(b, PurchaseOrderStatus.ORDERED),
        part_row(b, "B-OUT", on_hand=0),
    )

    body = await get_overview(api, a)

    stock_value = sum((part.on_hand * part.unit_cost for part in parts), Decimal(0))
    assert stock_value == 4 * 900 + 3 * 5200 + 1 * 1500 + 3 * 1200 + 1 * 700 == 25000
    assert body["inventory"] == {
        "parts_count": 6,
        "low_stock_count": 4,  # LOW and OUT together
        "out_of_stock_count": 2,
        "stock_value": "25000.00",  # inactive parts (100 x 1000 on hand) left out
        "open_purchase_orders": 2,  # ORDERED and PARTIALLY_RECEIVED
    }
    assert [part["sku"] for part in body["low_stock"]] == [
        "OUT-ACT",  # OUT first (available 0), SKU breaks the tie
        "OUT-RES",
        "LOW-ONE",  # then by available
        "LOW-TWO",
    ]
    first = body["low_stock"][0]
    assert first == {
        "id": str(out_active.id),
        "sku": "OUT-ACT",
        "name": "Part OUT-ACT",
        "unit_cost": "6500.00",
        "is_active": True,
        "on_hand": 0,
        "reserved": 0,
        "available": 0,
        "reorder_level": 2,
        "stock_state": "OUT",
        "on_order": 8,  # 5 ordered + (4 - 1) outstanding on the open purchase orders
        "created_at": first["created_at"],
        "updated_at": first["updated_at"],
    }
    assert body["low_stock"][1]["stock_state"] == "OUT"  # reserved == on hand: nothing available
    assert [part["stock_state"] for part in body["low_stock"][2:]] == ["LOW", "LOW"]
    assert body["setup"]["has_parts"] is True


async def test_rpt06_low_stock_lists_at_most_five(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    a = world.a
    await add_rows(
        db.sessionmaker,
        part_row(a, "C-1", on_hand=1, reorder_level=3),
        part_row(a, "A-1", on_hand=1, reorder_level=3),
        part_row(a, "B-1", on_hand=1, reorder_level=3),
        part_row(a, "Z-0", on_hand=0, reorder_level=0),
        part_row(a, "D-2", on_hand=2, reorder_level=3),
        part_row(a, "E-3", on_hand=3, reorder_level=3),
        part_row(a, "F-3", on_hand=3, reorder_level=3),
        part_row(a, "OK-4", on_hand=4, reorder_level=3),
    )
    body = await get_overview(api, a)
    assert [part["sku"] for part in body["low_stock"]] == ["Z-0", "A-1", "B-1", "C-1", "D-2"]
    assert body["inventory"]["low_stock_count"] == 7
    assert body["inventory"]["out_of_stock_count"] == 1
    assert body["inventory"]["parts_count"] == 8


async def test_rpt06_an_inactive_part_that_is_out_counts_nowhere(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    await add_rows(
        db.sessionmaker,
        part_row(world.a, "GONE", on_hand=0, reorder_level=5, active=False),
        part_row(world.a, "GONE-TOO", on_hand=7, unit_cost="300", active=False),
    )
    body = await get_overview(api, world.a)
    assert body["inventory"] == {
        "parts_count": 0,
        "low_stock_count": 0,
        "out_of_stock_count": 0,
        "stock_value": "0.00",
        "open_purchase_orders": 0,
    }
    assert body["low_stock"] == []
    assert body["setup"]["has_parts"] is False


async def test_rpt06_a_stock_value_beyond_ten_digits_is_still_served(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    """The sum of on hand * unit cost may exceed the 10 integer digits of one amount (D41)."""
    await add_rows(
        db.sessionmaker,
        part_row(world.a, "COSTLY", on_hand=2, unit_cost="9999999999"),
        part_row(world.a, "CHEAP", on_hand=3, unit_cost="1"),
    )
    body = await get_overview(api, world.a)
    assert body["inventory"]["stock_value"] == "20000000001.00"


# --- RPT-07 ---------------------------------------------------------------------------------------


async def test_rpt07_team_order_inactive_members_and_the_owner_row(
    api: httpx.AsyncClient, world: World
) -> None:
    a = world.a
    body = await get_overview(api, a)
    assert [(m["full_name"], m["role"], m["is_active"]) for m in body["team"]] == [
        ("Fatima Raza", "OWNER", True),
        ("Bilal", "SERVICE_ADVISOR", True),
        ("hamza", "TECHNICIAN", True),  # by name, case-insensitively
        ("Imran", "TECHNICIAN", True),
        ("Zubair", "TECHNICIAN", False),  # deactivated members stay listed (D19)
        ("Usman", "PARTS_PERSON", True),
        ("Hina", "QC_INSPECTOR", True),
        ("Sara", "QC_INSPECTOR", True),
    ]
    owner_row = body["team"][0]
    assert set(owner_row) == {
        "membership_id",
        "user_id",
        "full_name",
        "role",
        "is_active",
        "open_jobs",
    }
    assert owner_row["user_id"] == str(a.owner.id)
    assert all(member["open_jobs"] == 0 for member in body["team"])


async def test_rpt07_open_jobs_count_technician_parts_and_current_picker(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    a, customer = world.a, world.customer
    rows = [
        *booking_rows(a, customer, S.ASSIGNED),
        *booking_rows(a, customer, S.INSPECTING),
        *booking_rows(a, customer, S.PARTS_PENDING),
        *booking_rows(a, customer, S.IN_REPAIR, technician_user_id=a.technician_2.id),
        *booking_rows(a, customer, S.QC_PENDING),
        *booking_rows(a, customer, S.QC_IN_PROGRESS),  # Sara is the current picker
        *booking_rows(a, customer, S.READY_FOR_PICKUP),  # not open any more
        *booking_rows(a, customer, S.COMPLETED, qc_inspector_user_id=a.qc_2.id),
        *booking_rows(
            a,
            customer,
            S.CANCELLED,
            technician_user_id=a.technician.id,
            parts_person_user_id=a.parts.id,
        ),
        *booking_rows(a, customer, S.INSPECTING, technician_user_id=a.former.id),
        *booking_rows(a, customer, S.PENDING),
        *booking_rows(a, customer, S.CONFIRMED),
    ]
    await add_rows(db.sessionmaker, *rows)

    body = await get_overview(api, a)

    open_jobs = {member["full_name"]: member["open_jobs"] for member in body["team"]}
    assert open_jobs == {
        "Fatima Raza": 0,
        "Bilal": 0,
        "Imran": 5,  # ASSIGNED, INSPECTING, PARTS_PENDING, QC_PENDING, QC_IN_PROGRESS
        "hamza": 1,  # IN_REPAIR
        "Zubair": 1,  # still assigned while deactivated (D19)
        "Usman": 4,  # PARTS_PENDING, IN_REPAIR, QC_PENDING, QC_IN_PROGRESS
        "Hina": 0,  # passed a job that is completed now
        "Sara": 1,  # the current picker of the QC_IN_PROGRESS job, not of the finished ones
    }


async def test_rpt07_open_jobs_never_cross_shops(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    """A technician of both shops: each overview counts only its own shop's jobs."""
    a, b = world.a, world.b
    shared = make_user(full_name="Kashif")
    await add_rows(
        db.sessionmaker,
        shared,
        make_membership(a.shop, shared, TECH, created_by=a.owner),
        make_membership(b.shop, shared, TECH, created_by=b.owner),
    )
    await add_booking(db, a, world.customer, S.IN_REPAIR, technician_user_id=shared.id)
    for _ in range(3):
        await add_booking(db, b, world.customer, S.INSPECTING, technician_user_id=shared.id)

    in_a = {m["user_id"]: m["open_jobs"] for m in (await get_overview(api, a))["team"]}
    in_b = {m["user_id"]: m["open_jobs"] for m in (await get_overview(api, b))["team"]}

    assert in_a[str(shared.id)] == 1
    assert in_b[str(shared.id)] == 3


# --- RPT-08 ---------------------------------------------------------------------------------------


def _week() -> list[dict[str, Any]]:
    return [
        {
            "weekday": day,
            "is_closed": day == 6,
            "opens_at": None if day == 6 else "09:00",
            "closes_at": None if day == 6 else "18:00",
        }
        for day in range(7)
    ]


@pytest.mark.usefixtures("activity_reader")
async def test_rpt08_setup_flags_of_a_new_shop_then_each_flips(
    api: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    founder, staff = make_user(full_name="Nida Abbasi"), make_user(full_name="Omar")
    await add_rows(db.sessionmaker, founder, staff)
    owner = bearer(founder)
    created = await api.post(
        "/api/v1/shops",
        json={
            "name": "Margalla Motor Works",
            "address": "Blue Area",
            "city": "Islamabad",
            "phone": "+92 51 0000 0101",
            "slot_duration_minutes": 60,
            "slot_capacity": 2,
            "working_hours": _week(),
        },
        headers=owner,
    )
    assert created.status_code == 201, created.text
    shop_id = created.json()["id"]
    url = overview_url(shop_id)

    async def setup() -> dict[str, bool]:
        response = await api.get(url, headers=owner)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["shop"]["is_listed"] == body["setup"]["is_listed"]
        flags: dict[str, bool] = body["setup"]
        return flags

    fresh = (await api.get(url, headers=owner)).json()
    assert fresh["setup"] == {
        "has_services": False,
        "has_team": False,
        "has_parts": False,
        "is_listed": True,
    }
    assert fresh["shop"]["name"] == "Margalla Motor Works"
    assert fresh["shop"]["city"] == "Islamabad"
    assert fresh["status_counts"] == [
        {"status": status, "count": 0} for status in GLOSSARY_STATUS_ORDER
    ]
    assert fresh["today"] == {
        "date": "2026-10-14",
        "bookings": 0,
        "ready_for_pickup": 0,
        "completed": 0,
    }
    assert [(m["full_name"], m["role"], m["open_jobs"]) for m in fresh["team"]] == [
        ("Nida Abbasi", "OWNER", 0)
    ]
    assert fresh["inventory"] == {
        "parts_count": 0,
        "low_stock_count": 0,
        "out_of_stock_count": 0,
        "stock_value": "0.00",
        "open_purchase_orders": 0,
    }
    assert fresh["low_stock"] == []

    service = await api.post(
        f"/api/v1/shops/{shop_id}/services",
        json={"name": "Oil change", "estimated_duration_minutes": 60},
        headers=owner,
    )
    assert service.status_code == 201, service.text
    assert await setup() == {
        "has_services": True,
        "has_team": False,
        "has_parts": False,
        "is_listed": True,
    }

    member = await api.post(
        f"/api/v1/shops/{shop_id}/members",
        json={"email": staff.email, "full_name": "Omar", "role": "TECHNICIAN"},
        headers=owner,
    )
    assert member.status_code == 201, member.text
    assert (await setup())["has_team"] is True

    part = await api.post(
        f"/api/v1/shops/{shop_id}/parts",
        json={"sku": "OIL-FILTER", "name": "Oil filter", "unit_cost": "900"},
        headers=owner,
    )
    assert part.status_code == 201, part.text
    assert (await setup())["has_parts"] is True  # a part with no stock is still a part

    unlisted = await api.patch(f"/api/v1/shops/{shop_id}", json={"is_listed": False}, headers=owner)
    assert unlisted.status_code == 200, unlisted.text
    assert await setup() == {
        "has_services": True,
        "has_team": True,
        "has_parts": True,
        "is_listed": False,
    }

    # Each flag falls back once its last active item is deactivated.
    membership_id = member.json()["membership_id"]
    for path, payload in (
        (f"/members/{membership_id}", {"is_active": False}),
        (f"/services/{service.json()['id']}", {"is_active": False}),
        (f"/parts/{part.json()['id']}", {"is_active": False}),
        ("", {"is_listed": True}),
    ):
        changed = await api.patch(f"/api/v1/shops/{shop_id}{path}", json=payload, headers=owner)
        assert changed.status_code == 200, changed.text
    assert await setup() == {
        "has_services": False,
        "has_team": False,
        "has_parts": False,
        "is_listed": True,
    }


@pytest.mark.usefixtures("clock")
async def test_rpt08_only_active_items_set_the_flags(api: httpx.AsyncClient, db: Database) -> None:
    founder = make_user(full_name="Tariq Mehmood")
    await add_rows(db.sessionmaker, founder)
    cast = await make_cast(db, owner=founder)  # a full team: has_team is true
    body = await get_overview(api, cast)
    assert body["setup"] == {
        "has_services": False,
        "has_team": True,
        "has_parts": False,
        "is_listed": True,
    }
    await add_rows(
        db.sessionmaker,
        service_row(cast, "Brake service", active=False),
        part_row(cast, "OLD", on_hand=5, active=False),
    )
    body = await get_overview(api, cast)
    assert body["setup"]["has_services"] is False
    assert body["setup"]["has_parts"] is False
    await add_rows(db.sessionmaker, service_row(cast, "Brake service"), part_row(cast, "NEW"))
    body = await get_overview(api, cast)
    assert body["setup"]["has_services"] is True
    assert body["setup"]["has_parts"] is True
