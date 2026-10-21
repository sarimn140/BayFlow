"""`GET /health` (unversioned, glossary §9): Railway's deploy health check (D13, spec 07).

200 `{"status": "ok", "database": "ok"}` when `SELECT 1` succeeds within 2 s, otherwise 503
`{"status": "degraded", "database": "error"}`. No authentication and no host filtering, so
Railway's `healthcheck.railway.app` requests are accepted.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.database import Database, get_database

HEALTH_DB_TIMEOUT_SECONDS = 2.0

router = APIRouter(tags=["system"])


class HealthRead(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "error"]


@router.get(
    "/health",
    summary="Liveness and database check",
    response_model=HealthRead,
    responses={503: {"model": HealthRead, "description": "The database is unreachable."}},
)
async def health(database: Annotated[Database, Depends(get_database)]) -> JSONResponse:
    if await database.ping(timeout_seconds=HEALTH_DB_TIMEOUT_SECONDS):
        body = HealthRead(status="ok", database="ok")
        return JSONResponse(body.model_dump(), status_code=200)
    body = HealthRead(status="degraded", database="error")
    return JSONResponse(body.model_dump(), status_code=503)
