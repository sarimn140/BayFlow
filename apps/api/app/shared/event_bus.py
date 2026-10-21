"""In-process, synchronous event bus (spec 01 "Event bus").

`await uow.publish(event)` runs every handler subscribed to the event's exact type, in
registration order, on the same session and inside the same transaction as the publisher. A
failing handler rolls back the whole use case. Handlers never commit, never do network I/O and
queue user-facing side effects with `uow.after_commit(...)`. Subscriptions are wired explicitly by
`app.main.create_app()` (each module's `handlers.register(bus)`), never at import time.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.shared.uow import UnitOfWork

MAX_EVENT_DEPTH = 5


@dataclass(frozen=True, slots=True, kw_only=True)
class Event:
    """Base of every domain event: ids, enums and primitives only (no ORM objects)."""

    occurred_at: datetime


type EventHandler[E: Event] = Callable[[E, "UnitOfWork"], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[EventHandler[Any]]] = {}

    def subscribe[E: Event](self, event_type: type[E], handler: EventHandler[E]) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def handlers_for(self, event_type: type[Event]) -> tuple[EventHandler[Any], ...]:
        return tuple(self._handlers.get(event_type, ()))

    async def dispatch(self, event: Event, uow: "UnitOfWork") -> None:
        """Run the handlers of `type(event)` one after another (never concurrently)."""
        for handler in self.handlers_for(type(event)):
            await handler(event, uow)
