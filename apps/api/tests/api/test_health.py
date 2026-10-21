"""`GET /health` (spec 07, spec 12 API-08): database up and down."""

import httpx
import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.database import Database
from app.main import create_app

UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://bayflow:bayflow@127.0.0.1:1/unreachable"


@pytest.mark.db
async def test_health_is_ok_when_the_database_answers(db_client: httpx.AsyncClient) -> None:
    response = await db_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert "x-request-id" in response.headers


async def test_health_is_degraded_when_the_database_is_unreachable(settings: Settings) -> None:
    database = Database(UNREACHABLE_DATABASE_URL, poolclass=NullPool)
    app = create_app(settings, database=database)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
    await database.dispose()
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "error"}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.db
async def test_health_never_reads_credentials(db_client: httpx.AsyncClient) -> None:
    response = await db_client.get("/health", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 200
