"""In-process event bus and unit of work (spec 01 "Event bus")."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from starlette.datastructures import State
from starlette.requests import Request

from app.shared.event_bus import MAX_EVENT_DEPTH, Event, EventBus
from app.shared.uow import (
    EventNestingTooDeepError,
    UnitOfWork,
    drain_after_commit_tasks,
    get_uow,
    pending_after_commit_tasks,
)

NOW = datetime(2026, 10, 14, 4, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class SomethingHappened(Event):
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SomethingElse(Event):
    pass


class FakeSession:
    """Just enough of AsyncSession for the unit of work."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def make_uow(bus: EventBus) -> tuple[UnitOfWork, FakeSession]:
    session = FakeSession()
    return UnitOfWork(session, bus), session  # type: ignore[arg-type]


async def test_handlers_run_in_registration_order_with_the_same_uow() -> None:
    bus = EventBus()
    calls: list[tuple[str, str, UnitOfWork]] = []

    async def first(event: SomethingHappened, uow: UnitOfWork) -> None:
        calls.append(("first", event.name, uow))

    async def second(event: SomethingHappened, uow: UnitOfWork) -> None:
        calls.append(("second", event.name, uow))

    bus.subscribe(SomethingHappened, first)
    bus.subscribe(SomethingHappened, second)
    uow, _ = make_uow(bus)
    await uow.publish(SomethingHappened(occurred_at=NOW, name="x"))
    assert [(step, name) for step, name, _ in calls] == [("first", "x"), ("second", "x")]
    assert all(called_uow is uow for _, _, called_uow in calls)


async def test_only_handlers_of_the_exact_event_type_run() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def handler(event: SomethingElse, uow: UnitOfWork) -> None:
        seen.append("else")

    bus.subscribe(SomethingElse, handler)
    uow, _ = make_uow(bus)
    await uow.publish(SomethingHappened(occurred_at=NOW, name="x"))
    assert seen == []


async def test_a_failing_handler_propagates_to_the_publisher() -> None:
    bus = EventBus()

    async def broken(event: SomethingHappened, uow: UnitOfWork) -> None:
        raise RuntimeError("handler failed")

    bus.subscribe(SomethingHappened, broken)
    uow, _ = make_uow(bus)
    with pytest.raises(RuntimeError, match="handler failed"):
        await uow.publish(SomethingHappened(occurred_at=NOW, name="x"))


async def test_nested_publishing_is_capped() -> None:
    bus = EventBus()
    depth = 0

    async def republish(event: SomethingHappened, uow: UnitOfWork) -> None:
        nonlocal depth
        depth += 1
        await uow.publish(SomethingHappened(occurred_at=NOW, name="again"))

    bus.subscribe(SomethingHappened, republish)
    uow, _ = make_uow(bus)
    with pytest.raises(EventNestingTooDeepError):
        await uow.publish(SomethingHappened(occurred_at=NOW, name="x"))
    assert depth == MAX_EVENT_DEPTH


async def test_after_commit_callbacks_run_only_after_a_commit() -> None:
    bus = EventBus()
    uow, session = make_uow(bus)
    ran: list[str] = []

    async def push() -> None:
        ran.append("pushed")

    uow.after_commit(push)
    await asyncio.sleep(0)
    assert ran == []
    await uow.commit()
    assert session.commits == 1
    await drain_after_commit_tasks()
    assert ran == ["pushed"]
    assert pending_after_commit_tasks() == 0


async def test_rollback_discards_after_commit_callbacks() -> None:
    bus = EventBus()
    uow, session = make_uow(bus)
    ran: list[str] = []

    async def push() -> None:
        ran.append("pushed")

    uow.after_commit(push)
    await uow.rollback()
    await uow.commit()
    await drain_after_commit_tasks()
    assert ran == []
    assert session.rollbacks == 1


def test_a_hand_built_unit_of_work_has_no_app_state() -> None:
    uow, _ = make_uow(EventBus())
    assert uow.app_state is None  # D90: scripts, the seed and unit tests queue no push or e-mail


async def test_handlers_reach_per_app_resources_through_the_app_state() -> None:
    bus = EventBus()
    state = State()
    state.marker = "per-app resource"
    seen: list[object] = []

    async def handler(event: SomethingHappened, uow: UnitOfWork) -> None:
        seen.append(None if uow.app_state is None else uow.app_state.marker)

    bus.subscribe(SomethingHappened, handler)
    uow = UnitOfWork(FakeSession(), bus, app_state=state)  # type: ignore[arg-type]
    await uow.publish(SomethingHappened(occurred_at=NOW, name="x"))
    assert seen == ["per-app resource"]


async def test_get_uow_carries_the_request_app_state_and_bus() -> None:
    app = FastAPI()
    app.state.event_bus = EventBus()
    request = Request({"type": "http", "app": app})
    session = FakeSession()
    uow = await get_uow(request, session)  # type: ignore[arg-type]
    assert uow.app_state is app.state
    assert uow.bus is app.state.event_bus
    assert uow.session is session  # type: ignore[comparison-overlap]


async def test_a_failing_after_commit_callback_is_logged_not_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = EventBus()
    uow, _ = make_uow(bus)

    async def broken() -> None:
        raise RuntimeError("smtp down")

    uow.after_commit(broken)
    await uow.commit()
    await drain_after_commit_tasks()
    assert any("after-commit callback failed" in record.getMessage() for record in caplog.records)
