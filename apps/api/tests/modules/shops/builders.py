"""Test builders for the shops module (spec 12 §4.3): shops, teams and catalogues created through
the real service layer, acting as the shop's Owner."""

import itertools
import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Any

from app.core.database import Database
from app.modules.identity.schemas import UserRecord
from app.modules.shops import service as shops_service
from app.modules.shops.schemas import (
    MemberCreate,
    MemberUpdate,
    ServiceCreate,
    ServiceRead,
    ShopCreate,
    ShopRead,
    StaffRole,
)
from app.shared.enums import MembershipRole
from tests.modules.identity.builders import make_user, unit_of_work

_sequence = itertools.count(1)


def week(
    opens: str = "09:00", closes: str = "18:00", *, closed: Collection[int] = (6,)
) -> list[dict[str, Any]]:
    """A `WorkingHoursWrite` list: every day `opens` to `closes` except the `closed` weekdays."""
    return [
        {
            "weekday": weekday,
            "is_closed": weekday in closed,
            "opens_at": None if weekday in closed else opens,
            "closes_at": None if weekday in closed else closes,
        }
        for weekday in range(7)
    ]


MON_SAT_9_TO_18 = week()


def shop_payload(**overrides: Any) -> dict[str, Any]:
    """A valid `POST /api/v1/shops` body (Lahore Auto Care's settings, spec 11)."""
    payload: dict[str, Any] = {
        "name": f"Test Shop {next(_sequence)}",
        "address": "Plot 12, Main Boulevard, Gulberg III",
        "city": "Lahore",
        "phone": "+92 42 0000 0101",
        "slot_duration_minutes": 60,
        "slot_capacity": 2,
        "working_hours": MON_SAT_9_TO_18,
    }
    payload.update(overrides)
    return payload


@dataclass(frozen=True)
class ShopCtx:
    shop: ShopRead
    owner: UserRecord

    @property
    def id(self) -> uuid.UUID:
        return self.shop.id

    @property
    def slug(self) -> str:
        return self.shop.slug


@dataclass(frozen=True)
class Member:
    user: UserRecord
    membership_id: uuid.UUID
    role: MembershipRole

    @property
    def id(self) -> uuid.UUID:
        return self.user.id


@dataclass(frozen=True)
class Team:
    """SA, technician, parts person and two QC inspectors (spec 12 §4.3 `make_team`)."""

    advisor: Member
    technician: Member
    parts: Member
    qc: Member
    qc2: Member


async def make_shop(  # noqa: PLR0913 - the spec 12 builder's keyword options
    database: Database,
    *,
    owner: UserRecord | None = None,
    name: str | None = None,
    capacity: int = 2,
    slot_minutes: int = 60,
    hours: Sequence[dict[str, Any]] | None = None,
    timezone: str = "Asia/Karachi",
    listed: bool = True,
    city: str = "Lahore",
) -> ShopCtx:
    """A shop with its 7 working-hours rows and the owner's `OWNER` membership."""
    owner = owner or await make_user(database, full_name="Fatima Raza")
    overrides: dict[str, Any] = {
        "slot_capacity": capacity,
        "slot_duration_minutes": slot_minutes,
        "working_hours": list(hours) if hours is not None else MON_SAT_9_TO_18,
        "timezone": timezone,
        "is_listed": listed,
        "city": city,
    }
    if name is not None:
        overrides["name"] = name
    data = ShopCreate.model_validate(shop_payload(**overrides))
    async with unit_of_work(database) as uow:
        shop = await shops_service.create_shop(uow, actor_user_id=owner.id, data=data)
    return ShopCtx(shop=shop, owner=owner)


async def make_services(
    database: Database,
    ctx: ShopCtx,
    names: Sequence[str] = ("Check engine light", "Oil change"),
    *,
    active: bool = True,
) -> list[ServiceRead]:
    """Catalogue entries created by the Owner (spec 12 §4.3 `make_services`)."""
    services = []
    for name in names:
        data = ServiceCreate(
            name=name, estimated_duration_minutes=60, base_price="2000", is_active=active
        )
        async with unit_of_work(database) as uow:
            services.append(
                await shops_service.create_service(
                    uow, shop_id=ctx.id, actor_user_id=ctx.owner.id, data=data
                )
            )
    return services


async def set_member_active(
    database: Database, ctx: ShopCtx, membership_id: uuid.UUID, *, active: bool
) -> None:
    async with unit_of_work(database) as uow:
        await shops_service.update_member(
            uow,
            shop_id=ctx.id,
            actor_user_id=ctx.owner.id,
            membership_id=membership_id,
            data=MemberUpdate(is_active=active),
        )


async def add_member(
    database: Database,
    ctx: ShopCtx,
    role: MembershipRole,
    *,
    user: UserRecord | None = None,
    active: bool = True,
    full_name: str | None = None,
) -> Member:
    """A membership added by the Owner (D18); the account is created first by `make_user`."""
    user = user or await make_user(database, full_name=full_name)
    data = MemberCreate(email=user.email, full_name=user.full_name, role=StaffRole(role.value))
    async with unit_of_work(database) as uow:
        created = await shops_service.add_member(
            uow, shop_id=ctx.id, actor_user_id=ctx.owner.id, data=data
        )
    if not active:
        await set_member_active(database, ctx, created.membership_id, active=False)
    return Member(user=user, membership_id=created.membership_id, role=role)


async def make_team(database: Database, ctx: ShopCtx) -> Team:
    return Team(
        advisor=await add_member(database, ctx, MembershipRole.SERVICE_ADVISOR, full_name="Bilal"),
        technician=await add_member(database, ctx, MembershipRole.TECHNICIAN, full_name="Imran"),
        parts=await add_member(database, ctx, MembershipRole.PARTS_PERSON, full_name="Usman"),
        qc=await add_member(database, ctx, MembershipRole.QC_INSPECTOR, full_name="Sara"),
        qc2=await add_member(database, ctx, MembershipRole.QC_INSPECTOR, full_name="Hina"),
    )
