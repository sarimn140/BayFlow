# Module: ai

**Status:** Draft
**Package:** `app.modules.ai`
**Owns tables:** `ai_audit_events`, `ai_drafts`
**Priority:** P2 — the shared foundation of spec 13's text features (AI-41, AI-42, AI-43). It ships with no user-facing feature of its own; each feature (AI-05, AI-14, AI-18, AI-01, AI-33, …) is a thin slice in its own module that calls `run_feature`. With AI off (no key, or the feature not enabled) every feature reports `AI_DISABLED` and the core is unaffected (spec 13 principle 5).
**Authority:** D103 (the API may call an LLM for text features), spec 13 §1 (principles), this file.

## Purpose

One place where the API talks to a language model, so every text AI feature gets the same guarantees for free:

1. **One provider port.** `LlmProvider` with a Gemini adapter (the default) and a fake. Tests never call a real model.
2. **Structured output only.** Every call names a Pydantic model; the reply is validated against it. Free text is never parsed.
3. **Audit trail (AI-41).** Every model call is one append-only `ai_audit_events` row: feature, prompt version, provider, model, actor, subject, the **masked** prompt, the output, status, token counts and latency.
4. **Draft → decision (AI-42).** Output of a feature that touches money or what a customer is told is stored as an `ai_drafts` row in `PENDING`. A person in an approver role accepts (as is or edited) or rejects it; the draft records who and when. The AI never changes a booking, an estimate or a price itself: applying an accepted draft is an ordinary service call made by that person.
5. **Grounding guard and evaluation (AI-43).** A feature may pass the facts it sent (amounts, booking references); output that states an amount or a reference not among them is blocked (`GUARD_BLOCKED`) and never shown. The same checks drive the golden-set harness in the tests.
6. **Controls.** `LLM_API_KEY` (or `AI_TEXT_API_KEY`) blank = all text AI off; `AI_FEATURES` enables features one by one; per-shop daily and monthly caps; personal data masked before it leaves the API.
7. **Never inside a transaction.** A model call can take seconds. `run_feature` opens no transaction while the provider is called: it reads the caps in one short session, calls the model with no session open, then writes the audit row (and draft) in a second short transaction. Callers must not hold a row lock or an open unit of work across `run_feature`.

## Key decisions

| D | What it means here |
|---|---|
| D103 | Text AI runs in the API through this module; voice stays in `apps/agent` (D58). Default text provider Gemini (`AI_TEXT_PROVIDER=gemini`, `AI_TEXT_MODEL=gemini-2.5-flash`). |
| D90 | The provider is a per-app object on `app.state.ai_provider`, created on first use; tests replace it with `FakeLlmProvider`. |
| D63 | `created_at`, `decided_at` and the cap windows use the app clock. |
| D20 | Rows carry `shop_id`; every read and decision is scoped to the caller's shop. |
| D74 | `AiFeature`, `AiCallStatus`, `AiDraftStatus`, `AiSubjectType` live in `app.shared.enums`. |
| D84 | The two tables come in the expand-only migration `90a856e17478` (after `339df51b764d`); `ai_audit_events` is append-only (the baseline's `forbid_mutation` trigger). |

## Feature registry (`domain/features.py`)

| Feature (`AiFeature`) | Backlog | Output needs a decision? | Who decides | Caller |
|---|---|---|---|---|
| `ESTIMATE_EXPLAINER` | AI-05 | Yes — the text is sent to the customer | SA, Owner | SA, Owner |
| `ESTIMATE_CHECKER` | AI-14 | No — advisory flags shown to the SA | — | SA, Owner |
| `VOICE_TO_ESTIMATE` | AI-18 | Yes — draft estimate lines (money) | Technician, SA, Owner | Technician |
| `SYMPTOM_TRIAGE` | AI-01 | No — suggestions; the customer still picks services | — | Customer |
| `ASK_YOUR_SHOP` | AI-33 | No — numbers come from SQL, the model only words them | — | Owner |

Each entry also has a `prompt_version` string (bumped whenever its prompt changes, so audit rows and evaluations can be compared across versions).

## Tables

**`ai_audit_events`** (append-only): `id`, `shop_id` (FK shops), `feature`, `prompt_version` (≤ 32), `provider` (≤ 32), `model` (≤ 64), `actor_user_id` (FK users, nullable for system jobs), `actor_role` (`ActorRole`), `subject_type` (`AiSubjectType`: `BOOKING`, `ESTIMATE`, `SHOP`), `subject_id`, `input_masked` (text ≤ 32 000), `output` (JSONB, null unless the model returned valid output), `status` (`AiCallStatus`: `SUCCEEDED`, `PROVIDER_ERROR`, `INVALID_OUTPUT`, `GUARD_BLOCKED`), `error` (≤ 500), `input_tokens`, `output_tokens`, `latency_ms`, `created_at`. Index `(shop_id, created_at)` for the caps and the owner's usage view.

**`ai_drafts`**: `id`, `shop_id`, `feature`, `audit_event_id` (unique FK → `ai_audit_events`), `subject_type`, `subject_id`, `payload` (JSONB, the model's output), `status` (`AiDraftStatus`: `PENDING`, `ACCEPTED`, `EDITED`, `REJECTED`), `requested_by_user_id`, `decided_by_user_id`, `decided_at`, `final_payload` (JSONB: the accepted payload, the edit when `EDITED`), `decision_note` (≤ 500), `created_at`, `updated_at`. Checks: `decided_by_user_id` and `decided_at` are null exactly while `PENDING`; `final_payload` is set exactly when `ACCEPTED` or `EDITED`; `decision_note` is optional. A Technician sees and decides only the drafts they requested; SA and Owner see every draft of the features they may decide. Index `(shop_id, status, created_at)`.

## Public service interface

```python
runtime = get_ai_runtime(app_state)          # db, settings, provider (None when text AI is off)
result = await run_feature(runtime, AiRun(
    feature=AiFeature.ESTIMATE_EXPLAINER,
    actor=AiActor(user_id=..., role=ActorRole.SERVICE_ADVISOR, shop_id=...),
    subject=AiSubject(AiSubjectType.ESTIMATE, estimate_id),
    system="…", prompt="…", output_type=ExplainerOutput,
    facts=GroundingFacts(amounts={16100, 6500}, references={"BF-7K2M9Q"}),
))
result.output       # an ExplainerOutput instance
result.draft_id     # set when the feature needs a decision
```

`run_feature` order: feature enabled (`AI_DISABLED` 503) → caller's role allowed for the feature (403) → shop caps (`AI_LIMIT_REACHED` 429) → mask → provider call (no session open) → validate output → grounding guard → one transaction: audit row (+ `PENDING` draft) → commit → result. A provider error, invalid output or blocked output is audited and then raised as `AI_UNAVAILABLE` (503) — the feature shows "AI is unavailable right now" and the person carries on by hand.

Reads and decisions: `list_drafts(session, ctx, status, page)`, `get_draft`, `decide_draft(uow, ctx, draft_id, decision, final_payload, note)` (approver role for the draft's feature, else 403; not `PENDING` → 409 `CONFLICT`), `get_usage(session, ctx, settings)`.

## Endpoints (shop-scoped, tag `ai`)

| Method | Path | Who | Success |
|---|---|---|---|
| GET | `…/ai/usage` | Owner, SA | 200 `AiUsageRead`: calls today / this month, the two caps, enabled features, whether text AI is configured |
| GET | `…/ai/drafts?status=` | Any member who may decide some feature | 200 `Page[AiDraftRead]`, only drafts of features the caller may decide, newest first |
| GET | `…/ai/drafts/{draft_id}` | same | 200 `AiDraftRead` |
| POST | `…/ai/drafts/{draft_id}/accept` | Approver of the draft's feature | 200 `AiDraftRead` — body `{final_payload?, note?}`; a `final_payload` different from `payload` makes it `EDITED` |
| POST | `…/ai/drafts/{draft_id}/reject` | same | 200 `AiDraftRead` — body `{note?}` |

Feature endpoints (e.g. "explain this estimate") belong to the feature's own module and call `run_feature`.

## Personal data masking (`domain/masking.py`)

Before a prompt is sent or stored: e-mail addresses → `[email]`, phone numbers (10+ digits, `+92…`, `03…`) → `[phone]`, CNIC (`12345-1234567-1`) → `[cnic]`, and — unless the feature needs them — number plates (`LEA-1234`, `BKR-482`) → `[plate]`. Amounts, booking references, SKUs and dates are kept. Features still send only what the task needs (spec 13 principle 4); masking is the backstop.

## Evaluation (AI-43)

`tests/ai/harness.py`: a golden case = feature input + facts + expectations; the harness runs the feature through `run_feature` with a provider (the fake in CI, the real one on demand) and fails on (1) invalid output, (2) an amount or reference not in the facts (`domain/grounding.py`), (3) another customer's reference or personal data in the output, (4) a failed expectation. Each feature adds its golden set when it is built.

## Configuration (glossary §12)

| Variable | Default | Meaning |
|---|---|---|
| `AI_TEXT_PROVIDER` | `gemini` | `gemini` or `fake` (local demos without a key; never in production) |
| `AI_TEXT_MODEL` | `gemini-2.5-flash` | Model for text features |
| `AI_TEXT_API_KEY` | — | Key for the text provider; blank → `LLM_API_KEY` |
| `AI_FEATURES` | blank | Comma-separated `AiFeature` names, or `*` for all; blank = none |
| `AI_SHOP_DAILY_CAP` | `200` | Model calls per shop per UTC day |
| `AI_SHOP_MONTHLY_CAP` | `3000` | Model calls per shop per UTC month |
| `AI_TIMEOUT_SECONDS` | `30` | Provider call timeout |

## Errors

| Code | HTTP | When |
|---|---|---|
| `AI_DISABLED` | 503 | Text AI not configured or the feature not enabled |
| `AI_LIMIT_REACHED` | 429 | The shop's daily or monthly AI cap is reached |
| `AI_UNAVAILABLE` | 503 | The provider failed, returned invalid output, or the output failed the grounding guard |

## Tests

AI-01 … AI-12 (`tests/modules/ai/`): masking (unit); grounding (unit); feature registry and settings parsing (unit); `run_feature` with the fake: success + audit row, draft created only for decision features, disabled feature, role refused, cap reached (no provider call), provider error audited, invalid output audited, guard block audited, nothing masked-out reaches the provider; audit rows cannot be updated or deleted; draft accept / edit / reject, wrong role 403, second decision 409, other shop 404; usage endpoint; the harness catches an invented amount and a leaked reference.
