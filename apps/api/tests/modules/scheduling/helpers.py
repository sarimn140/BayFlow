"""Scheduling test helpers: take and free places in a slot through the real service layer, the way
booking creation (T01) and `DECLINE`/`CANCEL` (T03, T22) will."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.core.errors import SlotFull
from app.modules.scheduling import service as scheduling_service
from app.modules.scheduling.models import SlotCounter
from app.modules.shops import service as shops_service
from app.shared.clock import utcnow
from tests.modules.identity.builders import unit_of_work


async def book(database: Database, shop_id: uuid.UUID, slot_start: datetime) -> str:
    """One booking's slot step in its own transaction: shop `FOR SHARE` → `reserve_slot`."""
    async with unit_of_work(database) as uow:
        config = await shops_service.get_schedule_config(
            uow.session, shop_id=shop_id, for_share=True
        )
        try:
            await scheduling_service.reserve_slot(
                uow, config=config, slot_start=slot_start, now=utcnow()
            )
        except SlotFull:
            await uow.rollback()
            return "full"
        await uow.commit()
        return "booked"


async def free(database: Database, shop_id: uuid.UUID, slot_start: datetime) -> None:
    """A cancellation's slot step in its own transaction."""
    async with unit_of_work(database) as uow:
        await scheduling_service.release_slot(
            uow, shop_id=shop_id, slot_start=slot_start, now=utcnow()
        )
        await uow.commit()


async def counter_in(session: AsyncSession, shop_id: uuid.UUID, slot_start: datetime) -> int | None:
    """The slot's `booked_count` as `session` sees it (its own uncommitted writes included), or
    None without a row: checked right after a refusal, it proves nothing was written first."""
    return await session.scalar(
        select(SlotCounter.booked_count).where(
            SlotCounter.shop_id == shop_id, SlotCounter.slot_start == slot_start
        )
    )


async def booked_count(database: Database, shop_id: uuid.UUID, slot_start: datetime) -> int | None:
    """The committed `booked_count` (None without a row)."""
    async with database.sessionmaker() as session:
        return await counter_in(session, shop_id, slot_start)
