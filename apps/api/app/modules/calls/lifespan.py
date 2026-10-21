"""Background work of the calls module while the app runs (spec 05 §3.5; D104).

When calling is enabled, the sweeper runs at boot and every 5 s; it is stopped at shutdown. The hub
gets nothing from here: the notifications module registers its own connect hook (spec 01 rule 6).
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.modules.calls import service
from app.modules.calls.constants import SWEEP_INTERVAL_SECONDS


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if not app.state.settings.calling_enabled:
        yield
        return
    stop = asyncio.Event()
    task = asyncio.create_task(
        service.run_sweeper(app.state, stop, SWEEP_INTERVAL_SECONDS), name="calls-sweeper"
    )
    try:
        yield
    finally:
        stop.set()
        with contextlib.suppress(asyncio.CancelledError):
            await task
