"""In-process ring timers (spec 05 §3.5): a precise timer per ringing call, kept in a module-level
dict so the task is not garbage-collected.

The timer is only an optimisation. `ring_deadline` in the database is the truth, the expiry function
re-checks it under a row lock, and the sweeper (`lifespan.py`) catches anything a restart lost.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime

from app.shared.clock import utcnow

logger = logging.getLogger(__name__)

_ring_tasks: dict[uuid.UUID, asyncio.Task[None]] = {}


def schedule_ring_timeout(
    call_id: uuid.UUID, deadline: datetime, expire: Callable[[], Awaitable[object]]
) -> None:
    """Run `expire()` at `deadline` (app clock). A previous timer for the call is replaced."""
    cancel_ring_timeout(call_id)

    async def _run() -> None:
        try:
            await asyncio.sleep(max(0.0, (deadline - utcnow()).total_seconds()))
            await expire()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("calls.ring_timer_failed", extra={"call_id": str(call_id)})

    task = asyncio.create_task(_run(), name=f"ring-timeout:{call_id}")
    _ring_tasks[call_id] = task
    task.add_done_callback(lambda done: _forget(call_id, done))


def _forget(call_id: uuid.UUID, task: asyncio.Task[None]) -> None:
    if _ring_tasks.get(call_id) is task:
        del _ring_tasks[call_id]


def cancel_ring_timeout(call_id: uuid.UUID) -> None:
    task = _ring_tasks.pop(call_id, None)
    if task is not None and not task.done():
        task.cancel()


def pending_ring_timers() -> int:
    return sum(1 for task in _ring_tasks.values() if not task.done())
