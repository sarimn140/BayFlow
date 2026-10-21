"""Unit of work: one request = one session = one transaction (spec 01, spec 08 principle 4).

Services receive the `UnitOfWork`, write through their repositories on `uow.session`, publish
events with `await uow.publish(event)` and, as a top-level use case, finish with
`await uow.commit()`. Callbacks queued with `uow.after_commit(...)` (WebSocket pushes, e-mails)
start only after a successful commit, as background tasks that never reuse the request session;
their failures are logged and never change the HTTP response.

`uow.app_state` is the application's `State` (D90): handlers reach per-app resources through it
(`db`, `settings`, the notifications module's hub and e-mail sender), never through module-level
singletons. It is `None` when a script, the seed or a unit test builds the unit of work by hand;
handlers then still write their rows but queue no push and no e-mail.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import State

from app.core.database import DbSession
from app.shared.event_bus import MAX_EVENT_DEPTH, Event, EventBus

logger = logging.getLogger(__name__)

type AfterCommitCallback = Callable[[], Awaitable[None]]

# The event loop keeps only weak references to tasks; keep them alive until they finish.
_background_tasks: set[asyncio.Task[None]] = set()


class EventNestingTooDeepError(RuntimeError):
    """Raised when handlers publish events more than `MAX_EVENT_DEPTH` levels deep."""


class UnitOfWork:
    def __init__(
        self, session: AsyncSession, bus: EventBus, *, app_state: State | None = None
    ) -> None:
        self.session = session
        self.bus = bus
        self.app_state = app_state
        self._after_commit: list[AfterCommitCallback] = []
        self._depth = 0

    async def publish(self, event: Event) -> None:
        """Run the event's handlers now, in this transaction (synchronously, in order)."""
        if self._depth >= MAX_EVENT_DEPTH:
            msg = f"events nested deeper than {MAX_EVENT_DEPTH} levels ({type(event).__name__})"
            raise EventNestingTooDeepError(msg)
        self._depth += 1
        try:
            await self.bus.dispatch(event, self)
        finally:
            self._depth -= 1

    def after_commit(self, callback: AfterCommitCallback) -> None:
        """Queue `callback` to run only if the transaction commits."""
        self._after_commit.append(callback)

    async def commit(self) -> None:
        await self.session.commit()
        callbacks, self._after_commit = self._after_commit, []
        for callback in callbacks:
            _start_background(callback)

    async def rollback(self) -> None:
        self._after_commit.clear()
        await self.session.rollback()


def _start_background(callback: AfterCommitCallback) -> None:
    task = asyncio.create_task(_run_after_commit(callback))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _run_after_commit(callback: AfterCommitCallback) -> None:
    try:
        await callback()
    except Exception:
        logger.exception("after-commit callback failed")


def pending_after_commit_tasks() -> int:
    return sum(1 for task in _background_tasks if not task.done())


async def drain_after_commit_tasks(timeout_seconds: float = 5.0) -> None:
    """Wait for queued after-commit work on shutdown; cancel whatever is still running after."""
    pending = {task for task in _background_tasks if not task.done()}
    if not pending:
        return
    _, still_pending = await asyncio.wait(pending, timeout=timeout_seconds)
    for task in still_pending:
        task.cancel()
    if still_pending:
        logger.warning("cancelled %d after-commit task(s) at shutdown", len(still_pending))


def get_event_bus(request: Request) -> EventBus:
    bus = getattr(request.app.state, "event_bus", None)
    if not isinstance(bus, EventBus):
        msg = "the event bus is not initialised: build the app with create_app()"
        raise RuntimeError(msg)
    return bus


async def get_uow(request: Request, session: DbSession) -> UnitOfWork:
    return UnitOfWork(session, get_event_bus(request), app_state=request.app.state)


UowDep = Annotated[UnitOfWork, Depends(get_uow)]
