"""Repository base classes (spec 01 repository row, spec 02 §7.6).

A module's repository is the only code that writes the module's tables. Every method on
shop-owned data takes a keyword-only, non-optional `shop_id` (D20): there is no "get by id"
without a shop. Integrity errors map to error codes by constraint name (`app.core.db_errors`,
re-exported here for repositories); unmapped ones surface as 500.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.core.db_errors import (
    CHECK_VIOLATION,
    DEADLOCK_DETECTED,
    FOREIGN_KEY_VIOLATION,
    LOCK_NOT_AVAILABLE,
    NOT_NULL_VIOLATION,
    SERIALIZATION_FAILURE,
    UNIQUE_VIOLATION,
    constraint_name,
    error_code_for,
    sqlstate,
)

__all__ = [
    "CHECK_VIOLATION",
    "DEADLOCK_DETECTED",
    "FOREIGN_KEY_VIOLATION",
    "LOCK_NOT_AVAILABLE",
    "NOT_NULL_VIOLATION",
    "SERIALIZATION_FAILURE",
    "UNIQUE_VIOLATION",
    "Repository",
    "ShopScopedRepository",
    "constraint_name",
    "error_code_for",
    "sqlstate",
]


class Repository:
    """Base of every module repository."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add[M: Base](self, instance: M) -> M:
        self.session.add(instance)
        return instance

    async def flush(self) -> None:
        await self.session.flush()


class ShopScopedRepository(Repository):
    """Repository of shop-owned tables: every query filters by the `shop_id` argument (D20)."""
