"""Seed entry point: `python -m app.scripts.seed [--force]` (D13, D51; spec 07, spec 11).

Railway's pre-deploy step runs it right after `alembic upgrade head`. It does nothing unless
`SEED_ON_DEPLOY=true` or `--force` is given (`make seed`, the start scripts). The demo data
(`app/scripts/seed_data.py`) is created through the module services, as the real demo people,
under a `SimulatedClock` set to each step's scripted time (D51, D63):

- Phase A: owners, shops, teams, services, parts and opening stock, then the general POs.
- Phase R: demo-cast reconciliation (D60): seeded accounts active with the demo password, seeded
  memberships active with their canonical role.
- Phase B: the 15 sample bookings, in CREATE-time order; an interrupted script is resumed.
- Finally the sample bookings' stale notifications are marked read.

Idempotent: every unit is keyed by its natural key and skipped when present. Reads and writes both
go through the module services, as the person who may see or do them (D51). A failed unit is
logged and the run continues; any failure makes the exit code 1, which stops the deploy (SEED-09).
"""

import argparse
import asyncio
import hashlib
import logging
import os
import sys
import uuid
from collections import Counter, defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from functools import partial
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import Database
from app.core.logging import configure_logging
from app.modules.bookings import service as bookings_service
from app.modules.bookings.schemas import (
    CUSTOMER_ACTION_REQUESTS,
    STAFF_ACTION_REQUESTS,
    BookingCreate,
    BookingDetail,
    CustomerWrite,
    VehicleWrite,
)
from app.modules.estimates.schemas import EstimateUpdate
from app.modules.identity import service as identity_service
from app.modules.identity.schemas import UserRecord
from app.modules.inventory import service as inventory_service
from app.modules.inventory.schemas import (
    PartCreate,
    PartRead,
    PurchaseOrderCreate,
    PurchaseOrderItemCreate,
    PurchaseOrderReceive,
    PurchaseOrderReceiveItem,
)
from app.modules.notifications import service as notifications_service
from app.modules.shops import service as shops_service
from app.modules.shops.schemas import (
    MemberCreate,
    MemberRead,
    MemberUpdate,
    ServiceCreate,
    ServiceRead,
    ShopCreate,
    StaffRole,
)
from app.scripts import seed_data as data
from app.shared.auth import CurrentUser, ShopContext
from app.shared.clock import SimulatedClock, SystemClock, set_clock
from app.shared.enums import BookingAction, BookingStatus, MembershipRole
from app.shared.event_bus import EventBus
from app.shared.pagination import MAX_LIMIT, PageParams
from app.shared.uow import UnitOfWork, drain_after_commit_tasks

logger = logging.getLogger("app.seed")

SHOP_TIMEZONE = ZoneInfo("Asia/Karachi")  # every seeded shop (spec 11 "Shops")
BASE_DAYS_BEFORE = 21
ALL = PageParams(limit=MAX_LIMIT)  # every seeded list (teams, catalogues, bookings) fits one page
OWNER_OF = {shop.slug: shop.owner.email for shop in data.SHOPS}
LOCK_KEY = int.from_bytes(hashlib.sha256(b"bayflow:seed").digest()[:8], "big", signed=True)
WORKED_EXAMPLE_SKUS = (
    ("FLT-OIL-01", "oil filter"),
    ("OIL-4L-01", "engine oil"),
    ("IGN-COIL-01", "ignition coil"),
)
SA_OWNS = frozenset(
    {
        BookingStatus.PENDING,
        BookingStatus.CONFIRMED,
        BookingStatus.ESTIMATE_REVIEW,
        BookingStatus.ESTIMATE_APPROVED,
        BookingStatus.ESTIMATE_REJECTED,
        BookingStatus.READY_FOR_PICKUP,
    }
)
TECHNICIAN_OWNS = frozenset(
    {BookingStatus.ASSIGNED, BookingStatus.INSPECTING, BookingStatus.IN_REPAIR}
)
PARTS_PERSON_OWNS = frozenset(
    {BookingStatus.PARTS_PENDING, BookingStatus.PARTS_ORDERED, BookingStatus.PARTS_READY}
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.scripts.seed",
        description="Load the idempotent BayFlow demo data (spec 11).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="seed even when SEED_ON_DEPLOY is not true",
    )
    return parser.parse_args(argv)


# --- Time anchors (spec 11 "Time anchors") --------------------------------------------------------


@dataclass(frozen=True)
class Calendar:
    """Resolves `At` values for one shop: `B`, `P<n>` (open days before today), `F<n>` (after)."""

    today: date
    open_weekdays: frozenset[int]

    def day(self, ref: str) -> date:
        if ref == "B":
            return self.today - timedelta(days=BASE_DAYS_BEFORE)
        direction = {"P": -1, "F": 1}[ref[0]]
        wanted, found, day = int(ref[1:]), 0, self.today
        while found < wanted:
            day += timedelta(days=direction)
            if day.weekday() in self.open_weekdays:
                found += 1
        return day

    def instant(self, when: data.At) -> datetime:
        hours, minutes = (int(part) for part in when.time.split(":"))
        local = datetime.combine(self.day(when.day), time(hours, minutes), tzinfo=SHOP_TIMEZONE)
        return local.astimezone(UTC)


def calendar_for(shop: data.ShopSeed, today: date) -> Calendar:
    return Calendar(
        today, frozenset(day for day, hours in enumerate(shop.hours) if hours is not None)
    )


def next_step_owners(
    booking: BookingDetail, sas: set[uuid.UUID], qcs: set[uuid.UUID]
) -> set[uuid.UUID]:
    """Who owns the booking's next step (spec 11 "Notifications after seeding")."""
    status = booking.status
    owners: set[uuid.UUID] = set()
    if status in SA_OWNS:
        owners = sas
    elif status in TECHNICIAN_OWNS and booking.technician is not None:
        owners = {booking.technician.user_id}
    elif status == BookingStatus.AWAITING_CUSTOMER:
        owners = {booking.customer.user_id}
    elif status in PARTS_PERSON_OWNS and booking.parts_person is not None:
        owners = {booking.parts_person.user_id}
    elif status == BookingStatus.QC_PENDING:
        owners = qcs
    elif status == BookingStatus.QC_IN_PROGRESS and booking.qc_inspector is not None:
        owners = {booking.qc_inspector.user_id}
    return owners


# --- The run --------------------------------------------------------------------------------------


@dataclass
class Report:
    created: Counter[str] = field(default_factory=Counter)
    skipped: Counter[str] = field(default_factory=Counter)
    resumed: list[str] = field(default_factory=list)
    repairs: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


class SeedError(RuntimeError):
    """A seed invariant was broken (e.g. a created shop got an unexpected slug)."""


class Seeder:
    def __init__(self, db: Database, bus: EventBus, clock: SimulatedClock, run_now: datetime):
        self.db = db
        self.bus = bus
        self.clock = clock
        self.run_now = run_now
        self.today = run_now.astimezone(SHOP_TIMEZONE).date()
        self.report = Report()
        self.calendars = {shop.slug: calendar_for(shop, self.today) for shop in data.SHOPS}
        self.finished: list[tuple[str, uuid.UUID]] = []  # (shop slug, booking id) done this run

    # --- plumbing ---

    @asynccontextmanager
    async def uow(self) -> AsyncIterator[UnitOfWork]:
        """A unit of work with the real event subscribers and no app state (no pushes or e-mail)."""
        async with self.db.sessionmaker() as session:
            yield UnitOfWork(session, self.bus)

    @asynccontextmanager
    async def read(self) -> AsyncIterator[AsyncSession]:
        async with self.db.sessionmaker() as session:
            yield session

    def at(self, shop_slug: str, when: data.At) -> None:
        self.clock.set(self.calendars[shop_slug].instant(when))

    async def unit(self, label: str, work: Callable[[], Awaitable[object]]) -> bool:
        """Run one unit; a failure is logged and recorded, and the run goes on."""
        try:
            await work()
        except Exception:
            logger.exception("seed unit failed: %s", label)
            self.report.failures.append(label)
            return False
        return True

    async def user(self, email: str) -> UserRecord | None:
        async with self.read() as session:
            return await identity_service.find_user_by_email(session, email)

    async def require_user(self, email: str) -> UserRecord:
        found = await self.user(email)
        if found is None:
            msg = f"seeded account {email} is missing"
            raise SeedError(msg)
        return found

    async def shop_id(self, slug: str) -> uuid.UUID | None:
        """The seeded shop with this slug, found among its seeded owner's shops (any listing)."""
        owner = await self.user(OWNER_OF[slug])
        if owner is None:
            return None
        async with self.read() as session:
            memberships = await shops_service.list_memberships_for_user(
                session, user_id=owner.id, roles=[MembershipRole.OWNER]
            )
            for membership in memberships:
                shop = await shops_service.get_shop(session, shop_id=membership.shop_id)
                if shop.slug == slug:
                    return shop.id
        return None

    async def require_shop(self, slug: str) -> uuid.UUID:
        shop_id = await self.shop_id(slug)
        if shop_id is None:
            msg = f"seeded shop {slug} is missing"
            raise SeedError(msg)
        return shop_id

    async def staff_context(self, shop_id: uuid.UUID, email: str) -> ShopContext:
        user = await self.require_user(email)
        async with self.read() as session:
            membership = await shops_service.get_active_membership(
                session, shop_id=shop_id, user_id=user.id
            )
        if membership is None:
            msg = f"{email} has no active membership in shop {shop_id}"
            raise SeedError(msg)
        return ShopContext(
            shop_id=shop_id,
            user=CurrentUser(id=user.id, email=user.email, full_name=user.full_name),
            membership_id=membership.id,
            role=membership.role,
        )

    async def owner_context(self, slug: str) -> ShopContext:
        return await self.staff_context(await self.require_shop(slug), OWNER_OF[slug])

    async def customer_actor(self, email: str) -> CurrentUser:
        user = await self.require_user(email)
        return CurrentUser(id=user.id, email=user.email, full_name=user.full_name)

    async def members(self, shop_id: uuid.UUID) -> list[MemberRead]:
        """Every membership of the shop, as its Owner sees them (inactive ones included)."""
        async with self.read() as session:
            page = await shops_service.list_members(
                session,
                shop_id=shop_id,
                caller_role=MembershipRole.OWNER,
                roles=None,
                is_active=None,
                page=ALL,
            )
        return page.items

    async def services(self, shop_id: uuid.UUID) -> list[ServiceRead]:
        async with self.read() as session:
            page = await shops_service.list_services(
                session, shop_id=shop_id, include_inactive=True, page=ALL
            )
        return page.items

    async def parts(self, ctx: ShopContext) -> dict[str, PartRead]:
        async with self.read() as session:
            page = await inventory_service.list_parts(
                session,
                ctx,
                q=None,
                stock_states=(),
                include_inactive=True,
                sort="sku",
                page=ALL,
            )
        return {part.sku: part for part in page.items}

    # --- Phase A: base data ---

    async def phase_a(self) -> None:
        for shop in data.SHOPS:
            await self.unit(f"shop {shop.slug}", partial(self.seed_shop, shop))
        for order in data.PURCHASE_ORDERS:
            await self.unit(f"purchase order {order.po_number}", partial(self.seed_po, order))

    async def seed_shop(self, seed: data.ShopSeed) -> None:
        self.at(seed.slug, data.at("B", "09:00"))
        owner = await self.user(seed.owner.email)
        if owner is None:
            async with self.uow() as uow:
                await identity_service.register_owner(
                    uow,
                    email=seed.owner.email,
                    full_name=seed.owner.full_name,
                    password=SecretStr(data.DEMO_PASSWORD),
                )
            owner = await self.require_user(seed.owner.email)
            self.report.created["owners"] += 1
        shop_id = await self.shop_id(seed.slug)
        if shop_id is None:
            shop_id = await self.create_shop(seed, owner)
        else:
            self.report.skipped["shops"] += 1
        await self.seed_team(seed, shop_id, owner)
        await self.seed_services(seed, shop_id, owner)
        await self.seed_parts(seed, shop_id)

    async def create_shop(self, seed: data.ShopSeed, owner: UserRecord) -> uuid.UUID:
        hours = [
            {"weekday": day, "is_closed": True}
            if slot is None
            else {"weekday": day, "is_closed": False, "opens_at": slot[0], "closes_at": slot[1]}
            for day, slot in enumerate(seed.hours)
        ]
        body = ShopCreate.model_validate(
            {
                "name": seed.name,
                "address": seed.address,
                "city": seed.city,
                "phone": seed.phone,
                "timezone": "Asia/Karachi",
                "slot_duration_minutes": 60,
                "slot_capacity": 2,
                "is_listed": True,
                "working_hours": hours,
            }
        )
        async with self.uow() as uow:
            created = await shops_service.create_shop(uow, actor_user_id=owner.id, data=body)
        if created.slug != seed.slug:
            msg = f"shop {seed.name!r} got slug {created.slug!r}, expected {seed.slug!r}"
            raise SeedError(msg)
        if seed.rating is not None:
            async with self.uow() as uow:
                await shops_service.set_rating(uow, shop_id=created.id, rating=seed.rating)
        self.report.created["shops"] += 1
        return created.id

    async def seed_team(self, seed: data.ShopSeed, shop_id: uuid.UUID, owner: UserRecord) -> None:
        member_ids = {member.user.id for member in await self.members(shop_id)}
        for member in seed.staff:
            user = await self.user(member.email)
            if user is not None and user.id in member_ids:
                self.report.skipped["memberships"] += 1
                continue
            body = MemberCreate.model_validate(
                {
                    "email": member.email,
                    "full_name": member.full_name,
                    "role": StaffRole(member.role.value),
                    "password": data.DEMO_PASSWORD,
                }
            )
            async with self.uow() as uow:
                await shops_service.add_member(
                    uow, shop_id=shop_id, actor_user_id=owner.id, data=body
                )
            self.report.created["memberships"] += 1

    async def seed_services(
        self, seed: data.ShopSeed, shop_id: uuid.UUID, owner: UserRecord
    ) -> None:
        existing = {service.name.lower() for service in await self.services(shop_id)}
        for service in data.SERVICES:
            if seed.slug not in service.prices:
                continue
            if service.name.lower() in existing:
                self.report.skipped["services"] += 1
                continue
            body = ServiceCreate(
                name=service.name,
                description=service.description,
                estimated_duration_minutes=service.duration_minutes,
                base_price=service.prices[seed.slug],
            )
            async with self.uow() as uow:
                await shops_service.create_service(
                    uow, shop_id=shop_id, actor_user_id=owner.id, data=body
                )
            self.report.created["services"] += 1

    async def seed_parts(self, seed: data.ShopSeed, shop_id: uuid.UUID) -> None:
        ctx = await self.staff_context(shop_id, seed.parts_person)
        ids = {sku: part.id for sku, part in (await self.parts(ctx)).items()}
        for part in data.PARTS:
            if part.sku in ids:
                self.report.skipped["parts"] += 1
                continue
            body = PartCreate(
                sku=part.sku,
                name=part.name,
                unit_cost=part.unit_cost,
                reorder_level=part.reorder_level,
            )
            async with self.uow() as uow:
                created = await inventory_service.create_part(uow, ctx, body)
            ids[part.sku] = created.id
            self.report.created["parts"] += 1
        self.at(seed.slug, data.at("B", "10:00"))
        for sku, quantity in seed.opening_stock.items():
            if quantity == 0:
                continue
            async with self.read() as session:
                ledger = await inventory_service.list_part_movements(
                    session, ctx, ids[sku], PageParams(limit=1)
                )
            if ledger.total:
                continue  # opening stock (or later activity) already recorded
            async with self.uow() as uow:
                await inventory_service.adjust_stock(
                    uow, ctx, part_id=ids[sku], quantity_delta=quantity, reason="Opening stock"
                )
            self.report.created["opening stock movements"] += 1

    async def seed_po(self, seed: data.PurchaseOrderSeed) -> None:
        shop_id = await self.require_shop(seed.shop_slug)
        ctx = await self.staff_context(shop_id, seed.actor)
        ids = {sku: part.id for sku, part in (await self.parts(ctx)).items()}
        async with self.read() as session:
            po_id = await inventory_service.find_purchase_order_id(
                session, shop_id=shop_id, po_number=seed.po_number
            )
        if po_id is None:
            self.at(seed.shop_slug, seed.created_at)
            body = PurchaseOrderCreate(
                supplier_name=data.SUPPLIER,
                items=[
                    PurchaseOrderItemCreate(part_id=ids[sku], quantity=quantity)
                    for sku, quantity in seed.items.items()
                ],
            )
            async with self.uow() as uow:
                created = await inventory_service.create_purchase_order(
                    uow, ctx, body, po_number=seed.po_number
                )
            po_id = created.id
            self.report.created["purchase orders"] += 1
        else:
            self.report.skipped["purchase orders"] += 1
        target: Counter[str] = Counter()
        for receipt in seed.receipts:
            target.update(receipt.quantities)
            async with self.read() as session:
                order = await inventory_service.get_purchase_order(session, ctx, po_id)
            by_sku = {item.part.sku: item for item in order.items}
            missing = [
                PurchaseOrderReceiveItem(
                    item_id=by_sku[sku].id, quantity=target[sku] - by_sku[sku].received_qty
                )
                for sku in receipt.quantities
                if by_sku[sku].received_qty < target[sku]
            ]
            if not missing:
                continue
            self.at(seed.shop_slug, receipt.at)
            async with self.uow() as uow:
                await inventory_service.receive_purchase_order(
                    uow, ctx, po_id, PurchaseOrderReceive(items=missing)
                )
            self.report.created["purchase order receipts"] += 1

    # --- Phase R: demo-cast reconciliation (D60) ---

    async def phase_r(self) -> None:
        self.clock.set(self.run_now)
        emails = {shop.owner.email for shop in data.SHOPS}
        emails |= {member.email for shop in data.SHOPS for member in shop.staff}
        emails |= {seed.email for seed in data.CUSTOMERS}
        for email in sorted(emails):
            await self.unit(f"reconcile {email}", partial(self.reconcile_user, email))
        for shop in data.SHOPS:
            await self.unit(f"reconcile team {shop.slug}", partial(self.reconcile_team, shop))

    async def reconcile_user(self, email: str) -> None:
        user = await self.user(email)
        if user is None:
            return
        async with self.read() as session:
            matches = await identity_service.password_matches(
                session, user_id=user.id, password=SecretStr(data.DEMO_PASSWORD)
            )
        if not user.is_active:
            async with self.uow() as uow:
                await identity_service.set_user_active(uow, user_id=user.id, is_active=True)
            self.report.repairs.append(f"{email}: reactivated")
        if not matches:
            async with self.uow() as uow:
                await identity_service.set_password(
                    uow, user_id=user.id, new_password=SecretStr(data.DEMO_PASSWORD)
                )
            self.report.repairs.append(f"{email}: password reset")

    async def reconcile_team(self, seed: data.ShopSeed) -> None:
        shop_id = await self.shop_id(seed.slug)
        if shop_id is None:
            return
        owner = await self.require_user(seed.owner.email)
        by_user = {member.user.id: member for member in await self.members(shop_id)}
        for canonical in seed.staff:
            user = await self.user(canonical.email)
            membership = by_user.get(user.id) if user is not None else None
            if membership is None or membership.role == MembershipRole.OWNER:
                continue
            changes: dict[str, Any] = {}
            if not membership.is_active:
                changes["is_active"] = True
            if membership.role != canonical.role:
                changes["role"] = StaffRole(canonical.role.value)
            if not changes:
                continue
            async with self.uow() as uow:
                await shops_service.update_member(
                    uow,
                    shop_id=shop_id,
                    actor_user_id=owner.id,
                    membership_id=membership.membership_id,
                    data=MemberUpdate.model_validate(changes),
                )
            self.report.repairs.append(f"{canonical.email} at {seed.slug}: {', '.join(changes)}")

    # --- Phase B: sample bookings ---

    async def phase_b(self) -> None:
        scripts = sorted(
            data.BOOKINGS,
            key=lambda script: self.calendars[script.shop_slug].instant(script.created_at),
        )
        for script in scripts:
            await self.unit(f"booking {script.reference}", partial(self.seed_booking, script))

    async def find_booking(self, script: data.BookingScript) -> uuid.UUID | None:
        """The sample booking, among its customer's own bookings (references are global)."""
        customer = await self.user(script.customer)
        if customer is None:
            return None
        actor = CurrentUser(id=customer.id, email=customer.email, full_name=customer.full_name)
        async with self.read() as session:
            page = await bookings_service.list_customer_bookings(
                session, actor, active=None, sort=None, page=ALL
            )
        return next((item.id for item in page.items if item.reference == script.reference), None)

    async def seed_booking(self, script: data.BookingScript) -> None:
        booking_id = await self.find_booking(script)
        start: int | None = 0
        if booking_id is None:
            booking_id = await self.create_sample(script)
            self.report.created["bookings"] += 1
        else:
            start = await self.resume_point(script, booking_id)
            if start is None:
                return
        for step in script.steps[start:]:
            await self.run_step(script, booking_id, step)
        self.finished.append((script.shop_slug, booking_id))

    async def resume_point(self, script: data.BookingScript, booking_id: uuid.UUID) -> int | None:
        """The index of the next step to run, or None when complete or diverged (spec 11)."""
        ctx = await self.owner_context(script.shop_slug)
        async with self.read() as session:
            events = await bookings_service.list_booking_events(session, ctx, booking_id=booking_id)
        expected = [(BookingAction.CREATE, script.customer)] + [
            (step.action or BookingAction.EDIT_ESTIMATE, step.actor)
            for step in script.steps
            if step.emits_event
        ]
        wanted = [(action, (await self.require_user(email)).id) for action, email in expected]
        actual = [
            (event.action, event.actor.user_id if event.actor is not None else None)
            for event in events
        ]
        if actual[: len(wanted)] == wanted:
            self.report.skipped["bookings"] += 1
            return None
        if len(actual) < len(wanted) and actual == wanted[: len(actual)]:
            self.report.resumed.append(script.reference)
            emitted = 1  # the CREATE event
            for index, step in enumerate(script.steps):
                if emitted == len(actual):
                    return index  # a repeated "PUT estimate" before it is harmless
                emitted += step.emits_event
            return len(script.steps)
        logger.warning("booking %s diverged from its script; skipped", script.reference)
        self.report.skipped["bookings (diverged)"] += 1
        return None

    async def create_sample(self, script: data.BookingScript) -> uuid.UUID:
        shop_id = await self.require_shop(script.shop_slug)
        services = {
            service.name: service.id
            for service in await self.services(shop_id)
            if service.is_active
        }
        vehicle = data.VEHICLES[script.plate]
        account = next(seed for seed in data.CUSTOMERS if seed.email == script.customer)
        existing = await self.user(script.customer)
        caller = None
        customer = CustomerWrite.model_validate(
            {
                "full_name": account.full_name,
                "email": account.email,
                "password": data.DEMO_PASSWORD,
                "phone": account.phone,
            }
        )
        if existing is not None:  # the wizard's logged-in path (D32)
            caller = CurrentUser(id=existing.id, email=existing.email, full_name=existing.full_name)
            customer = CustomerWrite(phone=account.phone)
        body = BookingCreate(
            shop_id=shop_id,
            service_ids=[services[name] for name in script.services],
            slot_start=self.calendars[script.shop_slug].instant(script.slot),
            customer_notes=script.notes,
            customer=customer,
            vehicle=VehicleWrite(
                registration_number=vehicle.plate,
                make=vehicle.make,
                model=vehicle.model,
                year=vehicle.year,
                color=vehicle.color,
                mileage_km=script.mileage_km,
            ),
        )
        self.at(script.shop_slug, script.created_at)
        async with self.uow() as uow:
            created = await bookings_service.create_booking(
                uow, caller=caller, data=body, reference=script.reference
            )
        return created.booking.id

    async def resolve(self, value: Any, ctx: ShopContext) -> Any:
        if isinstance(value, data.User):
            return (await self.require_user(value.email)).id
        if isinstance(value, data.Part):
            return (await self.parts(ctx))[value.sku].id
        if isinstance(value, dict):
            return {key: await self.resolve(item, ctx) for key, item in value.items()}
        if isinstance(value, list):
            return [await self.resolve(item, ctx) for item in value]
        return value

    async def run_step(
        self, script: data.BookingScript, booking_id: uuid.UUID, step: data.Step
    ) -> None:
        owner = await self.owner_context(script.shop_slug)
        payload = await self.resolve(step.payload, owner)
        self.at(script.shop_slug, step.at)
        if step.kind == "estimate":
            ctx = await self.staff_context(owner.shop_id, step.actor)
            async with self.uow() as uow:
                await bookings_service.edit_estimate(
                    uow, ctx, booking_id=booking_id, body=EstimateUpdate.model_validate(payload)
                )
            return
        action = step.action
        if action is None:
            msg = f"{script.reference}: a {step.kind} step needs an action"
            raise SeedError(msg)
        if step.kind == "customer":
            actor = await self.customer_actor(step.actor)
            if action in {BookingAction.APPROVE_ESTIMATE, BookingAction.REJECT_ESTIMATE}:
                async with self.read() as session:
                    detail = await bookings_service.get_customer_booking(
                        session, actor, booking_id=booking_id
                    )
                if detail.estimate is None:
                    msg = f"{script.reference}: no estimate to decide"
                    raise SeedError(msg)
                payload["estimate_id"] = detail.estimate.id
            request = CUSTOMER_ACTION_REQUESTS[action].model_validate(payload)
            async with self.uow() as uow:
                await bookings_service.apply_customer_action(
                    uow, actor, booking_id=booking_id, action=action, payload=request
                )
            return
        ctx = await self.staff_context(owner.shop_id, step.actor)
        request = STAFF_ACTION_REQUESTS[action].model_validate(payload)
        async with self.uow() as uow:
            await bookings_service.apply_staff_action(
                uow, ctx, booking_id=booking_id, action=action, payload=request
            )

    # --- Notifications after seeding ---

    async def mark_stale_notifications_read(self) -> None:
        """Keep unread only the latest row per (recipient, booking) of whoever owns the booking's
        next step; mark the rest read (only bookings finished in this run, spec 11)."""
        self.clock.set(self.run_now)
        to_mark: defaultdict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
        for slug, booking_id in self.finished:
            ctx = await self.owner_context(slug)
            async with self.read() as session:
                booking = await bookings_service.get_staff_booking(
                    session, ctx, booking_id=booking_id
                )
                records = await notifications_service.list_for_bookings(
                    session, shop_id=ctx.shop_id, booking_ids=[booking_id]
                )
                sas = await shops_service.list_active_member_ids(
                    session, shop_id=ctx.shop_id, roles=[MembershipRole.SERVICE_ADVISOR]
                )
                qcs = await shops_service.list_active_member_ids(
                    session, shop_id=ctx.shop_id, roles=[MembershipRole.QC_INSPECTOR]
                )
            owners = next_step_owners(booking, set(sas), set(qcs))
            latest = {record.recipient_user_id: record.id for record in records}  # oldest first
            for record in records:
                keep = (
                    record.recipient_user_id in owners
                    and latest[record.recipient_user_id] == record.id
                )
                if record.read_at is None and not keep:
                    to_mark[record.recipient_user_id].add(record.id)
        for user_id, ids in to_mark.items():
            async with self.uow() as uow:
                await notifications_service.mark_read_bulk(
                    uow, user_id=user_id, notification_ids=ids
                )

    # --- Summary ---

    async def log_summary(self) -> None:
        report = self.report
        for name in sorted(set(report.created) | set(report.skipped)):
            logger.info(
                "%s: %d created, %d skipped", name, report.created[name], report.skipped[name]
            )
        if report.resumed:
            logger.info("resumed bookings: %s", ", ".join(report.resumed))
        for repair in report.repairs:
            logger.info("repaired %s", repair)
        logger.info("sample bookings: %s", ", ".join(script.reference for script in data.BOOKINGS))
        if await self.shop_id("lahore-auto-care") is not None:
            usman = await self.staff_context(
                await self.require_shop("lahore-auto-care"), "usman.parts@bayflow.test"
            )
            parts = await self.parts(usman)
            stock = ", ".join(
                f"{label} {parts[sku].on_hand}/{parts[sku].reserved}"
                for sku, label in WORKED_EXAMPLE_SKUS
                if sku in parts
            )
            logger.info("Lahore Auto Care worked-example stock: %s", stock)
        if report.failures:
            logger.error(
                "seed finished with %d failed unit(s): %s",
                len(report.failures),
                "; ".join(report.failures),
            )


async def seed(db: Database, *, now: datetime | None = None) -> int:
    """Run phases A, R and B against `db`; returns the process exit code.

    `now` is the run's real time, read once (D63); tests pass a fixed instant.
    """
    from app.main import create_app  # noqa: PLC0415 - the app wiring, built only when seeding

    bus: EventBus = create_app(get_settings(), database=db).state.event_bus
    async with db.engine.connect() as lock_connection:
        locked = await lock_connection.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY}
        )
        if not locked:
            logger.info("another seed is running; nothing to do")
            return 0
        run_now = now or SystemClock().now()
        clock = SimulatedClock(run_now)
        previous = set_clock(clock)
        seeder = Seeder(db, bus, clock, run_now)
        try:
            await seeder.phase_a()
            await seeder.phase_r()
            await seeder.phase_b()
            await seeder.unit("notifications", seeder.mark_stale_notifications_read)
            await drain_after_commit_tasks()
            await seeder.log_summary()
        finally:
            set_clock(previous)
            await lock_connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY}
            )
    return 1 if seeder.report.failures else 0


def run(*, force: bool) -> int:
    """Run the seed if enabled; returns the process exit code."""
    if not (force or get_settings().seed_on_deploy):
        logger.info("seed skipped (SEED_ON_DEPLOY is not true)")
        return 0
    os.environ["EMAIL_PROVIDER"] = "none"  # quiet: no e-mails while seeding (D26)
    get_settings.cache_clear()

    async def _main() -> int:
        db = Database.from_settings(get_settings())
        try:
            return await seed(db)
        finally:
            await db.dispose()

    return asyncio.run(_main())


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        configure_logging(get_settings().log_level)
        return run(force=args.force)
    except Exception:
        logger.exception("seed failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
