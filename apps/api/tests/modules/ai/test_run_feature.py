"""`run_feature` against the database with a fake provider (modules/ai.md "Tests" AI-01 … AI-09).

No test calls a real model.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import Database
from app.core.errors import AiDisabled, AiLimitReached, AiUnavailable, Forbidden
from app.modules.ai.domain.grounding import GroundingFacts
from app.modules.ai.providers.base import LlmError
from app.modules.ai.providers.fake import FakeLlmProvider
from app.modules.ai.service import AiRuntime, run_feature
from app.shared.enums import AiFeature
from tests.modules.ai.support import (
    GOOD,
    Explanation,
    ai_settings,
    build_ai_world,
    explain_run,
    rows,
    runtime,
)

AUDIT = (
    "select feature, status, prompt_version, provider, model, error, output from ai_audit_events"
)


async def test_a_successful_call_is_audited_and_returns_validated_output(db: Database) -> None:
    world = await build_ai_world(db)
    result = await run_feature(runtime(db), explain_run(world.actor(world.advisor)))
    assert result.output == GOOD
    [event] = await rows(db, AUDIT)
    assert event["feature"] == "ESTIMATE_EXPLAINER"
    assert event["status"] == "SUCCEEDED"
    assert (event["prompt_version"], event["provider"], event["model"]) == ("v1", "fake", "fake-1")
    assert event["output"] == GOOD.model_dump(mode="json")


async def test_a_decision_feature_creates_a_pending_draft(db: Database) -> None:
    world = await build_ai_world(db)
    result = await run_feature(runtime(db), explain_run(world.actor(world.advisor)))
    [draft] = await rows(db, "select id, status, requested_by_user_id, payload from ai_drafts")
    assert draft["id"] == result.draft_id
    assert draft["status"] == "PENDING"
    assert draft["requested_by_user_id"] == world.advisor.user.id
    assert draft["payload"] == GOOD.model_dump(mode="json")


async def test_an_advisory_feature_creates_no_draft(db: Database) -> None:
    world = await build_ai_world(db)
    run = explain_run(world.actor(world.advisor), feature=AiFeature.ESTIMATE_CHECKER)
    result = await run_feature(runtime(db), run)
    assert result.draft_id is None
    assert await rows(db, "select id from ai_drafts") == []


@pytest.mark.parametrize(
    "settings",
    [
        {"ai_features": ""},  # no feature enabled
        {"ai_features": "ASK_YOUR_SHOP"},  # another feature enabled
    ],
)
async def test_a_disabled_feature_never_reaches_the_provider(
    db: Database, settings: dict[str, object]
) -> None:
    world = await build_ai_world(db)
    ai = runtime(db, **settings)
    with pytest.raises(AiDisabled):
        await run_feature(ai, explain_run(world.actor(world.advisor)))
    assert isinstance(ai.provider, FakeLlmProvider)
    assert ai.provider.requests == []


async def test_no_provider_means_ai_is_off(db: Database) -> None:
    world = await build_ai_world(db)
    off = AiRuntime(db=db, settings=ai_settings(), provider=None)
    with pytest.raises(AiDisabled):
        await run_feature(off, explain_run(world.actor(world.advisor)))


async def test_a_role_that_may_not_run_the_feature_is_refused(db: Database) -> None:
    world = await build_ai_world(db)
    with pytest.raises(Forbidden):
        await run_feature(runtime(db), explain_run(world.actor(world.parts)))
    assert await rows(db, "select id from ai_audit_events") == []


async def test_the_shop_cap_stops_calls_before_the_provider(db: Database) -> None:
    world = await build_ai_world(db)
    ai = runtime(db, ai_shop_daily_cap=2)
    for _ in range(2):
        await run_feature(ai, explain_run(world.actor(world.advisor)))
    with pytest.raises(AiLimitReached):
        await run_feature(ai, explain_run(world.actor(world.advisor)))
    assert isinstance(ai.provider, FakeLlmProvider)
    assert len(ai.provider.requests) == 2


@pytest.mark.parametrize(
    ("answer", "status"),
    [
        (LlmError("provider error 503: UNAVAILABLE"), "PROVIDER_ERROR"),
        (RuntimeError("boom"), "PROVIDER_ERROR"),
        ({"summary": 42}, "INVALID_OUTPUT"),
    ],
)
async def test_provider_failures_are_audited_then_reported_as_unavailable(
    db: Database, answer: object, status: str
) -> None:
    world = await build_ai_world(db)
    with pytest.raises(AiUnavailable):
        await run_feature(runtime(db, answer), explain_run(world.actor(world.advisor)))
    [event] = await rows(db, AUDIT)
    assert event["status"] == status
    assert event["output"] is None
    assert event["error"]
    assert await rows(db, "select id from ai_drafts") == []


async def test_the_grounding_guard_blocks_invented_amounts(db: Database) -> None:
    world = await build_ai_world(db)
    invented = Explanation(summary="Total 17,000 rupees.", lines=[])
    facts = GroundingFacts.of(amounts=[16100, 6500], references=["BF-7K2M9Q"])
    with pytest.raises(AiUnavailable):
        await run_feature(
            runtime(db, invented), explain_run(world.actor(world.advisor), facts=facts)
        )
    [event] = await rows(db, AUDIT)
    assert event["status"] == "GUARD_BLOCKED"
    assert event["error"] == "amount 17,000 is not in the facts"
    assert event["output"] == invented.model_dump(mode="json")  # kept for review, never shown
    assert await rows(db, "select id from ai_drafts") == []


async def test_grounded_output_passes_the_guard(db: Database) -> None:
    world = await build_ai_world(db)
    facts = GroundingFacts.of(amounts=[16100, 6500], references=["BF-7K2M9Q"])
    result = await run_feature(runtime(db), explain_run(world.actor(world.advisor), facts=facts))
    assert result.output == GOOD


async def test_personal_data_never_reaches_the_provider_or_the_audit(db: Database) -> None:
    world = await build_ai_world(db)
    ai = runtime(db)
    prompt = "Customer ahmed@mail.com, 0300-1234567, car LEA-1234, booking BF-7K2M9Q, Rs 16,100."
    await run_feature(ai, explain_run(world.actor(world.advisor), prompt=prompt))
    assert isinstance(ai.provider, FakeLlmProvider)
    [request] = ai.provider.requests
    assert request.prompt == "Customer [email], [phone], car [plate], booking BF-7K2M9Q, Rs 16,100."
    [stored] = await rows(db, "select input_masked from ai_audit_events")
    assert "ahmed@mail.com" not in stored["input_masked"]
    assert "0300-1234567" not in stored["input_masked"]
    assert "[email]" in stored["input_masked"]


async def test_audit_rows_are_append_only(db: Database) -> None:
    world = await build_ai_world(db)
    await run_feature(runtime(db), explain_run(world.actor(world.advisor)))
    for statement in ("update ai_audit_events set model = 'x'", "delete from ai_audit_events"):
        async with db.sessionmaker() as session:
            with pytest.raises(DBAPIError, match="append-only"):
                await session.execute(text(statement))
