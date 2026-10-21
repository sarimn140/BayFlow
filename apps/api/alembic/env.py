"""Alembic environment: async template (spec 02 §9, spec 01 "Database sessions").

The URL comes from the app's own settings (`DATABASE_URL`, normalised to `postgresql+asyncpg://`),
and `target_metadata` holds every module's models (`app.models_registry`), with the constraint
naming convention of spec 02 §2.2. CHECK constraints are compared by name through Alembic's opt-in
`checkconstraint_byname` plugin, so `alembic check` also catches missing or extra CHECKs.
"""

import asyncio
from logging.config import fileConfig
from typing import Any, Literal

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy import CheckConstraint, Enum, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql.elements import conv

from app.core.config import get_settings
from app.models_registry import metadata as target_metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

AUTOGENERATE_PLUGINS = ["alembic.autogenerate.*", "alembic.ext.checkconstraint_byname"]


def _database_url() -> str:
    return get_settings().database_url.get_secret_value()


def render_item(
    type_: str, obj: Any, autogen_context: AutogenContext
) -> str | Literal[False] | None:
    """Render D29 enums as `VARCHAR(32)` plus exactly one named CHECK per column.

    SQLAlchemy 2.1 keeps an enum CHECK's create rule as a `functools.partial`, which Alembic 1.20's
    renderer no longer recognises as type-bound; it would emit the CHECK twice (once under the
    naming convention, once under the raw type name) next to an `sa.Enum` that creates it again.
    """
    if type_ == "type" and isinstance(obj, Enum) and not obj.native_enum:
        return f"sa.String(length={obj.length})"
    if type_ == "check" and isinstance(obj, CheckConstraint) and obj._type_bound:
        if not isinstance(obj.name, conv):
            return None  # the raw-named copy re-created when Alembic rebuilds the table
        sqltext = autogen_context.migration_context.impl.render_ddl_sql_expr(obj.sqltext)
        return f"sa.CheckConstraint({sqltext!r}, name=op.f({str(obj.name)!r}))"
    return False


def _context_options() -> dict[str, Any]:
    return {
        "target_metadata": target_metadata,
        "compare_type": True,
        "compare_server_default": True,
        "autogenerate_plugins": AUTOGENERATE_PLUGINS,
        "render_item": render_item,
    }


def run_migrations_offline() -> None:
    """Emit SQL to stdout (`alembic upgrade head --sql`) without connecting."""
    context.configure(
        url=_database_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_context_options(),
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, **_context_options())
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(_database_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
