"""Shared fixtures (spec 12 §4).

Test database (spec 12 §4.1): the `DATABASE_URL` database name plus `_test` (`bayflow` ->
`bayflow_test`) on the same server. The session creates it when missing, refuses any name that
does not end in `_test`, resets the `public` schema, runs `alembic upgrade head` as a subprocess
(the same command as Railway's pre-deploy) and sets `lock_timeout` / `statement_timeout`. Tests
that touch the database are marked `db` (or request the `db` fixture, which marks them); every
table is truncated after each of them. Engines use `NullPool`, so no connection is reused across
event loops.
"""

import asyncio
import os
import re
import sys
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import make_url, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings

API_DIR = Path(__file__).resolve().parents[1]
TEST_JWT_SECRET = "test-only-jwt-secret-that-is-longer-than-thirty-two-bytes"
TEST_CLIENT_URL = "http://localhost:3000"
WEDNESDAY_0900_PKT = datetime(2026, 10, 14, 4, 0, tzinfo=UTC)  # spec 12 §4.4


def _derive_test_database_url() -> URL:
    base = make_url(get_settings().database_url.get_secret_value())
    return base.set(database=f"{base.database}_test")


TEST_DATABASE_URL = _derive_test_database_url()
TEST_DATABASE_URL_STR = TEST_DATABASE_URL.render_as_string(hide_password=False)

# Make every in-process `get_settings()` (token signing, Alembic, scripts) see test values, whatever
# the developer's root .env contains. Process environment variables win over the .env file.
os.environ.update(
    {
        "APP_ENV": "development",
        "DATABASE_URL": TEST_DATABASE_URL_STR,
        "JWT_SECRET": TEST_JWT_SECRET,
        "JWT_EXPIRES_IN": "7d",
        "COOKIE_SECURE": "false",
        "CLIENT_URL": TEST_CLIENT_URL,
        "EMAIL_PROVIDER": "none",
        "SEED_ON_DEPLOY": "false",
        "LOG_LEVEL": "INFO",
    }
)
get_settings.cache_clear()

# Imported after the environment is fixed: `app.main` builds a module-level app on import.
from app.core.database import Database  # noqa: E402
from app.core.security import reset_rate_limits  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models_registry import metadata  # noqa: E402
from app.shared.clock import SimulatedClock, use_clock  # noqa: E402

APP_TABLES = sorted(metadata.tables)


def make_settings(**overrides: object) -> Settings:
    """Settings for an app under test, independent of any .env file."""
    values: dict[str, object] = {
        "app_env": "development",
        "database_url": TEST_DATABASE_URL_STR,
        "jwt_secret": TEST_JWT_SECRET,
        "cookie_secure": False,
        "client_url": TEST_CLIENT_URL,
        "email_provider": "none",
        "log_level": "INFO",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


# --- Markers ------------------------------------------------------------------------------------


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """`db` marker <-> `db` fixture: each implies the other (tables are truncated after each)."""
    for item in items:
        fixturenames = getattr(item, "fixturenames", None)
        if fixturenames is None:
            continue
        if "db" in fixturenames and item.get_closest_marker("db") is None:
            item.add_marker(pytest.mark.db)
        if item.get_closest_marker("db") is not None and "db" not in fixturenames:
            fixturenames.append("db")


# --- Database -----------------------------------------------------------------------------------


def _connect_kwargs(url: URL, database: str) -> dict[str, object]:
    return {
        "user": url.username,
        "password": url.password,
        "host": url.host or "localhost",
        "port": url.port or 5432,
        "database": database,
    }


async def _prepare_test_database(url: URL) -> None:
    name = url.database or ""
    if not re.fullmatch(r"[A-Za-z0-9_]+_test", name):
        pytest.fail(f"refusing to use database {name!r}: test databases must end in '_test'")
    try:
        admin = await asyncpg.connect(**_connect_kwargs(url, "postgres"))
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.fail(
            f"PostgreSQL is not reachable at {url.host}:{url.port} ({type(exc).__name__}). "
            "Start it (e.g. `make db-up`) or point DATABASE_URL at a running server."
        )
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if not exists:
            await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()
    connection = await asyncpg.connect(**_connect_kwargs(url, name))
    try:
        await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await connection.execute(f"ALTER DATABASE \"{name}\" SET lock_timeout = '5s'")
        await connection.execute(f"ALTER DATABASE \"{name}\" SET statement_timeout = '30s'")
    finally:
        await connection.close()


async def run_alembic(*args: str) -> str:
    """Run the Alembic CLI against the test database in a subprocess; fail the test on error."""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        *args,
        cwd=API_DIR,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL_STR},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await process.communicate()
    text_output = output.decode()
    if process.returncode != 0:
        pytest.fail(f"alembic {' '.join(args)} failed:\n{text_output}")
    return text_output


@pytest.fixture
def alembic_cli() -> object:
    """`await alembic_cli("upgrade", "head")`: the Alembic CLI against the test database."""
    return run_alembic


@pytest.fixture(scope="session")
async def test_database() -> str:
    await _prepare_test_database(TEST_DATABASE_URL)
    await run_alembic("upgrade", "head")
    return TEST_DATABASE_URL_STR


@pytest.fixture(scope="session")
async def database(test_database: str) -> AsyncIterator[Database]:
    db = Database(test_database, poolclass=NullPool)
    yield db
    await db.dispose()


@pytest.fixture
async def db(database: Database) -> AsyncIterator[Database]:
    """The test database; every application table is truncated after the test."""
    yield database
    async with database.engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {', '.join(APP_TABLES)} RESTART IDENTITY CASCADE"))


# --- App and HTTP clients -------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fresh_rate_limits() -> Iterator[None]:
    reset_rate_limits()
    yield
    reset_rate_limits()


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """An app without lifespan (no database): for tests that never reach the database."""
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
async def db_app(db: Database, settings: Settings) -> AsyncIterator[FastAPI]:
    """An app whose lifespan ran, wired to the test database."""
    application = create_app(settings, database=db)
    async with LifespanManager(application):
        yield application


@pytest.fixture
async def db_client(db_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=db_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


# --- Time -----------------------------------------------------------------------------------------


@pytest.fixture
def clock() -> Iterator[SimulatedClock]:
    """A frozen `SimulatedClock` installed as the process clock (spec 12 §4.4)."""
    simulated = SimulatedClock(WEDNESDAY_0900_PKT)
    with use_clock(simulated):
        yield simulated
