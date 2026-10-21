# Module: bookings

**Status:** Draft
**Package:** `app.modules.bookings`
**Owns tables:** `vehicles`, `bookings`, `booking_services`, `booking_events`

## 1. Purpose

Own the booking lifecycle. This module creates bookings through the wizard (with the D32 account rule), moves them **only** through spec 08's rule table, writes the audit log, computes `allowed_actions`, applies the D21 visibility rule to every list, detail, action and realtime fan-out, and orchestrates the side effects that belong to other modules (estimates, inventory, qc, scheduling, shops, identity) inside one transaction per action. It also serves the booking-scoped reads of estimates, booking parts and QC rounds (spec 03 §1.11), vetoes slot-grid changes while future bookings exist (D37), and turns purchase-order receipts into reservations and the `RECEIVE_PARTS` transition (D43).

Brief sections satisfied:

- §5 "This is the heart of the product … Implement this as an explicit state machine in the backend and reject any invalid transition"; §5.1 (customer journey, account created or reused at booking time); §5.2 (the 15 statuses and their owners); §5.3 (estimate rejected, parts already in stock, partial delivery, QC failure loop, slot conflicts, cancellation before `IN_REPAIR` releasing reserved parts).
- §7.5 "Single source of truth for statuses and allowed transitions, enforced in the service layer"; "Every transition recorded in a booking history/audit log (who, when, from, to, note)"; "Role guard per transition"; "Estimate versioning or at least a revision count".
- §7.3 customer dashboard (bookings with live status timeline, pending actions, accept/reject, ready-for-pick-up); §7.4 role dashboards (SA list with status filters, technician "my assigned jobs", parts "jobs awaiting parts", QC shared queue, Owner overview of bookings); §4 Access rules ("Technician sees only bookings assigned to them. QC sees the shared QC queue. SA and Owner see all bookings of the shop. The customer only sees their own bookings").
- §6 worked example, §7.8 definition of done ("full flow … to COMPLETED", "QC fail loop and the estimate-rejected path work", "No role can perform another role's action"); §7.1 acceptance (Shop A staff on Shop B bookings → 404).

## 2. Scope

| Priority | In scope |
|---|---|
| **P0** | `POST /api/v1/bookings` (T01, D32–D35, D65); customer list, detail, events and the 4 customer action routes; staff list (filters, sort, pagination), status counts, detail, events, estimate versions, `PUT …/estimate` (O1), booking parts, QC rounds and the 20 P0 staff action routes; the action executor (spec 08 steps 1–16) for T02–T22 and O1–O3; vehicles (D35) and references (`BF-XXXXXX`); `BookingActionApplied`; the handlers for `PurchaseOrderReceiving`, `PurchaseOrderReceived` (D43) and `ShopGridChanging` (D37); `list_booking_viewer_ids` for `booking.updated` (glossary §11); the D83 `BookingPartsChanged` event for parts changes without a status change (the pushes themselves need the P1 WebSocket hub, D88); booking-creation rate limits (D69); reads used by shops, notifications and reporting. |
| **P1** | Platform admin (spec 19): the cross-tenant read-only projections `list_admin_bookings` (E-72) and `get_admin_booking` (E-73, `AdminBookingDetail` without `allowed_actions`), `platform_booking_stats` and `count_created_by_shop` (E-61, E-62) — explicit admin functions that never touch the D21 predicate; shop suspension on the customer side (D96). `reassign-technician` / `reassign-parts-person` (O4, O5) — routes and `allowed_actions` entries appear together; **planned (D87):** `reassign-qc-inspector` (`REASSIGN_QC_INSPECTOR`, SA/Owner, allowed in `QC_IN_PROGRESS`, no status change; the new inspector must be an active `QC_INSPECTOR` member and not the booking's technician; `QC_REQUESTED` → the new inspector), built with O4/O5 once glossary §4, spec 08 (O6), `app.shared.enums` and `RULES` carry it — until then the Owner reactivates a deactivated picker to finish the round; `GET /api/v1/me/bookings/{booking_id}/estimates`; `GET /api/v1/me/vehicles`; CON-02 / CON-04 / CON-05 concurrency tests; N+1 guard (API-11). The `booking.updated` pushes of the after-commit step need the P1 WebSocket hub (D88); without it the step only writes rows and polling covers freshness. |
| **P2** | Read helpers for the `calls` module and the AI agent (`find_customer_bookings`, look-up by reference scoped to a customer, spec 05 §5.3; `get_booking_labels` for `CallRead` lists, §5.3); calls are attached to bookings by `calls`, which owns its tables. |
| **Out of scope** | Rescheduling a booking (spec 08 has no such action; a P2 reschedule request is only a task), editing services, vehicle or slot after creation, staff-created walk-in bookings (staff book their own car as customers), deleting bookings or events, payments and invoices, an active-booking cap per customer (spec 04 Open question 9), an `Idempotency-Key` on booking creation (spec 03 Open question 2), the notification rows and pushes themselves (`notifications`), stock arithmetic (`inventory`), estimate versioning rules (`estimates`), QC records (`qc`). |

## 3. Key decisions

| D | What it means here |
|---|---|
| D3 | One action = one transaction across bookings, estimates, inventory, qc and scheduling; this module opens and commits it. |
| D9, D20 | Staff routes sit on `shop_scoped_router()` (active membership or 404); every query on bookings carries `shop_id` (staff) or `customer_user_id` (customer); `shop_id` in the wizard body only selects where to book. |
| D14 | Pushes happen after commit (queued by the notifications handler), only to users who can see the booking; clients also poll every 15 s. |
| D16 | The Owner passes every Service Advisor rule and no technician, parts or QC rule (encoded in `RULES`); the Owner reads every booking of the shop. |
| D21 | Visibility: customer → own bookings; technician → `technician_user_id = me`; parts person → `parts_person_user_id = me`; QC → `QC_PENDING`/`QC_IN_PROGRESS` plus bookings they inspected; SA and Owner → all. Not visible → 404; visible, wrong role → 403 `FORBIDDEN`; right role, not the assignee → 403 `NOT_ASSIGNED`; wrong status → 409 `INVALID_TRANSITION`. |
| D22 | Spec 08's rule table (`domain/state_machine.py`, already built) is the only source of transitions; every transition and operation writes one `booking_events` row. |
| D23 | From `ESTIMATE_REJECTED`: `revise-estimate`, `return-to-technician` or `cancel`. |
| D24 | `DECLINE`/`CANCEL` release reservations, free the slot and record who and why; linked POs stay open and their later receipts become general stock. |
| D25 | `ALLOCATE_PARTS` moves `PARTS_READY → IN_REPAIR`; `START_REPAIR` is an operation that only stamps `repair_started_at`. |
| D27, D28 | QC pass → `READY_FOR_PICKUP` at once; `NOTIFY_READY` is a repeatable operation; `COMPLETE` by SA, Owner or the booking's customer. |
| D30 | Lock the booking row first (`SELECT … FOR UPDATE` by key only); lock order booking → purchase order → parts (ascending `id`) → slot counter; `version += 1` whenever an event row is written; `expected_version` mismatch → 409 `CONCURRENT_UPDATE`; QC pick is first-wins (`ALREADY_PICKED`). |
| D31 | Labour-only jobs still pass `assign-parts-person` → `mark-parts-ready` → `allocate-parts` with zero booking parts. |
| D32 | Wizard account rule: session → that user; new e-mail → account created; existing e-mail + right password → reused; wrong password or inactive account → 409 `EMAIL_ALREADY_REGISTERED` and nothing created. The password is checked **before** any row lock. A successful booking always logs the customer in (cookie **and** `access_token`, `expires_in`, `account_created`). |
| D33, D34, D35 | Optional phone fills an empty `users.phone`; selected services are snapshotted; vehicles are the customer's, keyed by the normalised registration, re-used and updated on re-booking. |
| D37 | Booking creation takes the shop row `FOR SHARE` first; this module vetoes `ShopGridChanging` while a future non-cancelled booking exists. |
| D43 | A receipt reserves for the linked booking only while it is `PARTS_ORDERED`; when every booking part is then fully reserved, `RECEIVE_PARTS` fires in the same transaction; `PurchaseOrderReceiving` lets this module lock the booking before inventory locks the PO and parts. |
| D47 | The QC picker is never the booking's technician (domain 403); `FAIL_QC` clears the picker and keeps the technician; `PASS_QC` keeps the picker; `SEND_TO_QC` resolves open issues and clears the picker. |
| D48 | One route per action slug per endpoint family; every booking response carries `allowed_actions` for the caller. |
| D50, D63, D79 | UUIDs generated in Python; one clock instant per action, read right after the booking lock (T01: at the start); timelines ordered by `(created_at, seq)`. |
| D51 | The seed calls `create_booking` and the executor as real actors; it may pass a reserved `reference` (`BF-SEEDnn`) through an internal keyword argument. |
| D64, D65, D68 | Booking creation requires a listed shop with ≥ 1 active service (else 404); the wizard's mileage is snapshotted on `bookings.mileage_km`. |
| D69 | Anonymous booking creation: 20/min per IP; with a session: 30/h per user; cases C/D share the per-account failed-password limiter with login. |
| D83 | A change of a booking's parts state without a status change (a partial PO receipt reserving stock for it) also pushes `booking.updated` to the booking's viewers, through the `BookingPartsChanged` event (glossary §7.1). |
| D86 | Bookings implements both read ports of the lower modules: `shop_activity_reader` is shops' `ShopActivityReader` (registered with `shops.service.register_activity_reader`) and `get_booking_refs` is inventory's `BookingRefReader` (registered with `inventory.service.register_booking_ref_reader`) (glossary §7.1a). No lower module imports bookings. |
| D89 | Wiring by convention: `service.register_ports()` makes both registrations above; `handlers.register(bus)` subscribes the §5.4 handlers; `router.routers` exports the routers. `app.main.wire_modules()` loads all three at start-up (and the seed calls the same function); this module never edits `app/main.py`. |
| D87 | Planned P1 operation `REASSIGN_QC_INSPECTOR` for a QC pick held by a deactivated inspector (§2 Scope); not in `RULES` until spec 08 and the glossary list it. |
| D88 | The WebSocket push of step 15 is P1; the P0 executor writes the same rows and the web's 15 s polling shows the change. |

## 4. Files

| File | Contents |
|---|---|
| `models.py` | `Vehicle`, `Booking`, `BookingService`, `BookingEvent` (exist; spec 02 §3.7–§3.10): composite FKs, every `ck_bookings_*` check, `uq_bookings_reference`, `uq_vehicles_owner_user_id_registration_key`, `uq_vehicles_owner_user_id_id`, event `seq` identity, append-only trigger on `booking_events` (migration). |
| `domain/state_machine.py` | **Exists** (PH0): `RULES`, `check()`, `allowed_actions()`, `next_status()`, `ActorContext`, `Denial`, `TransitionDenied`, `ACTION_TO_SLUG`, `SLUG_TO_ACTION`, `CANCELLABLE_STATUSES`, `TERMINAL_STATUSES`. Not modified by this spec. |
| `domain/references.py` | `REFERENCE_ALPHABET` (Crockford base32 `0123456789ABCDEFGHJKMNPQRSTVWXYZ`), `REFERENCE_PATTERN`, `RESERVED_PREFIX = "SEED"`, `new_booking_reference(choice=secrets.choice)`, `is_reserved_reference()`. |
| `domain/vehicles.py` | `registration_key(registration_number)`: remove whitespace and hyphens, upper-case; must match `^[A-Z0-9]{2,20}$` (mirrors `ck_vehicles_registration_key`). |
| `domain/visibility.py` | `QC_QUEUE_STATUSES = {QC_PENDING, QC_IN_PROGRESS}`; `can_view(role, *, is_technician, is_parts_person, status, has_inspected)` — the D21 rule for one booking, the reference for the SQL predicate and the viewer list. |
| `domain/timeline.py` | `is_status_change(event)`; the customer event projection (`CUSTOMER_HIDDEN_ACTIONS = {EDIT_ESTIMATE, REASSIGN_TECHNICIAN, REASSIGN_PARTS_PERSON}`, `CUSTOMER_NOTE_ACTIONS = {DECLINE, CANCEL, REJECT_ESTIMATE}`); `UNROUTED_SLUGS` (P1 slugs hidden until their routes exist). |
| `repository.py` | `VehicleRepository` (upsert, list by owner), `BookingRepository` (key-only `get_for_update`, scoped reads, the D21 predicate builder, list + count with filters and sorts, status counts, future-bookings exists, open-jobs counts, booking refs), `BookingServiceRepository`, `BookingEventRepository` (add, list by booking ordered by `(created_at, seq)`, latest per booking, `status_changed_at` for many). Every shop-data method takes `shop_id`; events are add-only. |
| `schemas.py` | Requests: `BookingCreate`, `CustomerWrite`, `VehicleWrite`, the action bodies `<PascalCaseSlug>Request` (`ConfirmRequest` … `ReassignPartsPersonRequest`) and `CustomerCancelRequest`. Responses (spec 03 §3.3): `VehicleRead`, `VehicleBrief`, `BookingServiceRead`, `BookingSummary`, `BookingDetail`, `CustomerBookingSummary`, `CustomerBookingDetail`, `BookingCreatedRead`, `BookingEventRead`, `CustomerBookingEventRead`, `StatusCountsRead`. Reuses `estimates`, `inventory` and `qc` schemas for the booking-scoped reads (`EstimateRead`, `EstimateEditRead`, `EstimateUpdate`, `EstimateSummary`, `CustomerEstimateRead`, `BookingPartsRead`, `PartsSummary`, `QcInspectionRead`, `QcChecklistItemWrite`). Every timestamp field (incl. the request's `slot_start`) is `app.shared.timestamps.Timestamp` (aware input only, UTC `Z` output), money is `Money`, e-mails `Email`, phones `Phone`. |
| `events.py` | `BookingActionApplied`; `BookingPartsChanged` (D83, glossary §7.1). |
| `handlers.py` | `on_purchase_order_receiving`, `on_purchase_order_received`, `on_shop_grid_changing`; `register(bus)`. |
| `service.py` | The use cases, the executor, the read assemblers and the reads for other modules (§5); `shop_activity_reader`. |
| `router.py` | `wizard_router` (`/api/v1`), `me_router` (`/api/v1/me`), `shop_router = shop_scoped_router(tags=["bookings"])`, exported as `routers` (D89); action routes generated from `RULES` (§7.8). Tag `bookings` on all. |

## 5. Public service interface

`uow` = write transaction, `session` = read. Actors are the dependency objects of `app.shared.auth`: `CurrentUser` (customer family, wizard) and `ShopContext` (staff family); the seed builds the same objects for its scripted actors (spec 11).

### 5.1 Use cases (top-level; each commits once)

| Function | Arguments → returns | Errors (beyond 401/404 of the dependencies) |
|---|---|---|
| `create_booking` | `(uow, *, caller: CurrentUser \| None, data: BookingCreate, reference: str \| None = None) → BookingCreatedRead` — `reference` is keyword-only, internal (seed), absent from every HTTP schema | 404, 422 `VALIDATION_ERROR`, 422 `INVALID_SLOT`, 409 `EMAIL_ALREADY_REGISTERED`, 409 `SLOT_FULL`, 429 |
| `apply_staff_action` | `(uow, ctx: ShopContext, *, booking_id, action: BookingAction, payload: ActionRequest) → BookingDetail` | 403 `FORBIDDEN` / `NOT_ASSIGNED`, 409 `INVALID_TRANSITION` / `ALREADY_PICKED` / `CONCURRENT_UPDATE` / `CONFLICT` / `INSUFFICIENT_STOCK`, 422 (per action) |
| `apply_customer_action` | `(uow, customer: CurrentUser, *, booking_id, action, payload) → CustomerBookingDetail` | 409 `INVALID_TRANSITION` / `CONCURRENT_UPDATE` / `STALE_ESTIMATE`, 422 |
| `edit_estimate` | `(uow, ctx: ShopContext, *, booking_id, body: EstimateUpdate) → EstimateEditRead` (O1) | 403 `FORBIDDEN`, 409 `ESTIMATE_LOCKED` / `CONCURRENT_UPDATE`, 422 |

### 5.2 Reads behind the routes

| Function | Arguments → returns |
|---|---|
| `list_customer_bookings` | `(session, customer, *, active, sort, page) → Page[CustomerBookingSummary]` |
| `get_customer_booking` | `(session, customer, *, booking_id) → CustomerBookingDetail` |
| `list_customer_booking_events` | `(session, customer, *, booking_id) → list[CustomerBookingEventRead]` |
| `list_customer_estimates` *(P1)* | `(session, customer, *, booking_id) → list[CustomerEstimateRead]` |
| `list_my_vehicles` *(P1)* | `(session, customer) → list[VehicleRead]` |
| `list_staff_bookings` | `(session, ctx, *, filters: StaffBookingFilters, sort, page) → Page[BookingSummary]` |
| `get_status_counts` | `(session, ctx) → StatusCountsRead` |
| `get_staff_booking` | `(session, ctx, *, booking_id) → BookingDetail` |
| `list_booking_events` | `(session, ctx, *, booking_id) → list[BookingEventRead]` |
| `list_booking_estimates` | `(session, ctx, *, booking_id) → list[EstimateRead]` |
| `get_booking_parts` | `(session, ctx, *, booking_id) → BookingPartsRead` |
| `list_booking_qc_inspections` | `(session, ctx, *, booking_id) → list[QcInspectionRead]` |

### 5.3 Reads and helpers for other modules

| Function | Arguments → returns | Used by |
|---|---|---|
| `list_booking_viewer_ids` | `(session, *, booking_id) → list[UUID]` (D21 at push time, active memberships only) | notifications (`booking.updated` fan-out) |
| `has_future_bookings` | `(session, *, shop_id, now) → bool` (`slot_start > now AND status <> 'CANCELLED'`) | own `ShopGridChanging` handler; `shop_activity_reader` |
| `count_open_jobs` | `(session, *, shop_id, user_ids) → dict[UUID, int]` (distinct bookings not `READY_FOR_PICKUP`/`COMPLETED`/`CANCELLED` where the user is technician, parts person or current QC picker) | `shop_activity_reader` (`MemberRead.open_jobs`), reporting overview `team` |
| `shop_activity_reader` | object implementing shops' `ShopActivityReader` port (D86) with the two functions above | registered by this module's `register_ports()` with `shops.service.register_activity_reader(shop_activity_reader)`, which `wire_modules()` calls at start-up (D89; `modules/shops.md` §5.3) |
| `count_by_status` | `(session, *, shop_id) → dict[BookingStatus, int]` | reporting overview; `get_status_counts` (with the caller's D21 scope) |
| `count_day_activity` | `(session, *, shop_id, start, end) → DayActivity(bookings: int, completed: int)` — `bookings` = non-cancelled bookings whose `slot_start` is in `[start, end)`; `completed` = bookings whose `completed_at` is in `[start, end)`; `start`/`end` are the UTC bounds of the shop-local day computed by reporting (`ix_bookings_shop_id_slot_start`) | reporting: overview `today.bookings` / `today.completed`, owner-summary `today_bookings` (`modules/reporting.md`) |
| `get_booking_refs` | `(session, *, shop_id, booking_ids) → dict[UUID, BookingRefData]` (objects with `id`, `reference`, `status`, `version`; inventory maps them to its `BookingRef` schema) | inventory's `BookingRefReader` port (D86), registered by this module's `register_ports()` with `inventory.service.register_booking_ref_reader(get_booking_refs)` (D89; `modules/inventory.md`), for `PurchaseOrderSummary.booking`, `StockMovementRead.booking` and `receive_parts_applied`; notifications (current `status`/`version` and `booking_reference` at push time) |
| `find_customer_bookings` *(P2)* | `(session, *, shop_id, customer_user_id, limit = 10) → list[…]` | calls / agent internal routes (spec 05) |
| `get_booking_labels` *(P2)* | `(session, *, shop_id, booking_ids) → dict[UUID, BookingLabel]` (`reference`, `vehicle_label` such as "2016 Honda Civic", `customer_user_id`), one batched query whatever the page size | calls: `CallRead.booking_reference` / `vehicle_label` and the customer scope of call lists without N+1 (`modules/calls.md`) |

### 5.4 Event handlers (`handlers.py`; `register(bus)` is loaded by `wire_modules()`, D89)

| Handler | Event | Behaviour (same transaction as the publisher) |
|---|---|---|
| `on_purchase_order_receiving` | `PurchaseOrderReceiving` (inventory) | Lock the linked booking `FOR UPDATE` (key only) so D30's order holds (§7.7) |
| `on_purchase_order_received` | `PurchaseOrderReceived` (inventory) | Reserve for the booking only while `PARTS_ORDERED`; apply `RECEIVE_PARTS` when fully reserved; otherwise publish `BookingPartsChanged` if anything was reserved (§7.7) |
| `on_shop_grid_changing` | `ShopGridChanging` (shops) | 409 `CONFLICT` when `has_future_bookings(shop_id, now = event.occurred_at)` (§7.9) |

### 5.5 What this module calls in other modules

| Module | Functions (spec 01 name, or *proposed* in that module's spec / this spec) |
|---|---|
| identity | `find_user_by_email`, `create_customer` (case B), `sign_in_for_booking` (cases C/D, D100), `set_phone_if_empty`, `get_users_by_ids`, *`issue_session`*, *`find_user_ids_by_name`*, `find_user_ids_by_email` (E-72) |
| shops | *`get_bookable_shop`* (twice in T01), `get_shop_suspension` (customer actions, D96), `get_shop_timezones` (E-72), `snapshot_services`, `get_schedule_config` (`for_share=True` in T01), `require_eligible_member`, *`get_member_refs`*, *`get_shop_briefs`*, `list_active_member_ids`, `get_owner_user_id` |
| scheduling | *`validate_slot`*, `reserve_slot`, `release_slot` |
| estimates | `ensure_draft`, `replace_lines`, `submit`, `send`, `approve`, `reject`, `copy_rejected_to_draft`, `supersede_open_versions`, `get_approved_part_requirements`, *`list_versions`*, *`get_estimate_summaries`* (staff, one shop), *`get_customer_estimate_summaries`* (the customer list across shops), *`get_customer_view`*, *`list_customer_versions`* (see `modules/estimates.md`) |
| inventory | `create_booking_parts`, `order_missing_parts`, `reserve_outstanding`, `reserve_received_for_booking` (returns the reservations made **and** whether every booking part is now fully reserved), `consume_reservations`, `release_reservations`, `get_booking_parts_summary` (batched over booking ids), *`get_booking_parts`* (`BookingPartsRead`) |
| qc | `open_inspection`, `record_pass`, `record_fail`, `resolve_open_issues`, `list_booking_qc_history`, *`list_inspected_booking_ids`*, *`has_inspected`*, *`get_qc_summaries`* (inspection count and open issues per booking), *`list_inspector_ids`* |

## 6. Endpoints

Contract: [spec 03 §3.3, §4.6–§4.8, §5](../03-api-contracts.md). Staff paths below `/api/v1/shops/{shop_id}` are shortened to `…` (all on `shop_scoped_router()`). Customer paths are scoped by `customer_user_id = caller` (anything else 404, even for staff of that shop).

| operationId | Method + path | Auth · roles | Success | Pri | Screens |
|---|---|---|---|---|---|
| `bookings_create_booking` | `POST /api/v1/bookings` | optional session (present but invalid → 401) | 201 `BookingCreatedRead` + `Set-Cookie` | P0 | P-03 W5, C-03 · E-10 |
| `bookings_list_my_bookings` | `GET /api/v1/me/bookings` | session | 200 `Page[CustomerBookingSummary]` | P0 | C-01 · E-11 |
| `bookings_get_my_booking` | `GET /api/v1/me/bookings/{booking_id}` | session, own | 200 `CustomerBookingDetail` | P0 | C-02, C-03 · E-12 |
| `bookings_list_my_booking_events` | `GET /api/v1/me/bookings/{booking_id}/events` | session, own | 200 `ItemList[CustomerBookingEventRead]` | P0 | C-02 · E-13 |
| `bookings_list_my_booking_estimates` | `GET /api/v1/me/bookings/{booking_id}/estimates` | session, own | 200 `ItemList[CustomerEstimateRead]` | P1 | C-02 · E-14 |
| `bookings_my_<slug>` (4) | `POST /api/v1/me/bookings/{booking_id}/actions/{approve-estimate \| reject-estimate \| complete \| cancel}` | session, own | 200 `CustomerBookingDetail` | P0 | C-02 · E-15 |
| `bookings_list_my_vehicles` | `GET /api/v1/me/vehicles` | session | 200 `ItemList[VehicleRead]` | P1 | P-03 W4 · E-16 |
| `bookings_list_shop_bookings` | `GET …/bookings` | member, D21 | 200 `Page[BookingSummary]` | P0 | SA-01, T-01, PP-01, QI-01, O-01, O-06 · E-33 |
| `bookings_get_status_counts` | `GET …/bookings/status-counts` (registered before `{booking_id}`) | member, D21 | 200 `StatusCountsRead` | P0 | SA-01 · E-34 |
| `bookings_get_shop_booking` | `GET …/bookings/{booking_id}` | member, D21 | 200 `BookingDetail` | P0 | SA-02, T-02, PP-02, QI-02 · E-35 |
| `bookings_list_booking_events` | `GET …/bookings/{booking_id}/events` | member, D21 | 200 `ItemList[BookingEventRead]` | P0 | SA-02, T-02, QI-02 · E-36 |
| `bookings_list_booking_estimates` | `GET …/bookings/{booking_id}/estimates` | member, D21 (stock fields null for QC) | 200 `ItemList[EstimateRead]` | P0 | SA-02, T-02, PP-02, QI-02 · E-38 |
| `bookings_edit_estimate` | `PUT …/bookings/{booking_id}/estimate` | assigned T in `INSPECTING`; SA, O in `ESTIMATE_REVIEW` | 200 `EstimateEditRead` | P0 | T-02, SA-02 · E-39 |
| `bookings_get_booking_parts` | `GET …/bookings/{booking_id}/parts` | O, SA, T, PP; D21 (QC → 403) | 200 `BookingPartsRead` | P0 | PP-02, SA-02, T-02 · E-40 |
| `bookings_list_booking_qc_inspections` | `GET …/bookings/{booking_id}/qc-inspections` | member, D21 | 200 `ItemList[QcInspectionRead]` | P0 | QI-02, T-02, SA-02 · E-41 |
| `bookings_<slug>` (22) | `POST …/bookings/{booking_id}/actions/{slug}` | per `RULES` (§7.4) | 200 `BookingDetail` | P0 (20) + P1 (`reassign-*`) | SA-02, T-01/02, PP-02, QI-01/02 · E-37 |

`edit-estimate` appears in `allowed_actions` but is **never** an `/actions/` route: it is `PUT …/estimate` (spec 03 §5.1). `RECEIVE_PARTS` has no route here; it fires inside `POST …/purchase-orders/{po_id}/receive` (inventory) through the §7.7 handler. A slug outside its family is an unknown route → 404 (API-10).

## 7. Domain rules and algorithms

### 7.1 Booking creation — `POST /api/v1/bookings` (T01, D32–D35, D37, D64, D65)

**Body `BookingCreate`** (spec 03 §4.6, `extra="forbid"` so `status`, `customer_user_id`, `reference`, `version` → 422, SEC-17): `shop_id` · `service_ids` 1–10 distinct · `slot_start` (aware timestamp) · `customer_notes`? ≤ 2000 · `customer`? `CustomerWrite` (`full_name` 1–120, `email` Email, `password` 12–128, `phone` Phone — all optional in the schema) · `vehicle` `VehicleWrite` (`registration_number` 2–20 whose key matches `^[A-Z0-9]{2,20}$`, `make` 1–60, `model` 1–60, `year` 1900–2100 in the schema, `color`? ≤ 30, `mileage_km`? 0–2 000 000).

**Order of checks** (spec 03 §4.6; the first failure answers):

| # | Step | Failure |
|---|---|---|
| 0 | `get_optional_user`: no credentials → anonymous; credentials present but invalid, expired or inactive → **401** (never a silent downgrade, spec 04 case A) | 401 |
| 1 | Schema | 422 |
| 2 | Router: anonymous → per-IP limit 20/min (`ANONYMOUS_BOOKING_IP_LIMIT`, keyed `"booking-ip", client_ip`) | 429 |
| 3 | Service: `now = utcnow()` (T01 reads the clock at the start, spec 02 §2). With a session → per-user limit 30/h (`AUTHENTICATED_BOOKING_LIMIT`, keyed `"booking-user", user_id`) | 429 |
| 4 | Anonymous: `customer.full_name`, `customer.email`, `customer.password` present | 422 (`customer.<field>`, `missing`) |
| 5 | `vehicle.year ≤ year(now) + 1` | 422 (`vehicle.year`, "Year must be between 1900 and {Y+1}.") |
| 6 | `shops.get_bookable_shop(shop_id)`: listed, not suspended (D96) **and** ≥ 1 active service (D64) | 404 (BK-15, BK-26) |
| 7 | `shops.snapshot_services(shop_id, service_ids)`: each an active service of this shop | 422 (`service_ids.N`, `invalid_reference`) |
| 8 | `config = shops.get_schedule_config(shop_id)` (unlocked); `scheduling.validate_slot(config, slot_start, now)` | 422 `INVALID_SLOT` |
| 9 | **Account rule (D32)** — no row lock is held yet, so Argon2 never holds one (table below) | 409 `EMAIL_ALREADY_REGISTERED`, 429 |
| 10 | **Lock 1:** `config = shops.get_schedule_config(shop_id, for_share=True)` (shop row `FOR SHARE`, D37), then `shops.get_bookable_shop(shop_id)` again: unlisting and suspension write the shop row, so this re-read under the lock is final, and a shop closed while the request waited answers like step 6 (spec 19 §7) | 404 |
| 11 | **Lock 2:** vehicle upsert (§7.2) | — |
| 12 | **Lock 3:** `slot = scheduling.reserve_slot(config, slot_start, now)` (re-validates under the share lock, then counter `FOR UPDATE`, capacity, `+1`) | 422 `INVALID_SLOT`, 409 `SLOT_FULL` |
| 13 | Insert the booking: `id = uuid4()`, `reference` (§7.3), `status = RULES[CREATE].to_status` (`PENDING`), `version = 1`, `slot_start`, `slot_end = slot.slot_end`, `mileage_km = data.vehicle.mileage_km` (D65), `customer_notes`, `created_at = updated_at = now` | — |
| 14 | Insert one `booking_services` row per snapshot (`name_snapshot`, `base_price_snapshot`, D34) | — |
| 15 | Insert the `CREATE` event (`from_status = NULL`, `to_status = PENDING`, actor = the customer, `actor_role = CUSTOMER`, `metadata = {}`) and publish `BookingActionApplied` (`BOOKING_CREATED` → SAs of the shop) | — |
| 16 | Commit; `token = identity.issue_session(user.id)`; build `CustomerBookingDetail`; return `BookingCreatedRead {access_token, token_type, expires_in, account_created, booking}`. The router sets `bf_session` with `set_session_cookie` in **every** successful case (with a session the token is re-issued) | — |

Any failure in steps 10–16 rolls back everything, including a case-B account, so the wizard never leaves an orphan user (spec 04 SEC-18). After commit the notifications module pushes `notification.created` to the SAs and `booking.updated` to the customer and the booking's viewers.

**Account rule (step 9, spec 04 cases A–D):**

| Case | Situation | Action | `account_created` |
|---|---|---|---|
| A | Valid session | Book for the session user; `customer.full_name`/`email`/`password` are ignored; `customer.phone` → `identity.set_phone_if_empty` (D33) | `false` |
| B | Anonymous, e-mail unknown (`identity.find_user_by_email` → `None`) | `identity.create_user(email, full_name, password, phone)` (Argon2 hash, insert, flush; a concurrent registration of the same e-mail → 409 `EMAIL_ALREADY_REGISTERED`) | `true` |
| C | Anonymous, e-mail known, `identity.sign_in_for_booking` (`authenticate`, audited, D100) succeeds | Reuse the account (rehash, `last_login_at` and the `auth.login_succeeded` audit row commit with the booking and are lost with it); `customer.phone` → `set_phone_if_empty` | `false` |
| D | Anonymous, e-mail known, `sign_in_for_booking` raises `INVALID_CREDENTIALS` (wrong password **or** inactive account) | Raise 409 `EMAIL_ALREADY_REGISTERED` ("There's already a BayFlow account for this e-mail and the password didn't match. Log in to finish your booking."); nothing of the booking is created; the failure counts for the per-account limiter and `auth.login_failed` is committed in identity's own short transaction before the 409 (D100). A blocked account gets 429 `RATE_LIMITED` instead, even with the right password (recorded as `auth.login_rate_limited` the same way) | — |

### 7.2 Vehicles (D35, D65)

- `registration_key = domain.vehicles.registration_key(registration_number)`: strip, remove every whitespace character and `-`, upper-case; anything else outside `[A-Z0-9]` fails the schema (spec 03 §3.3). The database re-derives and checks the same key (`ck_vehicles_registration_key`), so the two can never disagree. `lea 1234` and `LEA-1234` are the same car (BK-13); another customer's identical plate is a different vehicle row.
- Atomic upsert (spec 02 §3.7):

```sql
INSERT INTO vehicles (id, owner_user_id, registration_number, registration_key, make, model, year,
                      color, mileage_km, created_at, updated_at)
VALUES (:id, :customer, :reg_number, :reg_key, :make, :model, :year, :color, :mileage, :now, :now)
ON CONFLICT (owner_user_id, registration_key) DO UPDATE SET
    registration_number = EXCLUDED.registration_number, make = EXCLUDED.make, model = EXCLUDED.model,
    year = EXCLUDED.year, color = COALESCE(EXCLUDED.color, vehicles.color),
    mileage_km = COALESCE(EXCLUDED.mileage_km, vehicles.mileage_km), updated_at = :now
RETURNING id
```

- Re-booking updates the stored details (D35); omitted optional fields (`color`, `mileage_km`) keep their stored values. The booking's own `mileage_km` is the value sent **in this booking** (null when omitted), so an earlier booking's snapshot never changes (BK-28, D65).
- The composite FK `(customer_user_id, vehicle_id) → vehicles (owner_user_id, id)` guarantees a booking uses its own customer's car.

### 7.3 References (`BF-XXXXXX`, glossary §1)

- `new_booking_reference()`: 6 characters drawn with `secrets.choice` from `REFERENCE_ALPHABET`; a code starting with `SEED` is discarded and redrawn (reserved for seed data, glossary §14); result `BF-` + code, matching `ck_bookings_reference_format` (`^BF-[0-9A-HJKMNP-TV-Z]{6}$`).
- The insert runs inside `session.begin_nested()`; a `uq_bookings_reference` violation rolls back to the savepoint and retries with a new code, up to 5 attempts (spec 02 §7.6; 32⁶ ≈ 1.07 × 10⁹ codes), then 500.
- Seed path: `create_booking(..., reference="BF-SEED07")` must match the format **and** start with `BF-SEED`; otherwise `ValueError` (a programming error, never reachable over HTTP). An existing reference → 409 `CONFLICT` (the seed checks existence first, spec 11).
- References are human identifiers, not secrets: no endpoint grants access because the caller knows one (spec 04).

### 7.4 The action executor (spec 08 "How an action is executed", steps 1–16)

`apply_staff_action` / `apply_customer_action` share one private executor:

1. **Authenticate** — `get_current_user` (cookie or Bearer, `users.is_active` re-read, D9).
2. **Membership** (staff) — router-level `require_shop_member` → `ShopContext` or 404.
3. **Lock** — `SELECT … FROM bookings WHERE id = :booking_id AND shop_id = :shop_id FOR UPDATE` (staff) or `… AND customer_user_id = :me FOR UPDATE` (customer), **key only, never `status`** (spec 02 §7.3), with `populate_existing`. No row → 404. Then `now = utcnow()` (one instant for every timestamp the action writes).
4. **Visibility (D21)** — staff only: `can_view(role, …)` on the locked row (§7.5); a QC inspector outside the queue costs one `qc.has_inspected` read. Not visible → 404.
5. **Role** — build `ActorContext(role, is_assigned_technician = technician_user_id == me, is_assigned_parts_person = parts_person_user_id == me, is_qc_picker = qc_inspector_user_id == me, is_booking_customer = customer_user_id == me, is_booking_technician = technician_user_id == me)` with `role = ActorRole(ctx.role)` (staff) or `ActorRole.CUSTOMER`; `rule = check(action, booking.status, actor)`.
6. **Assignment** and 7. **status** — inside `check()`, in that order. `TransitionDenied` maps to `Forbidden`, `NotAssigned`, `InvalidTransition` or `AlreadyPicked` with the domain's message. For `PICK_QC` the 409 detail names the current picker ("Already picked by Sara."); a double click by the picker gets the same 409 and the UI just opens the inspection.
8. **Version** — `payload.expected_version` present and `≠ booking.version` → 409 `CONCURRENT_UPDATE` (after the status check, spec 03 §7.5).
9. **Payload and data guards** — per action (§7.6); 422 / 409.
10. **Side effects** through the owning modules' services on the same session, in lock order booking → purchase order → parts (ascending `id`) → slot counter (D30).
11. **Update the booking** — `status = next_status(rule, from_status)` for a transition; the action's columns; `version += 1`; `updated_at = now`.
12. **Audit** — insert one `booking_events` row: `action`, `from_status`, `to_status` (= from for an operation), `actor_user_id`, `actor_role`, `note`, `metadata` (§7.6), `created_at = now`.
13. **Publish** `BookingActionApplied` (§8); the notifications handler inserts the notification rows in this transaction and queues the after-commit pushes and e-mails.
14. **Commit.**
15. **After commit** — the queued callbacks push `booking.updated` and `notification.created` and send optional e-mail; failures are only logged (spec 01).
16. **Respond** — re-read and assemble `BookingDetail` / `CustomerBookingDetail` with the caller's fresh `allowed_actions`; the staff response's `last_event` is this action's event (e.g. `metadata.po_number` after `order-parts`).

### 7.5 Visibility (D21) — one rule, three uses

| Caller (staff family) | Visible bookings (always `shop_id = :shop_id`) |
|---|---|
| `OWNER`, `SERVICE_ADVISOR` | all |
| `TECHNICIAN` | `technician_user_id = :me` |
| `PARTS_PERSON` | `parts_person_user_id = :me` |
| `QC_INSPECTOR` | `status IN ('QC_PENDING','QC_IN_PROGRESS')` **or** `id = ANY(:inspected_ids)` where `inspected_ids = qc.list_inspected_booking_ids(shop_id, me)` |
| Customer family | `customer_user_id = :me` (no shop filter) |

- **Lists and counts** use the SQL predicate built by the repository from this table; filters (`status`, `technician_user_id`, …) are ANDed, so they narrow and never widen (a technician filtering by another technician gets an empty page).
- **Item routes and actions** evaluate `domain.visibility.can_view` on the loaded row (the locked row for actions), because the locking read must stay key-only.
- **Realtime** uses the same table for `list_booking_viewer_ids` (§7.11).
- A unit test asserts that `can_view` and the SQL predicate agree for every role × status × assignment combination.
- Consequences (spec 04): an unassigned technician or parts person gets **404**, never `NOT_ASSIGNED`; after a `reassign-*` the previous assignee gets 404; 403 `NOT_ASSIGNED` surfaces in practice only for a QC inspector passing or failing a job someone else picked.

### 7.6 Per-action behaviour (spec 08 T02–T22, O2–O5)

"Guards" are checked in step 9 after the rule check; "effects" run in step 10; notifications are created by the notifications handler from the event (glossary §6). Request bodies are spec 03 §5.2; every body also accepts `expected_version`.

| Action (row) · body | Guards | Effects (owning module) | Booking columns | Event `note` · `metadata` | Notification |
|---|---|---|---|---|---|
| `CONFIRM` (T02) · `note`? ≤ 500 | — | — | `status` | note · `{}` | `BOOKING_CONFIRMED` → customer |
| `DECLINE` (T03) · `reason` 1–500 | — | `scheduling.release_slot` | `cancelled_at`, `cancelled_by_user_id`, `cancel_reason` | reason · `{}` | `BOOKING_CANCELLED` → customer |
| `ASSIGN_TECHNICIAN` (T04) · `technician_user_id` | `shops.require_eligible_member(TECHNICIAN)` → 422 `MEMBER_NOT_ELIGIBLE` | — | `technician_user_id` | — · `{technician_user_id}` | `TECHNICIAN_ASSIGNED` → technician |
| `START_INSPECTION` (T05) · — | — | `estimates.ensure_draft` (v1 `DRAFT`, author = technician) | — | — · `{estimate_id, version}` | — |
| `SUBMIT_ESTIMATE` (T06) · `inspection_notes`? ≤ 4000 | `estimates.submit`: 422 `ESTIMATE_EMPTY`; part deactivated since → 422 `lines.N.part_id` `invalid_reference` | draft → `SUBMITTED` | `inspection_notes` (when sent) | — · `{estimate_id, version, grand_total}` | `ESTIMATE_SUBMITTED` → SAs |
| `SEND_ESTIMATE` (T07) · — | `estimates.send`: 422 `ESTIMATE_EMPTY` | open version → `SENT` (`sent_at`, `sent_by`) | — | — · `{estimate_id, version, grand_total}` | `ESTIMATE_SENT` → customer (+ e-mail, D26) |
| `APPROVE_ESTIMATE` (T08) · `estimate_id` | `estimates.approve`: 409 `STALE_ESTIMATE` unless it is the current `SENT` version | → `APPROVED`, `decided_at`, `decided_by` | — | — · `{estimate_id, version, grand_total}` | `ESTIMATE_APPROVED` → SAs |
| `REJECT_ESTIMATE` (T09) · `estimate_id`, `reason`? ≤ 500 | same | → `REJECTED`, `customer_note = reason` | — | reason · `{estimate_id, version, grand_total}` | `ESTIMATE_REJECTED` → SAs |
| `REVISE_ESTIMATE` (T10) · — | — | `estimates.copy_rejected_to_draft` (author = actor) | — | — · `{estimate_id, version}` | — |
| `RETURN_TO_TECHNICIAN` (T11) · `note`? ≤ 500 | — | `estimates.copy_rejected_to_draft` | — | note · `{estimate_id, version}` | `ESTIMATE_RETURNED` → technician |
| `ASSIGN_PARTS_PERSON` (T12) · `parts_person_user_id` | `require_eligible_member(PARTS_PERSON)` → 422 | `estimates.get_approved_part_requirements` → `inventory.create_booking_parts` (zero rows when labour-only, D31) | `parts_person_user_id` | — · `{parts_person_user_id, required: [{part_id, qty}]}` | `PARTS_NEEDED` → parts person |
| `ORDER_PARTS` (T13) · `supplier_name`?, `items`? | inventory: 409 `CONFLICT` when nothing is short (nothing reserved); 422 `missing_shortage` / `below_shortage` / `not_short` | `inventory.order_missing_parts` (locks parts ascending, `RESERVE`, PO `ORDERED` linked to the booking) | — | — · `{purchase_order_id, po_number, reserved: [{part_id, qty}]}` | — |
| `MARK_PARTS_READY` (T14) · — | inventory: 409 `INSUFFICIENT_STOCK` (atomic) | `inventory.reserve_outstanding` | — | — · `{reserved: [{part_id, qty}]}` | — |
| `ALLOCATE_PARTS` (T16) · — | inventory: 409 `INSUFFICIENT_STOCK` | `inventory.consume_reservations` (`CONSUME`) | — | — · `{consumed: [{part_id, qty}]}` | `PARTS_READY` → technician |
| `START_REPAIR` (O2) · — | — | — | `repair_started_at = now` (each round overwrites) | — · `{}` | — |
| `SEND_TO_QC` (T17) · `repair_notes`? ≤ 2000 | — | `qc.resolve_open_issues` (`resolved_by` = technician) | `qc_inspector_user_id = NULL` | repair_notes · `{resolved_qc_issue_ids}` | `QC_REQUESTED` → all active QC inspectors |
| `PICK_QC` (T18) · — | domain: 409 `ALREADY_PICKED`, 403 when the caller is the technician (D47) | `qc.open_inspection` (`picked_at`) | `qc_inspector_user_id = caller` | — · `{qc_inspection_id}` | — |
| `PASS_QC` (T19) · `checklist` (5 keys), `notes`? | `qc.record_pass`: 422 `checklist_incomplete` / `checklist_item_failed` | inspection `PASS` | picker **kept** | — · `{qc_inspection_id}` | `QC_PASSED` → SAs |
| `FAIL_QC` (T20) · `issue_title` 1–120, `issue_description` 1–2000, `checklist`?, `notes`? | `qc.record_fail`: 422 | inspection `FAIL` + `OPEN` issue | `qc_inspector_user_id = NULL` (technician unchanged) | `issue_title` (D92) · `{qc_inspection_id, qc_issue_id}` | `QC_FAILED` → technician |
| `NOTIFY_READY` (O3) · — | — | — | `ready_notified_at = now` | — · `{}` | `VEHICLE_READY` → customer (+ e-mail) |
| `COMPLETE` (T21) · — | — | — | `completed_at = now` | — · `{}` | — |
| `CANCEL` (T22) · staff `reason` 1–500 / customer `reason`? ≤ 500 | — | `inventory.release_reservations` (parts ascending, `RELEASE`) → `scheduling.release_slot` → `estimates.supersede_open_versions`; linked POs untouched (D24) | `cancelled_at`, `cancelled_by_user_id`, `cancel_reason` | reason · `{released: [{part_id, qty}]}` | `BOOKING_CANCELLED`: staff → customer; customer → SAs + technician + parts person |
| `REASSIGN_TECHNICIAN` (O4, P1) · `technician_user_id` | eligible (422 `MEMBER_NOT_ELIGIBLE`); different from the current one (422 `unchanged`) | — (the draft estimate stays) | `technician_user_id` | — · `{technician_user_id, previous_technician_user_id}` | `TECHNICIAN_ASSIGNED` → new technician |
| `REASSIGN_PARTS_PERSON` (O5, P1) · `parts_person_user_id` | same | — (reservations and POs unchanged) | `parts_person_user_id` | — · `{parts_person_user_id, previous_parts_person_user_id}` | `PARTS_NEEDED` → new parts person |

`RECEIVE_PARTS` (T15) is applied by the receipt handler (§7.7), `EDIT_ESTIMATE` (O1) by `edit_estimate` (§7.6.1). The `booking_events.note` column holds at most 2000 characters; every note above fits.

#### 7.6.1 `edit-estimate` — `PUT …/bookings/{booking_id}/estimate` (O1)

1. Steps 1–4 of §7.4 (lock, `now`, visibility → 404).
2. `check(EDIT_ESTIMATE, status, actor)`: `FORBIDDEN` → 403 (parts person, QC); `NOT_ASSIGNED` → 403 (unreachable in practice: an unassigned technician cannot see the booking); **`INVALID_TRANSITION` → 409 `ESTIMATE_LOCKED`** — the technician outside `INSPECTING`, the SA or Owner outside `ESTIMATE_REVIEW` (e.g. the Owner during `INSPECTING`, anyone after sending or approval), never 403 (EST-11, SM-16, SEC-35). The rule's `actors_by_status` (technician in `INSPECTING`, SA/Owner in `ESTIMATE_REVIEW`) makes the domain answer `INVALID_TRANSITION` for those cases.
3. `expected_version` → 409 `CONCURRENT_UPDATE`.
4. `inspection_notes` from an SA or the Owner → 422 (`inspection_notes`, `not_allowed`).
5. `edit = estimates.replace_lines(shop_id, booking_id, booking_status, actor_user_id, lines, now)` → validates every line, prices it, and either replaces the draft in place or supersedes the `SUBMITTED` version and creates a new `DRAFT` (D39; `modules/estimates.md` §7.3).
6. Technician with `inspection_notes` → save them on the booking (no event).
7. `edit.created_new_version` → one `EDIT_ESTIMATE` event (`from_status = to_status = ESTIMATE_REVIEW`, metadata `{estimate_id, version, grand_total}`), `version += 1`, `BookingActionApplied` (no notification type; `booking.updated` is pushed). Otherwise no event and no version bump: plain draft saves are last-write-wins (D30).
8. Commit; return `EstimateEditRead` (`booking_version`, `created_new_version`, lines with live stock).

### 7.7 Purchase-order receipt handlers (D43, D83)

Inventory's receive use case (`modules/inventory.md`) publishes two events in one transaction; this module reacts:

1. **`PurchaseOrderReceiving(shop_id, purchase_order_id, booking_id, actor_user_id)`** — only for a PO linked to a booking, before inventory locks the PO or any part: `SELECT … FROM bookings WHERE id = :booking_id AND shop_id = :shop_id FOR UPDATE`. The booking is now lock 1, so the receipt follows D30's order booking → purchase order → parts even though it started in inventory.
2. **`PurchaseOrderReceived(shop_id, purchase_order_id, po_number, booking_id, received, actor_user_id)`** — after inventory wrote the `RECEIVE` movements, PO items and PO status:
   - `booking_id` is `None` (general restock) → nothing (INV-08).
   - Re-read the locked booking (`populate_existing`; the lock is already held). Status ≠ `PARTS_ORDERED` (cancelled, or made ready another way) → **nothing is reserved**, the received stock stays general (D24, D43, INV-09, INV-24).
   - Otherwise `reserved, all_reserved = inventory.reserve_received_for_booking(shop_id, booking_id, purchase_order_id, received, actor_user_id, now=event.occurred_at)` (the receipt's single post-lock instant, D63; `PurchaseOrderReceiving.occurred_at` is read before the locks and is informational only) — `RESERVE` movements from parts this transaction already holds, at most each booking part's outstanding quantity; the excess stays general stock.
   - `all_reserved` → apply `RECEIVE_PARTS`: `check(RECEIVE_PARTS, PARTS_ORDERED, ActorContext(role=PARTS_PERSON))` (any active Parts Person: the receive route is Parts-Person-only), status `PARTS_READY`, `version += 1`, event by the receiving Parts Person (`actor_role = PARTS_PERSON`, metadata `{purchase_order_id}`), publish `BookingActionApplied` (no notification type; `booking.updated` is pushed) (INV-06, SM-12).
   - Not all reserved but `reserved` non-empty (partial delivery, §5.3) → the booking stays `PARTS_ORDERED`, no event, no version bump (D30), and this module publishes **`BookingPartsChanged`** so the notifications module pushes `booking.updated` after commit (D83).
3. The handler never commits; any exception rolls back the whole receipt. Inventory learns whether the booking moved by reading the booking's `BookingRef` through `get_booking_refs` before and after publishing `PurchaseOrderReceived` (`PARTS_ORDERED → PARTS_READY` ⇒ `receive_parts_applied = true`, `modules/inventory.md`).

### 7.8 `allowed_actions` and route generation (D48)

- `allowed_actions = [s for s in domain.allowed_actions(status, actor) if s not in UNROUTED_SLUGS]`, in `BookingAction` declaration order (glossary §4). Data guards (stock, checklist, empty estimate) are never pre-evaluated. Customers only ever see `approve-estimate`, `reject-estimate`, `complete`, `cancel`, and only `cancel` while the shop is suspended (D96: the other three would answer 403 `SHOP_SUSPENDED`); the Owner sees SA slugs only; `CREATE` and `RECEIVE_PARTS` never appear; `edit-estimate` appears when the caller may `PUT …/estimate` now.
- `UNROUTED_SLUGS = {"reassign-technician", "reassign-parts-person"}` until the P1 routes ship; it is emptied in the same commit that adds them, so a listed slug always has a route (spec 03 §3.3).
- Routes are generated from `RULES` with one factory: the staff family gets `POST …/actions/{slug}` for every listable rule with a staff actor except `edit-estimate` and `UNROUTED_SLUGS` (20 at P0, 22 with P1); the customer family gets every rule whose actors include `CUSTOMER` (4). Endpoint functions are named after the slug (`assign_technician`, customer `my_cancel`), so operation IDs are `bookings_<slug>` / `bookings_my_<slug>`; each route has its own `<PascalCaseSlug>Request` body (customer `cancel` uses `CustomerCancelRequest`). A body with no required field may be omitted. A test asserts both generated sets against `RULES`.

### 7.9 Grid-change veto (D37)

`on_shop_grid_changing(event)`: `EXISTS (SELECT 1 FROM bookings WHERE shop_id = :shop_id AND slot_start > :occurred_at AND status <> 'CANCELLED')` (index `ix_bookings_shop_id_slot_start`) → raise 409 `CONFLICT` ("This shop has upcoming bookings — slot duration and timezone can change when none are left."). The shop row is already locked `FOR UPDATE` by the shops service and booking creation holds it `FOR SHARE`, so no in-flight booking can be missed (CON-05). Bookings whose slot already started are not "future" and never block.

### 7.10 Read models and derived fields (spec 03 §3.3)

| Field | Rule |
|---|---|
| `status_changed_at` | `created_at` of the latest event whose `to_status` differs from `from_status` (the `CREATE` event counts). One aggregate query per page |
| `qc_round` | `qc` inspection count for the booking, `+1` while `QC_PENDING`; `0` if it never reached QC |
| `open_qc_issues_count` | `OPEN` QC issues (from `qc.get_qc_summaries`) |
| `estimate_summary` | Staff: latest version; customer: latest `SENT` / `APPROVED` / `REJECTED` version (D39) — staff from `estimates.get_estimate_summaries` (one shop), the customer list from `estimates.get_customer_estimate_summaries` (one query across shops, API-11) |
| `parts_summary` | `null` while `parts_person_user_id` is null (assign-parts-person has not run) and for QC callers (stock data); otherwise `inventory.get_booking_parts_summary` (zero rows → `all_available = true`, D31) |
| `technician` / `parts_person` / `qc_inspector` | `MemberRef` from `shops.get_member_refs` (`is_active` = membership, so a deactivated assignee shows a warning, D19) |
| `customer` | Staff list: `UserRef`; staff detail: `{user_id, full_name, email, phone}` with `email`/`phone` **null unless the caller is `OWNER` or `SERVICE_ADVISOR`** |
| `cancelled_by` / `cancelled_by_customer` | Staff `UserRef`; customer view `cancelled_by_user_id == customer_user_id` (null when not cancelled) |
| `estimate` / `estimate_revision_in_progress` (customer) | From `estimates.get_customer_view`: the latest customer-visible version and whether a newer open (`DRAFT`/`SUBMITTED`) version exists |
| `last_event` (staff detail) | The latest event with actor `UserRef` |
| `allowed_actions` | §7.8, for the caller and endpoint family |

- **Staff list** (`GET …/bookings`): D21 predicate + `status` (repeatable) + `q` ≤ 100 (case-insensitive: `reference` contains `q` — with or without `BF-`; the vehicle's `registration_key` contains the normalised `q`; or `customer_user_id = ANY(identity.find_user_ids_by_name(q))`) + `date_from`/`date_to` (shop-local dates on `slot_start`, converted with the shop's timezone; `date_from > date_to` → 422) + `technician_user_id` + `parts_person_user_id`; sort `slot_start` | `updated_at` | `status_changed_at` | `created_at`, each optionally descending, default `-updated_at`, tie-breaker `id`; `Page`. The QC queue is this endpoint with `status=QC_PENDING&status=QC_IN_PROGRESS&sort=status_changed_at` (no separate route).
- **Status counts**: `GROUP BY status` over the caller's D21 scope; all 17 statuses in glossary §3 order with zeros, plus `total`.
- **Customer list**: own bookings at every shop; `active` (`true` = non-terminal, `false` = terminal, omitted = all); sort `slot_start` | `-slot_start` | `-updated_at` (default `slot_start` when `active=true`, else `-slot_start`).
- **Timelines**: staff = every event, oldest first by `(created_at, seq)` (D79), with notes, actor and `metadata`; customer = the projection of `domain/timeline.py`: `EDIT_ESTIMATE`, `REASSIGN_TECHNICIAN`, `REASSIGN_PARTS_PERSON` omitted; `note` only for `DECLINE`, `CANCEL`, `REJECT_ESTIMATE`; `by_customer` instead of actor names, roles or metadata; `FAIL_QC` appears as `QC_IN_PROGRESS → IN_REPAIR` without issue details. `seq` is never exposed.
- **Booking-scoped reads**: `…/estimates` → `estimates.list_versions(include_stock = role ≠ QC_INSPECTOR)`; `…/parts` → visibility first (404), then 403 for `QC_INSPECTOR`, then `inventory.get_booking_parts`; `…/qc-inspections` → `qc.list_booking_qc_history`.
- **No N+1:** a page is assembled with a fixed number of batched calls (users, member refs, services, estimate summaries, parts summaries, QC summaries, `status_changed_at`) whatever its size (API-11, P1).

### 7.11 `booking.updated` recipients (glossary §11, D14, D21)

`list_booking_viewer_ids(booking_id)`, called by the notifications module **after commit, at push time**, with live data:

```
viewers = {booking.customer_user_id}
active = shops.list_active_member_ids(shop_id, roles=all five)          # active membership and account
viewers |= set(shops.list_active_member_ids(shop_id, roles={OWNER, SERVICE_ADVISOR}))
viewers |= {booking.technician_user_id, booking.parts_person_user_id} & active
qc_active = set(shops.list_active_member_ids(shop_id, roles={QC_INSPECTOR}))
if booking.status in QC_QUEUE_STATUSES: viewers |= qc_active
viewers |= set(qc.list_inspector_ids(shop_id, booking_id)) & qc_active
```

A deactivated member, a former assignee after `reassign-*`, a QC inspector who never touched the booking outside the queue, and members of other shops receive nothing (NOT-12, SEC-33).

## 8. Events

| Event | Direction | Payload | When | Consumers |
|---|---|---|---|---|
| `BookingActionApplied` | published | `shop_id`, `booking_id`, `reference`, `action`, `from_status` (null for `CREATE`), `to_status`, `version`, `actor_user_id`, `actor_role`, `customer_user_id`, `technician_user_id`, `parts_person_user_id`, `qc_inspector_user_id` (values **after** the action), `note`, `metadata`, `occurred_at` (spec 01) | Step 13 of every transition and operation, incl. `CREATE`, `RECEIVE_PARTS` and an `EDIT_ESTIMATE` that created a version | notifications: notification rows per glossary §6 (`recipient_role`, `link`, D67), after-commit `booking.updated` to `list_booking_viewer_ids` and `notification.created`, optional e-mail for `ESTIMATE_SENT` / `VEHICLE_READY` (D26) |
| `BookingPartsChanged` *(D83, glossary §7.1)* | published | `shop_id`, `booking_id`, `status`, `version`, `occurred_at` | A partial PO receipt reserved stock for a `PARTS_ORDERED` booking without completing it (§7.7) | notifications: no rows; after-commit `booking.updated` (`{booking_id, shop_id, status, version}`) to the viewers |
| `PurchaseOrderReceiving` | subscribed | `shop_id`, `purchase_order_id`, `booking_id`, `actor_user_id`, `occurred_at` | inventory receipt start | `on_purchase_order_receiving` |
| `PurchaseOrderReceived` | subscribed | `shop_id`, `purchase_order_id`, `po_number`, `booking_id`?, `received [{part_id, qty}]`, `actor_user_id`, `occurred_at` | inventory receipt written | `on_purchase_order_received` |
| `ShopGridChanging` | subscribed | `shop_id`, `changed_fields`, `actor_user_id`, `occurred_at` | shops `update_shop` changing duration or timezone | `on_shop_grid_changing` |

Events are `@dataclass(frozen=True, slots=True, kw_only=True)` with ids, enums and primitives only (spec 01). The `BOOKING_CANCELLED` recipient split (staff vs customer cancel) is read from `actor_role`.

## 9. Permissions and visibility

- **Who may act** is exactly spec 04 RBAC D / spec 08's rule table, evaluated by `check()`: Owner = SA for every SA action and never a technician, parts or QC action (D16, SM-16); technician, parts person and QC picker actions require the assignment guard; `pick-qc` is open to every active QC inspector except the booking's technician (D47); customer actions only on the customer family and only on the caller's own booking.
- **Who may see** is §7.5 (D21). Not visible → 404 with the identical problem body whether the booking does not exist, belongs to another shop or is simply not the caller's (SEC-01, SEC-08…SEC-11, SM-05, SM-17).
- **Audience-specific data** (spec 04 §C, SEC-12): customers never receive staff names, internal notes (inspection notes, repair notes, QC issue text, confirm notes), event `metadata`, stock data, or `DRAFT`/`SUBMITTED`/`SUPERSEDED` estimate versions; staff responses expose the customer's e-mail and phone only to `OWNER` and `SERVICE_ADVISOR`; QC callers get no stock fields and 403 on `…/parts`.
- **Check order** (spec 03 §1.4): 401 → 404 membership → 422 schema → 404 visibility → 403 `FORBIDDEN` → 403 `NOT_ASSIGNED` → 409 status (`INVALID_TRANSITION`, `ESTIMATE_LOCKED`, `ALREADY_PICKED`) → 409 `CONCURRENT_UPDATE` → 422 / 409 data guards.

## 10. Errors

| Code | HTTP | Raised when |
|---|---|---|
| `UNAUTHENTICATED` | 401 | Wizard with credentials present but invalid (from `get_optional_user`); any protected route without a valid session |
| `NOT_FOUND` | 404 | Booking not visible (D21), not own (customer family), other shop; wizard shop unknown, unlisted, suspended or without an active service (also when it closed while T01 waited for the shop row); unknown action slug in a family |
| `SHOP_SUSPENDED` | 403 | Customer action other than `cancel` on a booking of a suspended shop (D96, checked right after the own-booking lock); the three routes declare 403 |
| `FORBIDDEN` | 403 | Role not in the rule (e.g. technician `confirm`, Owner `pick-qc`); QC picker = technician (D47); QC on `…/parts`; parts person / QC on `PUT …/estimate` |
| `NOT_ASSIGNED` | 403 | Right role, not the assignee (in practice: non-picker `pass-qc` / `fail-qc`) |
| `INVALID_TRANSITION` | 409 | Action not allowed from the current status, incl. every action on `COMPLETED` / `CANCELLED` and `cancel` from `IN_REPAIR` on |
| `ESTIMATE_LOCKED` | 409 | `PUT …/estimate` outside the caller's editable status (domain `INVALID_TRANSITION` for `EDIT_ESTIMATE`, mapped here) |
| `ALREADY_PICKED` | 409 | `pick-qc` on `QC_IN_PROGRESS` (first pick wins) |
| `CONCURRENT_UPDATE` | 409 | `expected_version` mismatch; deadlock or lock timeout mapping (should not occur with the lock order) |
| `EMAIL_ALREADY_REGISTERED` | 409 | Wizard case D; case B losing the race on a new e-mail |
| `SLOT_FULL` | 409 | From `scheduling.reserve_slot` |
| `STALE_ESTIMATE` | 409 | From `estimates.approve` / `reject` |
| `INSUFFICIENT_STOCK` | 409 | From inventory (`mark-parts-ready`, `allocate-parts`) |
| `CONFLICT` | 409 | `order-parts` with nothing short (inventory); grid-change veto (§7.9); seed reference already used |
| `VALIDATION_ERROR` | 422 | Schema; anonymous wizard without name/e-mail/password; vehicle year; `service_ids.N`; estimate lines; QC checklist; `items` of `order-parts`; `decline`/staff `cancel` without reason (BK-22); `inspection_notes` `not_allowed`; `reassign-*` `unchanged`; `date_from > date_to` |
| `INVALID_SLOT` | 422 | From scheduling (wizard step 8 or 12) |
| `ESTIMATE_EMPTY` | 422 | From estimates (`submit-estimate`, `send-estimate`) |
| `MEMBER_NOT_ELIGIBLE` | 422 | From shops (`assign-*`, `reassign-*`) |
| `RATE_LIMITED` | 429 | Wizard per-IP (anonymous), per-user (session), per-account (cases C/D), with `Retry-After` |

## 11. Concurrency & transactions

- **One action = one transaction**, committed in the service before the response is built; nested service calls and handlers never commit (spec 01). A failure in any side effect rolls back status, event, estimates, stock, slot counter and notification rows together (NOT-07).
- **Locks per operation** (spec 02 §7.2 + D37):

| Operation | Locks, in order |
|---|---|
| `CREATE` (T01) | shop row `FOR SHARE` → vehicle row (upsert) → slot counter `FOR UPDATE` (the new booking row is an insert) |
| T02, T04–T12, T17–T21, O1–O5 | booking row only (estimates, booking parts, QC rows, events and notifications are written under it) |
| `ORDER_PARTS`, `MARK_PARTS_READY`, `ALLOCATE_PARTS` | booking → its booking parts' `parts` rows (ascending `id`) |
| PO receipt (+ `RECEIVE_PARTS`) | booking (via `PurchaseOrderReceiving`) → purchase order → received parts (ascending) |
| `DECLINE` | booking → slot counter |
| `CANCEL` | booking → parts reserved for it (ascending) → slot counter |

- **Key-only locking reads** (spec 02 §7.3): a transaction that waited for the booking lock re-reads the committed row and answers 409 (`INVALID_TRANSITION`, `ALREADY_PICKED`), never a misleading 404.
- **Proven races:** QC pick (SM-06 ★, lock gate on the booking), last slot (SM-07 ★, in scheduling), double submit (CON-01: one 200, one 409, one event, one version bump), cancel vs allocate (CON-02, P1), receipt vs cancel (CON-04, P1: either the receipt reserves and the cancel releases, or the cancel wins and the receipt reserves nothing), grid change vs booking (CON-05, P1).
- **Version:** `version` = number of events written (1 after `CREATE`); `expected_version` turns a stale client or a repeated `notify-ready` / `start-repair` into 409.
- **Clock:** one `utcnow()` per action, read right after the booking lock (T01: at the start), shared by every timestamp the action writes; event order within a booking equals commit order because all of them are written under the booking lock (D79).
- **Savepoints** only for reference retries (§7.3); a savepoint rollback keeps the outer transaction and its locks.
- **Argon2 never under a lock:** the wizard resolves the account (step 9) before its first lock (step 10).
- **No network I/O in the transaction:** pushes and e-mails run in after-commit callbacks.

## 12. Tests

Spec 12 / 08 / 04 IDs this module must make pass:

- **State machine (API halves):** SM-01 ★, SM-02, SM-03 ★, SM-04, SM-05 ★, SM-06 ★, SM-08 ★, SM-09, SM-10 ★, SM-11 ★, SM-12 ★, SM-13, SM-14, SM-15, SM-16 ★, SM-17, SM-18 ★, SM-19, SM-20 ★ (with SM-07 ★ through scheduling).
- **Security:** SEC-01 ★, SEC-02 (booking routes), SEC-07 (action matrix), SEC-08, SEC-09, SEC-10, SEC-11, SEC-12, SEC-17 (booking create), SEC-18, SEC-19, SEC-20, SEC-27 (wizard half), SEC-33 (no push to non-viewers), SEC-35.
- **Bookings:** BK-01…BK-07, BK-09, BK-10, BK-13…BK-15, BK-17…BK-26 (BK-25 is P1), BK-28, BK-29, BK-31, BK-32 (BK-08, BK-11, BK-12, BK-27, BK-30 belong to scheduling and shops).
- **Estimates through the flows:** EST-01, EST-02, EST-03, EST-10, EST-11, EST-13, EST-14, EST-15, EST-17, EST-19 *(P1)*.
- **Inventory and QC through the flows:** INV-05, INV-06, INV-09, INV-24 (receipt handler), INV-13 (cancel release); QC-03, QC-04, QC-05, QC-07, QC-09, QC-10.
- **Notifications contract:** NOT-01, NOT-02 *(P1)*, NOT-07, NOT-08 *(P1)*, NOT-12 (viewer ids).
- **API conventions:** API-06, API-10, API-11 *(P1)*.
- **Concurrency:** CON-01, CON-02 *(P1)*, CON-04 *(P1)*, CON-05 *(P1)*.
- **Seed and live:** SEED-06, SEED-10 ★, SEED-11, SEED-15 *(P1)*, DEP-09, DEP-10.

Proposed additional tests:

| ID (proposed) | Test |
|---|---|
| BK-33 | D83: a partial receipt for a `PARTS_ORDERED` booking writes no event and keeps `version`, but `booking.updated` reaches its viewers (server-side `TestClient` sockets) |
| BK-34 | `allowed_actions` of a list item equals the detail's for the same caller, for every role and status reached by `drive_booking_to` |
| BK-35 | `status_changed_at` ignores operations: after `start-repair`, `notify-ready` and an in-place estimate save it still equals the last status change |
| BK-36 | Customer projection: `EDIT_ESTIMATE` and `REASSIGN_*` absent; notes only on `DECLINE`, `CANCEL`, `REJECT_ESTIMATE`; no actor, role or `metadata` keys (complements SEC-12) |
| BK-37 | `GET …/parts`: QC inspector → 403 when the booking is in the queue, 404 when not visible; technician sees it only when assigned |
| BK-38 | `PUT …/estimate` by an SA or the Owner with `inspection_notes` → 422 `not_allowed`; by the technician → saved, no event |
| BK-39 | Concurrent `pick-qc` loser gets `ALREADY_PICKED` naming the picker; the picker's own repeated click gets the same 409 |
| BK-40 | `can_view` and the SQL predicate agree for every role × status × assignment combination (unit + one DB round-trip per role) |
| BK-41 | Grid veto counts only future non-cancelled bookings: a past booking or a cancelled future one does not block a duration change (complements BK-29) |
| BK-42 | Generated routes: the staff family has exactly the 20 (22 with P1) slugs and the customer family exactly 4; `POST …/actions/edit-estimate` → 404 |

## 13. Implementation checklist

Ordered by the roadmap phases (spec 14):

1. **PH1 (with shops):** `has_future_bookings`, `count_open_jobs`, `shop_activity_reader`, `on_shop_grid_changing`, `handlers.register(bus)`, and `service.register_ports()` calling `shops.service.register_activity_reader(shop_activity_reader)` (D86); `wire_modules()` loads them (D89), so `app/main.py` is not edited. `register_ports()` adds `inventory.service.register_booking_ref_reader(get_booking_refs)` once the PH5 inventory routes exist.
2. **PH2 domain:** `domain/references.py`, `domain/vehicles.py`, `domain/visibility.py`, `domain/timeline.py` with unit tests (BK-14, BK-40); `state_machine.py` is done.
3. **PH2 data access:** repositories (key-only `get_for_update` with `populate_existing`, the D21 predicate builder, list/count/sort, vehicle upsert, events with `(created_at, seq)` ordering, reference insert in a savepoint with retry).
4. **PH2 schemas** (requests with `extra="forbid"`; per-slug bodies; responses of spec 03 §3.3) and `events.py`.
5. **PH2 `create_booking`** (§7.1) + wizard router with the per-IP limit and `set_session_cookie`. The route serves anonymous and logged-in callers, so the anonymous ceiling is applied in the router body (`account_limiter().hit(parse(ANONYMOUS_BOOKING_IP_LIMIT), "booking-ip", client_ip(request))` only when `get_optional_user` returned `None`); a slowapi decorator would also count logged-in requests. The per-user limit lives in the service (spec 04 rate-limit table).
6. **PH2 executor** (§7.4) with T02, T03, T04, T22 (slot release; parts release arrives in PH5), `list_booking_viewer_ids`, staff and customer reads (lists, counts, detail, events), action-route factory; tests SM-05, SM-07, SM-15, SM-17, CON-01, BK-01…BK-19, SEC-01, SEC-18…SEC-20.
7. **PH4:** T05–T12 and `edit_estimate` with the estimates module; booking-scoped estimate reads; SM-08, SM-09, SM-14, EST tests.
8. **PH5:** T13, T14, T16, T22 parts release, the receipt handlers (§7.7) incl. `BookingPartsChanged`, `…/parts` read; SM-11, SM-12, SM-13, INV-05, INV-06, INV-09, INV-24.
9. **PH6:** T17–T21, O2, O3, QC reads, `count_day_activity` (reporting overview); SM-06, SM-10, SM-18 end to end; NOT-12 once the P1 WebSocket ships (D88).
10. **P1:** O4/O5 (empty `UNROUTED_SLUGS`), and D87's `REASSIGN_QC_INSPECTOR` with them once spec 08 / the glossary list it; customer estimate history, my vehicles, CON-02/04/05, API-11.
11. **P2:** read helpers for `calls` (spec 05): `find_customer_bookings`, `get_booking_labels`.
12. After each step: `make gen-api` (D76) and the import-linter contracts (spec 01).

## 14. Dependencies (specs)

[08-booking-state-machine.md](../08-booking-state-machine.md) (all of it), [17-decisions.md](../17-decisions.md) (D3, D9, D14, D16, D20–D35, D37, D43, D47, D48, D50, D51, D63–D65, D68, D69, D79, D83, D86–D89), [18-glossary.md](../18-glossary.md) (§1, §3, §4, §6, §7.1, §10, §11, §14), [01-architecture.md](../01-architecture.md) (layers, events, after-commit, rule 3), [02-data-model.md](../02-data-model.md) §3.7–§3.10, §4, §6, §7, [03-api-contracts.md](../03-api-contracts.md) §1.3–§1.7, §3.3, §4.6–§4.8, §5, §6, [04-auth-and-security.md](../04-auth-and-security.md) (wizard cases A–D, RBAC C/D, visibility predicate), [06-workflows.md](../06-workflows.md), [11-seed-data.md](../11-seed-data.md) (sample scripts, reserved references), [12-quality-and-testing.md](../12-quality-and-testing.md) §3–§5. Uses `modules/identity.md`, `modules/shops.md`, `modules/scheduling.md`, `modules/estimates.md`, and the inventory, qc and notifications module specs.

## Open questions

1. ✅ **Resolved by D83, spec 03 §6.4 and spec 09 §2.7: D83 push with an unchanged version.** A partial receipt publishes `BookingPartsChanged` (glossary §7.1) and the push carries the unchanged `version`; clients treat an **equal** version as "refetch the booking, its lists and the parts views" and ignore only an older one. The glossary §11 payload is unchanged.
2. ✅ **Resolved by D86: read ports.** `shop_activity_reader` implements shops' `ShopActivityReader` (`shops.service.register_activity_reader`) and `get_booking_refs` implements inventory's `BookingRefReader` (`inventory.service.register_booking_ref_reader`); this module's `register_ports()` registers both and `wire_modules()` calls it (D89; glossary §7.1a; spec 01 describes the mechanism, its open question 10).
3. **How inventory reports `receive_parts_applied`.** Settled in `modules/inventory.md`: it compares the booking's `BookingRef` before and after publishing `PurchaseOrderReceived` (handlers return nothing).
4. ✅ **Resolved in spec 12 (EST-11): who maps `ESTIMATE_LOCKED`.** The bookings edit-estimate use case maps the domain's `INVALID_TRANSITION` to 409 `ESTIMATE_LOCKED` (§7.6.1), because `estimates` may not import `bookings.domain`; `estimates.replace_lines` raises `ESTIMATE_LOCKED` itself as a backstop when the version is not editable.
5. ✅ **Resolved in spec 11: seed function names.** Spec 11 now calls `apply_staff_action` / `apply_customer_action` and `bookings.service.edit_estimate` (estimate edits must lock the booking and may write an event, which only bookings can do), creates booking-linked POs only through `order-parts` (D43), and orders events by `(created_at, seq)` (D79).
6. **Customer-name search.** `q` on the staff list needs user ids from identity (`find_user_ids_by_name`, capped); this module never joins `users`.
7. **Vehicle overwrite rule.** On re-booking, omitted `color` / `mileage_km` keep the stored values (so a quick re-booking does not erase them). Confirm against D35's "updates its details".
8. **Metadata shapes not fixed by spec 08.** Proposed here: `START_INSPECTION`, `REVISE_ESTIMATE`, `RETURN_TO_TECHNICIAN` `{estimate_id, version}`; `ASSIGN_PARTS_PERSON` `{parts_person_user_id, required}`; `MARK_PARTS_READY` `{reserved}`; `SEND_TO_QC` `{resolved_qc_issue_ids}`; `REASSIGN_*` `{…_user_id, previous_…_user_id}`; `CREATE`, `CONFIRM`, `DECLINE`, `START_REPAIR`, `NOTIFY_READY`, `COMPLETE` `{}`.
9. ✅ **Resolved by D87 (planned, P1): QC pick held by a deactivated inspector.** `REASSIGN_QC_INSPECTOR` will move the pick (§2 Scope); until it ships, the Owner reactivates the inspector to finish the round. Its implementation also needs a qc function that moves the open `qc_inspections` round to the new inspector (`modules/qc.md`).
10. **Not in P0, still open elsewhere:** `Idempotency-Key` on `POST /api/v1/bookings` (spec 03 Open question 2) and an active-booking cap per customer (spec 04 Open question 9).

## Proposed glossary additions

| Kind | Name | Meaning |
|---|---|---|
| Event (§7.1) | ✅ merged — `BookingPartsChanged` (bookings → notifications) | A booking's parts state changed without a booking event (D83); notifications pushes `booking.updated` |
| Read ports (§7.1a) | ✅ merged — `shop_activity_reader` (shops' `ShopActivityReader`), `get_booking_refs` (inventory's `BookingRefReader`) | D86 |
| Domain files and constants | `bookings/domain/vehicles.py`, `visibility.py`, `timeline.py` (spec 01 already names `references.py`); `REFERENCE_ALPHABET`, `QC_QUEUE_STATUSES`, `UNROUTED_SLUGS`, `CUSTOMER_HIDDEN_ACTIONS`, `CUSTOMER_NOTE_ACTIONS` | Pure rules shared by queries, responses and tests |
| Service functions | `bookings.service`: `has_future_bookings`, `count_open_jobs`, `count_day_activity` (+ its `DayActivity` result), `get_status_counts`, `list_booking_events`, `list_customer_booking_events`, `list_booking_estimates`, `list_customer_estimates`, `get_booking_parts`, `list_booking_qc_inspections`, `list_my_vehicles`; P2 `get_booking_labels` (+ `BookingLabel`) | Additions to spec 01's bookings catalogue |
| Booking action (planned, D87) | `REASSIGN_QC_INSPECTOR` / `reassign-qc-inspector` (O6) | Glossary §4 and spec 08 when it is implemented |
| Functions required from other modules | qc: `list_inspected_booking_ids`, `has_inspected`, `get_qc_summaries`, `list_inspector_ids`; inventory: `get_booking_parts` (and `reserve_received_for_booking` returning `(reserved, all_reserved)`); identity: `issue_session`, `find_user_ids_by_name`; shops: `get_bookable_shop`, `get_shop_briefs`, `get_member_refs`; scheduling: `validate_slot` | To be adopted by those module specs |
| Limiter identifiers | `"booking-ip", <ip>`, `"booking-user", <user_id>` | Keys in the shared `account_limiter()` storage |
