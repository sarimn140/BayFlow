"""`shops.service` look-ups other modules and the seed call (`modules/shops.md` §5.2, §7.10).

Covers the shops halves of BK-21 (`require_eligible_member`), BK-06 (`snapshot_services`), D26
(`list_active_member_ids`, `get_owner_user_id`), D19 (`get_member_refs`), the reporting reads
(`list_team`, `get_setup_flags`, `list_memberships_for_user`), `get_schedule_config` (D37),
`get_shop_briefs`, `get_shop_profile` and the seed's `set_rating` (D56).
"""

import asyncio
import uuid
from datetime import time
from decimal import Decimal

import pytest

from app.core.database import Database
from app.core.errors import MemberNotEligible, NotFound, ValidationFailed
from app.modules.shops import service as shops_service
from app.modules.shops.schemas import MemberRef, ServiceSnapshot, ShopUpdate
from app.shared.enums import MembershipRole
from tests.lockgate import wait_for_lock_waiters
from tests.modules.identity.builders import make_user, unit_of_work
from tests.modules.shops.builders import (
    add_member,
    make_services,
    make_shop,
    make_team,
    set_member_active,
    week,
)

pytestmark = pytest.mark.db


async def test_get_active_membership_and_memberships_for_user(db: Database) -> None:
    worker = await make_user(db)
    alpha = await make_shop(db, name="Alpha Garage")
    beta = await make_shop(db, name="beta Motors")
    owned = await make_shop(db, owner=worker, name="Worker Motors")
    tech = await add_member(db, alpha, MembershipRole.TECHNICIAN, user=worker)
    qc = await add_member(db, beta, MembershipRole.QC_INSPECTOR, user=worker)
    await set_member_active(db, beta, qc.membership_id, active=False)
    async with db.sessionmaker() as session:
        record = await shops_service.get_active_membership(
            session, shop_id=alpha.id, user_id=worker.id
        )
        assert record is not None
        assert (record.id, record.role, record.is_active) == (
            tech.membership_id,
            MembershipRole.TECHNICIAN,
            True,
        )
        assert (
            await shops_service.get_active_membership(session, shop_id=beta.id, user_id=worker.id)
            is None
        )
        mine = await shops_service.list_memberships_for_user(session, user_id=worker.id)
        assert [m.shop_id for m in mine] == [alpha.id, owned.id]  # by shop name, active only
        owners = await shops_service.list_memberships_for_user(
            session, user_id=worker.id, roles={MembershipRole.OWNER}
        )
        assert [m.shop_id for m in owners] == [owned.id]


async def test_shop_briefs_listed_and_bookable_shops(db: Database) -> None:
    listed = await make_shop(db, name="Listed Garage", city="Multan")
    hidden = await make_shop(db, name="Hidden Garage", listed=False)
    await make_services(db, listed)
    await make_services(db, hidden)
    async with db.sessionmaker() as session:
        briefs = await shops_service.get_shop_briefs(
            session, shop_ids=[listed.id, hidden.id, uuid.uuid4()]
        )
        assert set(briefs) == {listed.id, hidden.id}
        brief = briefs[listed.id]
        assert (brief.slug, brief.name, brief.city, brief.timezone, brief.is_listed) == (
            "listed-garage",
            "Listed Garage",
            "Multan",
            "Asia/Karachi",
            True,
        )
        assert brief.phone == "+924200000101"
        assert briefs[hidden.id].is_listed is False
        assert await shops_service.get_shop_briefs(session, shop_ids=[]) == {}
        listed_brief = await shops_service.get_listed_shop(session, shop_slug="listed-garage")
        assert listed_brief == brief
        assert await shops_service.get_listed_shop(session, shop_slug=hidden.slug) is None
        assert await shops_service.get_bookable_shop(session, shop_id=listed.id) == brief
        assert await shops_service.get_bookable_shop(session, shop_id=hidden.id) is None
        assert await shops_service.get_bookable_shop(session, shop_id=uuid.uuid4()) is None


async def test_get_schedule_config(db: Database) -> None:
    hours = week("09:00", "18:00")
    hours[5] = {"weekday": 5, "is_closed": False, "opens_at": "10:00", "closes_at": "14:00"}
    ctx = await make_shop(db, capacity=3, slot_minutes=30, hours=hours, timezone="Asia/Dubai")
    async with db.sessionmaker() as session:
        for for_share in (False, True):
            config = await shops_service.get_schedule_config(
                session, shop_id=ctx.id, for_share=for_share
            )
            assert (config.shop_id, config.timezone) == (ctx.id, "Asia/Dubai")
            assert (config.slot_duration_minutes, config.slot_capacity) == (30, 3)
            assert len(config.days) == 7
            assert (config.day(5).opens_at, config.day(5).closes_at) == (time(10), time(14))
            assert config.day(6).is_closed
        await session.rollback()
        with pytest.raises(NotFound):
            await shops_service.get_schedule_config(session, shop_id=uuid.uuid4())


async def test_get_schedule_config_for_share_blocks_only_grid_changes(db: Database) -> None:
    """D37: `for_share=True` is booking creation's first lock. Two share readers never wait for
    each other; a writer that locks the shop row `FOR UPDATE` (`update_shop`) waits for both; a
    plain read locks nothing."""
    ctx = await make_shop(db)

    async def change_the_shop() -> None:
        async with unit_of_work(db) as uow:
            await shops_service.update_shop(
                uow, shop_id=ctx.id, actor_user_id=ctx.owner.id, data=ShopUpdate(slot_capacity=3)
            )

    async with db.sessionmaker() as first, db.sessionmaker() as second:
        await shops_service.get_schedule_config(first, shop_id=ctx.id, for_share=True)
        await asyncio.wait_for(  # not blocked by the first share lock
            shops_service.get_schedule_config(second, shop_id=ctx.id, for_share=True), timeout=2
        )
        writer = asyncio.create_task(change_the_shop())
        await wait_for_lock_waiters(db, 1)  # the FOR UPDATE writer queues behind the readers
        assert not writer.done()
        await first.rollback()
        await wait_for_lock_waiters(db, 1)  # still behind the second reader
        assert not writer.done()
        await second.rollback()
    await asyncio.wait_for(writer, timeout=5)

    async with db.sessionmaker() as reader:
        await shops_service.get_schedule_config(reader, shop_id=ctx.id)  # unlocked read
        await asyncio.wait_for(change_the_shop(), timeout=5)  # the writer does not wait
        await reader.rollback()


async def test_snapshot_services_reports_every_bad_id_in_request_order(db: Database) -> None:
    ctx = await make_shop(db)
    other = await make_shop(db)
    oil, brakes, retired = await make_services(db, ctx, ["Oil change", "Brakes", "Retired"])
    async with unit_of_work(db) as uow:
        from app.modules.shops.schemas import ServiceUpdate  # noqa: PLC0415

        await shops_service.update_service(
            uow,
            shop_id=ctx.id,
            actor_user_id=ctx.owner.id,
            service_id=retired.id,
            data=ServiceUpdate(is_active=False),
        )
    (theirs,) = await make_services(db, other, ["Theirs"])
    async with db.sessionmaker() as session:
        snapshots = await shops_service.snapshot_services(
            session, shop_id=ctx.id, service_ids=[brakes.id, oil.id]
        )
        assert snapshots == [
            ServiceSnapshot(service_id=brakes.id, name="Brakes", base_price=Decimal("2000.00")),
            ServiceSnapshot(service_id=oil.id, name="Oil change", base_price=Decimal("2000.00")),
        ]
        with pytest.raises(ValidationFailed) as caught:
            await shops_service.snapshot_services(
                session,
                shop_id=ctx.id,
                service_ids=[oil.id, retired.id, theirs.id, uuid.uuid4()],
            )
    assert [(e["field"], e["code"]) for e in caught.value.errors or []] == [
        ("service_ids.1", "invalid_reference"),
        ("service_ids.2", "invalid_reference"),
        ("service_ids.3", "invalid_reference"),
    ]


async def test_bk21_require_eligible_member(db: Database) -> None:
    ctx = await make_shop(db)
    other = await make_shop(db)
    team = await make_team(db, ctx)
    inactive = await add_member(db, ctx, MembershipRole.TECHNICIAN, active=False)
    disabled_account = await make_user(db, active=False)
    await add_member(db, ctx, MembershipRole.TECHNICIAN, user=disabled_account)
    elsewhere = await add_member(db, other, MembershipRole.TECHNICIAN)
    async with db.sessionmaker() as session:
        ref = await shops_service.require_eligible_member(
            session,
            shop_id=ctx.id,
            user_id=team.technician.id,
            role=MembershipRole.TECHNICIAN,
            field="technician_user_id",
        )
        assert ref == MemberRef(user_id=team.technician.id, full_name="Imran", is_active=True)
        for user_id in (
            team.parts.id,  # wrong role
            inactive.id,  # inactive membership
            disabled_account.id,  # inactive account
            elsewhere.id,  # another shop's technician
            uuid.uuid4(),  # unknown
            ctx.owner.id,  # the owner is not a technician
        ):
            with pytest.raises(MemberNotEligible) as caught:
                await shops_service.require_eligible_member(
                    session,
                    shop_id=ctx.id,
                    user_id=user_id,
                    role=MembershipRole.TECHNICIAN,
                    field="technician_user_id",
                )
            assert caught.value.errors == [
                {
                    "field": "technician_user_id",
                    "code": "invalid_reference",
                    "message": "Choose an active Technician of this shop.",
                }
            ]


async def test_d26_active_member_ids_owner_and_member_refs(db: Database) -> None:
    ctx = await make_shop(db)
    first_sa = await add_member(db, ctx, MembershipRole.SERVICE_ADVISOR)
    second_sa = await add_member(db, ctx, MembershipRole.SERVICE_ADVISOR)
    gone_sa = await add_member(db, ctx, MembershipRole.SERVICE_ADVISOR, active=False)
    disabled = await make_user(db, active=False, full_name="Disabled SA")
    await add_member(db, ctx, MembershipRole.SERVICE_ADVISOR, user=disabled)
    qc = await add_member(db, ctx, MembershipRole.QC_INSPECTOR)
    async with db.sessionmaker() as session:
        advisors = await shops_service.list_active_member_ids(
            session, shop_id=ctx.id, roles={MembershipRole.SERVICE_ADVISOR}
        )
        assert advisors == sorted([first_sa.id, second_sa.id])  # active membership and account
        both = await shops_service.list_active_member_ids(
            session,
            shop_id=ctx.id,
            roles=[MembershipRole.QC_INSPECTOR, MembershipRole.OWNER],
        )
        assert both == sorted([qc.id, ctx.owner.id])
        assert await shops_service.list_active_member_ids(session, shop_id=ctx.id, roles=[]) == []
        assert await shops_service.get_owner_user_id(session, shop_id=ctx.id) == ctx.owner.id
        with pytest.raises(NotFound):
            await shops_service.get_owner_user_id(session, shop_id=uuid.uuid4())
        refs = await shops_service.get_member_refs(
            session, shop_id=ctx.id, user_ids=[first_sa.id, gone_sa.id, uuid.uuid4()]
        )
        assert refs == {
            first_sa.id: MemberRef(
                user_id=first_sa.id, full_name=first_sa.user.full_name, is_active=True
            ),
            gone_sa.id: MemberRef(
                user_id=gone_sa.id, full_name=gone_sa.user.full_name, is_active=False
            ),
        }


async def test_list_team_and_setup_flags(db: Database) -> None:
    ctx = await make_shop(db)
    async with db.sessionmaker() as session:
        flags = await shops_service.get_setup_flags(session, shop_id=ctx.id)
        assert (flags.has_services, flags.has_team, flags.is_listed) == (False, False, True)
    team = await make_team(db, ctx)
    await set_member_active(db, ctx, team.qc2.membership_id, active=False)
    await make_services(db, ctx)
    async with db.sessionmaker() as session:
        flags = await shops_service.get_setup_flags(session, shop_id=ctx.id)
        assert (flags.has_services, flags.has_team) == (True, True)
        members = await shops_service.list_team(session, shop_id=ctx.id)
        with pytest.raises(NotFound):
            await shops_service.get_setup_flags(session, shop_id=uuid.uuid4())
    assert [(m.role, m.full_name, m.is_active) for m in members] == [
        (MembershipRole.OWNER, "Fatima Raza", True),
        (MembershipRole.SERVICE_ADVISOR, "Bilal", True),
        (MembershipRole.TECHNICIAN, "Imran", True),
        (MembershipRole.PARTS_PERSON, "Usman", True),
        (MembershipRole.QC_INSPECTOR, "Hina", False),
        (MembershipRole.QC_INSPECTOR, "Sara", True),
    ]


async def test_get_shop_profile_ignores_the_listing(db: Database) -> None:
    hidden = await make_shop(db, name="Hidden Garage", listed=False)
    await make_services(db, hidden, ["Oil change"])
    async with db.sessionmaker() as session:
        profile = await shops_service.get_shop_profile(session, shop_id=hidden.id)
        assert (profile.slug, profile.is_bookable) == ("hidden-garage", True)
        assert [service.name for service in profile.services] == ["Oil change"]
        with pytest.raises(NotFound):
            await shops_service.get_shop_profile(session, shop_id=uuid.uuid4())


async def test_set_rating_is_internal_and_validated(db: Database) -> None:
    ctx = await make_shop(db)
    async with unit_of_work(db) as uow:
        await shops_service.set_rating(uow, shop_id=ctx.id, rating=Decimal("4.5"))
    async with db.sessionmaker() as session:
        shop = await shops_service.get_shop(session, shop_id=ctx.id)
    assert shop.rating == 4.5
    for bad in (Decimal("5.5"), Decimal("-0.1"), Decimal("4.55")):
        async with unit_of_work(db) as uow:
            with pytest.raises(ValidationFailed):
                await shops_service.set_rating(uow, shop_id=ctx.id, rating=bad)
    async with unit_of_work(db) as uow:
        await shops_service.set_rating(uow, shop_id=ctx.id, rating=None)  # "New" again
        with pytest.raises(NotFound):
            await shops_service.set_rating(uow, shop_id=uuid.uuid4(), rating=Decimal(4))
    async with db.sessionmaker() as session:
        assert (await shops_service.get_shop(session, shop_id=ctx.id)).rating is None


async def test_owner_only_use_cases_recheck_the_actor(db: Database) -> None:
    """The seed calls services directly: no active membership → 404, another role → 403."""
    from app.core.errors import Forbidden  # noqa: PLC0415
    from app.modules.shops.schemas import ServiceCreate, ShopUpdate  # noqa: PLC0415

    ctx = await make_shop(db)
    advisor = await add_member(db, ctx, MembershipRole.SERVICE_ADVISOR)
    stranger = await make_user(db)
    async with unit_of_work(db) as uow:
        with pytest.raises(Forbidden):
            await shops_service.update_shop(
                uow, shop_id=ctx.id, actor_user_id=advisor.id, data=ShopUpdate(slot_capacity=4)
            )
        with pytest.raises(NotFound):
            await shops_service.create_service(
                uow,
                shop_id=ctx.id,
                actor_user_id=stranger.id,
                data=ServiceCreate(name="X", estimated_duration_minutes=30),
            )
