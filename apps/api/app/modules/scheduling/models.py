"""ORM models of the scheduling module: `slot_counters` (spec 02 §3.6, D37).

Slots themselves are computed, never stored; only booked counts are. The natural primary key
`(shop_id, slot_start)` is the one documented exception to the `id uuid` rule (glossary §13).
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.orm import TimestampMixin


class SlotCounter(TimestampMixin, Base):
    """Non-cancelled bookings that start in one grid slot of one shop."""

    __tablename__ = "slot_counters"
    __table_args__ = (CheckConstraint("booked_count >= 0", name="booked_count_non_negative"),)

    shop_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shops.id", ondelete="RESTRICT"), primary_key=True
    )
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    booked_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
