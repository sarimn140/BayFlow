# 18 — Glossary & Canonical Names

**Status:** ✅ Locked (foundation spec) — consolidated 2026-10-09 after the first spec wave (see "Change log")

## Purpose

The single source of truth for every name used in BayFlow: roles, statuses, actions, tables, modules, error codes, events, environment variables and API path patterns. **Every other spec, and later the code, MUST use these exact spellings.** If a spec needs a name that is not here, it must list it under a "Proposed glossary additions" heading in that spec instead of silently inventing it; the reviewer merges approved additions into this file.

Source of truth for requirements: `helping-folder/Web Dev - Virtual.pdf` (BayFlow Hackathon Brief v1.1, October 2026). Section numbers such as "§5.2" refer to that brief. Decisions are cited as "Dnn" from [17-decisions.md](17-decisions.md).

---

## 1. Domain terms

| Term | Meaning |
|---|---|
| **Tenant** | A **shop**. Every shop-owned record carries `shop_id`, and every query on shop-owned data is scoped by it (§3 "What multi-tenant means here"). |
| **Shop-owned record** | Any row that belongs to exactly one shop: memberships, working hours, services, slot counters, bookings, booking services, booking events, estimates, estimate lines, parts, stock movements, booking parts, purchase orders, PO items, QC inspections, QC issues, and (bonus) call logs, AI call summaries, tasks. |
| **User** | One login account (`users` row). A user may be a customer, staff in one or more shops, an owner of one or more shops, or any mix. |
| **Customer** | A user acting on their *own* bookings. Customers are **global** (not tied to a shop) and can book at any shop (§3). "Customer" is not a membership role. |
| **Membership** | The link between a user and a shop with exactly **one** role (`shop_memberships` row). Roles are scoped per shop (§4 Access rules; FAQ "one role per shop membership"). |
| **Staff** | A user with an active membership in a shop whose role is not `OWNER`. |
| **Booking** | One service visit for one vehicle at one shop, moving through the booking state machine (spec 08). |
| **Booking reference** | Short human-readable code shown to customers and staff, format `BF-XXXXXX` (6 chars, Crockford base32 alphabet `0123456789ABCDEFGHJKMNPQRSTVWXYZ`). Used for phone/AI lookup. Random codes must never start with `SEED` (reserved for seed data, §14). |
| **Slot** | A fixed-length appointment window on the shop's grid: the grid is anchored at local midnight and steps by `slot_duration_minutes`; working hours select which grid slots are open (D37). Not stored as rows; only booked counts are stored in `slot_counters`. |
| **Slot capacity** | Max bookings allowed to start in the same slot at one shop (`shops.slot_capacity`). The number of places still free in a slot is called **`remaining`** (never "available", which is reserved for stock). |
| **Estimate** | One *version* of the cost estimate for a booking (`estimates` row). A booking can have several versions; at most one is open (`DRAFT`, `SUBMITTED` or `SENT`). |
| **Estimate line** | One item on an estimate: a `PART` (from the shop's parts catalogue) or `LABOUR`. |
| **Revision / version** | `estimates.version` (1, 2, 3 …). Satisfies "estimate versioning or at least a revision count" (§7.5). |
| **Part** | An inventory item in one shop's catalogue (`parts` row) with `on_hand` and `reserved` quantities. New parts start at `on_hand = 0` (D44). |
| **Available quantity** | `parts.on_hand − parts.reserved`. Never stored; always computed. |
| **Reservation** | Holding stock for a specific booking (`reserved` goes up; `on_hand` unchanged). |
| **Allocation** | The Parts Person's `ALLOCATE_PARTS` action: reservations are **consumed** (`on_hand` and `reserved` both go down) and linked to the booking. "Allocation decreases it" (§7.6). |
| **Release** | Returning reserved stock to available (on cancellation). |
| **Stock movement** | Append-only ledger row recording every stock change (`stock_movements`). |
| **Purchase order (PO)** | An order to a supplier for parts (`purchase_orders` + `purchase_order_items`), optionally linked to one booking. |
| **QC inspection** | One QC attempt on a booking (`qc_inspections` row): who picked it, checklist, notes, result. |
| **QC issue** | A problem recorded by a failed QC inspection (`qc_issues` row); returns the job to the technician (§5.3). |
| **Booking event** | Audit-log row for every transition and operation on a booking (`booking_events`): who, role, when, from, to, action, note (§7.5). |
| **Platform admin** | A BayFlow operator ("super admin"): a user with `is_platform_admin`, not a shop role; manages tenants and accounts from the admin console (D94, spec 19). |
| **Audit event** | One row of the platform-wide, append-only `audit_events` log: who did what to which target in which shop, when, from where (D95, spec 19 §3). |
| **Suspended shop** | A shop a platform admin has switched off with a reason: hidden publicly, closed to its staff, readable by its customers; fully reversible (D96). |
| **Shop membership gate** | The rule that a shop's pages and routes open only for an active member of that shop (D20, `require_shop_member`). Anyone else — another shop's staff, a customer, a platform admin without a membership — gets "We couldn't find that shop", with no sidebar and no shop name, exactly as for a shop that does not exist. Members then meet the suspension check (D96) and, per section, their role in this shop (spec 10 S-01, X-03). |
| **Read-only view** | A role's screen that the Owner opens to look, not act (D16): the Technician jobs, the parts queue and parts jobs, the purchase orders and the QC queue and inspection. The role's actions are hidden, and an `info` notice titled "Read-only view" says who acts and links to where the Owner can (Bookings, or Inventory). The Owner's inventory is **catalogue only** instead: parts can be added and edited, stock is never changed (D44). |
| **Notification** | In-app message shown under the bell icon with unread count (§5.4). |
| **Transition** | A booking action that changes `bookings.status`. |
| **Operation** | A booking action that does **not** change status (e.g. `START_REPAIR`, `NOTIFY_READY`) but is still role-guarded and audited. |
| **Allowed actions** | The list of action slugs the *current user* may perform on a booking right now, returned by the API so the UI never re-implements the rules. |
| **Capabilities** | The non-booking permissions of the current user in a shop (§7), returned per membership by `GET /api/v1/me` (D66). |
| **Clock** | The single source of "now" in the API (`app.shared.clock`): `SystemClock` in production, `SimulatedClock` in seed and tests (D63). |
| **Call log** *(bonus)* | One in-app call attempt (`call_logs`) with state, participants, duration, outcome (§8.1). |
| **AI leg** *(bonus)* | The part of a missed customer → shop call that the AI Front Desk answers; tracked in `call_logs.ai_*` columns (spec 05). |
| **AI call summary** *(bonus)* | Intent, details, sentiment and transcript produced after an AI Front Desk call (`ai_call_summaries`) (§8.2). |
| **Task** *(bonus)* | A to-do for Service Advisors created from an AI call (`tasks`), e.g. "Call back Ahmed about estimate" (§8.2). |

---

## 2. Roles

### 2.1 `MembershipRole` (stored in `shop_memberships.role`)

| Value | Display name | Notes |
|---|---|---|
| `OWNER` | Owner | Exactly one per shop. Created automatically when a user creates a shop. Cannot be deactivated or changed (403 `FORBIDDEN`, D19). |
| `SERVICE_ADVISOR` | Service Advisor (SA) | Front desk. |
| `TECHNICIAN` | Technician | Mechanic. |
| `PARTS_PERSON` | Parts Person | Inventory and procurement. |
| `QC_INSPECTOR` | QC Inspector | Quality control. |

`StaffRole` = `MembershipRole` without `OWNER` (the roles an owner can assign).

### 2.2 `ActorRole` (stored in `booking_events.actor_role` and `notifications.recipient_role`)

`CUSTOMER`, `OWNER`, `SERVICE_ADVISOR`, `TECHNICIAN`, `PARTS_PERSON`, `QC_INSPECTOR`, `SYSTEM`.

`SYSTEM` is used only for automated actions with no human actor — in practice the bonus AI Front Desk (tasks it creates). The seed script acts **as the real demo people** and never uses `SYSTEM`. No core booking transition is performed by `SYSTEM`.

### 2.3 Role tags (used in demo e-mail addresses)

`owner`, `sa`, `tech`, `parts`, `qc`, `customer`.

The UI shows roles by their §2.1 display name, never by tag: role chips are `brand` badges, and the POS bar's role pill shows only its icon on narrow screens, with the name in `sr-only` text (spec 09 §3.4, §4.1; D101).

### 2.4 Capabilities (D66)

Returned per membership by `GET /api/v1/me`, computed on the server from the role (D16, D44): `shop.manage` (Owner), `team.manage` (Owner), `services.manage` (Owner), `parts.manage` (Owner, Parts Person — catalogue), `stock.manage` (Parts Person — POs, receipts, adjustments), `tasks.manage` (bonus: Owner, SA — present only when the calls module is enabled).

---

## 3. Booking statuses (`BookingStatus`, stored in `bookings.status`)

17 values. The first 15 come from the brief's table (§5.2); `ESTIMATE_REJECTED` and `CANCELLED` appear as "Next" values in that table and are fully defined in spec 08. Staff labels are used in the POS, customer labels in the customer portal; phases group statuses for color and filters (spec 09).

| # | Value | Owner of step (§5.2) | Staff label | Customer-facing label | Phase | Terminal |
|---|---|---|---|---|---|---|
| 1 | `PENDING` | Service Advisor | Pending | Booking received | `INTAKE` | |
| 2 | `CONFIRMED` | Service Advisor | Confirmed | Booking confirmed | `INTAKE` | |
| 3 | `ASSIGNED` | Technician | Assigned | Technician assigned | `INSPECTION` | |
| 4 | `INSPECTING` | Technician | Inspecting | Inspection in progress | `INSPECTION` | |
| 5 | `ESTIMATE_REVIEW` | Service Advisor | Estimate review | Preparing your estimate | `ESTIMATE` | |
| 6 | `AWAITING_CUSTOMER` | Customer | Awaiting customer | Estimate awaiting your approval | `ESTIMATE` | |
| 7 | `ESTIMATE_APPROVED` | Service Advisor | Estimate approved | Estimate approved | `ESTIMATE` | |
| — | `ESTIMATE_REJECTED` | Service Advisor | Estimate rejected | Estimate declined — the shop will follow up | `ESTIMATE` | |
| 8 | `PARTS_PENDING` | Parts Person | Parts pending | Checking parts | `PARTS` | |
| 9 | `PARTS_ORDERED` | Parts Person | Parts ordered | Parts ordered | `PARTS` | |
| 10 | `PARTS_READY` | Parts Person | Parts ready | Parts ready | `PARTS` | |
| 11 | `IN_REPAIR` | Technician | In repair | Repair in progress | `REPAIR_QC` | |
| 12 | `QC_PENDING` | Any QC Inspector | QC pending | Waiting for quality check | `REPAIR_QC` | |
| 13 | `QC_IN_PROGRESS` | QC Inspector (picker) | QC in progress | Quality check in progress | `REPAIR_QC` | |
| 14 | `READY_FOR_PICKUP` | Service Advisor | Ready for pick-up | Ready for pick-up | `HANDOVER` | |
| 15 | `COMPLETED` | Customer / SA | Completed | Completed | `HANDOVER` | ✅ |
| — | `CANCELLED` | — | Cancelled | Cancelled | `CLOSED` | ✅ |

**Cancellable statuses** (customer or SA, "before IN_REPAIR", §5.3): `PENDING`, `CONFIRMED`, `ASSIGNED`, `INSPECTING`, `ESTIMATE_REVIEW`, `AWAITING_CUSTOMER`, `ESTIMATE_APPROVED`, `ESTIMATE_REJECTED`, `PARTS_PENDING`, `PARTS_ORDERED`, `PARTS_READY` (11 statuses).

---

## 4. Booking actions (`BookingAction`)

`Kind`: **T** = transition (changes status), **O** = operation (no status change). Priority per D36: P0 = mandatory core, P1 = recommended extra.
Endpoint pattern: staff → `POST /api/v1/shops/{shop_id}/bookings/{booking_id}/actions/{slug}`; customer → `POST /api/v1/me/bookings/{booking_id}/actions/{slug}`. Full rules (guards, side effects, notifications) live in spec 08.

| Enum value | Slug | Kind | From | To | Who may perform | Pri |
|---|---|---|---|---|---|---|
| `CREATE` | *(POST /api/v1/bookings)* | T | — | `PENDING` | Customer (new or existing account) | P0 |
| `CONFIRM` | `confirm` | T | `PENDING` | `CONFIRMED` | SA, Owner | P0 |
| `DECLINE` | `decline` | T | `PENDING` | `CANCELLED` | SA, Owner | P0 |
| `ASSIGN_TECHNICIAN` | `assign-technician` | T | `CONFIRMED` | `ASSIGNED` | SA, Owner | P0 |
| `START_INSPECTION` | `start-inspection` | T | `ASSIGNED` | `INSPECTING` | Assigned Technician | P0 |
| `EDIT_ESTIMATE` | `edit-estimate` (listed in `allowed_actions`; performed via `PUT /api/v1/shops/{shop_id}/bookings/{booking_id}/estimate`) | O | `INSPECTING` (tech) / `ESTIMATE_REVIEW` (SA, Owner) | same | Assigned Technician; SA, Owner | P0 |
| `SUBMIT_ESTIMATE` | `submit-estimate` | T | `INSPECTING` | `ESTIMATE_REVIEW` | Assigned Technician | P0 |
| `SEND_ESTIMATE` | `send-estimate` | T | `ESTIMATE_REVIEW` | `AWAITING_CUSTOMER` | SA, Owner | P0 |
| `APPROVE_ESTIMATE` | `approve-estimate` | T | `AWAITING_CUSTOMER` | `ESTIMATE_APPROVED` | Booking's Customer | P0 |
| `REJECT_ESTIMATE` | `reject-estimate` | T | `AWAITING_CUSTOMER` | `ESTIMATE_REJECTED` | Booking's Customer | P0 |
| `REVISE_ESTIMATE` | `revise-estimate` | T | `ESTIMATE_REJECTED` | `ESTIMATE_REVIEW` | SA, Owner | P0 |
| `RETURN_TO_TECHNICIAN` | `return-to-technician` | T | `ESTIMATE_REJECTED` | `INSPECTING` | SA, Owner | P0 |
| `ASSIGN_PARTS_PERSON` | `assign-parts-person` | T | `ESTIMATE_APPROVED` | `PARTS_PENDING` | SA, Owner | P0 |
| `ORDER_PARTS` | `order-parts` | T | `PARTS_PENDING` | `PARTS_ORDERED` | Assigned Parts Person | P0 |
| `MARK_PARTS_READY` | `mark-parts-ready` | T | `PARTS_PENDING`, `PARTS_ORDERED` | `PARTS_READY` | Assigned Parts Person | P0 |
| `RECEIVE_PARTS` | *(triggered by PO receive endpoint)* | T | `PARTS_ORDERED` | `PARTS_READY` | Parts Person who received the PO | P0 |
| `ALLOCATE_PARTS` | `allocate-parts` | T | `PARTS_READY` | `IN_REPAIR` | Assigned Parts Person | P0 |
| `START_REPAIR` | `start-repair` | O | `IN_REPAIR` | same | Assigned Technician | P0 |
| `SEND_TO_QC` | `send-to-qc` | T | `IN_REPAIR` | `QC_PENDING` | Assigned Technician | P0 |
| `PICK_QC` | `pick-qc` | T | `QC_PENDING` | `QC_IN_PROGRESS` | Any active QC Inspector of the shop | P0 |
| `PASS_QC` | `pass-qc` | T | `QC_IN_PROGRESS` | `READY_FOR_PICKUP` | QC Inspector who picked it | P0 |
| `FAIL_QC` | `fail-qc` | T | `QC_IN_PROGRESS` | `IN_REPAIR` | QC Inspector who picked it | P0 |
| `NOTIFY_READY` | `notify-ready` | O | `READY_FOR_PICKUP` | same | SA, Owner | P0 |
| `COMPLETE` | `complete` | T | `READY_FOR_PICKUP` | `COMPLETED` | SA, Owner, Booking's Customer | P0 |
| `CANCEL` | `cancel` | T | any of the 11 cancellable statuses | `CANCELLED` | Booking's Customer, SA, Owner | P0 |
| `REASSIGN_TECHNICIAN` | `reassign-technician` | O | `ASSIGNED`, `INSPECTING`, `IN_REPAIR` | same | SA, Owner | P1 |
| `REASSIGN_PARTS_PERSON` | `reassign-parts-person` | O | `PARTS_PENDING`, `PARTS_ORDERED`, `PARTS_READY` | same | SA, Owner | P1 |

---

## 5. Other enums

| Enum | Values | Stored in |
|---|---|---|
| `EstimateStatus` | `DRAFT`, `SUBMITTED`, `SENT`, `APPROVED`, `REJECTED`, `SUPERSEDED` | `estimates.status` |
| `EstimateLineType` | `PART`, `LABOUR` | `estimate_lines.line_type` |
| `StockMovementType` | `RECEIVE`, `RESERVE`, `RELEASE`, `CONSUME`, `ADJUST` | `stock_movements.movement_type` |
| `PurchaseOrderStatus` | `ORDERED`, `PARTIALLY_RECEIVED`, `RECEIVED` (exactly the brief's three, §7.6) | `purchase_orders.status` |
| `QcResult` | `PASS`, `FAIL` (NULL while in progress) | `qc_inspections.result` |
| `QcIssueStatus` | `OPEN`, `RESOLVED` | `qc_issues.status` |
| `QcChecklistKey` | `road_test`, `no_warning_lights`, `no_leaks`, `fluid_levels`, `complaint_resolved` (default checklist, D46) | `qc_inspections.checklist` (JSON keys) |
| `StatusPhase` | `INTAKE`, `INSPECTION`, `ESTIMATE`, `PARTS`, `REPAIR_QC`, `HANDOVER`, `CLOSED` (UI grouping only, not stored) | — |
| `NotificationType` | see §6 | `notifications.type` |
| `Weekday` | `0`=Monday … `6`=Sunday (ISO-8601 order, Monday first) | `shop_working_hours.weekday` |
| `CallStatus` *(bonus)* | `RINGING`, `CONNECTED`, `ENDED`, `MISSED` (the brief's four, §8.1). A missed customer → shop call answered by the AI **stays `MISSED`**; the AI leg is tracked separately. | `call_logs.status` |
| `CallDirection` *(bonus)* | `CUSTOMER_TO_SHOP`, `SHOP_TO_CUSTOMER` | `call_logs.direction` |
| `MissedReason` *(bonus)* | `NO_ANSWER`, `DECLINED`, `CALLER_HUNG_UP` | `call_logs.missed_reason` |
| `AiLegStatus` *(bonus, derived, not stored)* | `NONE`, `CONNECTING`, `ACTIVE`, `ENDED`, `FAILED` | API field `CallRead.ai.status` |
| `IdentityMethod` *(bonus)* | `NAME`, `PHONE`, `EMAIL`, `BOOKING_REFERENCE` | `call_logs.ai_identity_method` |
| `CallIntent` *(bonus)* | `STATUS_INQUIRY`, `ESTIMATE_INQUIRY`, `APPOINTMENT_INQUIRY`, `RESCHEDULE_REQUEST`, `PICKUP_INQUIRY`, `CALLBACK_REQUEST`, `COMPLAINT`, `SAFETY_CONCERN`, `OTHER` | `ai_call_summaries.intent_category` |
| `Sentiment` *(bonus)* | `POSITIVE`, `NEUTRAL`, `NEGATIVE` | `ai_call_summaries.sentiment` |
| `TaskKind` *(bonus)* | `CALLBACK`, `RESCHEDULE_REQUEST`, `ESCALATION`, `FOLLOW_UP` | `tasks.kind` |
| `TaskStatus` *(bonus)* | `OPEN`, `DONE` | `tasks.status` |
| `AiFeature` *(bonus, D103)* | `ESTIMATE_EXPLAINER`, `ESTIMATE_CHECKER`, `VOICE_TO_ESTIMATE`, `SYMPTOM_TRIAGE`, `ASK_YOUR_SHOP` | `ai_audit_events.feature`, `ai_drafts.feature` |
| `AiCallStatus` *(bonus, D103)* | `SUCCEEDED`, `PROVIDER_ERROR`, `INVALID_OUTPUT`, `GUARD_BLOCKED` | `ai_audit_events.status` |
| `AiDraftStatus` *(bonus, D103)* | `PENDING`, `ACCEPTED`, `EDITED`, `REJECTED` | `ai_drafts.status` |
| `AiSubjectType` *(bonus, D103)* | `BOOKING`, `ESTIMATE`, `SHOP` | `ai_audit_events.subject_type`, `ai_drafts.subject_type` |

All stored enums are `VARCHAR` with a `CHECK` constraint (non-native enums; D29).

---

## 6. Notification types (`NotificationType`)

"Minimum" = required by the brief's §5.4 table. "Extra" = our addition (P1, cheap, improves the demo).
"SAs of the shop" always means *all active `SERVICE_ADVISOR` members of that shop; if the shop has none, the `OWNER` instead* (D26). Every notification row stores the recipient's `recipient_role` and a server-computed deep `link` for that recipient (D67).

| Type | Fired by | Recipients | Brief |
|---|---|---|---|
| `BOOKING_CREATED` | `CREATE` | SAs of the shop | Minimum |
| `BOOKING_CONFIRMED` | `CONFIRM` | Booking's customer | Extra |
| `TECHNICIAN_ASSIGNED` | `ASSIGN_TECHNICIAN`, `REASSIGN_TECHNICIAN` | That technician | Minimum |
| `ESTIMATE_SUBMITTED` | `SUBMIT_ESTIMATE` | SAs of the shop | Minimum |
| `ESTIMATE_SENT` | `SEND_ESTIMATE` | Booking's customer (+ e-mail when configured, D26) | Minimum |
| `ESTIMATE_APPROVED` | `APPROVE_ESTIMATE` | SAs of the shop | Minimum |
| `ESTIMATE_REJECTED` | `REJECT_ESTIMATE` | SAs of the shop | Minimum |
| `ESTIMATE_RETURNED` | `RETURN_TO_TECHNICIAN` | Assigned technician | Extra |
| `PARTS_NEEDED` | `ASSIGN_PARTS_PERSON`, `REASSIGN_PARTS_PERSON` | That parts person | Minimum ("parts needed → Parts Person") |
| `PARTS_READY` | `ALLOCATE_PARTS` | Assigned technician | Minimum ("parts ready → Technician") |
| `QC_REQUESTED` | `SEND_TO_QC` | All active QC inspectors of the shop | Minimum ("Sent to QC → QC queue") |
| `QC_FAILED` | `FAIL_QC` | Assigned technician | Minimum |
| `QC_PASSED` | `PASS_QC` | SAs of the shop | Extra |
| `VEHICLE_READY` | `NOTIFY_READY` | Booking's customer (+ e-mail when configured, D26) | Minimum |
| `BOOKING_CANCELLED` | `CANCEL`, `DECLINE` | If staff cancelled: the customer. If the customer cancelled: SAs of the shop + assigned technician + assigned parts person | Extra |
| `CALL_MISSED` *(bonus)* | Call ends `MISSED` | Customer → shop call: SAs of the shop. Shop → customer call: the customer | Bonus |
| `AI_TASK_CREATED` *(bonus)* | AI Front Desk creates a task | SAs of the shop | Bonus |

---

## 7. Modules (backend, modular monolith) and the tables each owns

A module is the **only** code allowed to write its tables. Other modules call its service functions or react to its events (spec 01).

| Module | Python package | Owns tables |
|---|---|---|
| identity | `app.modules.identity` | `users` |
| shops | `app.modules.shops` | `shops`, `shop_working_hours`, `shop_memberships`, `services` |
| scheduling | `app.modules.scheduling` | `slot_counters` |
| bookings | `app.modules.bookings` | `vehicles`, `bookings`, `booking_services`, `booking_events` |
| estimates | `app.modules.estimates` | `estimates`, `estimate_lines` |
| inventory | `app.modules.inventory` | `parts`, `stock_movements`, `booking_parts`, `purchase_orders`, `purchase_order_items` |
| qc | `app.modules.qc` | `qc_inspections`, `qc_issues` |
| notifications | `app.modules.notifications` | `notifications` |
| reporting | `app.modules.reporting` | *(none — read-only queries)* |
| calls *(bonus)* | `app.modules.calls` | `call_logs`, `ai_call_summaries`, `tasks` |
| ai *(bonus)* | `app.modules.ai` | `ai_audit_events`, `ai_drafts` (D103) |

Cross-cutting packages (not modules):
- `app.core` — `config`, `database`, `db_errors` (constraint name → error code), `security` (`issue_token(…, now)`, `decode_token(token, now, expected_typ)`, `parse_duration`, `hash_password`, `verify_password`), `errors` (`ErrorCode`, `AppError`), `error_handlers`, `logging`, `middleware`, `health`.
- `app.shared` — `auth` (`get_current_user`, `get_optional_user`, `require_shop_member`, `require_roles`, `shop_scoped_router()` (D80), `CurrentUser`, `ShopContext`), `tenancy` (re-exports the shop-scoping pieces of `auth` under one name), `event_bus`, `uow` (`UnitOfWork`; `uow.app_state` = the app's `State`, D90), `pagination` (`Page`, `PageParams`, `ItemList`), `repository`, `money` (`Money`), `clock` (`Clock`, `SystemClock`, `SimulatedClock`, `get_clock()`, `utcnow()`), `email` (the project `Email` type, D62), `phone` (the project `Phone` type, D84), `timestamps` (`Timestamp`: UTC with `Z`), `enums` (every stored enum as a `StrEnum`, D74).

Wiring (D89): `router.py` exports `routers: tuple[APIRouter, ...]`; `handlers.py` exports `register(bus)`; `service.py` may export `register_ports()`; `app.main.wire_modules()` loads them in `MODULES` order. A module package uses these file names, creating only the ones it needs: `router.py`, `schemas.py`, `service.py`, `repository.py`, `models.py`, `events.py`, `handlers.py`, `domain/` (e.g. `estimates` has no router of its own).

### 7.1a Read ports (D86)

`ShopActivityReader` (defined by shops, registered with `shops.service.register_activity_reader`, implemented by `bookings.service.shop_activity_reader`) and `BookingRefReader` (defined by inventory, implemented by `bookings.service.get_booking_refs`). Registered by `create_app()` at startup through `wire_modules()` (D89).

### 7.1 Domain events (in-process event bus, spec 01)

`BookingActionApplied` (bookings), `PurchaseOrderReceiving` (inventory → lets bookings lock the booking first, D43), `PurchaseOrderReceived` (inventory), `ShopGridChanging` (shops → bookings may veto a slot-grid change while future bookings exist, D37), `BookingPartsChanged` (bookings → notifications pushes `booking.updated` after a partial receipt changes a booking's reservations, D83), and bonus `CallStateChanged`, `AiTaskCreated` (calls).

---

## 8. Table names (PostgreSQL, snake_case plural)

`users`, `shops`, `shop_working_hours`, `shop_memberships`, `services`, `slot_counters`, `vehicles`, `bookings`, `booking_services`, `booking_events`, `estimates`, `estimate_lines`, `parts`, `stock_movements`, `booking_parts`, `purchase_orders`, `purchase_order_items`, `qc_inspections`, `qc_issues`, `notifications`, and bonus: `call_logs`, `ai_call_summaries`, `tasks`, `ai_audit_events`, `ai_drafts`.

Key column names other specs rely on (full definitions in spec 02; bonus tables in spec 05 §7, which is authoritative for them):

- `users`: `id`, `email` (stored lower-case), `password_hash`, `full_name`, `phone`, `is_active`, `last_login_at`.
- `shops`: `id`, `name`, `slug`, `address`, `city`, `phone`, `timezone`, `slot_duration_minutes`, `slot_capacity`, `logo_url`, `rating`, `is_listed`.
- `shop_memberships`: `id`, `shop_id`, `user_id`, `role`, `is_active`, `created_by_user_id`.
- `bookings`: `id`, `shop_id`, `reference`, `customer_user_id`, `vehicle_id`, `mileage_km` (snapshot at booking time, D65), `slot_start`, `slot_end`, `status`, `technician_user_id`, `parts_person_user_id`, `qc_inspector_user_id`, `customer_notes`, `inspection_notes`, `repair_started_at`, `ready_notified_at`, `completed_at`, `cancelled_at`, `cancelled_by_user_id`, `cancel_reason`, `version`, `created_at`, `updated_at`.
- `parts`: `id`, `shop_id`, `sku`, `name`, `unit_cost`, `on_hand`, `reserved`, `reorder_level`, `is_active`.
- `estimates`: `id`, `shop_id`, `booking_id`, `version`, `status`, `parts_total`, `labour_total`, `grand_total`, `created_by_user_id`, `submitted_at`, `sent_at`, `sent_by_user_id`, `decided_at`, `decided_by_user_id`, `customer_note`.
- `booking_events`: `id`, `seq` (tie-breaker, D79), `shop_id`, `booking_id`, `action`, `from_status`, `to_status`, `actor_user_id`, `actor_role`, `note`, `metadata`, `created_at`.
- `stock_movements`: `id`, `seq` (tie-breaker, D79), `shop_id`, `part_id`, `movement_type`, `quantity`, `on_hand_delta`, `reserved_delta`, `booking_id`, `purchase_order_id`, `actor_user_id`, `note`, `created_at`.
- `slot_counters`: primary key `(shop_id, slot_start)`, `booked_count` — the one documented exception to the "`id uuid` PK" rule.
- `notifications`: `id`, `recipient_user_id`, `recipient_role`, `shop_id`, `booking_id`, `type`, `title`, `body`, `link`, `read_at`, `created_at`.

---

## 9. API conventions

**Spec 03 is the authoritative endpoint catalogue.** This section fixes the patterns every endpoint follows.

| Item | Convention |
|---|---|
| Base path | `/api/v1` (health check is `/health`, unversioned) |
| Public (no login) | `/api/v1/public/...` — shops are addressed **by slug**: `/api/v1/public/shops/{shop_slug}`, `/api/v1/public/shops/{shop_slug}/availability?date=YYYY-MM-DD` (D68) |
| Auth | `/api/v1/auth/...` (`register-owner`, `login`, `logout`) — identity module; login returns token + user, then the web calls `GET /api/v1/me` (D81) |
| Current user / customer | `/api/v1/me`, `/api/v1/me/...` (bookings, notifications, vehicles, owner summary) |
| Booking creation (wizard) | `POST /api/v1/bookings` (body carries `shop_id`) |
| Shop-scoped staff routes | `/api/v1/shops/{shop_id}/...` (UUID) |
| Booking actions | `.../bookings/{booking_id}/actions/{slug}` (slugs in §4) |
| Realtime ticket | `GET /api/v1/realtime/ticket`; socket `wss://<api-host>/api/v1/ws?ticket=…` |
| Webhooks (bonus) | `/api/v1/webhooks/...` (e.g. `POST /api/v1/webhooks/livekit`, signature-verified) |
| Internal (bonus agent only) | `/api/v1/internal/...` (service token + per-call token, never called by browsers) |
| JSON casing | `snake_case` keys everywhere (no aliasing) |
| IDs | UUID v4 strings |
| Timestamps | ISO 8601 in UTC with `Z` (e.g. `2026-10-16T05:00:00Z`); UI renders in the shop's timezone (default `Asia/Karachi`, UTC+5, no DST) |
| Money | PKR **whole rupees** (D41): DB `numeric(12,2)` always holding `.00`; JSON decimal **string** with 2 places (e.g. `"16100.00"`); unit prices must be whole rupees; line totals rounded half-up to whole rupees |
| Quantities | Stock quantities (`on_hand`, `reserved`, `required_qty` …) are JSON integers. Estimate-line `quantity` is a decimal string with 2 places (`"1.00"`, `"1.50"`); `PART` lines must be whole numbers |
| Pagination | `?limit=` (default 20, max 100) and `?offset=`; response `{ "items": [...], "total": n, "limit": l, "offset": o }` |
| Errors | RFC 9457 `application/problem+json` with an extra `code` field (see §10) |
| Caching | Every `/api/*` response carries `Cache-Control: no-store` (D61) |
| Trailing slashes | No redirects (`redirect_slashes=False`); paths are defined without a trailing slash |
| Request ID | `X-Request-ID` header echoed on every response and logged |
| Auth transport | httpOnly cookie `bf_session` (browser) **or** `Authorization: Bearer <token>` (Swagger, curl, tests, Bearer fallback) |
| JWT `typ` values | `session` (login/session token), `ws` (realtime ticket) |

---

## 10. Error codes (`code` field in every error response)

| Code | HTTP | When |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Request body/query fails validation |
| `INVALID_SLOT` | 422 | Slot not on the shop's grid, in the past, outside working hours or beyond the booking horizon; the 422 `errors[]` item for `slot_start` carries one reason code: `off_grid`, `in_past`, `beyond_horizon`, `closed_day`, `outside_hours` |
| `ESTIMATE_EMPTY` | 422 | Submitting/sending an estimate with no lines |
| `MEMBER_NOT_ELIGIBLE` | 422 | Assignee is not an active member with the required role in this shop |
| `UNAUTHENTICATED` | 401 | Missing/invalid/expired token, or user deactivated |
| `INVALID_CREDENTIALS` | 401 | Wrong e-mail or password at login |
| `FORBIDDEN` | 403 | Visible resource, but the user's role may not do this (incl. any change to the `OWNER` membership); the admin API for anyone but a platform admin, or for a cross-site request (D94, D98) |
| `NOT_ASSIGNED` | 403 | Role is right but the user is not the assigned technician / parts person / QC picker |
| `IDENTITY_NOT_VERIFIED` *(bonus)* | 403 | Internal agent data endpoint called before the caller's identity was verified |
| `NOT_FOUND` | 404 | Does not exist **or** is not visible to this user (other shop, not assigned, not own booking, inactive membership), unknown path, or an action slug that does not exist in the caller's endpoint family |
| `METHOD_NOT_ALLOWED` | 405 | HTTP method not supported on this path |
| `EMAIL_ALREADY_REGISTERED` | 409 | Owner sign-up with an existing e-mail; booking wizard with an existing e-mail and a wrong password |
| `INVALID_TRANSITION` | 409 | Action not allowed from the booking's current status |
| `CONCURRENT_UPDATE` | 409 | `expected_version` (or a PO receipt's `expected_received_qty`) sent by the client no longer matches |
| `SLOT_FULL` | 409 | Slot capacity already reached |
| `ALREADY_PICKED` | 409 | Another QC inspector picked this job first |
| `STALE_ESTIMATE` | 409 | Customer approved/rejected an estimate version that is not the current `SENT` one |
| `ESTIMATE_LOCKED` | 409 | Editing an estimate that is not editable in the current status |
| `INSUFFICIENT_STOCK` | 409 | Not enough available stock to reserve or allocate, or a stock adjustment would take `on_hand` below `reserved` or below 0 |
| `CALL_BUSY` *(bonus)* | 409 | The booking already has an active call, or the caller or the called customer is already in another call |
| `CALL_ALREADY_ANSWERED` *(bonus)* | 409 | Another SA accepted the call first |
| `CALL_NOT_ACTIVE` *(bonus)* | 409 | Accept/decline on a call that is no longer ringing, or an internal agent request for a call outside its active window (ending an already-ended call is idempotent and returns 200) |
| `CONFLICT` | 409 | Other conflicts (duplicate SKU, duplicate membership, grid change blocked by future bookings, `order-parts` when nothing is short, receiving a PO that is already `RECEIVED`, …) |
| `PAYLOAD_TOO_LARGE` | 413 | Request body over the size limit |
| `SHOP_SUSPENDED` | 403 | The shop is suspended by BayFlow: every staff route, and customer booking actions except `cancel` (D96) |
| `RATE_LIMITED` | 429 | Too many attempts (login, logout, owner registration, booking creation, shop creation, member creation, and — bonus — call starts) |
| `INTERNAL_ERROR` | 500 | Unexpected error (no internals leaked) |
| `AI_DISABLED` *(bonus, D103)* | 503 | Text AI not configured, or the feature is not in `AI_FEATURES` |
| `AI_LIMIT_REACHED` *(bonus, D103)* | 429 | The shop's daily or monthly text-AI cap is reached |
| `AI_UNAVAILABLE` *(bonus, D103)* | 503 | The model failed, returned invalid output, or its output failed the grounding guard |
| `CALLING_DISABLED` *(bonus)* | 503 | Calling not configured (`CALL_PROVIDER_*` blank) or the monthly calling cap (`CALL_MONTHLY_MINUTES_CAP`) reached. A blank `LLM_API_KEY` or a reached `AI_DAILY_CALL_CAP` never fails a call; they only mean no AI answers missed calls |

Check order for any booking action: **visibility (404) → role (403 `FORBIDDEN`) → assignment (403 `NOT_ASSIGNED`) → status (409 `INVALID_TRANSITION`) → data guards (409/422)**. A deactivated **user** gets 401 everywhere; a deactivated **membership** gets 404 on that shop's routes (D9, D21).

---

## 11. Realtime (WebSocket) message types

Server → client JSON `{ "type": "<type>", "data": { ... } }`:

| Type | Sent to | Data |
|---|---|---|
| `notification.created` | The notification's recipient | The notification object |
| `booking.updated` | The booking's customer + shop members who can **see** the booking under D21 (SAs, Owner, its technician, its parts person, QC inspectors while `QC_PENDING`/`QC_IN_PROGRESS` or if they inspected it) | `{ booking_id, shop_id, status, version }` |
| `call.incoming` *(bonus)* | Callee(s) | Call object |
| `call.updated` *(bonus)* | Call participants **and everyone who was rung** (so their pop-ups close) | Call object |
| `task.created` *(bonus)* | SAs of the shop | Task object |

Client → server: `{ "type": "ping" }` only (server replies `pong`).
Connection: `wss://<api-host>/api/v1/ws?ticket=<ticket>`; the ticket comes from `GET /api/v1/realtime/ticket`, is a JWT with `typ` = `ws`, lives **60 seconds** and is only needed for the handshake (D70). An invalid or expired ticket closes the socket with code **1008**; the client then fetches a new ticket (a 401 from the ticket endpoint means the session has expired). The ticket is redacted from server logs.

---

## 12. Environment variables (canonical names)

Names follow the brief's sample `.env.example` (§9.3) wherever possible. Spec 07 holds the full `.env.example`.

| Variable | App | Purpose |
|---|---|---|
| `APP_ENV` | api | `development` / `production` (the brief's `NODE_ENV` equivalent; explained in README) |
| `PORT` | api, agent | HTTP port (`4000` locally for the API; Railway injects its own) |
| `CLIENT_URL` | api | Web origin for CORS and links in e-mails (`http://localhost:3000`) |
| `DATABASE_URL` | api | PostgreSQL URL (the app converts `postgresql://` to `postgresql+asyncpg://`) |
| `JWT_SECRET` | api | HS256 signing secret, **at least 32 bytes**; production refuses to start with a weak or placeholder value |
| `JWT_EXPIRES_IN` | api | Token lifetime, e.g. `7d` (brief's sample value) |
| `COOKIE_SECURE` | api | `true` in production, `false` for plain-HTTP local dev |
| `LOG_LEVEL` | api, agent | `INFO` default |
| `SEED_ON_DEPLOY` | api | `true` → run the idempotent seed in the pre-deploy step |
| `EMAIL_PROVIDER` | api | `none` (default) / `smtp` (local Mailpit) / `http` (HTTPS e-mail API in production — Railway Hobby blocks outbound SMTP, D26) |
| `EMAIL_API_KEY` | api | Key for the HTTPS e-mail API when `EMAIL_PROVIDER=http` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` | api | Used when `EMAIL_PROVIDER=smtp`; `SMTP_FROM` is also the sender for `http` |
| `API_BASE_URL` | web | Server-side only: where Next.js rewrites `/api/*` to. **Fixed at build time** on Vercel (change = redeploy) |
| `NEXT_PUBLIC_WS_URL` | web | Browser WebSocket URL of the API, ending in `/api/v1/ws` (build-time) |
| `CALL_PROVIDER_URL`, `CALL_PROVIDER_API_KEY`, `CALL_PROVIDER_API_SECRET` | api, agent | Bonus: LiveKit project URL/key/secret (blank = calling disabled). LiveKit SDKs default to `LIVEKIT_*` names, so our code passes these values explicitly |
| `NEXT_PUBLIC_CALL_PROVIDER_URL` | web | Bonus: LiveKit URL for the browser SDK (build-time) |
| `LLM_API_KEY` | api, agent | Bonus: key for the selected `AI_PROVIDER` (blank = AI disabled; the API only checks presence) |
| `AI_PROVIDER` | agent | Bonus: `openai` (default) or `gemini` (fallback, D58) |
| `AI_REALTIME_MODEL`, `AI_SUMMARY_MODEL` | agent | Bonus: model overrides (defaults in code: `gpt-realtime-2.1-mini` for voice) |
| `STT_TTS_API_KEY` | agent | Bonus: only if a separate STT/TTS provider is used (blank when using a realtime speech model) |
| `AI_TEXT_PROVIDER`, `AI_TEXT_MODEL`, `AI_TEXT_API_KEY` | api | Bonus (D103): text AI provider (`gemini` default, or `fake`), model (`gemini-2.5-flash`) and key (blank → `LLM_API_KEY`) |
| `AI_FEATURES` | api | Bonus (D103): comma-separated `AiFeature` names enabled, or `*`; blank = none |
| `AI_SHOP_DAILY_CAP`, `AI_SHOP_MONTHLY_CAP`, `AI_TIMEOUT_SECONDS` | api | Bonus (D103): text AI calls per shop per UTC day (`200`) and month (`3000`); provider timeout (`30`) |
| `AI_RING_TIMEOUT_SECONDS` | api | Bonus: seconds before the AI answers (default `20`) |
| `AI_DAILY_CALL_CAP`, `CALL_MONTHLY_MINUTES_CAP` | api | Bonus: app-level usage caps kept below provider hard caps |
| `AGENT_SERVICE_TOKEN` | api, agent | Bonus: shared secret for `/api/v1/internal/*` |
| `API_INTERNAL_URL` | agent | Bonus: API base URL reachable from the agent (Railway private network) |
| `AGENT_PORT` | agent | Bonus: the worker's health-server port (default `8081`; Railway health check `/`). Not `PORT`, which the API uses locally (D104 notes). |
| `POSTGRES_HOST_PORT` | docker compose only | Host port of the local PostgreSQL container (default `5434`, D73) |

Placeholder secret values in `.env.example` use letters and hyphens only (so the repo's own secret scanner does not flag them).

Local dev ports (D73): web `3000`, API `4000`, PostgreSQL `5434` (host), Mailpit UI `8025` / SMTP `1025`.

---

## 13. Naming conventions

| Where | Convention |
|---|---|
| DB | `snake_case`, plural tables, `id uuid` PK (exception: `slot_counters`), FKs `<entity>_id`, user FKs `<role>_user_id`, timestamps `created_at` / `updated_at` (`timestamptz`); constraint prefixes `pk_`, `fk_`, `uq_`, `ck_`, `ix_` (SQLAlchemy naming convention, so DB errors map to error codes by constraint name) |
| Python | modules/functions `snake_case`; classes `PascalCase`; Pydantic schemas `XxxCreate`, `XxxUpdate`, `XxxRead`; enums `StrEnum` classes with `UPPER_SNAKE` members identical to the stored value |
| TypeScript | components `PascalCase`; files `kebab-case.tsx`; hooks `useXxx`; API types generated from OpenAPI into `apps/web/src/lib/api/schema.d.ts` (never hand-written) |
| URLs | lowercase `kebab-case` path segments; IDs (UUID) or shop slugs as path params; no trailing slash |
| Git | Conventional Commits (`feat(bookings): …`, `fix(inventory): …`) |
| Spec IDs | Spec 02's data invariants are `DI-1` … `DI-7` (spec 02 §6); test IDs are `<PREFIX>-nn` with two digits (spec 12 §5), so `INV-01` … is always an inventory test; roadmap phases `PH0` … `PH10`, QC Inspector screens `QI-xx`, AI Front Desk tests `FD-xx` (D75) |

---

## 14. Demo cast and seeded shops (canonical — from the brief's worked example, §6; full data in spec 11)

All demo accounts share the password **`BayFlow@2026`**. Demo e-mails use the reserved `.test` TLD so they can never be real (validated by the project `Email` type, D62). Seeded booking references start with `BF-SEED`, seeded PO numbers with `PO-SEED`.

### 14.1 Lahore Auto Care team and customers

| Person | Role | Shop | E-mail |
|---|---|---|---|
| Fatima Raza | `OWNER` | Lahore Auto Care **and** Raza Auto Works (shop switcher demo) | `fatima.owner@bayflow.test` |
| Bilal | `SERVICE_ADVISOR` | Lahore Auto Care | `bilal.sa@bayflow.test` |
| Imran | `TECHNICIAN` | Lahore Auto Care | `imran.tech@bayflow.test` |
| Hamza | `TECHNICIAN` (second) | Lahore Auto Care | `hamza.tech@bayflow.test` |
| Sara | `QC_INSPECTOR` | Lahore Auto Care | `sara.qc@bayflow.test` |
| Hina | `QC_INSPECTOR` (second — shows "first pick wins") | Lahore Auto Care | `hina.qc@bayflow.test` |
| Usman | `PARTS_PERSON` | Lahore Auto Care | `usman.parts@bayflow.test` |
| Ayesha Khan | Customer (seeded, has sample bookings) | — | `ayesha.customer@bayflow.test` |
| Kamran, Zainab, Nadia, Omar | Customers (seeded extras) | — | `kamran.customer@bayflow.test`, `zainab.customer@bayflow.test`, `nadia.customer@bayflow.test`, `omar.customer@bayflow.test` |
| Ahmed | Customer (**not seeded**; created live via the booking wizard, §6) | — | `ahmed@mail.com` in the brief; judges should use a fresh `.test` address when replaying |

### 14.2 Seeded shops

| Shop | Slug | City | Owner |
|---|---|---|---|
| Lahore Auto Care | `lahore-auto-care` | Lahore | Fatima Raza |
| Raza Auto Works | `raza-auto-works` | Lahore | Fatima Raza |
| Clifton Car Clinic | `clifton-car-clinic` | Karachi | Asif Memon |
| Margalla Motor Works | `margalla-motor-works` | Islamabad | Nida Abbasi |
| Pindi Auto Garage | `pindi-auto-garage` | Rawalpindi | Tariq Mehmood |
| Lyallpur Motors | `lyallpur-motors` | Faisalabad | Khalid Chaudhry |

Staff of the other shops follow `<role-tag>.<shop-slug>@bayflow.test` (e.g. `sa.clifton-car-clinic@bayflow.test`); Raza Auto Works has no separate owner account (Fatima owns it).

Worked-example vehicle: 2016 Honda Civic, plate `LEA-1234`. Worked-example prices (PKR): ignition coil 6,500; oil filter 900; engine oil 4 L 5,200; labour 4,000 → SA edits labour to 3,500 (total 16,600 → 16,100).

## Change log

- 2026-10-09 (consolidation after wave 1): added `StaffRole`, capabilities, staff labels and phases, QC checklist keys, bonus enums (`MissedReason.CALLER_HUNG_UP`, `AiLegStatus`, `IdentityMethod`, `CallIntent`, `TaskKind`), error codes (`IDENTITY_NOT_VERIFIED`, `METHOD_NOT_ALLOWED`, `CALL_*`, `PAYLOAD_TOO_LARGE`, `CALLING_DISABLED`), domain events, `app.core`/`app.shared` names, `bookings.mileage_km`, `notifications.recipient_role`/`link`, money as whole rupees, slug-based public routes, `remaining` for slots, `Cache-Control: no-store`, WebSocket ticket rules, `booking.updated` visibility fan-out, `CALL_MISSED` recipients, e-mail provider variables, AI variables, build-time notes, seeded shops and extra cast, reserved `SEED` prefixes.

- 2026-10-09 (implementation start): `app.shared.enums` (D74), `POSTGRES_HOST_PORT` and local dev ports (D73); ID prefixes PH (roadmap phases), QI (QC Inspector screens), FD (AI Front Desk tests) per D75.
- 2026-10-09 (wave-2 findings): `seq` tie-breaker columns on `booking_events` and `stock_movements` (D79); wording of `CALL_BUSY`, `CALL_NOT_ACTIVE`, `CALLING_DISABLED`, `RATE_LIMITED`.
- 2026-10-09 (module specs 1): read ports (D86), `INVALID_SLOT` reason codes, `app.core.db_errors`/`health`, `app.shared.timestamps`, token functions take `now`.
- 2026-10-09 (API contract): `tasks.manage` only with the calls module; wording of `NOT_FOUND`, `CONCURRENT_UPDATE`, `INSUFFICIENT_STOCK`, `CONFLICT`; auth routes per D81.
- 2026-10-09 (wave-2 findings 2): `shop_scoped_router()` (D80), `ShopGridChanging` event (D37), `get_clock()`/`utcnow()` (D63), module files "only as needed".
- 2026-10-09 (final consistency sweep): ID prefix `DI` for spec 02's data invariants (`DI-1` … `DI-7`, formerly `INV-1` … `INV-7`, which collided with spec 12's inventory tests `INV-01` …), §13.
- 2026-10-10 (design language, D101): role tags (§2.3) are no longer shown in UI chips; the UI uses the §2.1 display names.
- 2026-10-10 (spec sync after the page redesign): added **Shop membership gate** and **Read-only view** (§1), the names spec 10 and the built screens use (D16, D20, D44, D102).

## Dependencies

- Read by every other spec. Depends on the brief and spec 17.

## Open questions

None. Changes require updating spec 17 (decisions) first.
