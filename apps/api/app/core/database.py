"""Async database access (spec 01 "Database sessions and transactions", spec 02 §2).

- `Base`: the declarative base for every module's models, with the constraint naming convention
  (`pk_`, `fk_`, `uq_`, `ck_`, `ix_`) that error mapping and Alembic rely on, timezone-aware
  `datetime` columns, `eager_defaults` and UUID primary keys generated in Python (D50).
- `Database`: one async engine (`pool_pre_ping`) + `async_sessionmaker(expire_on_commit=False)`.
  It is created in the app lifespan, never at import time.
- `get_session` / `DbSession`: one session per request. The dependency only closes the session
  (rolling back anything uncommitted); services commit before the response is built.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any, ClassVar

from fastapi import Depends, Request
from sqlalchemy import DateTime, MetaData, Uuid, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import Pool

from app.core.config import Settings

logger = logging.getLogger(__name__)

NAMING_CONVENTION: dict[str, str] = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
}


class Base(DeclarativeBase):
    """Declarative base of every ORM model (models live in their owning module, glossary §7)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
        uuid.UUID: Uuid(),
    }
    # Spec 02 §2.3: fetch server-generated values right after INSERT/UPDATE (no lazy IO later).
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 - read once by the declarative scan

    def __init__(self, **kwargs: Any) -> None:
        """Keyword constructor that assigns a UUID v4 primary key immediately (spec 02 §2).

        Services need ids before the flush (event metadata, notification links, responses);
        a column `default` would only run at INSERT time.
        """
        cls = type(self)
        for key in kwargs:
            if not hasattr(cls, key):
                msg = f"{key!r} is an invalid keyword argument for {cls.__name__}"
                raise TypeError(msg)
        id_column = cls.__table__.c.get("id")
        if id_column is not None and isinstance(id_column.type, Uuid) and kwargs.get("id") is None:
            kwargs["id"] = uuid.uuid4()
        for key, value in kwargs.items():
            setattr(self, key, value)


class Database:
    """The async engine and session factory of one process (or one test)."""

    def __init__(
        self,
        url: str,
        *,
        hide_parameters: bool = False,
        poolclass: type[Pool] | None = None,
        echo: bool = False,
    ) -> None:
        options: dict[str, Any] = {
            "pool_pre_ping": True,
            "hide_parameters": hide_parameters,  # spec 04: no SQL parameters in production logs
            "echo": echo,
        }
        if poolclass is None:
            options.update(pool_size=5, max_overflow=5)
        else:
            options["poolclass"] = poolclass
        self.engine: AsyncEngine = create_async_engine(url, **options)
        self.sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine, expire_on_commit=False
        )

    @classmethod
    def from_settings(
        cls, settings: Settings, *, poolclass: type[Pool] | None = None
    ) -> "Database":
        return cls(
            settings.database_url.get_secret_value(),
            hide_parameters=settings.is_production,
            poolclass=poolclass,
        )

    async def ping(self, timeout_seconds: float = 2.0) -> bool:
        """`SELECT 1` within `timeout_seconds`; False on any failure (used by `GET /health`)."""
        try:
            async with asyncio.timeout(timeout_seconds), self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception as exc:  # unreachable, timeout, auth failure: reported as degraded
            logger.warning("database ping failed: %s", type(exc).__name__)
            return False
        return True

    async def server_version(self, timeout_seconds: float = 2.0) -> str | None:
        """PostgreSQL `server_version`, or None when the database cannot be reached."""
        try:
            async with asyncio.timeout(timeout_seconds), self.engine.connect() as connection:
                result = await connection.execute(text("SHOW server_version"))
                return str(result.scalar_one())
        except Exception as exc:  # best effort: only used for the start-up log line
            logger.warning("could not read the database server version: %s", type(exc).__name__)
            return None

    async def dispose(self) -> None:
        await self.engine.dispose()


def get_database(request: Request) -> Database:
    database = getattr(request.app.state, "db", None)
    if not isinstance(database, Database):
        msg = "the database is not initialised: the application lifespan has not run"
        raise RuntimeError(msg)
    return database


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One `AsyncSession` per request; closing it rolls back anything left uncommitted."""
    async with get_database(request).sessionmaker() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_session)]
