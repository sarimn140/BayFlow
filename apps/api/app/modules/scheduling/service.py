"""Use cases of the scheduling module (`modules/scheduling.md` §5).

- `list_availability` — `GET /api/v1/public/shops/{shop_slug}/availability` (read).
- `validate_slot` — the pure `INVALID_SLOT` check bookings runs early in `create_booking`.
- `reserve_slot` — nested in booking creation (T01): re-validates against the config read under
  the shop's `FOR SHARE` lock, then `INSERT … ON CONFLICT DO NOTHING` → `SELECT … FOR UPDATE` →
  capacity check (409 `SLOT_FULL`) → increment.
- `release_slot` — nested in `DECLINE` / `CANCEL`: decrement; fails loudly when the counter row is
  missing (DI-4 broken).
- P2 helpers for the AI Front Desk: `list_open_slots`, `is_slot_open` (never hold a slot).

Scheduling sits below bookings and never imports it (D86); schedule settings come from
`shops.service.get_schedule_config`.
"""

import uuid
from collections.abc import Iterable
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import FieldError, InvalidSlot, NotFound, SlotFull
from app.modules.scheduling.domain.slots import (
    SLOT_PROBLEM_MESSAGES,
    GridSlot,
    bookable_dates,
    day_slots,
    grid_slot_at,
    is_offered,
    slot_problem,
)
from app.modules.scheduling.repository import SlotCounterRepository
from app.modules.scheduling.schemas import AvailabilityRead, SlotRead
from app.modules.shops import service as shops_service
from app.modules.shops.domain.grid import ScheduleConfig
from app.shared.clock import utcnow
from app.shared.uow import UnitOfWork

OPEN_SLOTS_MAX_DAYS = 7
OPEN_SLOTS_DEFAULT_LIMIT = 12


class SlotCounterMissingError(RuntimeError):
    """`release_slot` found no counter row: every non-cancelled booking incremented its counter in
    the transaction that created it (DI-4), so this is a bug and must surface as a 500."""


async def _open_slots(
    session: AsyncSession,
    config: ScheduleConfig,
    days: Iterable[date],
    now: datetime,
    limit: int | None = None,
) -> list[SlotRead]:
    """The offered slots of `days` with `remaining > 0`, in time order (§7.3)."""
    first_day, last_day = bookable_dates(now, config.timezone)
    candidates = [
        slot
        for day in days
        if first_day <= day <= last_day  # also keeps extreme dates away from the datetime limits
        for slot in day_slots(config, day)
        if is_offered(slot, config, now)
    ]
    if not candidates:
        return []
    counts = await SlotCounterRepository(session).counts_between(
        shop_id=config.shop_id,
        first=min(slot.slot_start for slot in candidates),
        last=max(slot.slot_start for slot in candidates),
    )
    slots: list[SlotRead] = []
    for slot in candidates:
        # A capacity lowered below the places already booked just closes the slot (never < 0).
        remaining = config.slot_capacity - counts.get(slot.slot_start, 0)
        if remaining > 0:
            slots.append(
                SlotRead(slot_start=slot.slot_start, slot_end=slot.slot_end, remaining=remaining)
            )
            if limit is not None and len(slots) >= limit:
                break
    return slots


async def list_availability(
    session: AsyncSession, *, shop_slug: str, day: date
) -> AvailabilityRead:
    """The free slots of a listed shop on one shop-local date (spec 03 §4.5, D37, D68).

    Unknown or unlisted slug → 404 (a listed shop without an active service still answers, D64).
    Past dates, dates beyond the horizon and closed days → `slots: []`; full slots are omitted.
    """
    shop = await shops_service.get_listed_shop(session, shop_slug=shop_slug)
    if shop is None:
        raise NotFound
    config = await shops_service.get_schedule_config(session, shop_id=shop.id)
    slots = await _open_slots(session, config, [day], utcnow())
    return AvailabilityRead(
        shop_id=shop.id,
        date=day,
        timezone=config.timezone,
        slot_duration_minutes=config.slot_duration_minutes,
        slots=slots,
    )


def validate_slot(config: ScheduleConfig, *, slot_start: datetime, now: datetime) -> GridSlot:
    """The grid slot starting at `slot_start`, or 422 `INVALID_SLOT` with one `slot_start` field
    error naming the first broken rule (`off_grid`, `in_past`, `beyond_horizon`, `closed_day`,
    `outside_hours`; spec 03 §2.3)."""
    problem = slot_problem(config, slot_start, now)
    if problem is not None:
        message = SLOT_PROBLEM_MESSAGES[problem]
        raise InvalidSlot(
            message,
            errors=[FieldError(field="slot_start", code=problem.value, message=message)],
        )
    return grid_slot_at(config, slot_start)


async def reserve_slot(
    uow: UnitOfWork, *, config: ScheduleConfig, slot_start: datetime, now: datetime
) -> GridSlot:
    """Take one place in a slot (nested in booking creation, T01; D37, spec 02 §7.4).

    `config` must have been read under the shop row's `FOR SHARE` lock in this transaction
    (`shops.get_schedule_config(for_share=True)`), so a concurrent grid change can neither slip in
    nor change the capacity before the booking commits. Re-validating here turns a slot that is
    off a just-committed new grid into 422 `INVALID_SLOT` (CON-05). The counter row is the last
    lock of the transaction (D30); a full slot → 409 `SLOT_FULL` and the caller rolls back.
    """
    slot = validate_slot(config, slot_start=slot_start, now=now)
    counters = SlotCounterRepository(uow.session)
    await counters.insert_if_missing(shop_id=config.shop_id, slot_start=slot.slot_start, now=now)
    booked = await counters.lock(shop_id=config.shop_id, slot_start=slot.slot_start)
    if booked >= config.slot_capacity:
        raise SlotFull
    await counters.increment(shop_id=config.shop_id, slot_start=slot.slot_start, now=now)
    return slot


async def release_slot(
    uow: UnitOfWork, *, shop_id: uuid.UUID, slot_start: datetime, now: datetime
) -> None:
    """Free one place (nested in `DECLINE` / `CANCEL`, D24; called under the booking lock).

    A missing counter row raises `SlotCounterMissingError` (500); the CHECK on `booked_count`
    stops a double release from going below 0. Rows are never deleted: a freed slot keeps a row
    with `booked_count = 0` and is offered again.
    """
    remaining = await SlotCounterRepository(uow.session).decrement(
        shop_id=shop_id, slot_start=slot_start, now=now
    )
    if remaining is None:
        msg = f"no slot counter for shop {shop_id} at {slot_start.isoformat()}"
        raise SlotCounterMissingError(msg)


async def list_open_slots(
    session: AsyncSession,
    *,
    shop_id: uuid.UUID,
    date_from: date,
    days: int,
    limit: int = OPEN_SLOTS_DEFAULT_LIMIT,
) -> list[SlotRead]:
    """P2 (AI Front Desk `available-slots`): the first `limit` free slots over `days` (1-7)
    consecutive shop-local dates from `date_from`, in time order. Holds nothing."""
    if not 1 <= days <= OPEN_SLOTS_MAX_DAYS:
        msg = f"days must be between 1 and {OPEN_SLOTS_MAX_DAYS}"
        raise ValueError(msg)
    if limit < 1:
        msg = "limit must be at least 1"
        raise ValueError(msg)
    config = await shops_service.get_schedule_config(session, shop_id=shop_id)
    dates = [date_from + timedelta(days=offset) for offset in range(days)]
    return await _open_slots(session, config, dates, utcnow(), limit=limit)


async def is_slot_open(session: AsyncSession, *, shop_id: uuid.UUID, slot_start: datetime) -> bool:
    """P2 (reschedule requests): `slot_start` passes `validate_slot` and has a free place right
    now. No lock and no hold."""
    config = await shops_service.get_schedule_config(session, shop_id=shop_id)
    if slot_problem(config, slot_start, utcnow()) is not None:
        return False
    booked = await SlotCounterRepository(session).get_count(shop_id=shop_id, slot_start=slot_start)
    return config.slot_capacity - booked > 0
