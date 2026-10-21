"""`GET /api/v1/me/owner-summary` — `reporting_get_owner_summary` (P1; spec 03 §3.7, §4.13;
`modules/reporting.md`).

RPT-02 (only the shops the caller owns; `items: []` for everyone else, never a 403) and the API
half of RPT-09 (an owner of two shops who is staff in a third gets exactly two rows), plus the
row figures in each shop's own time zone, the order by shop name then id, and the status groups
partitioning every booking.
"""

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.core.database import Database
from app.modules.identity.models import User
from app.shared.clock import SimulatedClock
from app.shared.enums import BookingStatus, MembershipRole
from tests.assertions import assert_problem
from tests.modules.reporting.support import (
    LONDON,
    SUMMARY_URL,
    Cast,
    World,
    bearer,
    booking_rows,
    make_cast,
    make_owned_shop,
    overview_url,
    part_row,
)
from tests.rows import add_rows, make_membership, make_user

pytestmark = pytest.mark.db

S = BookingStatus


async def summary_of(api: httpx.AsyncClient, user: User) -> list[dict[str, Any]]:
    response = await api.get(SUMMARY_URL, headers=bearer(user))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"  # API-13 (D61)
    body = response.json()
    assert set(body) == {"items"}
    items: list[dict[str, Any]] = body["items"]
    return items


def shop_ref(cast: Cast) -> dict[str, str]:
    return {
        "id": str(cast.id),
        "slug": cast.shop.slug,
        "name": cast.shop.name,
        "city": cast.shop.city,
    }


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


async def test_rpt09_two_owned_shops_and_staff_in_a_third_gives_two_rows(
    api: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    """Frozen at 2026-10-15T19:30Z: Friday 16 Oct 00:30 in Lahore (PKT), still Thursday 15 Oct
    20:30 in London (BST), so each shop's "today" is its own local date."""
    clock.set(at(15, 19, 30))
    owner, customer = make_user(full_name="Fatima Raza"), make_user(full_name="Ayesha Khan")
    await add_rows(db.sessionmaker, owner, customer)
    lahore = await make_cast(db, owner=owner, name="Lahore Auto Care")
    raza = await make_cast(db, owner=owner, name="Raza Auto Works", timezone=LONDON, city="London")
    clifton = await make_cast(db, name="Clifton Car Clinic", city="Karachi")
    await add_rows(
        db.sessionmaker,
        make_membership(clifton.shop, owner, MembershipRole.TECHNICIAN, created_by=clifton.owner),
    )
    rows: list[object] = []
    for status, slot_start in (
        (S.PENDING, at(16, 5)),  # today in Lahore; SA
        (S.CONFIRMED, at(15, 12)),  # yesterday in Lahore; SA
        (S.ESTIMATE_REJECTED, at(14, 5)),  # SA
        (S.AWAITING_CUSTOMER, at(14, 5)),  # in progress (the customer's step)
        (S.IN_REPAIR, at(13, 5)),  # in progress
        (S.QC_PENDING, at(13, 5)),  # in progress
        (S.READY_FOR_PICKUP, at(12, 5)),  # SA and ready for pick-up
        (S.COMPLETED, at(16, 6)),  # today, not cancelled: counts for today, in no group
        (S.CANCELLED, at(16, 7)),  # today but cancelled: counts nowhere
    ):
        rows += booking_rows(lahore, customer, status, slot_start=slot_start)
    for status, slot_start in (
        (S.PENDING, at(15, 12)),  # 13:00 BST on the 15th: today in London
        (S.PENDING, at(16, 5)),  # the 16th in London: not today
        (S.INSPECTING, at(15, 22, 30)),  # 23:30 BST: still today
        (S.PARTS_ORDERED, at(15, 23)),  # 00:00 BST on the 16th: not today
    ):
        rows += booking_rows(raza, customer, status, slot_start=slot_start)
    rows += booking_rows(clifton, customer, S.PENDING, slot_start=at(16, 5))
    rows += [
        part_row(lahore, "OUT", on_hand=0, reorder_level=1),
        part_row(lahore, "LOW", on_hand=2, reorder_level=2),
        part_row(lahore, "OK", on_hand=5, reorder_level=2),
        part_row(lahore, "RETIRED", on_hand=0, reorder_level=3, active=False),
        part_row(clifton, "CLIFTON-OUT", on_hand=0),
    ]
    await add_rows(db.sessionmaker, *rows)

    items = await summary_of(api, owner)

    assert items == [
        {
            "shop": shop_ref(lahore),
            "today_bookings": 2,
            "needs_sa_action": 4,  # PENDING, CONFIRMED, ESTIMATE_REJECTED, READY_FOR_PICKUP
            "in_progress": 3,  # AWAITING_CUSTOMER, IN_REPAIR, QC_PENDING
            "ready_for_pickup": 1,
            "low_stock_count": 2,  # OUT and LOW; the inactive part is left out
        },
        {
            "shop": shop_ref(raza),
            "today_bookings": 2,
            "needs_sa_action": 2,
            "in_progress": 2,  # INSPECTING, PARTS_ORDERED
            "ready_for_pickup": 0,
            "low_stock_count": 0,
        },
    ]
    # The third shop is not summarised, and its overview stays closed to a technician there.
    response = await api.get(overview_url(clifton.id), headers=bearer(owner))
    assert_problem(response, 403, "FORBIDDEN")


async def test_rpt09_the_groups_and_terminal_statuses_cover_every_booking(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    rows = [
        row
        for status in BookingStatus
        for row in booking_rows(world.a, world.customer, status, slot_start=at(10, 5))
    ]
    await add_rows(db.sessionmaker, *rows)
    [item] = await summary_of(api, world.a.owner)
    terminal = 2  # COMPLETED, CANCELLED
    assert item["needs_sa_action"] == 6
    assert item["in_progress"] == 9
    assert item["needs_sa_action"] + item["in_progress"] + terminal == len(BookingStatus)
    assert item["ready_for_pickup"] == 1


async def test_rpt02_each_owner_sees_only_their_own_shop(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    await add_rows(
        db.sessionmaker,
        *booking_rows(world.b, world.customer, S.PENDING),
        part_row(world.b, "B-OUT", on_hand=0),
    )
    [mine] = await summary_of(api, world.a.owner)
    [theirs] = await summary_of(api, world.b.owner)
    assert mine["shop"] == shop_ref(world.a)
    assert (mine["needs_sa_action"], mine["low_stock_count"]) == (0, 0)
    assert theirs["shop"] == shop_ref(world.b)
    assert (theirs["needs_sa_action"], theirs["low_stock_count"]) == (1, 1)


async def test_rpt02_customers_and_staff_get_an_empty_list_never_403(
    api: httpx.AsyncClient, world: World
) -> None:
    a = world.a
    callers = {
        "customer": world.customer,
        "service advisor": a.advisor,
        "technician": a.technician,
        "parts person": a.parts,
        "QC inspector": a.qc,
        "deactivated member": a.former,
    }
    for label, user in callers.items():
        assert await summary_of(api, user) == [], label


async def test_rpt02_a_shop_owner_with_bookings_as_a_customer_elsewhere(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    """Being a customer of another shop adds nothing: only owned shops are rows."""
    await add_rows(db.sessionmaker, *booking_rows(world.b, world.a.owner, S.PENDING))
    items = await summary_of(api, world.a.owner)
    assert [item["shop"]["id"] for item in items] == [str(world.a.id)]


async def test_rpt02_rows_are_ordered_by_shop_name_then_id(
    api: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    owner = make_user(full_name="Khalid Chaudhry")
    await add_rows(db.sessionmaker, owner)
    bravo = await make_owned_shop(db, owner, name="bravo garage")
    twin_1 = await make_owned_shop(db, owner, name="Twin Motors")
    alpha = await make_owned_shop(db, owner, name="Alpha Motors")
    twin_2 = await make_owned_shop(db, owner, name="Twin Motors")

    items = await summary_of(api, owner)

    twins = sorted([twin_1.id, twin_2.id])  # equal names: by id
    assert [item["shop"]["id"] for item in items] == [
        str(alpha.id),
        str(bravo.id),  # case-insensitive: "bravo" sorts between "Alpha" and "Twin"
        str(twins[0]),
        str(twins[1]),
    ]
    assert all(
        item
        == {
            "shop": item["shop"],
            "today_bookings": 0,
            "needs_sa_action": 0,
            "in_progress": 0,
            "ready_for_pickup": 0,
            "low_stock_count": 0,
        }
        for item in items
    )


async def test_rpt02_a_query_parameter_cannot_select_another_user(
    api: httpx.AsyncClient, world: World
) -> None:
    response = await api.get(
        SUMMARY_URL,
        params={"user_id": str(world.b.owner.id), "shop_id": str(world.b.id)},
        headers=bearer(world.a.owner),
    )
    assert response.status_code == 200
    assert [item["shop"]["id"] for item in response.json()["items"]] == [str(world.a.id)]
