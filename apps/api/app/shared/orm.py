"""Column helpers shared by every module's models (spec 02 §2, §2.1, §2.3).

- `UUIDPrimaryKeyMixin`: `id uuid` PK, generated in Python (D50; the `Base` constructor assigns
  it immediately, the column default is only a fallback). No database default.
- `CreatedAtMixin` / `TimestampMixin`: `timestamptz NOT NULL DEFAULT now()`. The service assigns
  the action's clock instant (D63); the ORM default/onupdate read the same injectable clock; the
  database default is only a fallback for hand-written SQL.
- `enum_type()`: `varchar(32)` + a CHECK listing exactly the enum's values, named
  `ck_<table>_<column>` (D29: `native_enum=False, create_constraint=True`).
- `not_blank()`: `ck_<table>_<column>_not_blank` for required free-text columns.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Enum, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm.attributes import flag_modified

from app.shared.clock import utcnow


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, sort_order=-100
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        sort_order=100,
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
        sort_order=101,
    )


def touch(row: TimestampMixin, now: datetime) -> None:
    """Stamp a changed row with the action's single instant `now` (D63), unconditionally.

    `TimestampMixin.updated_at` has `onupdate=utcnow` as a safety net, and SQLAlchemy leaves a
    column out of the `UPDATE` when it is set to the value it already holds. When one action
    updates a row twice (a receipt raises a part's `on_hand`, then its handler reserves the same
    part; an executor writes a booking, then a handler touches it again), the second `UPDATE` would
    omit `updated_at` and `onupdate` would read the clock a second time. `flag_modified` always
    sends `now`. Every service write stamps its rows with this function.
    """
    row.updated_at = now
    flag_modified(row, "updated_at")


def enum_type(enum_class: type[StrEnum], column_name: str) -> Enum:
    """A non-native enum type whose CHECK constraint is named `ck_<table>_<column_name>`."""
    return Enum(
        enum_class,
        name=column_name,
        native_enum=False,
        create_constraint=True,
        length=32,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


def not_blank(column_name: str) -> CheckConstraint:
    """`CHECK (btrim(<column>) <> '')`, named `ck_<table>_<column>_not_blank`."""
    return CheckConstraint(f"btrim({column_name}) <> ''", name=f"{column_name}_not_blank")
