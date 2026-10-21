"""Draft decisions and usage over HTTP (modules/ai.md "Endpoints", AI-10, AI-11).

`…/ai/drafts`, `…/ai/drafts/{id}/accept|reject` and `…/ai/usage`, with real sessions.
"""

import uuid

import httpx

from app.core.database import Database
from app.modules.ai.providers.fake import FakeLlmProvider
from app.modules.ai.service import AiRuntime, run_feature
from app.shared.enums import AiFeature
from tests.assertions import assert_problem
from tests.modules.ai.support import GOOD, AiWorld, ai_settings, build_ai_world, explain_run
from tests.modules.identity.builders import bearer
from tests.modules.shops.builders import make_shop

BASE = "/api/v1/shops/{shop_id}/ai"


async def _draft(world: AiWorld, feature: AiFeature = AiFeature.ESTIMATE_EXPLAINER) -> uuid.UUID:
    member = world.technician if feature is AiFeature.VOICE_TO_ESTIMATE else world.advisor
    ai = AiRuntime(db=world.db, settings=ai_settings(), provider=FakeLlmProvider(GOOD))
    result = await run_feature(ai, explain_run(world.actor(member), feature=feature))
    assert result.draft_id is not None
    return result.draft_id


def _url(world: AiWorld, path: str = "") -> str:
    return BASE.format(shop_id=world.shop.id) + path


async def test_an_advisor_lists_and_accepts_a_draft_as_is(
    db: Database, db_client: httpx.AsyncClient
) -> None:
    world = await build_ai_world(db)
    draft_id = await _draft(world)
    headers = bearer(world.advisor.user.id)

    listed = await db_client.get(_url(world, "/drafts?status=PENDING"), headers=headers)
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [str(draft_id)]

    accepted = await db_client.post(
        _url(world, f"/drafts/{draft_id}/accept"), json={"note": "Looks right"}, headers=headers
    )
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["status"] == "ACCEPTED"
    assert body["final_payload"] == body["payload"] == GOOD.model_dump(mode="json")
    assert body["decided_by"] == {"user_id": str(world.advisor.user.id), "full_name": "Bilal"}
    assert body["decision_note"] == "Looks right"


async def test_an_edited_acceptance_keeps_both_versions(
    db: Database, db_client: httpx.AsyncClient
) -> None:
    world = await build_ai_world(db)
    draft_id = await _draft(world)
    edit = {"summary": "Version 2 is 16,100 rupees in total.", "lines": []}
    response = await db_client.post(
        _url(world, f"/drafts/{draft_id}/accept"),
        json={"final_payload": edit},
        headers=bearer(world.shop.owner.id),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "EDITED"
    assert body["payload"] == GOOD.model_dump(mode="json")  # what the AI wrote, kept (AI-41)
    assert body["final_payload"] == edit


async def test_a_draft_is_decided_once(db: Database, db_client: httpx.AsyncClient) -> None:
    world = await build_ai_world(db)
    draft_id = await _draft(world)
    headers = bearer(world.advisor.user.id)
    reject_url = _url(world, f"/drafts/{draft_id}/reject")
    rejected = await db_client.post(reject_url, json={}, headers=headers)
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["final_payload"] is None
    accept_url = _url(world, f"/drafts/{draft_id}/accept")
    again = await db_client.post(accept_url, json={}, headers=headers)
    assert_problem(again, 409, "CONFLICT")


async def test_roles_without_drafts_are_refused_and_other_shops_see_nothing(
    db: Database, db_client: httpx.AsyncClient
) -> None:
    world = await build_ai_world(db)
    draft_id = await _draft(world)
    refused = await db_client.get(_url(world, "/drafts"), headers=bearer(world.parts.user.id))
    assert_problem(refused, 403, "FORBIDDEN")
    # A technician may decide only voice-to-estimate drafts: an explainer draft is not theirs.
    hidden = await db_client.get(
        _url(world, f"/drafts/{draft_id}"), headers=bearer(world.technician.user.id)
    )
    assert_problem(hidden, 404, "NOT_FOUND")
    other = await make_shop(db, name="Clifton Car Clinic")
    foreign = await db_client.post(
        BASE.format(shop_id=other.id) + f"/drafts/{draft_id}/accept",
        json={},
        headers=bearer(other.owner.id),
    )
    assert_problem(foreign, 404, "NOT_FOUND")


async def test_a_technician_decides_only_their_own_voice_drafts(
    db: Database, db_client: httpx.AsyncClient
) -> None:
    world = await build_ai_world(db)
    own = await _draft(world, AiFeature.VOICE_TO_ESTIMATE)
    await _draft(world)  # an explainer draft the technician must not see
    listed = await db_client.get(_url(world, "/drafts"), headers=bearer(world.technician.user.id))
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [str(own)]
    # The advisor sees both features' drafts.
    both = await db_client.get(_url(world, "/drafts"), headers=bearer(world.advisor.user.id))
    assert both.json()["total"] == 2


async def test_usage_counts_calls_against_the_caps(
    db: Database, db_client: httpx.AsyncClient
) -> None:
    world = await build_ai_world(db)
    await _draft(world)
    await _draft(world)
    response = await db_client.get(_url(world, "/usage"), headers=bearer(world.shop.owner.id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["calls_today"], body["calls_this_month"]) == (2, 2)
    assert (body["daily_cap"], body["monthly_cap"]) == (200, 3000)
    assert body["configured"] is False  # the test app has no key and the gemini provider
    technician = await db_client.get(
        _url(world, "/usage"), headers=bearer(world.technician.user.id)
    )
    assert_problem(technician, 403, "FORBIDDEN")
