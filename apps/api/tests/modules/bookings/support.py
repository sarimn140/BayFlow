"""Builders and helpers for the bookings tests (spec 12 §4.3).

Everything goes through the real service layer or the HTTP API with real actors (never raw SQL),
so every booking the tests build is reachable and consistent:

- `World`: Lahore Auto Care (shop A) with the brief's cast — Fatima (Owner), Bilal (SA), Imran and
  Hamza (technicians), Usman and Kashif (parts persons), Sara and Hina (QC inspectors) — its
  services and the worked-example parts (oil filter and engine oil in stock, ignition coil at 0),
  plus a second tenant (shop B) with its own Owner and SA.
- `Desk`: the API as each actor uses it: the wizard, staff and customer action routes, the
  estimate editor, purchase-order receipts, reads.
- `drive_booking_to`: a booking in any of the 17 statuses, reached by performing the real
  actions of spec 12 §4.3's canonical paths.
"""

import itertools
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select, text

from app.core.database import Database
from app.core.security import decode_token
from app.modules.bookings.models import Booking, BookingEvent
from app.modules.identity.schemas import UserRecord
from app.modules.inventory import service as inventory_service
from app.modules.inventory.schemas import PartCreate
from app.modules.shops.schemas import ServiceRead
from app.shared.auth import CurrentUser, ShopContext
from app.shared.clock import utcnow
from app.shared.enums import BookingStatus, MembershipRole, QcChecklistKey
from tests.assertions import assert_problem
from tests.modules.identity.builders import (
    TEST_PASSWORD,
    bearer,
    make_user,
    unique_email,
    unit_of_work,
)
from tests.modules.shops.builders import Member, ShopCtx, add_member, make_services, make_shop

FRIDAY_1000 = datetime(2026, 10, 16, 5, 0, tzinfo=UTC)
"""Friday 16 Oct 2026, 10:00 in Karachi: the worked example's slot (glossary §9)."""

THURSDAY_0900 = datetime(2026, 10, 15, 4, 0, tzinfo=UTC)
"""Thursday 15 Oct 2026, 09:00 in Karachi: the first slot of the day after the test clock."""

CHECKLIST_KEYS = [key.value for key in QcChecklistKey]


def full_checklist(*, failed: Sequence[str] = ()) -> list[dict[str, Any]]:
    """The D46 checklist, every key once; `failed` keys are not passed."""
    unknown = set(failed) - set(CHECKLIST_KEYS)
    assert not unknown, f"not checklist keys: {unknown}"
    return [{"key": key, "passed": key not in failed} for key in CHECKLIST_KEYS]


_slot_numbers = itertools.count()
_client_numbers = itertools.count(1)


def next_client_ip() -> str:
    """A distinct documentation address (RFC 3849, `2001:db8::/32`) per anonymous wizard call."""
    return f"2001:db8::{next(_client_numbers):x}"


def next_slot() -> datetime:
    """A distinct future slot on the 60-minute grid (Thu-Sat 09:00-17:00 local, then the next
    weeks), so tests that book many cars never fill one slot by accident."""
    number = next(_slot_numbers) % (9 * 3 * 4)
    week, rest = divmod(number, 27)
    day, hour = divmod(rest, 9)
    return THURSDAY_0900 + timedelta(weeks=week, days=day, hours=hour)


# --- The world ------------------------------------------------------------------------------------


@dataclass
class Parts:
    coil: dict[str, Any]
    oil_filter: dict[str, Any]
    engine_oil: dict[str, Any]

    @property
    def ids(self) -> list[str]:
        return [self.coil["id"], self.oil_filter["id"], self.engine_oil["id"]]


@dataclass
class World:
    db: Database
    shop: ShopCtx
    advisor: Member
    technician: Member
    technician2: Member
    parts: Member
    parts2: Member
    qc: Member
    qc2: Member
    services: list[ServiceRead]
    catalogue: Parts
    other: ShopCtx
    other_advisor: Member
    other_services: list[ServiceRead]

    @property
    def shop_id(self) -> uuid.UUID:
        return self.shop.id

    @property
    def owner(self) -> UserRecord:
        return self.shop.owner


def context(world: World, member: Member) -> ShopContext:
    """The `ShopContext` the route dependency would build for `member` in shop A."""
    user = member.user
    return ShopContext(
        shop_id=world.shop_id,
        user=CurrentUser(id=user.id, email=user.email, full_name=user.full_name),
        membership_id=member.membership_id,
        role=member.role,
    )


async def _part(
    db: Database, ctx: ShopContext, sku: str, name: str, cost: str, stock: int
) -> dict[str, Any]:
    async with unit_of_work(db) as uow:
        part = await inventory_service.create_part(
            uow, ctx, PartCreate(sku=sku, name=name, unit_cost=cost, reorder_level=2)
        )
    if stock:
        async with unit_of_work(db) as uow:
            await inventory_service.adjust_stock(
                uow, ctx, part_id=part.id, quantity_delta=stock, reason="Opening stock"
            )
    return {"id": str(part.id), "sku": part.sku, "name": part.name}


async def build_world(
    db: Database,
    *,
    capacity: int = 50,
    filters: int = 100,
    oil: int = 100,
    coils: int = 0,
) -> World:
    """Lahore Auto Care and a second tenant, through the real services (spec 12 §4.3)."""
    owner = await make_user(db, full_name="Fatima Raza")
    shop = await make_shop(db, owner=owner, name="Lahore Auto Care", capacity=capacity)
    advisor = await add_member(db, shop, MembershipRole.SERVICE_ADVISOR, full_name="Bilal")
    technician = await add_member(db, shop, MembershipRole.TECHNICIAN, full_name="Imran")
    technician2 = await add_member(db, shop, MembershipRole.TECHNICIAN, full_name="Hamza")
    parts = await add_member(db, shop, MembershipRole.PARTS_PERSON, full_name="Usman")
    parts2 = await add_member(db, shop, MembershipRole.PARTS_PERSON, full_name="Kashif")
    qc = await add_member(db, shop, MembershipRole.QC_INSPECTOR, full_name="Sara")
    qc2 = await add_member(db, shop, MembershipRole.QC_INSPECTOR, full_name="Hina")
    services = await make_services(
        db, shop, ("Check engine light", "Oil change", "Wheel alignment")
    )
    other_owner = await make_user(db, full_name="Asif Memon")
    other = await make_shop(db, owner=other_owner, name="Clifton Car Clinic", city="Karachi")
    other_advisor = await add_member(db, other, MembershipRole.SERVICE_ADVISOR, full_name="Kamran")
    other_services = await make_services(db, other, ("Brake check",))
    world = World(
        db=db,
        shop=shop,
        advisor=advisor,
        technician=technician,
        technician2=technician2,
        parts=parts,
        parts2=parts2,
        qc=qc,
        qc2=qc2,
        services=services,
        catalogue=Parts({}, {}, {}),
        other=other,
        other_advisor=other_advisor,
        other_services=other_services,
    )
    stocker = context(world, parts)
    world.catalogue = Parts(
        coil=await _part(db, stocker, "IGN-COIL-01", "Ignition coil", "6500", coils),
        oil_filter=await _part(db, stocker, "OIL-FILTER-01", "Oil filter", "900", filters),
        engine_oil=await _part(db, stocker, "ENGINE-OIL-4L", "Engine oil 4 L", "5200", oil),
    )
    return world


def worked_lines(world: World, *, labour: str = "4000") -> list[dict[str, Any]]:
    """The worked example's estimate: coil 6,500 + filter 900 + oil 5,200 + labour."""
    parts = world.catalogue
    return [
        {"line_type": "PART", "part_id": parts.coil["id"], "quantity": "1"},
        {"line_type": "PART", "part_id": parts.oil_filter["id"], "quantity": "1"},
        {"line_type": "PART", "part_id": parts.engine_oil["id"], "quantity": "1"},
        {
            "line_type": "LABOUR",
            "description": "Diagnosis and repair labour",
            "quantity": "1",
            "unit_price": labour,
        },
    ]


def labour_lines(price: str = "2000") -> list[dict[str, Any]]:
    return [
        {
            "line_type": "LABOUR",
            "description": "Four-wheel alignment",
            "quantity": "1",
            "unit_price": price,
        }
    ]


def vehicle(registration: str = "LEA-1234", **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "registration_number": registration,
        "make": "Honda",
        "model": "Civic",
        "year": 2016,
    }
    body.update(overrides)
    return body


# --- The API as each actor uses it ----------------------------------------------------------------


@dataclass
class Customer:
    user_id: uuid.UUID
    email: str
    full_name: str
    password: str = TEST_PASSWORD

    @property
    def headers(self) -> dict[str, str]:
        return bearer(self.user_id)


@dataclass
class Journey:
    """A booking driven through the real actions, and what the steps produced."""

    booking: dict[str, Any]
    customer: Customer
    estimate_ids: list[str] = field(default_factory=list)
    purchase_order_id: str | None = None
    labour_only: bool = False

    @property
    def id(self) -> str:
        return str(self.booking["id"])

    @property
    def reference(self) -> str:
        return str(self.booking["reference"])


class Desk:
    """HTTP calls of the bookings API, asserting the expected status."""

    def __init__(self, api: httpx.AsyncClient, world: World) -> None:
        self.api = api
        self.world = world

    # paths
    def shop_path(self, path: str = "", *, shop_id: uuid.UUID | None = None) -> str:
        return f"/api/v1/shops/{shop_id or self.world.shop_id}{path}"

    def booking_path(self, booking_id: str, path: str = "", **kw: Any) -> str:
        return self.shop_path(f"/bookings/{booking_id}{path}", **kw)

    @staticmethod
    def my_path(booking_id: str, path: str = "") -> str:
        return f"/api/v1/me/bookings/{booking_id}{path}"

    # the wizard
    def booking_body(
        self,
        *,
        slot: datetime | None = None,
        services: Sequence[ServiceRead] | None = None,
        registration: str = "LEA-1234",
        shop_id: uuid.UUID | None = None,
        **overrides: Any,
    ) -> dict[str, Any]:
        chosen = services if services is not None else self.world.services[:2]
        body: dict[str, Any] = {
            "shop_id": str(shop_id or self.world.shop_id),
            "service_ids": [str(service.id) for service in chosen],
            "slot_start": (slot or next_slot()).isoformat().replace("+00:00", "Z"),
            "vehicle": vehicle(registration),
        }
        body.update(overrides)
        return body

    async def wizard(
        self, body: dict[str, Any], *, headers: dict[str, str] | None = None
    ) -> httpx.Response:
        """`POST /api/v1/bookings`. The client's cookie jar is emptied afterwards: the 201 sets
        `bf_session` (D32), and a cookie left in the jar would turn the test's next anonymous
        wizard call into a booking for this customer (every other call sends a Bearer header)."""
        try:
            return await self.api.post("/api/v1/bookings", json=body, headers=headers or {})
        finally:
            self.api.cookies.clear()

    async def book(
        self,
        customer: Customer | None = None,
        *,
        full_name: str = "Ahmed",
        **body_options: Any,
    ) -> Journey:
        """A `PENDING` booking: a new account through the wizard (case B), or `customer`'s
        session (case A)."""
        body = self.booking_body(**body_options)
        if customer is None:
            email = unique_email("ahmed")
            body["customer"] = {
                "full_name": full_name,
                "email": email,
                "password": TEST_PASSWORD,
            }
            self.api.cookies.clear()  # anonymous: no session from an earlier call (D32 case B)
            # Each new customer books from their own address, so a test that books many cars
            # never meets the per-IP wizard limit (D69; BK-32 tests that limit on its own).
            response = await self.wizard(body, headers={"X-Real-IP": next_client_ip()})
            assert response.status_code == 201, response.text
            created = response.json()
            user_id = decode_token(created["access_token"], utcnow(), "session")
            customer = Customer(user_id=user_id, email=email, full_name=full_name)
            return Journey(booking=created["booking"], customer=customer)
        response = await self.wizard(body, headers=customer.headers)
        assert response.status_code == 201, response.text
        return Journey(booking=response.json()["booking"], customer=customer)

    # staff
    async def act(
        self,
        member: Member | UserRecord,
        booking_id: str,
        slug: str,
        body: dict[str, Any] | None = None,
        *,
        expect: int = 200,
        shop_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        user_id = member.user.id if isinstance(member, Member) else member.id
        response = await self.api.post(
            self.booking_path(booking_id, f"/actions/{slug}", shop_id=shop_id),
            json=body if body is not None else {},
            headers=bearer(user_id),
        )
        assert response.status_code == expect, (slug, response.status_code, response.text)
        result: dict[str, Any] = response.json()
        return result

    async def act_raw(
        self,
        user_id: uuid.UUID,
        booking_id: str,
        slug: str,
        body: dict[str, Any] | None = None,
        *,
        shop_id: uuid.UUID | None = None,
    ) -> httpx.Response:
        return await self.api.post(
            self.booking_path(booking_id, f"/actions/{slug}", shop_id=shop_id),
            json=body if body is not None else {},
            headers=bearer(user_id),
        )

    async def my_act(
        self,
        customer: Customer,
        booking_id: str,
        slug: str,
        body: dict[str, Any] | None = None,
        *,
        expect: int = 200,
    ) -> dict[str, Any]:
        response = await self.api.post(
            self.my_path(booking_id, f"/actions/{slug}"),
            json=body if body is not None else {},
            headers=customer.headers,
        )
        assert response.status_code == expect, (slug, response.status_code, response.text)
        result: dict[str, Any] = response.json()
        return result

    async def edit(
        self,
        member: Member | UserRecord,
        booking_id: str,
        lines: list[dict[str, Any]],
        *,
        expect: int = 200,
        **extra: Any,
    ) -> dict[str, Any]:
        user_id = member.user.id if isinstance(member, Member) else member.id
        response = await self.api.put(
            self.booking_path(booking_id, "/estimate"),
            json={"lines": lines, **extra},
            headers=bearer(user_id),
        )
        assert response.status_code == expect, response.text
        result: dict[str, Any] = response.json()
        return result

    async def get(self, user_id: uuid.UUID, path: str, *, expect: int = 200, **params: Any) -> Any:
        response = await self.api.get(path, headers=bearer(user_id), params=params)
        assert response.status_code == expect, (path, response.status_code, response.text)
        return response.json()

    async def detail(self, member: Member | UserRecord, booking_id: str) -> dict[str, Any]:
        user_id = member.user.id if isinstance(member, Member) else member.id
        result: dict[str, Any] = await self.get(user_id, self.booking_path(booking_id))
        return result

    async def my_detail(self, customer: Customer, booking_id: str) -> dict[str, Any]:
        result: dict[str, Any] = await self.get(customer.user_id, self.my_path(booking_id))
        return result

    # purchase orders
    async def receive(
        self,
        purchase_order_id: str,
        quantities: dict[str, int] | None = None,
        *,
        by: Member | None = None,
        expect: int = 200,
    ) -> dict[str, Any]:
        """Receive a purchase order as a Parts Person: `quantities` per part id, else everything
        outstanding."""
        receiver = by or self.world.parts
        order = await self.get(
            receiver.user.id, self.shop_path(f"/purchase-orders/{purchase_order_id}")
        )
        items = []
        for item in order["items"]:
            quantity = (
                item["outstanding_qty"]
                if quantities is None
                else quantities.get(item["part"]["id"], 0)
            )
            items.append({"item_id": item["id"], "quantity": quantity})
        response = await self.api.post(
            self.shop_path(f"/purchase-orders/{purchase_order_id}/receive"),
            json={"items": items},
            headers=bearer(receiver.user.id),
        )
        assert response.status_code == expect, response.text
        result: dict[str, Any] = response.json()
        return result

    async def balance(self, part: dict[str, Any]) -> tuple[int, int]:
        """`(on_hand, reserved)` of a part, as the Parts Person sees it."""
        listing = await self.get(self.world.parts.user.id, self.shop_path("/parts"), q=part["sku"])
        (row,) = [item for item in listing["items"] if item["id"] == part["id"]]
        return int(row["on_hand"]), int(row["reserved"])


# --- drive_booking_to (spec 12 §4.3) --------------------------------------------------------------


async def _decline(desk: Desk, journey: Journey) -> None:
    body = {"reason": "Both bays are booked that morning."}
    journey.booking = await desk.act(desk.world.advisor, journey.id, "decline", body)


async def _confirm(desk: Desk, journey: Journey) -> None:
    journey.booking = await desk.act(desk.world.advisor, journey.id, "confirm")


async def _assign_technician(desk: Desk, journey: Journey) -> None:
    body = {"technician_user_id": str(desk.world.technician.id)}
    journey.booking = await desk.act(desk.world.advisor, journey.id, "assign-technician", body)


async def _start_inspection(desk: Desk, journey: Journey) -> None:
    journey.booking = await desk.act(desk.world.technician, journey.id, "start-inspection")


async def _estimate_and_submit(desk: Desk, journey: Journey) -> None:
    lines = labour_lines() if journey.labour_only else worked_lines(desk.world)
    edit = await desk.edit(desk.world.technician, journey.id, lines)
    journey.estimate_ids.append(edit["id"])
    journey.booking = await desk.act(desk.world.technician, journey.id, "submit-estimate")


async def _send_estimate(desk: Desk, journey: Journey) -> None:
    journey.booking = await desk.act(desk.world.advisor, journey.id, "send-estimate")


async def _decide(desk: Desk, journey: Journey, slug: str) -> None:
    estimate_id = journey.booking["estimate_summary"]["estimate_id"]
    await desk.my_act(journey.customer, journey.id, slug, {"estimate_id": estimate_id})
    journey.booking = await desk.detail(desk.world.advisor, journey.id)


async def _approve(desk: Desk, journey: Journey) -> None:
    await _decide(desk, journey, "approve-estimate")


async def _reject(desk: Desk, journey: Journey) -> None:
    await _decide(desk, journey, "reject-estimate")


async def _assign_parts_person(desk: Desk, journey: Journey) -> None:
    body = {"parts_person_user_id": str(desk.world.parts.id)}
    journey.booking = await desk.act(desk.world.advisor, journey.id, "assign-parts-person", body)


async def _order_parts(desk: Desk, journey: Journey) -> None:
    journey.booking = await desk.act(desk.world.parts, journey.id, "order-parts")
    journey.purchase_order_id = journey.booking["last_event"]["metadata"]["purchase_order_id"]


async def _parts_ready(desk: Desk, journey: Journey) -> None:
    if journey.purchase_order_id is None:  # labour-only, or stock already there
        journey.booking = await desk.act(desk.world.parts, journey.id, "mark-parts-ready")
        return
    await desk.receive(journey.purchase_order_id)  # RECEIVE_PARTS fires on the full receipt
    journey.booking = await desk.detail(desk.world.parts, journey.id)


async def _allocate(desk: Desk, journey: Journey) -> None:
    journey.booking = await desk.act(desk.world.parts, journey.id, "allocate-parts")


async def _send_to_qc(desk: Desk, journey: Journey) -> None:
    journey.booking = await desk.act(desk.world.technician, journey.id, "send-to-qc")


async def _pick_qc(desk: Desk, journey: Journey) -> None:
    journey.booking = await desk.act(desk.world.qc, journey.id, "pick-qc")


async def _pass_qc(desk: Desk, journey: Journey) -> None:
    body = {"checklist": full_checklist()}
    journey.booking = await desk.act(desk.world.qc, journey.id, "pass-qc", body)


async def _complete(desk: Desk, journey: Journey) -> None:
    journey.booking = await desk.act(desk.world.advisor, journey.id, "complete")


type Step = Callable[[Desk, Journey], Awaitable[None]]

CANONICAL_PATH: tuple[tuple[BookingStatus, Step], ...] = (
    (BookingStatus.CONFIRMED, _confirm),
    (BookingStatus.ASSIGNED, _assign_technician),
    (BookingStatus.INSPECTING, _start_inspection),
    (BookingStatus.ESTIMATE_REVIEW, _estimate_and_submit),
    (BookingStatus.AWAITING_CUSTOMER, _send_estimate),
    (BookingStatus.ESTIMATE_APPROVED, _approve),
    (BookingStatus.PARTS_PENDING, _assign_parts_person),
    (BookingStatus.PARTS_ORDERED, _order_parts),
    (BookingStatus.PARTS_READY, _parts_ready),
    (BookingStatus.IN_REPAIR, _allocate),
    (BookingStatus.QC_PENDING, _send_to_qc),
    (BookingStatus.QC_IN_PROGRESS, _pick_qc),
    (BookingStatus.READY_FOR_PICKUP, _pass_qc),
    (BookingStatus.COMPLETED, _complete),
)
"""Spec 12 §4.3's canonical path from `PENDING`; each step is one or two real actions."""


def path_to(target: BookingStatus, *, labour_only: bool = False) -> list[Step]:
    """The steps from `PENDING` to `target`. `CANCELLED` = declined while `PENDING`;
    `ESTIMATE_REJECTED` = rejected while `AWAITING_CUSTOMER`; labour-only skips `order-parts`."""
    if target == BookingStatus.PENDING:
        return []
    if target == BookingStatus.CANCELLED:
        return [_decline]
    if target == BookingStatus.ESTIMATE_REJECTED:
        return [*path_to(BookingStatus.AWAITING_CUSTOMER), _reject]
    if labour_only and target == BookingStatus.PARTS_ORDERED:
        msg = "a labour-only job has nothing to order"
        raise ValueError(msg)
    steps: list[Step] = []
    for status, step in CANONICAL_PATH:
        if not (labour_only and status == BookingStatus.PARTS_ORDERED):
            steps.append(step)
        if status == target:
            return steps
    msg = f"no canonical path to {target}"
    raise ValueError(msg)


async def drive_booking_to(
    desk: Desk,
    target: BookingStatus,
    *,
    labour_only: bool = False,
    customer: Customer | None = None,
    **book_options: Any,
) -> Journey:
    """A booking in `target`, reached by the real actions of spec 12 §4.3."""
    journey = await desk.book(customer, **book_options)
    journey.labour_only = labour_only
    for step in path_to(target, labour_only=labour_only):
        await step(desk, journey)
    assert journey.booking["status"] == target, (target, journey.booking["status"])
    return journey


# --- Database checks (read-only) ------------------------------------------------------------------


async def booking_row(db: Database, booking_id: str | uuid.UUID) -> Booking:
    async with db.sessionmaker() as session:
        booking = await session.get(Booking, uuid.UUID(str(booking_id)))
        assert booking is not None
        return booking


async def events_of(db: Database, booking_id: str | uuid.UUID) -> list[BookingEvent]:
    async with db.sessionmaker() as session:
        statement = (
            select(BookingEvent)
            .where(BookingEvent.booking_id == uuid.UUID(str(booking_id)))
            .order_by(BookingEvent.created_at, BookingEvent.seq)
        )
        return list((await session.execute(statement)).scalars())


async def count_rows(db: Database, table: str) -> int:
    async with db.sessionmaker() as session:
        return int((await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one())  # noqa: S608


async def slot_count(db: Database, shop_id: uuid.UUID, slot_start: datetime) -> int | None:
    async with db.sessionmaker() as session:
        value = (
            await session.execute(
                text(
                    "SELECT booked_count FROM slot_counters"
                    " WHERE shop_id = :shop_id AND slot_start = :slot_start"
                ),
                {"shop_id": shop_id, "slot_start": slot_start},
            )
        ).scalar_one_or_none()
    return None if value is None else int(value)


async def estimate_statuses(db: Database, booking_id: str) -> list[tuple[int, str]]:
    async with db.sessionmaker() as session:
        rows = await session.execute(
            text("SELECT version, status FROM estimates WHERE booking_id = :b ORDER BY version"),
            {"b": uuid.UUID(booking_id)},
        )
        return [(int(row[0]), str(row[1])) for row in rows]


def problem(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    return assert_problem(response, status, code)


def field_codes(body: dict[str, Any]) -> list[tuple[str, str]]:
    return [(error["field"], error["code"]) for error in body.get("errors", [])]


async def new_customer(db: Database, *, full_name: str = "Ayesha Khan", **kw: Any) -> Customer:
    """A customer account created through identity (no booking yet)."""
    user = await make_user(db, full_name=full_name, **kw)
    return Customer(user_id=user.id, email=user.email, full_name=user.full_name)
