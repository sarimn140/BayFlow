"""`validate_slot`, `reserve_slot`, `release_slot` and the P2 helpers (`modules/scheduling.md` §5).

Covers the scheduling halves of BK-08 (error shape), BK-09 (capacity), BK-10 (release frees the
place, never below 0), SCH-06 (missing counter fails loudly) and the D37 re-validation under the
shop lock (CON-05's booking side).
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.database import Database
from app.core.errors import InvalidSlot, SlotFull
from app.modules.scheduling import service as scheduling_service
from app.modules.scheduling.domain.slots import GridSlot
from app.modules.scheduling.models import SlotCounter
from app.modules.scheduling.service import SlotCounterMissingError
from app.modules.shops import service as shops_service
from app.modules.shops.schemas import ShopUpdate
from app.shared.clock import SimulatedClock, utcnow
from tests.modules.identity.builders import unit_of_work
from tests.modules.scheduling.helpers import book, booked_count, counter_in, free
from tests.modules.shops.builders import make_shop

pytestmark = pytest.mark.db

FRIDAY_0900_PKT = datetime(2026, 10, 16, 4, tzinfo=UTC)
FRIDAY_1000_PKT = datetime(2026, 10, 16, 5, tzinfo=UTC)
FRIDAY_1100_PKT = datetime(2026, 10, 16, 6, tzinfo=UTC)


async def test_validate_slot_returns_the_grid_slot_or_a_field_error(
    db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db)
    async with db.sessionmaker() as session:
        config = await shops_service.get_schedule_config(session, shop_id=ctx.id)
    slot = scheduling_service.validate_slot(config, slot_start=FRIDAY_1000_PKT, now=utcnow())
    assert slot == GridSlot(FRIDAY_1000_PKT, FRIDAY_1000_PKT + timedelta(hours=1))
    with pytest.raises(InvalidSlot) as caught:
        scheduling_service.validate_slot(
            config, slot_start=FRIDAY_1000_PKT + timedelta(minutes=15), now=utcnow()
        )
    assert caught.value.status_code == 422
    assert caught.value.detail == "This time is not one of the shop's slot start times."
    assert caught.value.errors == [
        {
            "field": "slot_start",
            "code": "off_grid",
            "message": "This time is not one of the shop's slot start times.",
        }
    ]


async def test_bk09_capacity_two_takes_two_bookings(db: Database, clock: SimulatedClock) -> None:
    ctx = await make_shop(db, capacity=2)
    assert await book(db, ctx.id, FRIDAY_1000_PKT) == "booked"
    assert await booked_count(db, ctx.id, FRIDAY_1000_PKT) == 1
    assert await book(db, ctx.id, FRIDAY_1000_PKT) == "booked"
    assert await book(db, ctx.id, FRIDAY_1000_PKT) == "full"  # 409 SLOT_FULL, rolled back
    assert await booked_count(db, ctx.id, FRIDAY_1000_PKT) == 2
    assert await book(db, ctx.id, FRIDAY_1100_PKT) == "booked"  # other slots unaffected
    assert await booked_count(db, ctx.id, FRIDAY_1100_PKT) == 1
    assert await booked_count(db, ctx.id, FRIDAY_0900_PKT) is None  # created lazily


async def test_reserve_slot_writes_the_actions_clock_instant(
    db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db)
    instant = datetime(2026, 10, 14, 4, 30, tzinfo=UTC)
    async with unit_of_work(db) as uow:
        config = await shops_service.get_schedule_config(
            uow.session, shop_id=ctx.id, for_share=True
        )
        slot = await scheduling_service.reserve_slot(
            uow, config=config, slot_start=FRIDAY_1000_PKT, now=instant
        )
        await uow.commit()
    assert slot.slot_end == FRIDAY_1000_PKT + timedelta(hours=1)
    async with db.sessionmaker() as session:
        counter = (await session.execute(select(SlotCounter))).scalar_one()
    assert (counter.booked_count, counter.created_at, counter.updated_at) == (1, instant, instant)


async def test_slot_full_raises_and_rolls_back(db: Database, clock: SimulatedClock) -> None:
    ctx = await make_shop(db, capacity=1)
    await book(db, ctx.id, FRIDAY_1000_PKT)
    async with unit_of_work(db) as uow:
        config = await shops_service.get_schedule_config(
            uow.session, shop_id=ctx.id, for_share=True
        )
        with pytest.raises(SlotFull) as caught:
            await scheduling_service.reserve_slot(
                uow, config=config, slot_start=FRIDAY_1000_PKT, now=utcnow()
            )
        # Same transaction, right after the refusal: the capacity check ran before the increment.
        assert await counter_in(uow.session, ctx.id, FRIDAY_1000_PKT) == 1
    assert (caught.value.status_code, caught.value.code.value) == (409, "SLOT_FULL")
    assert await booked_count(db, ctx.id, FRIDAY_1000_PKT) == 1


async def test_reserve_slot_revalidates_against_the_config_read_under_the_lock(
    db: Database, clock: SimulatedClock
) -> None:
    """CON-05's booking side: the early check passes on the old grid, a grid change commits, and
    the booking re-reads the config under the shop lock: `off_grid`, nothing written."""
    ctx = await make_shop(db)  # 60-minute grid: Friday 10:00 is a slot
    async with db.sessionmaker() as session:
        early = await shops_service.get_schedule_config(session, shop_id=ctx.id)
    scheduling_service.validate_slot(early, slot_start=FRIDAY_1000_PKT, now=utcnow())  # passes
    async with unit_of_work(db) as uow:
        await shops_service.update_shop(  # 09:00-18:00 lie on the 45-minute grid; 10:00 does not
            uow,
            shop_id=ctx.id,
            actor_user_id=ctx.owner.id,
            data=ShopUpdate(slot_duration_minutes=45),
        )
    async with unit_of_work(db) as uow:
        locked = await shops_service.get_schedule_config(
            uow.session, shop_id=ctx.id, for_share=True
        )
        with pytest.raises(InvalidSlot) as caught:
            await scheduling_service.reserve_slot(
                uow, config=locked, slot_start=FRIDAY_1000_PKT, now=utcnow()
            )
        # Same transaction: validation ran before the counter insert.
        assert await counter_in(uow.session, ctx.id, FRIDAY_1000_PKT) is None
    assert [(e["field"], e["code"]) for e in caught.value.errors or []] == [
        ("slot_start", "off_grid")
    ]
    assert await booked_count(db, ctx.id, FRIDAY_1000_PKT) is None
    assert await book(db, ctx.id, datetime(2026, 10, 16, 4, 45, tzinfo=UTC)) == "booked"  # 09:45


@pytest.mark.parametrize(
    ("slot_start", "code"),
    [
        (datetime(2026, 10, 13, 5, tzinfo=UTC), "in_past"),
        (datetime(2026, 11, 16, 5, tzinfo=UTC), "beyond_horizon"),
        (datetime(2026, 10, 18, 5, tzinfo=UTC), "closed_day"),
        (datetime(2026, 10, 16, 3, tzinfo=UTC), "outside_hours"),
    ],
)
async def test_bk08_reserve_slot_refuses_invalid_slots_without_writing(
    db: Database, clock: SimulatedClock, slot_start: datetime, code: str
) -> None:
    ctx = await make_shop(db)
    async with unit_of_work(db) as uow:
        config = await shops_service.get_schedule_config(
            uow.session, shop_id=ctx.id, for_share=True
        )
        with pytest.raises(InvalidSlot) as caught:
            await scheduling_service.reserve_slot(
                uow, config=config, slot_start=slot_start, now=utcnow()
            )
        assert await counter_in(uow.session, ctx.id, slot_start) is None  # nothing written first
    assert [(e["field"], e["code"]) for e in caught.value.errors or []] == [("slot_start", code)]
    assert await booked_count(db, ctx.id, slot_start) is None


async def test_bk10_release_frees_the_place_and_keeps_the_row(
    db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db, capacity=1)
    await book(db, ctx.id, FRIDAY_1000_PKT)
    assert await book(db, ctx.id, FRIDAY_1000_PKT) == "full"
    clock.advance(timedelta(minutes=10))
    await free(db, ctx.id, FRIDAY_1000_PKT)
    assert await booked_count(db, ctx.id, FRIDAY_1000_PKT) == 0  # the row is never deleted
    async with db.sessionmaker() as session:
        counter = (await session.execute(select(SlotCounter))).scalar_one()
    assert counter.updated_at == clock.now()
    assert await book(db, ctx.id, FRIDAY_1000_PKT) == "booked"  # bookable again


async def test_sch06_release_fails_loudly_and_never_goes_below_zero(
    db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db)
    with pytest.raises(SlotCounterMissingError, match="no slot counter"):
        await free(db, ctx.id, FRIDAY_1000_PKT)  # DI-4 broken: a bug, so a 500
    await book(db, ctx.id, FRIDAY_1000_PKT)
    await free(db, ctx.id, FRIDAY_1000_PKT)
    with pytest.raises(IntegrityError) as caught:
        await free(db, ctx.id, FRIDAY_1000_PKT)  # a double release
    assert "ck_slot_counters_booked_count_non_negative" in str(caught.value)
    assert await booked_count(db, ctx.id, FRIDAY_1000_PKT) == 0


async def test_counters_are_scoped_by_shop(db: Database, clock: SimulatedClock) -> None:
    first = await make_shop(db, capacity=1)
    second = await make_shop(db, capacity=1)
    assert await book(db, first.id, FRIDAY_1000_PKT) == "booked"
    assert await book(db, second.id, FRIDAY_1000_PKT) == "booked"  # another shop's counter
    with pytest.raises(SlotCounterMissingError):
        await free(db, uuid.uuid4(), FRIDAY_1000_PKT)


# --- P2 helpers for the AI Front Desk (spec 05) ---------------------------------------------------


async def test_list_open_slots_and_is_slot_open(db: Database, clock: SimulatedClock) -> None:
    ctx = await make_shop(db, capacity=1)
    await book(db, ctx.id, FRIDAY_1000_PKT)
    async with db.sessionmaker() as session:
        found = await scheduling_service.list_open_slots(
            session, shop_id=ctx.id, date_from=date(2026, 10, 16), days=2, limit=12
        )
        starts = [slot.slot_start for slot in found]
        assert len(found) == 12  # 8 left on Friday + the first 4 on Saturday
        assert FRIDAY_1000_PKT not in starts  # full
        assert starts == sorted(starts)
        assert starts[0] == FRIDAY_0900_PKT
        assert starts[-1] == datetime(2026, 10, 17, 7, tzinfo=UTC)  # Saturday 12:00 PKT
        today = await scheduling_service.list_open_slots(
            session, shop_id=ctx.id, date_from=date(2026, 10, 14), days=1, limit=3
        )
        assert [slot.slot_start.hour for slot in today] == [5, 6, 7]  # after now only
        assert await scheduling_service.is_slot_open(
            session, shop_id=ctx.id, slot_start=FRIDAY_0900_PKT
        )
        assert not await scheduling_service.is_slot_open(
            session, shop_id=ctx.id, slot_start=FRIDAY_1000_PKT
        )  # full
        assert not await scheduling_service.is_slot_open(
            session, shop_id=ctx.id, slot_start=FRIDAY_0900_PKT + timedelta(minutes=5)
        )  # off the grid
        for days, limit in ((0, 12), (8, 12), (1, 0)):
            with pytest.raises(ValueError, match="must be"):
                await scheduling_service.list_open_slots(
                    session, shop_id=ctx.id, date_from=date(2026, 10, 16), days=days, limit=limit
                )
