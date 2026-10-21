"""SQL for the scheduling module's table: `slot_counters` (spec 02 §3.6, §7.4; D37).

Counter rows are created lazily by a slot's first booking and never deleted. Every statement is
keyed by `(shop_id, slot_start)`, the primary key (D20), and every write takes the action's clock
instant `now` (D63), never the database's `now()`. The counter is always the last row lock of a
transaction (D30: booking → purchase order → parts → slot counter).
"""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.modules.scheduling.models import SlotCounter
from app.shared.repository import ShopScopedRepository


class SlotCounterRepository(ShopScopedRepository):
    async def counts_between(
        self, *, shop_id: uuid.UUID, first: datetime, last: datetime
    ) -> dict[datetime, int]:
        """`booked_count` per slot start in `[first, last]`: one range scan on the primary key."""
        statement = select(SlotCounter.slot_start, SlotCounter.booked_count).where(
            SlotCounter.shop_id == shop_id,
            SlotCounter.slot_start >= first,
            SlotCounter.slot_start <= last,
        )
        rows = await self.session.execute(statement)
        return {row.slot_start: row.booked_count for row in rows}

    async def get_count(self, *, shop_id: uuid.UUID, slot_start: datetime) -> int:
        """The slot's current `booked_count` (0 without a row), unlocked."""
        statement = select(SlotCounter.booked_count).where(
            SlotCounter.shop_id == shop_id, SlotCounter.slot_start == slot_start
        )
        count = (await self.session.execute(statement)).scalar_one_or_none()
        return count or 0

    async def insert_if_missing(
        self, *, shop_id: uuid.UUID, slot_start: datetime, now: datetime
    ) -> None:
        """`INSERT … ON CONFLICT DO NOTHING`: exactly one row exists even when two transactions
        create the slot's counter at the same time (spec 02 §7.4)."""
        statement = (
            insert(SlotCounter)
            .values(
                shop_id=shop_id,
                slot_start=slot_start,
                booked_count=0,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=[SlotCounter.shop_id, SlotCounter.slot_start])
        )
        await self.session.execute(statement)

    async def lock(self, *, shop_id: uuid.UUID, slot_start: datetime) -> int:
        """`SELECT booked_count … FOR UPDATE`: serialises bookings of one slot; a transaction that
        waited sees the committed increment of the one before it."""
        statement = (
            select(SlotCounter.booked_count)
            .where(SlotCounter.shop_id == shop_id, SlotCounter.slot_start == slot_start)
            .with_for_update()
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def increment(self, *, shop_id: uuid.UUID, slot_start: datetime, now: datetime) -> None:
        statement = (
            update(SlotCounter)
            .where(SlotCounter.shop_id == shop_id, SlotCounter.slot_start == slot_start)
            .values(booked_count=SlotCounter.booked_count + 1, updated_at=now)
        )
        await self.session.execute(statement)

    async def decrement(
        self, *, shop_id: uuid.UUID, slot_start: datetime, now: datetime
    ) -> int | None:
        """`booked_count - 1 … RETURNING booked_count`: None when the row does not exist. The
        `ck_slot_counters_booked_count_non_negative` CHECK stops the count going below 0."""
        statement = (
            update(SlotCounter)
            .where(SlotCounter.shop_id == shop_id, SlotCounter.slot_start == slot_start)
            .values(booked_count=SlotCounter.booked_count - 1, updated_at=now)
            .returning(SlotCounter.booked_count)
        )
        result = (await self.session.execute(statement)).scalar_one_or_none()
        return None if result is None else int(result)
