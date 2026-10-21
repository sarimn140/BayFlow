"""Builders for the ai module tests: a shop with a team, a fake provider and a runtime."""

import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import Settings
from app.core.database import Database
from app.modules.ai.providers.fake import FakeAnswer, FakeLlmProvider
from app.modules.ai.service import AiActor, AiRun, AiRuntime, AiSubject
from app.shared.auth import CurrentUser, ShopContext
from app.shared.enums import ActorRole, AiFeature, AiSubjectType, MembershipRole
from tests.conftest import make_settings
from tests.modules.shops.builders import Member, ShopCtx, add_member, make_shop


class Explanation(BaseModel):
    """The output model the tests ask for."""

    summary: str
    lines: list[str]


GOOD = Explanation(summary="Version 2 totals 16,100 rupees.", lines=["Ignition coil Rs 6,500"])


@dataclass
class AiWorld:
    db: Database
    shop: ShopCtx
    advisor: Member
    technician: Member
    parts: Member

    def context(self, member: Member | None = None) -> ShopContext:
        """The `ShopContext` the route dependency builds (the Owner when `member` is None)."""
        user = member.user if member else self.shop.owner
        membership_id = member.membership_id if member else uuid.uuid4()
        role = member.role if member else MembershipRole.OWNER
        return ShopContext(
            shop_id=self.shop.id,
            user=CurrentUser(id=user.id, email=user.email, full_name=user.full_name),
            membership_id=membership_id,
            role=role,
        )

    def actor(self, member: Member | None = None) -> AiActor:
        ctx = self.context(member)
        return AiActor(user_id=ctx.user.id, role=ActorRole(ctx.role.value), shop_id=self.shop.id)


async def build_ai_world(db: Database) -> AiWorld:
    shop = await make_shop(db, name="Lahore Auto Care")
    return AiWorld(
        db=db,
        shop=shop,
        advisor=await add_member(db, shop, MembershipRole.SERVICE_ADVISOR, full_name="Bilal"),
        technician=await add_member(db, shop, MembershipRole.TECHNICIAN, full_name="Imran"),
        parts=await add_member(db, shop, MembershipRole.PARTS_PERSON, full_name="Usman"),
    )


def ai_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"ai_text_provider": "fake", "ai_features": "*"}
    values.update(overrides)
    return make_settings(**values)


def runtime(db: Database, answer: FakeAnswer | Any = GOOD, **settings: object) -> AiRuntime:
    return AiRuntime(db=db, settings=ai_settings(**settings), provider=FakeLlmProvider(answer))


def explain_run(
    actor: AiActor,
    *,
    prompt: str = "Explain the estimate for BF-7K2M9Q.",
    feature: AiFeature = AiFeature.ESTIMATE_EXPLAINER,
    **options: Any,
) -> AiRun[Explanation]:
    return AiRun(
        feature=feature,
        actor=actor,
        subject=AiSubject(AiSubjectType.BOOKING, uuid.uuid4()),
        system="You explain estimates to customers.",
        prompt=prompt,
        output_type=Explanation,
        **options,
    )


async def rows(db: Database, sql: str) -> list[dict[str, Any]]:
    async with db.sessionmaker() as session:
        return [dict(row) for row in (await session.execute(text(sql))).mappings().all()]
