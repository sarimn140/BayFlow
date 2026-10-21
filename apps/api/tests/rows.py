"""Direct ORM rows for schema-level tests (constraints, auth dependencies).

These bypass the service layer on purpose: they prove what the database itself enforces (spec 12
§3.3, INV-14, SEC-45). Feature tests use the service-based builders of spec 12 §4.3 instead.
"""

import itertools
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.bookings.models import Booking, Vehicle
from app.modules.identity.models import User
from app.modules.inventory.models import Part
from app.modules.shops.models import Shop, ShopMembership
from app.shared.enums import BookingStatus, MembershipRole

FRIDAY_1000_PKT = datetime(2026, 10, 16, 5, 0, tzinfo=UTC)

_sequence = itertools.count(1)


def _next() -> int:
    return next(_sequence)


def make_user(**overrides: object) -> User:
    n = _next()
    values: dict[str, object] = {
        "email": f"user-{n}@bayflow.test",
        "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$not-a-real-hash",
        "full_name": f"Test User {n}",
    }
    values.update(overrides)
    return User(**values)


def make_shop(**overrides: object) -> Shop:
    n = _next()
    values: dict[str, object] = {
        "name": f"Test Shop {n}",
        "slug": f"test-shop-{n}",
        "address": "1 Mall Road",
        "city": "Lahore",
        "phone": "+924200000000",
    }
    values.update(overrides)
    return Shop(**values)


def make_membership(
    shop: Shop,
    user: User,
    role: MembershipRole,
    *,
    created_by: User | None = None,
    **overrides: object,
) -> ShopMembership:
    values: dict[str, object] = {
        "shop_id": shop.id,
        "user_id": user.id,
        "role": role,
        "created_by_user_id": (created_by or user).id,
    }
    values.update(overrides)
    return ShopMembership(**values)


def make_vehicle(owner: User, **overrides: object) -> Vehicle:
    n = _next()
    values: dict[str, object] = {
        "owner_user_id": owner.id,
        "registration_number": f"LEA-{n:04d}",
        "registration_key": f"LEA{n:04d}",
        "make": "Honda",
        "model": "Civic",
        "year": 2016,
    }
    values.update(overrides)
    return Vehicle(**values)


def make_booking(shop: Shop, customer: User, vehicle: Vehicle, **overrides: object) -> Booking:
    n = _next()
    slot_start = overrides.pop("slot_start", FRIDAY_1000_PKT)
    assert isinstance(slot_start, datetime)
    values: dict[str, object] = {
        "shop_id": shop.id,
        "reference": f"BF-T{n:05d}",
        "customer_user_id": customer.id,
        "vehicle_id": vehicle.id,
        "slot_start": slot_start,
        "slot_end": slot_start + timedelta(hours=1),
        "status": BookingStatus.PENDING,
    }
    values.update(overrides)
    return Booking(**values)


def make_part(shop: Shop, **overrides: object) -> Part:
    n = _next()
    values: dict[str, object] = {
        "shop_id": shop.id,
        "sku": f"SKU-{n}",
        "name": f"Part {n}",
        "unit_cost": Decimal("900"),
    }
    values.update(overrides)
    return Part(**values)


async def add_rows(sessionmaker: async_sessionmaker[AsyncSession], *rows: object) -> None:
    """Insert rows in the order given (one flush each), then commit."""
    async with sessionmaker() as session:
        for row in rows:
            session.add(row)
            await session.flush()
        await session.commit()


def new_id() -> uuid.UUID:
    return uuid.uuid4()
