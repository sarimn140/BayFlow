"""The reporting use cases with every read they compose replaced by a recording fake (DB-free).

- `get_owner_overview` re-checks the role before reading anything (403 `FORBIDDEN`, D16), reads
  "now" once (D63), passes the shop-local window to bookings, asks for open jobs once for the
  whole team, fills missing statuses and open jobs with 0, keeps at most 5 low-stock parts, takes
  `has_parts` from the active parts count and one `is_listed` for both blocks, and answers 404
  if the shop cannot be read.
- `get_owner_summary` reads only the caller's `OWNER` memberships when they own nothing (no clock,
  no other read), keeps the membership order (shop name, then id), computes each shop's window in
  its own time zone from one instant, and defaults a missing low-stock count to 0.
"""

import uuid
from collections.abc import Collection, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Forbidden, NotFound
from app.modules.bookings import service as bookings_service
from app.modules.bookings.service import DayActivity
from app.modules.inventory import service as inventory_service
from app.modules.inventory.schemas import PartRead, StockSummary
from app.modules.reporting import service
from app.modules.shops import service as shops_service
from app.modules.shops.schemas import MembershipRecord, SetupFlags, ShopBrief, TeamMember
from app.shared.auth import CurrentUser, ShopContext
from app.shared.clock import use_clock
from app.shared.enums import BookingStatus, MembershipRole, StockState

S = BookingStatus
SESSION = cast(AsyncSession, object())
NOW = datetime(2026, 10, 15, 19, 30, tzinfo=UTC)  # Fri 16 Oct 00:30 PKT, Thu 15 Oct 20:30 BST


class CountingClock:
    def __init__(self, instant: datetime) -> None:
        self.instant = instant
        self.reads = 0

    def now(self) -> datetime:
        self.reads += 1
        return self.instant


@pytest.fixture
def counting_clock() -> Iterator[CountingClock]:
    counting = CountingClock(NOW)
    with use_clock(counting):
        yield counting


def brief(
    name: str, timezone: str = "Asia/Karachi", *, listed: bool = True, suspended: bool = False
) -> ShopBrief:
    return ShopBrief(
        id=uuid.uuid4(),
        slug=name.lower().replace(" ", "-"),
        name=name,
        address="Main Boulevard",
        city="Lahore",
        phone="+924200000000",
        timezone=timezone,
        is_listed=listed,
        is_suspended=suspended,
    )


def member(name: str, role: MembershipRole, *, active: bool = True) -> TeamMember:
    return TeamMember(
        membership_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        full_name=name,
        role=role,
        is_active=active,
    )


def part(sku: str) -> PartRead:
    return PartRead(
        id=uuid.uuid4(),
        sku=sku,
        name=f"Part {sku}",
        unit_cost=Decimal("900"),
        is_active=True,
        on_hand=0,
        reserved=0,
        available=0,
        reorder_level=1,
        stock_state=StockState.OUT,
        on_order=0,
        created_at=NOW,
        updated_at=NOW,
    )


@dataclass
class FakeReads:
    """Canned answers for every read reporting composes, and a log of the calls."""

    briefs: dict[uuid.UUID, ShopBrief] = field(default_factory=dict)
    counts: dict[uuid.UUID, dict[BookingStatus, int]] = field(default_factory=dict)
    activity: dict[uuid.UUID, DayActivity] = field(default_factory=dict)
    team: list[TeamMember] = field(default_factory=list)
    open_jobs: dict[uuid.UUID, int] = field(default_factory=dict)
    stock: StockSummary | None = None
    flags: SetupFlags | None = None
    memberships: list[MembershipRecord] = field(default_factory=list)
    low_stock: dict[uuid.UUID, int] = field(default_factory=dict)
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def arguments(self, name: str) -> list[dict[str, Any]]:
        return [arguments for called, arguments in self.calls if called == name]

    async def get_shop_briefs(
        self, session: AsyncSession, *, shop_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, ShopBrief]:
        self.calls.append(("get_shop_briefs", {"shop_ids": list(shop_ids)}))
        return {shop_id: self.briefs[shop_id] for shop_id in shop_ids if shop_id in self.briefs}

    async def count_by_status(
        self, session: AsyncSession, *, shop_id: uuid.UUID
    ) -> dict[BookingStatus, int]:
        self.calls.append(("count_by_status", {"shop_id": shop_id}))
        return self.counts.get(shop_id, {})

    async def count_day_activity(
        self, session: AsyncSession, *, shop_id: uuid.UUID, start: datetime, end: datetime
    ) -> DayActivity:
        self.calls.append(("count_day_activity", {"shop_id": shop_id, "start": start, "end": end}))
        return self.activity.get(shop_id, DayActivity(bookings=0, completed=0))

    async def list_team(self, session: AsyncSession, *, shop_id: uuid.UUID) -> list[TeamMember]:
        self.calls.append(("list_team", {"shop_id": shop_id}))
        return self.team

    async def count_open_jobs(
        self, session: AsyncSession, *, shop_id: uuid.UUID, user_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        self.calls.append(("count_open_jobs", {"shop_id": shop_id, "user_ids": list(user_ids)}))
        return self.open_jobs

    async def get_stock_summary(self, session: AsyncSession, *, shop_id: uuid.UUID) -> StockSummary:
        self.calls.append(("get_stock_summary", {"shop_id": shop_id}))
        assert self.stock is not None
        return self.stock

    async def get_setup_flags(self, session: AsyncSession, *, shop_id: uuid.UUID) -> SetupFlags:
        self.calls.append(("get_setup_flags", {"shop_id": shop_id}))
        assert self.flags is not None
        return self.flags

    async def list_memberships_for_user(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        roles: Collection[MembershipRole] | None = None,
    ) -> list[MembershipRecord]:
        self.calls.append(("list_memberships_for_user", {"user_id": user_id, "roles": roles}))
        return self.memberships

    async def count_low_stock(
        self, session: AsyncSession, *, shop_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        self.calls.append(("count_low_stock", {"shop_ids": list(shop_ids)}))
        return self.low_stock


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> FakeReads:
    fake = FakeReads()
    for name in ("get_shop_briefs", "list_team", "get_setup_flags", "list_memberships_for_user"):
        monkeypatch.setattr(shops_service, name, getattr(fake, name))
    for name in ("count_by_status", "count_day_activity", "count_open_jobs"):
        monkeypatch.setattr(bookings_service, name, getattr(fake, name))
    for name in ("get_stock_summary", "count_low_stock"):
        monkeypatch.setattr(inventory_service, name, getattr(fake, name))
    return fake


USER = CurrentUser(id=uuid.uuid4(), email="fatima.owner@bayflow.test", full_name="Fatima Raza")


def context(shop_id: uuid.UUID, role: MembershipRole = MembershipRole.OWNER) -> ShopContext:
    return ShopContext(shop_id=shop_id, user=USER, membership_id=uuid.uuid4(), role=role)


def stock(*, parts_count: int, low: list[PartRead], value: str = "286400") -> StockSummary:
    return StockSummary(
        parts_count=parts_count,
        low_stock_count=len(low),
        out_of_stock_count=len(low),
        stock_value=Decimal(value),
        open_purchase_orders=2,
        low_stock=low,
    )


# --- get_owner_overview -------------------------------------------------------------------------


@pytest.mark.parametrize("role", sorted(set(MembershipRole) - {MembershipRole.OWNER}))
async def test_the_overview_rechecks_the_role_before_any_read(
    reads: FakeReads, counting_clock: CountingClock, role: MembershipRole
) -> None:
    with pytest.raises(Forbidden):
        await service.get_owner_overview(SESSION, context(uuid.uuid4(), role))
    assert reads.calls == []
    assert counting_clock.reads == 0


async def test_the_overview_composes_every_block(
    reads: FakeReads, counting_clock: CountingClock
) -> None:
    shop = brief("Lahore Auto Care", listed=False)
    owner = member("Fatima Raza", MembershipRole.OWNER)
    imran = member("Imran", MembershipRole.TECHNICIAN)
    former = member("Zubair", MembershipRole.TECHNICIAN, active=False)
    reads.briefs = {shop.id: shop}
    reads.counts = {shop.id: {S.PENDING: 2, S.READY_FOR_PICKUP: 1, S.CANCELLED: 3}}
    reads.activity = {shop.id: DayActivity(bookings=4, completed=1)}
    reads.team = [owner, imran, former]
    reads.open_jobs = {imran.user_id: 3}  # no key for the others: 0
    low = [part(f"P-{index}") for index in range(7)]  # more than the overview shows
    reads.stock = stock(parts_count=9, low=low, value="19999999998")
    reads.flags = SetupFlags(has_services=True, has_team=True, is_listed=True)

    overview = await service.get_owner_overview(SESSION, context(shop.id))
    body = overview.model_dump(mode="json")

    assert counting_clock.reads == 1
    assert body["shop"] == {
        "id": str(shop.id),
        "slug": "lahore-auto-care",
        "name": "Lahore Auto Care",
        "city": "Lahore",
        "is_listed": False,
    }
    assert [item["status"] for item in body["status_counts"]] == [s.value for s in BookingStatus]
    assert {item["status"]: item["count"] for item in body["status_counts"] if item["count"]} == {
        "PENDING": 2,
        "READY_FOR_PICKUP": 1,
        "CANCELLED": 3,
    }
    assert body["today"] == {
        "date": "2026-10-16",
        "bookings": 4,
        "ready_for_pickup": 1,
        "completed": 1,
    }
    assert [(m["full_name"], m["is_active"], m["open_jobs"]) for m in body["team"]] == [
        ("Fatima Raza", True, 0),
        ("Imran", True, 3),
        ("Zubair", False, 0),
    ]
    assert body["inventory"] == {
        "parts_count": 9,
        "low_stock_count": 7,
        "out_of_stock_count": 7,
        "stock_value": "19999999998.00",
        "open_purchase_orders": 2,
    }
    assert [p["sku"] for p in body["low_stock"]] == ["P-0", "P-1", "P-2", "P-3", "P-4"]
    # One read of `is_listed` (the shop brief) feeds both blocks.
    assert body["setup"] == {
        "has_services": True,
        "has_team": True,
        "has_parts": True,
        "is_listed": False,
    }
    assert reads.arguments("get_shop_briefs") == [{"shop_ids": [shop.id]}]
    assert reads.arguments("count_day_activity") == [
        {
            "shop_id": shop.id,
            "start": datetime(2026, 10, 15, 19, tzinfo=UTC),
            "end": datetime(2026, 10, 16, 19, tzinfo=UTC),
        }
    ]
    assert reads.arguments("count_open_jobs") == [
        {"shop_id": shop.id, "user_ids": [owner.user_id, imran.user_id, former.user_id]}
    ]
    assert sorted(reads.names()) == sorted(
        [
            "get_shop_briefs",
            "count_by_status",
            "count_day_activity",
            "list_team",
            "count_open_jobs",
            "get_stock_summary",
            "get_setup_flags",
        ]
    )


async def test_the_overview_of_a_shop_without_active_parts(
    reads: FakeReads, counting_clock: CountingClock
) -> None:
    shop = brief("Pindi Auto Garage", "Europe/London")
    reads.briefs = {shop.id: shop}
    reads.team = [member("Tariq Mehmood", MembershipRole.OWNER)]
    reads.stock = stock(parts_count=0, low=[], value="0")
    reads.flags = SetupFlags(has_services=False, has_team=False, is_listed=True)

    body = (await service.get_owner_overview(SESSION, context(shop.id))).model_dump(mode="json")

    assert body["setup"] == {
        "has_services": False,
        "has_team": False,
        "has_parts": False,
        "is_listed": True,
    }
    assert body["status_counts"] == [{"status": s.value, "count": 0} for s in BookingStatus]
    assert body["today"]["date"] == "2026-10-15"  # 20:30 BST
    assert body["inventory"]["stock_value"] == "0.00"


async def test_the_overview_of_an_unreadable_shop_is_404(
    reads: FakeReads, counting_clock: CountingClock
) -> None:
    with pytest.raises(NotFound):
        await service.get_owner_overview(SESSION, context(uuid.uuid4()))
    assert reads.names() == ["get_shop_briefs"]


# --- get_owner_summary --------------------------------------------------------------------------


def owner_membership(shop_id: uuid.UUID) -> MembershipRecord:
    return MembershipRecord(
        id=uuid.uuid4(),
        shop_id=shop_id,
        user_id=USER.id,
        role=MembershipRole.OWNER,
        is_active=True,
    )


async def test_the_summary_of_someone_who_owns_nothing_reads_nothing_else(
    reads: FakeReads, counting_clock: CountingClock
) -> None:
    summary = await service.get_owner_summary(SESSION, USER)
    assert summary.model_dump(mode="json") == {"items": []}
    assert reads.calls == [
        ("list_memberships_for_user", {"user_id": USER.id, "roles": {MembershipRole.OWNER}})
    ]
    assert counting_clock.reads == 0


async def test_the_summary_keeps_the_membership_order_and_each_time_zone(
    reads: FakeReads, counting_clock: CountingClock
) -> None:
    lahore = brief("Lahore Auto Care")
    london = brief("A London Branch", "Europe/London")  # sorts first by name, listed second
    vanished = uuid.uuid4()  # a membership whose shop cannot be read: skipped
    closed = brief("Closed By BayFlow", suspended=True)  # D99: a suspended shop is left out
    reads.memberships = [
        owner_membership(lahore.id),
        owner_membership(vanished),
        owner_membership(closed.id),
        owner_membership(london.id),
        owner_membership(lahore.id),  # repeated: one row
    ]
    reads.briefs = {lahore.id: lahore, london.id: london, closed.id: closed}
    reads.counts = {
        lahore.id: {S.PENDING: 1, S.ESTIMATE_APPROVED: 2, S.READY_FOR_PICKUP: 3, S.IN_REPAIR: 4},
        london.id: {S.QC_PENDING: 5, S.COMPLETED: 6, S.CANCELLED: 7},
    }
    reads.activity = {
        lahore.id: DayActivity(bookings=8, completed=1),
        london.id: DayActivity(bookings=9, completed=2),
    }
    reads.low_stock = {lahore.id: 2}  # nothing for London: 0

    body = (await service.get_owner_summary(SESSION, USER)).model_dump(mode="json")

    assert counting_clock.reads == 1
    assert body["items"] == [
        {
            "shop": {
                "id": str(lahore.id),
                "slug": "lahore-auto-care",
                "name": "Lahore Auto Care",
                "city": "Lahore",
            },
            "today_bookings": 8,
            "needs_sa_action": 6,  # PENDING 1 + ESTIMATE_APPROVED 2 + READY_FOR_PICKUP 3
            "in_progress": 4,
            "ready_for_pickup": 3,
            "low_stock_count": 2,
        },
        {
            "shop": {
                "id": str(london.id),
                "slug": "a-london-branch",
                "name": "A London Branch",
                "city": "Lahore",
            },
            "today_bookings": 9,
            "needs_sa_action": 0,
            "in_progress": 5,
            "ready_for_pickup": 0,
            "low_stock_count": 0,
        },
    ]
    assert reads.arguments("count_low_stock") == [{"shop_ids": [lahore.id, london.id]}]
    windows = {
        arguments["shop_id"]: (arguments["start"], arguments["end"])
        for arguments in reads.arguments("count_day_activity")
    }
    assert windows == {
        lahore.id: (  # Friday 16 Oct in Karachi
            datetime(2026, 10, 15, 19, tzinfo=UTC),
            datetime(2026, 10, 16, 19, tzinfo=UTC),
        ),
        london.id: (  # still Thursday 15 Oct in London
            datetime(2026, 10, 14, 23, tzinfo=UTC),
            datetime(2026, 10, 15, 23, tzinfo=UTC),
        ),
    }
