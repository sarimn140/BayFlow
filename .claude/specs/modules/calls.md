# Module: calls

**Status:** Draft
**Package:** `app.modules.calls`
**Owns tables:** `call_logs`, `ai_call_summaries`, `tasks` (glossary §7; spec 05 §7 is authoritative for their columns)
**Priority:** **P2 — bonus track** (brief §8). Started only after the core works end to end on the live URL: spec 14's default gate is the PH7 exit (D36). Blank `CALL_PROVIDER_*` variables disable it and the core keeps working.
**Authority:** [spec 05](../05-calling-and-ai-front-desk.md) owns the behaviour. This file maps it onto the module's code: files, service functions, routes, events, checks and tests. If the two ever differ, spec 05 wins and this file is corrected.

## Purpose

The API side of in-app calling (brief §8.1) and of the AI Front Desk (brief §8.2): the single source of truth for call state, LiveKit rooms, tokens and agent dispatch, the internal endpoints the agent's tools call, call summaries and the SA's tasks. Brief §8.1: a call button on the booking page for both parties, no shared phone numbers, browser voice through a provider such as LiveKit, an incoming popup with accept/decline, states ringing / connected / ended / missed, a call log against the booking (who, when, duration, outcome), and a recorded missed call that can trigger the AI. Brief §8.2: after a set time (20 s) the AI answers, identifies the caller (name, phone, e-mail or booking reference), answers from real booking data through tool calls, handles simple requests, never invents data, and leaves a summary (intent, details, sentiment) and a Task linked to the booking and the call log, shown in an SA dashboard section with mark-as-done. Evidence: brief §8.3 and the §6 bonus path. The agent worker itself (`apps/agent`, its prompt and tools) is spec 05 §2 and §4–§6, not this module.

## In scope (all P2)

- Call lifecycle C1–C6 for both directions, first accept wins, idempotent hang-up (spec 05 §3.1–§3.4).
- Ring set from presence (§3.3); ring timer + DB deadline + sweeper (§3.5, D77).
- LiveKit: one room per call `call-<call_id>`, per-user audio-only tokens, explicit agent dispatch, signed webhook (§2, §8.3, §8.5).
- The AI leg A1–A6 (§3.7): dispatched on `NO_ANSWER` or `DECLINED` for customer → shop calls only; the call stays `MISSED` (D58).
- Agent endpoints `/api/v1/internal/calls/{call_id}/…` with service token, per-call token, AI-call check, time window, identity gate and call-row scope (§5.1, §5.3); caller verification (§4.2).
- Summaries (§6.3), tasks (§6.4), the tasks panel API and mark-done (§6.5, §8.2).
- Usage limits (§11.3): call-start rate limit, monthly participant-minutes cap, AI daily cap, duration limits.
- Events `CallStateChanged`, `AiTaskCreated` (rows and pushes are the notifications module's).

## Out of scope

Everything in spec 05 §1.3 (phone numbers/SIP/PSTN, recording, video, live AI → human transfer, outbound AI calls, SMS/WhatsApp, summaries of human calls, Urdu by default); the agent's prompt, tools and summary model (`apps/agent`); retention and deletion of transcripts (spec 13); manual tasks created by staff (`tasks.booking_id` is nullable only for that future case); a reschedule booking action (spec 05 open question 3).

## Key decisions

| D | What it means here |
|---|---|
| D57 | LiveKit Cloud, one room per call, the API owns state in `call_logs` and issues tokens; customer → shop calls ring every online SA, first accept wins. |
| D58 | `bayflow-front-desk` agent dispatched into the same room with metadata `{call_id, booking_id, customer_user_id, call_token}` (only the token's SHA-256 is stored); internal routes need `AGENT_SERVICE_TOKEN` + `X-Agent-Call-Token`; scope from the call row; data refused until the caller is verified; the call stays `MISSED`; the agent's summary becomes `ai_call_summaries` + `tasks`. |
| D77 | A customer → shop call rings for the full `AI_RING_TIMEOUT_SECONDS` (default 20) even when nobody is online, unless every rung SA declines first. |
| D78 | The incoming-call panel is non-modal and stacks up to 3 calls: the API lets several calls ring the same SA at once (one active call per **booking**, not per callee). |
| D69 | Call starts: 5 per caller per 10 minutes → 429 `RATE_LIMITED`, counted from `call_logs`. |
| D21 | Calls and tasks are SA and Owner data; customers see only their own calls on their own bookings, never summaries, transcripts or tasks. |
| D26 | `CALL_MISSED`: customer → shop → the SAs of the shop (Owner fallback); shop → customer → the customer (glossary §6). |
| D14, D70 | Pushes (`call.incoming`, `call.updated`, `task.created`) go through the notifications hub after commit; presence (`rung_user_ids`) comes from the same hub. |
| D88 | That hub, `GET /api/v1/realtime/ticket` and `/api/v1/ws` are P1; calling cannot work without them, so they are live before B1 starts (spec 05 B0). |
| D86 | Calls reads bookings through ordinary service calls (it sits above bookings), so it needs no read port; its own injected ports (`CallMediaGateway`, `Presence`) are wired at start-up like shops' `ShopActivityReader` (`shops.service.register_activity_reader`) and inventory's `BookingRefReader` (`inventory.service.register_booking_ref_reader`). |
| D89 | `router.py` exports `routers`; `app.main.wire_modules()` includes them (calls is last in `MODULES`) and the module never edits `app/main.py`. Calls has no `handlers.py`. How the conditional webhook and internal routers and the two injected ports fit this convention is Open question 2. |
| D63 | `started_at`, `ring_deadline`, every `*_at`, rate windows and sweeper limits use the app clock; the sweeper passes `clock.now()` into its queries. |
| D61, D36 | Token-bearing responses are `no-store`; every bonus feature is off while its variables are blank. |
| D20, D29, D74, D75 | Composite tenant FKs; enums in `app.shared.enums`; tests `CALL-xx`, `FD-xx`, `AG-xx`. |

## Files

| File | Contents |
|---|---|
| `router.py` | Customer routes under `/api/v1/me` and staff routes on `shop_scoped_router(tags=["calls"])` — always mounted, so the OpenAPI export never depends on environment variables; the webhook `POST /api/v1/webhooks/livekit` (`include_in_schema=False`), mounted only when calling is enabled. |
| `internal_router.py` | The ten agent routes (`include_in_schema=False`), mounted only when `AGENT_SERVICE_TOKEN` is set, and the `require_agent_call` dependency (spec 05 §5.1). |
| `schemas.py` | Spec 05 §8.3 / spec 03 §3.8: `CallRead`, `CallConnection`, `CallStartRead`, `CallDetailRead`, `TaskRead`; internal request/response models of §5.3 and §6.3. |
| `service.py` | Use cases below. |
| `repository.py` | `CallLogRepository` (lock by id, busy queries, sweeper claims with `FOR UPDATE SKIP LOCKED`, usage sums), `AiCallSummaryRepository`, `TaskRepository` (upsert per `(call_log_id, kind)`). |
| `models.py` | Already implemented: `CallLog`, `AiCallSummary`, `Task`. |
| `events.py` | `CallStateChanged`, `AiTaskCreated`. |
| `timers.py` | `schedule_ring_timeout`, `expire_ringing_call`, `sweep_once`, `run_sweeper` (spec 05 §3.5). |
| `constants.py` | `AI_JOIN_TIMEOUT_SECONDS` 10, `CALL_MAX_SECONDS` 900, `AI_MAX_CALL_SECONDS` 300, `SUMMARY_GRACE_SECONDS` 180, sweep interval 5 s, start limit 5 per 600 s, token TTL 120 s, summary window 600 s, transcript ≤ 300 entries / 200 KB, room options. |
| `providers/livekit.py` | `LiveKitGateway`: the `CallMediaGateway` port (`create_room`, `delete_room`, `create_dispatch`, `delete_dispatch`, `issue_token`) and the webhook receiver, on `livekit-api` with the `CALL_PROVIDER_*` values passed explicitly. |
| `domain/lifecycle.py` | Pure C1–C6 / A1–A6 guards and outcomes; `ai_leg_status(call)` (`AiLegStatus`, derived, never stored); the ring-set rule. |
| `domain/caller_match.py` | Spec 05 §4.2 normalisation and matching. |
| `domain/tasks.py` | Task titles and kinds (§6.4); the fallback summary. |
| `domain/usage.py` | Participant-minute formula; rate-window arithmetic. |

No `handlers.py`: the module subscribes to nothing.

## Public service interface

**Ports**, per app through `uow.app_state` (D90; the WebSocket and webhook routes use `request.app.state`): `CallMediaGateway` at `app.state.call_media`, created on first use by this module (tests use a fake, spec 05 §14.1), and `Presence` = the notifications hub at `app.state.realtime_hub` (`online_user_ids`), read duck-typed through this module's `Presence` protocol because calls may not import notifications; no hub yet means nobody is online. Feature flags `settings.calling_enabled` and `settings.ai_enabled` already exist in `app.core.config`.

**Use cases** (top-level; one transaction that locks only the `call_logs` row; LiveKit calls and timers run after commit). `actor` is a `CallActor(user_id, shop: ShopContext | None)`: the route family decides customer or staff.

| Function | Spec 05 | Returns | Raises |
|---|---|---|---|
| `start_customer_call(uow, user, booking_id, media, presence)` | C1, C2S | `CallStartRead` (caller's token) | 404, 503 `CALLING_DISABLED`, 429, 409 `CALL_BUSY` |
| `start_staff_call(uow, ctx, booking_id, media, presence)` | C1, S2C | `CallStartRead` | 404, 403, 503, 429, 409 `CALL_BUSY` |
| `answer_call(uow, actor, call_id, media)` | C2 | `CallStartRead` (callee's token) | 404, 403, 409 `CALL_ALREADY_ANSWERED` / `CALL_NOT_ACTIVE` |
| `decline_call(uow, actor, call_id)` | C3 (+A1) | `CallRead` | 404, 403, 409 `CALL_NOT_ACTIVE` |
| `end_call(uow, actor, call_id, media)` | C5, C6, A3; idempotent | `CallRead` | 404, 403 |
| `mark_task_done(uow, ctx, task_id, note)` | §6.5; idempotent | `TaskRead` | 404, 422 |

Reads: `list_my_booking_calls`, `list_booking_calls`, `list_shop_calls(status, direction, ai_handled, booking_id, page)`, `get_call_detail`, `list_tasks(status, kinds, page)`.

**System entry points** (own sessions; idempotent: each re-reads the locked row and does nothing if the state moved on): `expire_ringing_call(call_id)` (C4 + A1), `sweep_once(now)` (the five checks of §3.5), `dispatch_agent(call_id, call_token)` (A1's after-commit half; failure → A4), `on_livekit_event(event)` (webhook).

**Agent use cases** (internal router; writes lock the call row): `start_ai_session` (A2), `verify_caller`, `get_agent_shop`, `list_agent_bookings`, `get_agent_booking`, `get_agent_estimate`, `list_agent_slots`, `create_agent_task`, `end_ai_leg` (A3), `record_ai_summary` (A5).

**For notifications:** `get_call_read(session, call_id)` (base `CallRead`, no staff-only fields), `get_task_read(session, task_id)`, `list_ringing_calls_for_user(session, user_id)` (re-send on connect).

**Reads from other modules** (spec 05 §7.5): bookings ([bookings.md](bookings.md) §5): `get_staff_booking` (D21 visibility for staff routes), `get_customer_booking` (own booking), `find_customer_bookings` *(P2)* with the customer's `allowed_actions`, and the batch label read `get_booking_labels(session, *, shop_id, booking_ids)` for `CallRead` (`reference`, `vehicle_label`, `customer_user_id` per booking id; [bookings.md](bookings.md) §5.3, P2); estimates `get_customer_view` (the latest `SENT` / `APPROVED` / `REJECTED` version, its lines and whether a newer version is in progress); shops ([shops.md](shops.md) §5.2): `list_active_member_ids(roles)`, `get_owner_user_id`, `get_shop_briefs`, `get_shop_profile` *(P2, the agent's `GET /shop`)*; scheduling ([scheduling.md](scheduling.md)): `list_open_slots` and `is_slot_open` *(P2)*; identity `get_users_by_ids` (names; e-mail and phone are used only inside `verify_caller` and never returned).

## Endpoints

Customer and staff routes ([spec 03 §4.14](../03-api-contracts.md), spec 05 §8.1–§8.2):

| Method | Path | `operationId` | Who | Success |
|---|---|---|---|---|
| POST | `/api/v1/me/bookings/{booking_id}/calls` | `calls_start_my_call` | the booking's customer | 201 `CallStartRead` |
| GET | `/api/v1/me/bookings/{booking_id}/calls` | `calls_list_my_booking_calls` | the booking's customer | 200 `Page[CallRead]` |
| POST | `/api/v1/me/calls/{call_id}/accept` · `/decline` · `/end` | `calls_accept_my_call` · `calls_decline_my_call` · `calls_end_my_call` | the called customer / a participant | 200 `CallStartRead` · `CallRead` · `CallRead` |
| POST | `…/bookings/{booking_id}/calls` | `calls_start_call` | SA, O | 201 `CallStartRead` |
| GET | `…/bookings/{booking_id}/calls` | `calls_list_booking_calls` | SA, O | 200 `Page[CallRead]` |
| GET | `…/calls` | `calls_list_shop_calls` | SA, O | 200 `Page[CallRead]` |
| GET | `…/calls/{call_id}` | `calls_get_call` | SA, O | 200 `CallDetailRead` |
| POST | `…/calls/{call_id}/accept` · `/decline` · `/end` | `calls_accept_call` · `calls_decline_call` · `calls_end_call` | an eligible callee (an active SA of the shop, or the Owner only when the shop has no active SA; rung or not) · the same · a participant | 200 `CallStartRead` · `CallRead` · `CallRead` |
| GET | `…/tasks` | `calls_list_tasks` | SA, O (`tasks.manage`) | 200 `Page[TaskRead]` |
| POST | `…/tasks/{task_id}/mark-done` | `calls_mark_task_done` | SA, O | 200 `TaskRead` |

Not in OpenAPI: `POST /api/v1/webhooks/livekit` (LiveKit, signed) and the agent routes under `/api/v1/internal/calls/{call_id}`: `POST /session`, `POST /verify-caller`, `GET /shop`, `GET /bookings`, `GET /bookings/{reference}`, `GET /bookings/{reference}/estimate`, `GET /available-slots`, `POST /tasks`, `POST /end`, `POST /summary` (bodies and responses: spec 05 §5.3, §6.3).

## Domain rules and algorithms

### Lifecycle (spec 05 §3.2; guards in check order)

| ID | Trigger | Guards | Effects (one transaction) | After commit |
|---|---|---|---|---|
| C1 | start | booking visible (404) → staff role SA/Owner (403) → calling enabled and monthly cap not reached (503) → ≤ 5 starts in 10 min (429) → no active call for the booking, the caller or the called customer (409 `CALL_BUSY`) → `create_room(name, empty_timeout=60, departure_timeout=10, max_participants=3)` succeeds (else 503, nothing stored) | insert `RINGING` with `started_at = now`, `ring_deadline = now + AI_RING_TIMEOUT_SECONDS`, `rung_user_ids`, `room_name = call-<id>` (id generated first, D50), `customer_user_id` from the booking; a `uq_call_logs_one_active_per_booking` violation → 409 `CALL_BUSY` and the room is deleted | ring timer; `call.incoming` to rung users; caller's token in the response |
| C2 | accept | call visible (404) → eligible callee (403) → still `RINGING` (else 409 `CALL_ALREADY_ANSWERED` when `CONNECTED`, `CALL_NOT_ACTIVE` otherwise) | `CONNECTED`, `answered_by_user_id`, `answered_at` | cancel the timer; `call.updated`; callee's token |
| C3 | decline | eligible callee (rung or not, spec 05 CALL-15; else 403) → `RINGING` (else 409 `CALL_NOT_ACTIVE`) | add to `declined_user_ids`; only when `rung_user_ids` is non-empty and every rung user has declined: `MISSED` / `DECLINED`, `ended_at`; customer → shop: A1 (a non-rung decline never ends the call) | `call.updated`; dispatch or delete the room |
| C4 | timer or sweeper, `now ≥ ring_deadline` | still `RINGING`, else nothing | `MISSED` / `NO_ANSWER`, `ended_at`; customer → shop: A1 | as C3 |
| C5 | caller ends while ringing, or a webhook says the caller left | caller | `MISSED` / `CALLER_HUNG_UP`, `ended_at`, `ended_by_user_id`; **no AI** | delete the room; `call.updated` |
| C6 | a participant ends, the other side disconnects, a webhook, or the sweeper after `CALL_MAX_SECONDS` | participant (403 otherwise); already `ENDED` → 200 unchanged | `ENDED`, `ended_at`, `duration_seconds = ended_at − answered_at`, `ended_by_user_id` (NULL for the system) | delete the room; `call.updated` |

**Who is rung (§3.3).** Customer → shop: eligible = the SAs of the shop (active SAs; none → the Owner, D26); rung = eligible ∩ `presence.online_user_ids(…)` minus anyone in a `CONNECTED` call and minus the caller. Only an **eligible callee** may **accept** or **decline** — any active SA, or the Owner when the shop has no active SA — whether or not they were rung (spec 05 §3.3, C2, C3; a non-rung SA who opens the POS mid-ring receives `call.incoming` on connect). Shop → customer: the customer, if online. An empty ring set never ends the call early (D77); `rung_count` lets the UI say "No advisor is online right now".

**Busy (C1).** A user is busy when they are the caller or answerer of a `RINGING` / `CONNECTED` call, or the customer of a call whose AI leg is open (`ai_dispatched_at IS NOT NULL AND ai_ended_at IS NULL`); a booking is busy under the same predicate as the partial unique index.

**Ring timeout (§3.5).** C1 writes `ring_deadline`, the only truth. After commit `schedule_ring_timeout` starts an `asyncio` task (kept in a module-level dict until done) that sleeps until the deadline and calls `expire_ringing_call`, which opens its own session, locks the row and applies C4 (+A1) only if it is still `RINGING` and `ring_deadline ≤ now`. The lifespan starts `run_sweeper` (when calling is enabled): at boot and every 5 s, each check in its own transaction with `FOR UPDATE SKIP LOCKED`: (1) `RINGING` past its deadline → `expire_ringing_call`; (2) AI leg `CONNECTING` for more than `AI_JOIN_TIMEOUT_SECONDS` → A4; (3) `CONNECTED` longer than `CALL_MAX_SECONDS` → C6 by the system; (4) AI leg `ACTIVE` longer than `AI_MAX_CALL_SECONDS + 60` → A3 with `ai_error = 'MAX_DURATION_BACKSTOP'`; (5) an answered AI leg ended more than `SUMMARY_GRACE_SECONDS` ago without a summary → A6. A crash delays a ringing call by about 5 s at most.

### The AI leg (§3.7; customer → shop only)

| ID | Effect |
|---|---|
| A1 | In the C3/C4 transaction, when `settings.ai_enabled` and today's AI legs (UTC day, all shops) < `AI_DAILY_CALL_CAP`: `ai_dispatched_at = now`; `call_token = secrets.token_urlsafe(32)` (43 characters) kept only in memory; `ai_call_token_hash` = its SHA-256 hex. After commit: `create_dispatch(agent_name="bayflow-front-desk", room="call-<id>", metadata={call_id, booking_id, customer_user_id, call_token})`, then `ai_dispatch_id` is stored in a short transaction; an exception → A4. AI disabled or capped: no leg, the room is deleted ("No one could answer — the shop has been notified"). |
| A2 | `POST /session`: only from `CONNECTING` (else 409 `CALL_NOT_ACTIVE`, the agent exits): `ai_answered_at = now`; returns `{shop: {name, city, timezone}, max_ai_seconds: 300}` and no customer data. |
| A3 | The customer ends, the agent calls `/end` (optional `error`, cut to 200 characters), a webhook reports the customer or the agent left, or the sweeper backstop: `ai_ended_at`, `ai_duration_seconds` (when answered), `ai_error`; delete the room; with an `ai_error` and no task yet → a `CALLBACK` task. |
| A4 | No session within 10 s, or the dispatch failed: `ai_ended_at`, `ai_error = 'AGENT_UNAVAILABLE'`; delete the dispatch and room (best effort); `CALLBACK` task "Missed call from {first_name} — AI Front Desk unavailable"; `AiTaskCreated`. |
| A5 | `POST /summary` (§6.3): lock the row; transcript ≤ 300 entries and ≤ 200 KB (else 422; the body cap is 256 KiB → 413); a summary already stored → 200 with it; set `ai_ended_at` if still null; validate the summary against the API's own model (lengths of §7.2/§7.3, enums) or store the fallback (`"Summary unavailable"`, `OTHER`, `NEUTRAL`, `is_fallback`); insert `ai_call_summaries`; when the call has no task yet: a `FOLLOW_UP` task (title = `follow_up_task_title`, urgent when `urgent` or `SAFETY_CONCERN`), or a `CALLBACK` task when the transcript has no customer speech; `AiTaskCreated` per new task. |
| A6 | Sweeper: fallback summary + `CALLBACK` task + `AiTaskCreated`. |

The call keeps `status = MISSED` during and after the leg (D58); `AiLegStatus` is derived: `NONE` (not dispatched), `CONNECTING`, `ACTIVE`, `ENDED` (ended without error), `FAILED` (ended with `ai_error`). The log reads "Missed (no answer) → AI Front Desk · 1:58".

### Agent endpoints (§5.1, §5.3)

`require_agent_call` checks, in order: `Authorization: Bearer <AGENT_SERVICE_TOKEN>` with `hmac.compare_digest` (401; session JWTs never accepted) → SHA-256 of `X-Agent-Call-Token` equals `ai_call_token_hash` (404) → the call has an AI leg (404) → time window: data and task routes only while `ai_ended_at IS NULL`, `/summary` until `ai_ended_at + 10 min` (409 `CALL_NOT_ACTIVE`; `/end` is idempotent) → identity gate for `bookings`, `bookings/{reference}`, `…/estimate` and `RESCHEDULE_REQUEST` tasks (403 `IDENTITY_NOT_VERIFIED`) → scope: every query uses the `shop_id` and `customer_user_id` **read from the call row**; every id in a request except the path's `call_id` is ignored; out of scope → 404.

- **`verify-caller` (§4.2):** at least one of `name`, `phone`, `email`, `booking_reference`, compared only with the dispatched customer, strongest first: reference (upper case, spaces and dashes removed, optional `BF`, `O→0`, `I`/`L→1`; one of this customer's bookings at this shop), e-mail (trimmed, case-insensitive), phone (last 10 digits of `users.phone`), name (full name, or first word within one edit of the stored first name). Success: `ai_identity_verified_at`, `ai_identity_method`; response adds `first_name` and `call_booking_reference`. Failure: `ai_identity_attempts + 1`; `locked` at 3; a failed response never contains a stored value. Already verified → verified again, attempts unchanged.
- **Reads:** booking list (≤ 10, newest first), booking view and estimate view exactly as spec 05 §5.3 (customer-facing status label, `appointment_local` in the shop's time zone, customer `allowed_actions`, only `SENT` / `APPROVED` / `REJECTED` estimate versions, `revision_in_progress`, money as whole-rupee strings); never internal notes, QC issues, part costs, stock, suppliers, staff contacts or other customers. Slots: `scheduling.list_open_slots(shop_id, date_from, days 1–7, limit 12)` → `{start, start_local}` (D37); a reschedule's `preferred_starts` are re-checked with `scheduling.is_slot_open` (never held or booked).
- **`POST /tasks`:** kinds `CALLBACK`, `RESCHEDULE_REQUEST` (verified caller, in-scope reference, 1–3 `preferred_starts` still available → else 403 / 404 / 422), `ESCALATION` (urgent; allowed unverified). The API composes titles (§6.4: "Call back {first_name} about {topic}", "Reschedule request from {first_name} ({reference})", "URGENT: {first_name} — {reason}"); `first_name` comes from the database. One task per `(call_log_id, kind)`: a repeat updates description and metadata → 200 `{task_id, created: false}`; a new task → 201 `{task_id, created: true}` and `AiTaskCreated` (urgent tasks reach the SAs during the call). The booking and its slot are never changed (FD-07).

### Tokens, rooms and limits

- Token (§8.3): `AccessToken(key, secret).with_identity("u_<user_id>").with_name(display_name).with_ttl(2 min).with_grants(VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=True, can_publish_data=False, can_publish_sources=["microphone"]))`; `CallConnection = {url: CALL_PROVIDER_URL, room, token, identity, expires_at = now + 2 min}`. A callee gets a token only after accepting.
- Start limit: calls with this `caller_user_id` and `started_at > now − 600 s` ≥ 5 → 429 with `Retry-After` = seconds until the oldest of them leaves the window.
- Monthly cap: Σ over this UTC month's calls of ringing seconds × 1 + `duration_seconds` × 2 + `ai_duration_seconds` × 2, rounded up to minutes, ≥ `CALL_MONTHLY_MINUTES_CAP` → 503 (assumes the self-hosted agent counts as a participant, spec 05 §11.1).
- Webhook (§8.5): `WebhookReceiver(TokenVerifier(key, secret)).receive(raw_body, authorization)`; failure → 401 and nothing processed. `participant_left` / `participant_connection_aborted`: the caller while `RINGING` → C5; a participant while `CONNECTED` → C6 (`ended_by` NULL); the customer or the agent while the AI leg is open → A3. `room_finished`: `CONNECTED` → C6, open AI leg → A3, `RINGING` → ignored (the timer settles it). Rooms not named `call-<uuid>` and unknown calls are ignored with 200.

### Views

`CallRead` (§8.3): `caller {user_id, display_name}`, `callee_label` (customer → shop: the shop's name; shop → customer: the customer's name), `answered_by`, `rung_count`, `vehicle_label`, `booking_reference`, `shop_name`, timestamps, `ai` (null when `NONE`). Staff lists and detail add `has_summary` and `open_task_count`. **No phone number or e-mail in any call or task object** (CALL-14). Lists: calls by `started_at DESC, id DESC` (filter `ai_handled` = `ai_answered_at IS NOT NULL`); tasks `OPEN` by default, urgent first, then newest. `mark-done` on a `DONE` task returns it unchanged (the first closer is kept).

## Events

| Event | Published when | Payload (`occurred_at` from the base) | Consumer |
|---|---|---|---|
| `CallStateChanged` | Every change a client must see: C1–C6 and the AI-leg changes A1–A4 (A1 shares one event with its C3/C4) | `shop_id`, `call_id`, `booking_id`, `direction`, `previous_status` (null for C1), `status`, `missed_reason`, `ai_status` (`AiLegStatus`), `caller_user_id`, `customer_user_id`, `answered_by_user_id`, `rung_user_ids` | notifications: `CALL_MISSED` rows when `previous_status = RINGING` and `status = MISSED` (text says "answered by the AI Front Desk" when `ai_status ≠ NONE`); after commit `call.incoming` (C1) or `call.updated` |
| `AiTaskCreated` | A new task from A3, A4, A5, A6 or `POST /tasks` (not on an update) | `shop_id`, `task_id`, `call_id`, `booking_id`, `booking_reference`, `kind`, `title`, `is_urgent` | notifications: `AI_TASK_CREATED` rows for the SAs of the shop; after commit `task.created` |

Subscribes to nothing. No core module imports this package; notifications registers its call handlers only when the package exists (see [notifications.md](notifications.md)).

## Permissions and visibility

Spec 04 RBAC E:

| Capability | Customer | O | SA | T | PP | QC |
|---|---|---|---|---|---|---|
| Start a call from a booking | own booking (to the shop) | ✅ (to the customer) | ✅ | 403 if the booking is visible, else 404 | same | same |
| Accept / decline a ringing call | shop → customer calls to them | customer → shop calls, only when the shop has no active SA (then the Owner is the eligible callee) | customer → shop calls (rung or not) | 404 | 404 | 404 |
| Hang up | as a participant | as a participant | as a participant | — | — | — |
| Call logs | own calls on own bookings | all of the shop | all of the shop | 403 (collections) / 404 (items) | same | same |
| Summaries and transcripts | never | read | read | — | — | — |
| Tasks, mark done (`tasks.manage`) | never | ✅ | ✅ | 403 / 404 | same | same |

Customer routes are scoped by `call_logs.customer_user_id = me` (another customer's call or booking → 404). The agent is never a user: it reaches data only through the internal routes, read-only except tasks (spec 04 threats 26, 28).

## Errors

| Code | HTTP | When |
|---|---|---|
| `CALLING_DISABLED` | 503 | `CALL_PROVIDER_*` blank, LiveKit unreachable or out of quota, monthly cap reached. A blank `LLM_API_KEY` or a reached `AI_DAILY_CALL_CAP` never fails a call: there is just no AI leg |
| `CALL_BUSY` | 409 | The booking, the caller or the called customer already has an active call |
| `CALL_ALREADY_ANSWERED` | 409 | Another callee accepted first |
| `CALL_NOT_ACTIVE` | 409 | Accept/decline when no longer ringing; agent routes outside the AI leg's window; `/session` when not `CONNECTING` |
| `IDENTITY_NOT_VERIFIED` | 403 | Agent booking, estimate or reschedule routes before `verify-caller` succeeded |
| `RATE_LIMITED` | 429 | 6th call start within 10 minutes (`Retry-After`) |
| `FORBIDDEN` | 403 | Wrong role on a visible resource; not an eligible callee; not a participant |
| `NOT_FOUND` | 404 | Not visible; wrong per-call token; not an AI call; out of the call's scope |
| `UNAUTHENTICATED` | 401 | No session; wrong service token; bad webhook signature |
| `VALIDATION_ERROR` / `PAYLOAD_TOO_LARGE` | 422 / 413 | Bad bodies; transcript limits; summary body over 256 KiB |

## Concurrency and transactions

- Every change locks only its `call_logs` row (`SELECT … FOR UPDATE`, the QC-pick pattern of D30); calls code never locks a booking, so it cannot deadlock with booking actions (§3.9).
- First accept wins (CALL-03); accept, decline, hang-up, the timer and webhooks race on the same row lock and the first commit wins, the others find a non-`RINGING` row.
- One active call per booking is enforced by `uq_call_logs_one_active_per_booking` (CALL-11 → 409 `CALL_BUSY`).
- The sweeper claims rows with `FOR UPDATE SKIP LOCKED`, safe even with more than one replica.
- Network calls (LiveKit) run after commit, except `create_room` in C1, which happens before the insert while no row lock is held.
- Task upserts rely on `uq_tasks_one_per_call_and_kind`; summaries on `uq_ai_call_summaries_call_log_id`; mark-done locks the task row.

## Tests

- **Must pass (spec 05 §14, spec 04, spec 12):** CALL-01 … CALL-16 (spec 05's CALL-15 is D77's empty ring set incl. a decline by a non-rung SA; CALL-16 is D78's web panel test), FD-01 … FD-12, SEC-36, SEC-49, SEC-50, NOT-13 (with notifications); AG-01 … AG-03 in `apps/agent` CI, AG-04 … AG-06 by hand before the demo; the §14.3 scripted demo call three times on the live site. All use a fake `CallMediaGateway` and the `SimulatedClock`.
- **Proposed additions** (numbered after spec 05's CALL-16, as spec 12 §5 adopted them; CALL-21 is new):

| ID | Test |
|---|---|
| CALL-17 | D77: a customer → shop call with nobody online rings the full `AI_RING_TIMEOUT_SECONDS`, then dispatches the AI — the same subject as spec 05's CALL-15, so it is implemented once (spec 12 records the ID) |
| CALL-18 | A socket that connects while a call is `RINGING` for that user receives `call.incoming` again |
| CALL-19 | Accept pushes `call.updated` to every rung user (their pop-ups close) and to the caller |
| CALL-20 | With `CALL_PROVIDER_*` blank: both start routes → 503, nothing stored; the OpenAPI document still lists the 14 call and task operations |
| CALL-21 | Eligibility (spec 05 §3.3): an active SA who was not rung can accept a ringing customer → shop call (200); the Owner of a shop that has an active SA gets 403 on accept and decline; with no active SA the Owner is the eligible callee and may accept |
| FD-13 | A repeated task kind for the same call updates the description and returns 200 `created: false` with no new `AI_TASK_CREATED` |
| FD-14 | An AI leg that ends with an `ai_error` creates exactly one `CALLBACK` task |
| FD-15 | Monthly-minutes formula (unit) and the 503 when it is reached |

## Implementation checklist

Spec 05 §16, after the PH7 gate (B0):

1. **B1 (PH8):** `domain/lifecycle.py`, `constants.py`, `CallMediaGateway` + fake, `LiveKitGateway`; start/accept/decline/end, ring timer, sweeper (lifespan), `CallStateChanged`; notifications' call handlers (`CALL_MISSED`, `call.*`, re-send on connect); presence from the hub (the P1 hub must already be live, D88). CALL-01 … CALL-12, CALL-15 (= CALL-17), CALL-18, CALL-19 and CALL-21 green.
2. **B2:** web `CallProvider`, call button, incoming panel (D78), in-call bar, booking call log (specs 09/10).
3. **B3:** webhook, max-duration limits, rate limit, monthly cap; CALL-13, CALL-14, CALL-20, FD-15.
4. **B4 (PH9):** A1 dispatch, `/session`, A4 fallback; `apps/agent` service on Railway.
5. **B5:** `internal_router.py`, `domain/caller_match.py`, all agent reads, `POST /tasks`; FD-01 … FD-09, FD-13.
6. **B6:** summary (A5, A6), tasks API, mark-done, `AiTaskCreated`; FD-10 … FD-12, FD-14; the AI calls and tasks panel (B-04).
7. **B7:** AG-04 … AG-06, three scripted runs, the demo video (spec 05 §15).

The three tables (and `ix_users_phone`) already exist in the implemented baseline migration, so no migration is needed when P2 starts (see Open questions).

## Dependencies (specs)

- [05-calling-and-ai-front-desk.md](../05-calling-and-ai-front-desk.md) (authoritative); [17-decisions.md](../17-decisions.md) D14, D20, D21, D26, D33, D36, D37, D41, D57, D58, D61, D63, D69, D70, D74, D75, D77, D78, D84, D86, D88, D89; [18-glossary.md](../18-glossary.md) §1, §5, §6, §9–§12.
- [03-api-contracts.md](../03-api-contracts.md) §3.8, §4.14; [02-data-model.md](../02-data-model.md) §3.21; [04-auth-and-security.md](../04-auth-and-security.md) RBAC E, "AI agent and LiveKit webhook", threats 26–29; [01-architecture.md](../01-architecture.md) event catalogue; [07-deployment-and-docs.md](../07-deployment-and-docs.md) agent service, variables; [12-quality-and-testing.md](../12-quality-and-testing.md) bonus index; [14-roadmap.md](../14-roadmap.md) PH8, PH9.
- Other modules: [notifications.md](notifications.md) (rows, pushes, presence), [bookings.md](bookings.md), [shops.md](shops.md), [scheduling.md](scheduling.md), [identity.md](identity.md), estimates (`get_customer_view`).

## Open questions

1. ✅ **Resolved in spec 01 (its open question 13): `CallStateChanged` for AI-leg changes.** It is also published for A1–A4 while the call stays `MISSED`, with `previous_status` and `ai_status` in the payload, so the caller's UI gets `call.updated`.
2. ✅ **Resolved by D104 (2026-10-10): conditional routers and the sweeper.** Every router is always mounted; the webhook and the agent routes answer 404 while their variables are blank; the sweeper runs from the module's `lifespan.py`. Original question — **Ports and D89 wiring.** *Ports: ✅ resolved by D90* (per-app objects on `app.state`, reached through `uow.app_state`; see Public service interface). *Still open:* the conditional routers below. `CallMediaGateway` (spec 05 §14.1) and `Presence` (the notifications hub) must be injected at start-up. D86 names the read ports (`ShopActivityReader` with `shops.service.register_activity_reader`, `BookingRefReader` with `inventory.service.register_booking_ref_reader`) but not these two, and D89's `wire_modules()` passes nothing to a module (`register_ports()` takes no argument, `handlers.register(bus)` only the bus) and includes every router in `router.routers`, so the webhook (only when calling is enabled) and `internal_router.py` (only when `AGENT_SERVICE_TOKEN` is set) must be decided when `routers` is built. Same question as `modules/notifications.md` Open question 7; spec 01 and the glossary should list both ports next to the D86 ports.
3. ✅ **Resolved by D84: migration timing.** The single baseline migration (`23165172278b`, "baseline schema") already creates `call_logs`, `ai_call_summaries`, `tasks` and `ix_users_phone`, so P2 needs no migration; spec 02 (§3.21, §9) and spec 05 (B1, B6) say so.
4. ✅ **Resolved: screen specs.** Spec 10 B-01 now describes the non-modal stacked panel (D78, spec 05 §9.3), and spec 06 B4 uses `GET …/calls` / `GET …/calls/{call_id}` and `POST …/tasks/{task_id}/mark-done`.
5. **Declined shop → customer calls.** Spec 05 §3.8 sends `CALL_MISSED` to the customer for every missed shop → customer call, including one the customer declined. Kept literally; the web may skip the toast for a call the user declined.
6. **AI leg ended before the agent joined.** A customer who hangs up while the leg is `CONNECTING` ends it without an error, so no task is created (A3 makes one only on `ai_error`, A6 only for answered legs). The SAs still get `CALL_MISSED`. Should spec 05 add a `CALLBACK` task here?
7. ✅ **Resolved: who may accept or decline.** An earlier draft of this spec let the Owner accept any customer → shop call (D16) and limited decline to rung users. Spec 05 §3.3 (authoritative) allows both only to an eligible callee — any active SA, or the Owner when the shop has no active SA — rung or not; this spec, spec 03 §4.14 and spec 04 RBAC E now say so (CALL-21).

## Proposed glossary additions

| Kind | Name | Meaning |
|---|---|---|
| Files | `internal_router.py`, `timers.py`, `constants.py`, `providers/` | Extra module files of spec 01/05, not in glossary §7's list |
| Ports | `CallMediaGateway` (`app.state.call_media`; proposed by spec 05), `Presence` | LiveKit adapter; presence from the notifications hub |
| Event payloads | `CallStateChanged` (`previous_status`, `status`, `missed_reason`, `ai_status`, `rung_user_ids`, …), `AiTaskCreated` (`task_id`, `kind`, `title`, `is_urgent`, …) | Spec 01 left them to spec 05 |
| Service functions | `start_customer_call`, `start_staff_call`, `answer_call`, `decline_call`, `end_call`, `expire_ringing_call`, `sweep_once`, `dispatch_agent`, `on_livekit_event`, `get_call_read`, `get_task_read`, `list_ringing_calls_for_user`, `CallActor` | Refine spec 01's "defined in spec 05" list |
| Constants | Spec 05 §3.5's four limits plus the start limit (5 per 600 s), token TTL (120 s), summary window (600 s), transcript limits | `app/modules/calls/constants.py` |
| Cross-module read (P2) | `get_booking_labels(session, *, shop_id, booking_ids)` → `reference`, `vehicle_label`, `customer_user_id` | ✅ adopted by `modules/bookings.md` §5.3; batch data for `CallRead` lists without N+1 |
| Test IDs | CALL-21 (numbered in spec 12 §5; listed in spec 05 §14.1); CALL-17 … CALL-20 and FD-13 … FD-15 are adopted by spec 12 §5 and spec 05 §14.1 | For spec 12's bonus index |
