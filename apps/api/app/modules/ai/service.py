"""Use cases of the ai module (modules/ai.md, D103).

- `run_feature`: the one way a feature calls a model. Order: enabled → caller's role → shop caps →
  mask → provider call with **no session open** → validate → grounding guard → one transaction
  (audit row, plus a `PENDING` draft for decision features) → commit. Failures are audited, then
  raised as `AI_UNAVAILABLE`, so the person carries on by hand.
- Drafts: `list_drafts`, `get_draft`, `accept_draft`, `reject_draft` (AI-42).
- `get_usage`: calls against the shop's caps (spec 13 principle 5).

The provider is a per-app object on `app.state.ai_provider` (D90), built on first use from the
settings; tests replace it with `FakeLlmProvider`.
"""

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import State

from app.core.config import Settings
from app.core.database import Database
from app.core.errors import AiDisabled, AiLimitReached, AiUnavailable, Conflict, Forbidden, NotFound
from app.modules.ai.domain.caps import Usage, cap_reached, day_start, month_start
from app.modules.ai.domain.features import FEATURES, decidable_by, enabled_features, is_enabled
from app.modules.ai.domain.grounding import GroundingFacts, ungrounded
from app.modules.ai.domain.masking import mask_pii
from app.modules.ai.models import MAX_ERROR_CHARS, MAX_INPUT_CHARS, AiAuditEvent, AiDraft
from app.modules.ai.providers.base import LlmError, LlmInvalidOutputError, LlmProvider, LlmRequest
from app.modules.ai.providers.fake import FakeLlmProvider
from app.modules.ai.providers.gemini import GeminiProvider
from app.modules.ai.repository import AiAuditRepository, AiDraftRepository
from app.modules.ai.schemas import AiDraftAccept, AiDraftRead, AiDraftReject, AiUsageRead
from app.modules.identity import service as identity_service
from app.shared.auth import ShopContext
from app.shared.clock import utcnow
from app.shared.enums import (
    ActorRole,
    AiCallStatus,
    AiDraftStatus,
    AiFeature,
    AiSubjectType,
)
from app.shared.event_bus import EventBus
from app.shared.orm import touch
from app.shared.pagination import Page, PageParams
from app.shared.uow import UnitOfWork

logger = logging.getLogger(__name__)

ALREADY_DECIDED = "This AI draft has already been decided."


# --- Runtime --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AiRuntime:
    """What `run_feature` needs: its own sessions, the settings, the provider (None = AI off)."""

    db: Database
    settings: Settings
    provider: LlmProvider | None


def build_provider(settings: Settings) -> LlmProvider | None:
    """The configured provider, or None when text AI is off (no key; fake in production)."""
    if not settings.text_ai_configured:
        return None
    if settings.ai_text_provider == "fake":
        return FakeLlmProvider()
    key = settings.text_ai_key()
    if key is None:  # unreachable: text_ai_configured checked it
        return None
    return GeminiProvider(
        api_key=key.get_secret_value(),
        model=settings.ai_text_model,
        timeout_seconds=settings.ai_timeout_seconds,
    )


def get_ai_runtime(state: State) -> AiRuntime:
    """The app's runtime; the provider is created on first use at `state.ai_provider` (D90)."""
    settings: Settings = state.settings
    if not hasattr(state, "ai_provider"):
        state.ai_provider = build_provider(settings)
    return AiRuntime(db=state.db, settings=settings, provider=state.ai_provider)


# --- run_feature ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AiActor:
    """Who asked: `user_id` None only for system jobs (no drafts)."""

    user_id: uuid.UUID | None
    role: ActorRole
    shop_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class AiSubject:
    type: AiSubjectType
    id: uuid.UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class AiRun[T: BaseModel]:
    """One feature call. `facts` turns on the grounding guard; `mask_plates` keeps number plates
    in the prompt when the task needs them."""

    feature: AiFeature
    actor: AiActor
    subject: AiSubject
    system: str
    prompt: str
    output_type: type[T]
    facts: GroundingFacts | None = None
    mask_plates: bool = True
    temperature: float = 0.2


@dataclass(frozen=True, slots=True)
class AiResult[T: BaseModel]:
    output: T
    audit_event_id: uuid.UUID
    draft_id: uuid.UUID | None


@dataclass(slots=True)
class _Outcome:
    status: AiCallStatus = AiCallStatus.SUCCEEDED
    output: BaseModel | None = None
    error: str | None = None
    model: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None


async def _usage(session: AsyncSession, *, shop_id: uuid.UUID) -> Usage:
    now = utcnow()
    audits = AiAuditRepository(session)
    return Usage(
        today=await audits.count_since(shop_id=shop_id, since=day_start(now)),
        this_month=await audits.count_since(shop_id=shop_id, since=month_start(now)),
    )


async def _call(
    provider: LlmProvider, request: LlmRequest[Any], facts: GroundingFacts | None
) -> _Outcome:
    """The provider call and the checks on its answer; never raises."""
    outcome = _Outcome(model=provider.model)
    try:
        response = await provider.generate(request)
    except LlmInvalidOutputError as exc:
        outcome.status, outcome.error = AiCallStatus.INVALID_OUTPUT, str(exc)
        return outcome
    except LlmError as exc:
        outcome.status, outcome.error = AiCallStatus.PROVIDER_ERROR, str(exc)
        return outcome
    except Exception as exc:  # any provider failure is audited, never a 500
        outcome.status, outcome.error = AiCallStatus.PROVIDER_ERROR, type(exc).__name__
        return outcome
    outcome.output = response.output
    outcome.model = response.model
    outcome.input_tokens, outcome.output_tokens = response.input_tokens, response.output_tokens
    problems = ungrounded(response.output.model_dump(mode="json"), facts) if facts else []
    if problems:
        outcome.status, outcome.error = AiCallStatus.GUARD_BLOCKED, "; ".join(problems)
    return outcome


async def run_feature[T: BaseModel](runtime: AiRuntime, run: AiRun[T]) -> AiResult[T]:
    """Call the model for one feature; see the module docstring for the order of checks.

    The caller must not hold an open transaction or row lock: this function opens its own short
    sessions before and after the model call.
    """
    spec = FEATURES[run.feature]
    settings = runtime.settings
    provider = runtime.provider
    if provider is None or not is_enabled(run.feature, settings.enabled_ai_features):
        raise AiDisabled
    if run.actor.role not in spec.callers or (spec.needs_decision and run.actor.user_id is None):
        raise Forbidden
    async with runtime.db.sessionmaker() as session:
        usage = await _usage(session, shop_id=run.actor.shop_id)
    if cap_reached(
        usage, daily_cap=settings.ai_shop_daily_cap, monthly_cap=settings.ai_shop_monthly_cap
    ):
        raise AiLimitReached

    system = mask_pii(run.system, plates=run.mask_plates)
    prompt = mask_pii(run.prompt, plates=run.mask_plates)
    request = LlmRequest(
        system=system, prompt=prompt, output_type=run.output_type, temperature=run.temperature
    )
    started = time.monotonic()
    outcome = await _call(provider, request, run.facts)  # no session is open here
    latency_ms = round((time.monotonic() - started) * 1000)

    payload = outcome.output.model_dump(mode="json") if outcome.output is not None else None
    needs_draft = outcome.status is AiCallStatus.SUCCEEDED and spec.needs_decision
    async with runtime.db.sessionmaker() as session:
        uow = UnitOfWork(session, EventBus())
        event = AiAuditEvent(
            id=uuid.uuid4(),
            shop_id=run.actor.shop_id,
            feature=run.feature,
            prompt_version=spec.prompt_version,
            provider=provider.name,
            model=(outcome.model or provider.model)[:64],
            actor_user_id=run.actor.user_id,
            actor_role=run.actor.role,
            subject_type=run.subject.type,
            subject_id=run.subject.id,
            input_masked=f"[system]\n{system}\n\n[prompt]\n{prompt}"[:MAX_INPUT_CHARS],
            output=payload,
            status=outcome.status,
            error=outcome.error[:MAX_ERROR_CHARS] if outcome.error else None,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            latency_ms=latency_ms,
        )
        AiAuditRepository(session).add(event)
        await session.flush()  # the audit row exists before the draft's composite FK
        draft_id = None
        if needs_draft and payload is not None and run.actor.user_id is not None:
            draft = AiDraft(
                id=uuid.uuid4(),
                shop_id=run.actor.shop_id,
                feature=run.feature,
                audit_event_id=event.id,
                subject_type=run.subject.type,
                subject_id=run.subject.id,
                payload=payload,
                status=AiDraftStatus.PENDING,
                requested_by_user_id=run.actor.user_id,
            )
            AiDraftRepository(session).add(draft)
            draft_id = draft.id
        await uow.commit()

    if outcome.status is not AiCallStatus.SUCCEEDED or outcome.output is None:
        logger.warning(
            "ai.call_failed",
            extra={"feature": run.feature.value, "status": outcome.status.value},
        )
        raise AiUnavailable
    output: T = run.output_type.model_validate(payload)
    return AiResult(output=output, audit_event_id=event.id, draft_id=draft_id)


# --- Drafts (AI-42) -------------------------------------------------------------------------------


def _role(ctx: ShopContext) -> ActorRole:
    return ActorRole(ctx.role.value)


def _decidable(ctx: ShopContext) -> frozenset[AiFeature]:
    features = decidable_by(_role(ctx))
    if not features:
        raise Forbidden
    return features


def _visible(ctx: ShopContext, draft: AiDraft | None) -> AiDraft:
    """A Technician sees only the drafts they requested; others every draft they may decide."""
    if draft is None or draft.feature not in decidable_by(_role(ctx)):
        raise NotFound
    if _role(ctx) is ActorRole.TECHNICIAN and draft.requested_by_user_id != ctx.user.id:
        raise NotFound
    return draft


async def _reads(session: AsyncSession, drafts: list[AiDraft]) -> list[AiDraftRead]:
    user_ids = {draft.requested_by_user_id for draft in drafts}
    user_ids |= {draft.decided_by_user_id for draft in drafts if draft.decided_by_user_id}
    refs = await identity_service.get_user_refs(session, user_ids)
    return [
        AiDraftRead(
            id=draft.id,
            feature=draft.feature,
            status=draft.status,
            subject_type=draft.subject_type,
            subject_id=draft.subject_id,
            payload=draft.payload,
            final_payload=draft.final_payload,
            requested_by=refs[draft.requested_by_user_id],
            decided_by=refs[draft.decided_by_user_id] if draft.decided_by_user_id else None,
            decided_at=draft.decided_at,
            decision_note=draft.decision_note,
            created_at=draft.created_at,
        )
        for draft in drafts
    ]


async def list_drafts(
    session: AsyncSession, ctx: ShopContext, *, status: AiDraftStatus | None, page: PageParams
) -> Page[AiDraftRead]:
    """`GET …/ai/drafts`: newest first; only drafts the caller may decide."""
    features = _decidable(ctx)
    requested_by = ctx.user.id if _role(ctx) is ActorRole.TECHNICIAN else None
    rows, total = await AiDraftRepository(session).page(
        shop_id=ctx.shop_id,
        features=features,
        status=status,
        requested_by=requested_by,
        limit=page.limit,
        offset=page.offset,
    )
    return Page.build(await _reads(session, list(rows)), total=total, params=page)


async def get_draft(session: AsyncSession, ctx: ShopContext, draft_id: uuid.UUID) -> AiDraftRead:
    _decidable(ctx)
    found = await AiDraftRepository(session).get(shop_id=ctx.shop_id, draft_id=draft_id)
    draft = _visible(ctx, found)
    return (await _reads(session, [draft]))[0]


async def _decide(
    uow: UnitOfWork,
    ctx: ShopContext,
    draft_id: uuid.UUID,
    *,
    status: AiDraftStatus,
    final_payload: dict[str, Any] | None,
    note: str | None,
) -> AiDraftRead:
    _decidable(ctx)
    repository = AiDraftRepository(uow.session)
    draft = _visible(ctx, await repository.lock(shop_id=ctx.shop_id, draft_id=draft_id))
    if draft.status is not AiDraftStatus.PENDING:
        raise Conflict(ALREADY_DECIDED)
    now = utcnow()
    if status is AiDraftStatus.ACCEPTED:
        edited = final_payload is not None and final_payload != draft.payload
        draft.status = AiDraftStatus.EDITED if edited else AiDraftStatus.ACCEPTED
        draft.final_payload = final_payload if edited else draft.payload
    else:
        draft.status = status
    draft.decided_by_user_id = ctx.user.id
    draft.decided_at = now
    draft.decision_note = note
    touch(draft, now)
    await uow.commit()
    logger.info(
        "ai.draft_decided",
        extra={"draft_id": str(draft.id), "status": draft.status.value},
    )
    return (await _reads(uow.session, [draft]))[0]


async def accept_draft(
    uow: UnitOfWork, ctx: ShopContext, draft_id: uuid.UUID, body: AiDraftAccept
) -> AiDraftRead:
    """`POST …/accept`: as is, or `EDITED` when `final_payload` differs from the draft."""
    return await _decide(
        uow,
        ctx,
        draft_id,
        status=AiDraftStatus.ACCEPTED,
        final_payload=body.final_payload,
        note=body.note,
    )


async def reject_draft(
    uow: UnitOfWork, ctx: ShopContext, draft_id: uuid.UUID, body: AiDraftReject
) -> AiDraftRead:
    return await _decide(
        uow, ctx, draft_id, status=AiDraftStatus.REJECTED, final_payload=None, note=body.note
    )


# --- Usage ----------------------------------------------------------------------------------------


async def get_usage(session: AsyncSession, ctx: ShopContext, settings: Settings) -> AiUsageRead:
    """`GET …/ai/usage` (Owner, SA): calls today and this month against the caps."""
    usage = await _usage(session, shop_id=ctx.shop_id)
    return AiUsageRead(
        configured=settings.text_ai_configured,
        provider=settings.ai_text_provider,
        model=settings.ai_text_model,
        enabled_features=enabled_features(settings.enabled_ai_features),
        calls_today=usage.today,
        calls_this_month=usage.this_month,
        daily_cap=settings.ai_shop_daily_cap,
        monthly_cap=settings.ai_shop_monthly_cap,
    )
