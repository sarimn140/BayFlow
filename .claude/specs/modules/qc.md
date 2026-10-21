# Module: qc

**Status:** Draft
**Package:** `app.modules.qc`
**Owns tables:** `qc_inspections`, `qc_issues` (glossary §7)
**Priority:** P0 (brief §7.4, §5.3). One planned P1 addition (D87, see In scope); nothing in P2.

## Purpose

Record every quality-check round of a booking and the issues a failed round raises. Brief §7.4 QC Inspector: "Shared QC queue; pick a job; checklist/notes; pass or create issue (title, description) which returns the job to the technician". Brief §5.2 rows 12–13 (any QC person picks from the queue; pass → `READY_FOR_PICKUP`, problem → issue and `IN_REPAIR`), §5.3 "QC failure loop: a failed QC creates an Issue record and returns the job to the technician; it can repeat until QC passes", §7.8 "Both the QC fail loop and the estimate-rejected path work", FAQ "Who can pick a QC job? Any QC person of that shop … first to pick locks it", §7.4 Technician "view QC issues sent back", §6 steps 12–14, and the §2/§3 pain "QC skipped or done by the same person who did the repair".

The module does not change booking status and does not own the queue. The bookings module runs T17–T20 (spec 08) under its booking lock and calls the functions below; the QC queue is the bookings list filtered by `QC_PENDING` / `QC_IN_PROGRESS`, which D21 already scopes (spec 03 §4.8).

## In scope

- **P0**
  - The default checklist (D46), defined in code, and `GET …/qc/checklist`.
  - One `qc_inspections` row per round: opened on `pick-qc` (T18), completed by `pass-qc` (T19) or `fail-qc` (T20).
  - Issues: created `OPEN` by `fail-qc`, `RESOLVED` by the next `send-to-qc` (T17).
  - QC history of a booking for `GET …/bookings/{booking_id}/qc-inspections` (served by bookings).
  - Derived counts for booking summaries: `qc_round` and `open_qc_issues_count` (spec 03 §3.3).
  - Visibility helpers for D21: the bookings a QC inspector inspected, and the inspectors of a booking (realtime fan-out, glossary §11).
- **P1 (planned, D87):** when bookings ships `REASSIGN_QC_INSPECTOR`, this module needs one more nested write, e.g. `reassign_open_inspection(uow, *, shop_id, booking_id, new_inspector_user_id, now)`, that moves the open round (`result IS NULL`) to the new inspector — otherwise the new picker's `pass-qc` / `fail-qc` would hit the "open round's inspector ≠ caller → 500" rule of §"A QC round". The previous picker stays in the booking event's metadata.
- **P2:** none. The AI Front Desk never receives QC issues (spec 05 §4.3).

## Out of scope

Per-shop or custom checklists, photos and attachments, issue severity or categories, reopening or editing issues, sending an issue to a different technician (always the same one, D47), QC timers or SLAs, editing a finished inspection, QC statistics (owner analytics such as "QC fail rate" are a brief §8.3 optional idea, not built).

## Key decisions

| D | What it means here |
|---|---|
| D46 | Default checklist keys `road_test`, `no_warning_lights`, `no_leaks`, `fluid_levels`, `complaint_resolved` + free-text notes, stored as JSON on `qc_inspections.checklist` for pass and fail. `PASS_QC` needs every item passed; `FAIL_QC` needs an issue title and description, checklist optional. |
| D47 | `FAIL_QC` creates an `OPEN` issue, clears the picker and returns the job to the **same** technician; `PASS_QC` keeps the picker; `SEND_TO_QC` resolves open issues and clears the picker; any inspector may re-test; the picker is never the booking's technician. |
| D30 | First pick wins: the booking row lock plus the status check give the loser 409 `ALREADY_PICKED`; `uq_qc_inspections_one_open_per_booking` is the database backstop. |
| D21 | QC inspectors see bookings in `QC_PENDING` / `QC_IN_PROGRESS` of their shop plus those they inspected; everything else is 404. |
| D16 | The Owner opens the QC views read-only and never performs a QC action (403, SM-16). |
| D20 | `qc_inspections (shop_id, inspector_user_id)` → `shop_memberships (shop_id, user_id)` and the booking composite FKs keep QC rows inside one shop. |
| D63 | `picked_at`, `completed_at`, `resolved_at` and issue `created_at` are the action's instant, passed in by bookings. |
| D74, D75 | `QcResult`, `QcIssueStatus`, `QcChecklistKey` come from `app.shared.enums`; test IDs are `QC-xx`, QC Inspector screens `QI-xx`. |
| D86 | QC sits below bookings and never imports it; bookings calls the functions below and passes everything they need. A future upward read would use a read port that bookings registers from its `register_ports()` at start-up (D89), like shops' `ShopActivityReader` (`shops.service.register_activity_reader`) and inventory's `BookingRefReader` (`inventory.service.register_booking_ref_reader`). |
| D87 | Planned P1 `REASSIGN_QC_INSPECTOR` (bookings) un-sticks a pick held by a deactivated inspector; it needs the open-round move described under In scope. Until then the Owner reactivates the inspector. |

## Files

| File | Contents |
|---|---|
| `router.py` | `shop_scoped_router(tags=["qc"])` with the one route `GET …/qc/checklist` (spec 03 §4.11). |
| `schemas.py` | Spec 03 §3.6: `QcChecklistTemplateItem`, `QcChecklistItemWrite`, `QcChecklistItemRead`, `QcIssueRead`, `QcInspectionRead`. Internal: `QcSummary`, `FailRecorded`. |
| `service.py` | The functions below. |
| `repository.py` | `QcInspectionRepository` (open round by booking, rounds by booking, counts, inspector ids), `QcIssueRepository` (open issues, resolve-all update); every method takes `shop_id`. |
| `models.py` | Already implemented: `QcInspection`, `QcIssue`. |
| `domain/checklist.py` | `CHECKLIST` template and `validate_checklist(items, *, require_all_passed)` (pure). |

No `events.py` or `handlers.py`: the module publishes and subscribes to nothing.

## Public service interface

Writes take `uow`, reads `session`, first (spec 01). All take `shop_id` keyword-only (D20). The four write functions are **nested**: only `bookings.service` calls them, inside a booking action that already holds the booking lock and has passed the state machine (role, `QC_PICKER` guard, status, `expected_version`). They never commit. `now` is the action's instant.

| Function | Rule | Returns | Raises |
|---|---|---|---|
| `resolve_open_issues(uow, *, shop_id, booking_id, resolved_by_user_id, now)` | T17 | ids of the issues resolved (possibly none) | — |
| `open_inspection(uow, *, shop_id, booking_id, inspector_user_id, now)` | T18 | the new `qc_inspection_id` (`PICK_QC` metadata) | 409 `ALREADY_PICKED` (unique-index backstop) |
| `record_pass(uow, *, shop_id, booking_id, inspector_user_id, checklist, notes, now)` | T19 | `qc_inspection_id` (`PASS_QC` metadata) | 422 `VALIDATION_ERROR` |
| `record_fail(uow, *, shop_id, booking_id, inspector_user_id, issue_title, issue_description, checklist, notes, now)` | T20 | `FailRecorded(qc_inspection_id, qc_issue_id)` (`FAIL_QC` metadata) | 422 `VALIDATION_ERROR` |

Reads:

| Function | Caller | Returns |
|---|---|---|
| `default_checklist()` | qc router | `list[QcChecklistTemplateItem]` in D46 order (pure) |
| `list_booking_qc_history(session, *, shop_id, booking_id)` | bookings (`bookings_list_booking_qc_inspections`, after D21) | `list[QcInspectionRead]`, rounds ascending |
| `get_qc_summaries(session, *, shop_id, booking_ids)` | bookings (lists and details; batch, API-11) | `dict[UUID, QcSummary(inspections, open_issues)]`, one entry per id (zeros included) |
| `list_inspected_booking_ids(session, *, shop_id, inspector_user_id)` | bookings (D21 predicate on lists for QC callers) | `frozenset[UUID]` |
| `has_inspected(session, *, shop_id, booking_id, inspector_user_id)` | bookings (D21 on item routes and actions) | `bool` |
| `list_inspector_ids(session, *, shop_id, booking_id)` | bookings (`list_booking_viewer_ids`, glossary §11) | `frozenset[UUID]` |

`checklist` arguments are `Sequence[QcChecklistItemWrite]` (`record_fail`: `… | None`). The bookings schemas `PassQcRequest` and `FailQcRequest` (spec 03 §5.2) embed `QcChecklistItemWrite` from this module. Bookings derives `qc_round = inspections + (1 if status == QC_PENDING else 0)` (0 when the booking never reached QC) and `open_qc_issues_count = open_issues`. Actor names in `QcInspectionRead` / `QcIssueRead` (`UserRef`) come from `identity.service.get_users_by_ids` in one batch.

## Endpoints

Served by this module ([spec 03 §4.11](../03-api-contracts.md)):

| Method | Path | `operationId` | Roles | Success | Pri |
|---|---|---|---|---|---|
| GET | `/api/v1/shops/{shop_id}/qc/checklist` | `qc_get_checklist` | any active member | 200 `ItemList[QcChecklistTemplateItem]` | P0 |

Served by **bookings** with this module's data (spec 03 §4.8, §5.2):

| Route | `operationId` | qc function |
|---|---|---|
| `GET …/bookings?status=QC_PENDING&status=QC_IN_PROGRESS&sort=status_changed_at` (the QC queue, QI-01) | `bookings_list_shop_bookings` | `list_inspected_booking_ids`, `get_qc_summaries` |
| `GET …/bookings/{booking_id}` | `bookings_get_shop_booking` | `has_inspected`, `get_qc_summaries` |
| `GET …/bookings/{booking_id}/qc-inspections` | `bookings_list_booking_qc_inspections` | `list_booking_qc_history` |
| `POST …/actions/send-to-qc` (T17) | `bookings_send_to_qc` | `resolve_open_issues` |
| `POST …/actions/pick-qc` (T18) | `bookings_pick_qc` | `open_inspection` |
| `POST …/actions/pass-qc` (T19) | `bookings_pass_qc` | `record_pass` |
| `POST …/actions/fail-qc` (T20) | `bookings_fail_qc` | `record_fail` |

## Domain rules and algorithms

### The checklist (D46)

| Order | `key` (`QcChecklistKey`) | `label` (spec 03 §3.6) |
|---|---|---|
| 1 | `road_test` | Road test |
| 2 | `no_warning_lights` | No warning lights |
| 3 | `no_leaks` | No leaks |
| 4 | `fluid_levels` | Fluid levels OK |
| 5 | `complaint_resolved` | Customer complaint resolved |

`validate_checklist(items, *, require_all_passed)` returns field errors (no exceptions in the domain):

- Exactly these five keys, each once, in any order. A missing or repeated key → field `checklist`, code `checklist_incomplete`.
- An unknown key never reaches the domain: `QcChecklistItemWrite.key` is the `QcChecklistKey` enum, so the schema answers 422 at `checklist.N.key`, code `enum` (see Open questions).
- `require_all_passed` (pass only): every failed item → field `checklist.N.passed`, code `checklist_item_failed`, message "This item failed — use fail-qc." All failed items are reported together.
- Item `note` ≤ 500 characters, inspection `notes` ≤ 2000, issue title 1–120 and description 1–2000, trimmed and not blank: schema rules (spec 03 §5.2), mirrored by the column sizes and `not_blank` CHECKs.

Stored form (`qc_inspections.checklist`, `jsonb` array, spec 02 §3.18): the five items in template order, each `{"key", "label", "passed"}` plus `"note"` when given. The label is copied at write time, so a finished round keeps its wording if a label changes later.

### A QC round (spec 08 T17–T20, "QC loop")

| Step | Booking (written by bookings) | `qc_inspections` | `qc_issues` |
|---|---|---|---|
| T17 `send-to-qc` | → `QC_PENDING`; `qc_inspector_user_id` = NULL | — | every `OPEN` issue of the booking → `RESOLVED`, `resolved_at = now`, `resolved_by_user_id` = the technician (one `UPDATE … WHERE shop_id, booking_id, status = 'OPEN'`) |
| T18 `pick-qc` | → `QC_IN_PROGRESS`; `qc_inspector_user_id` = picker | new row: `inspector_user_id` = picker, `picked_at = now`, `result` NULL | — |
| T19 `pass-qc` | → `READY_FOR_PICKUP`; picker **kept** | the open row: `result = PASS`, `completed_at = now`, checklist (required, all passed), `notes` | — |
| T20 `fail-qc` | → `IN_REPAIR`, same technician; picker cleared | the open row: `result = FAIL`, `completed_at = now`, checklist if sent (else NULL), `notes` | new `OPEN` issue: `booking_id`, `qc_inspection_id` = the open row, `title`, `description`, `created_by_user_id` = picker |

Rules:

- The open round is `SELECT … WHERE shop_id = :shop_id AND booking_id = :booking_id AND result IS NULL` (at most one, by the partial unique index). In T19/T20 it must exist and its `inspector_user_id` must equal the caller, because the state machine already checked `bookings.qc_inspector_user_id`; a mismatch is a data-integrity bug → 500, never a user error.
- `qc_issues.booking_id` always equals its inspection's booking (no CHECK can see the other table, spec 02 §3.19; the service guarantees it).
- Rounds are unlimited (brief §5.3). `round` in `QcInspectionRead` is the 1-based position by `(picked_at, id)`.
- Any active QC inspector may pick a re-test (QC-10); the previous picker has no claim on it.
- The picker can never be the booking's technician: the state machine's `PICK_QC` check (`is_booking_technician` → 403 `FORBIDDEN`, D47, QC-08) and `ck_bookings_qc_picker_not_technician`. With one role per shop membership it cannot happen through the API.
- A cancelled booking never has QC rows: `cancel` is refused from `IN_REPAIR` onwards (glossary §3).

Worked example (spec 08 trace steps 11–14): `send-to-qc` → Sara picks (round 1) → fails with "Oil leak at filter" (issue `OPEN`, Imran gets `QC_FAILED`) → Imran resends (issue `RESOLVED`) → Sara picks (round 2) → passes. Two rows (`FAIL`, `PASS`), one resolved issue.

### Who sees QC data

- Staff with visibility of the booking (D21) see every round with checklist, notes and issues; the technician sees the issues sent back (brief §7.4, QC-09).
- Customers never see QC details: their timeline shows `FAIL_QC` as `QC_IN_PROGRESS → IN_REPAIR` without the issue (spec 03 §3.3, spec 04 §C).
- QC inspectors get `parts_summary: null` and no stock data (bookings and inventory apply that).

## Events

Publishes nothing and subscribes to nothing. Bookings publishes `BookingActionApplied` for T17–T20 with metadata `PICK_QC`/`PASS_QC` `{qc_inspection_id}` and `FAIL_QC` `{qc_inspection_id, qc_issue_id}` (spec 08). Notifications then sends `QC_REQUESTED` → every active QC inspector (T17), `QC_FAILED` → the technician (T20) and `QC_PASSED` → the SAs of the shop (T19, extra); `PICK_QC` has no notification. `booking.updated` reaches QC inspectors while the booking is `QC_PENDING` / `QC_IN_PROGRESS` and those who inspected it (`list_inspector_ids`).

## Permissions and visibility

| Capability | O | SA | T | PP | QC |
|---|---|---|---|---|---|
| Checklist template | ✅ | ✅ | ✅ | ✅ | ✅ |
| QC queue and QC history (bookings reads) | read, all bookings | read, all bookings | own assigned bookings | own assigned bookings | `QC_PENDING` / `QC_IN_PROGRESS` of the shop + inspected ones |
| `pick-qc` | 403 | 403 | 403 | 403 | any active QC inspector, never the booking's technician |
| `pass-qc`, `fail-qc` | 403 | 403 | 403 | 403 | the picker; another inspector → 403 `NOT_ASSIGNED` |
| `send-to-qc` | 403 | 403 | assigned technician | 403 | 403 |

Non-members get 404 on every route. A booking outside the caller's D21 set is 404 (SEC-10). These checks run in bookings before any qc function (spec 08 "How an action is executed").

## Errors

| Code | HTTP | When |
|---|---|---|
| `VALIDATION_ERROR` | 422 | `checklist_incomplete`, `checklist_item_failed`, `enum` (unknown key), missing or over-long issue fields or notes |
| `ALREADY_PICKED` | 409 | A second `pick-qc` (state machine on the locked row) or the unique-index backstop |
| `NOT_ASSIGNED` | 403 | `pass-qc` / `fail-qc` by a QC inspector who is not the picker |
| `FORBIDDEN` | 403 | Another role; the picker would be the booking's technician (D47) |
| `INVALID_TRANSITION` | 409 | Action not allowed from the current status |
| `CONCURRENT_UPDATE` | 409 | Stale `expected_version` (checked by bookings) |
| `NOT_FOUND` | 404 | Booking not visible; non-member |

## Concurrency and transactions

- Every qc write happens inside one booking action under the booking row lock (spec 02 §7.2: T17–T21 lock only the booking). No qc row is locked separately; the booking lock serialises all QC writes of that booking.
- **First pick wins (SM-06, lock-gate test):** two inspectors queue on the booking lock; the second re-reads `QC_IN_PROGRESS` and gets 409 `ALREADY_PICKED`; afterwards there is one open inspection and one `PICK_QC` event. `uq_qc_inspections_one_open_per_booking` maps to 409 `ALREADY_PICKED` by constraint name (spec 03 §2.4).
- The QC fail loop is sequential by construction (each step needs the previous status), so no other race exists.
- All rows of one action share the action's `now` (D63); a stepping `SimulatedClock` in tests gives each round its own instant.

## Tests

- **Must pass (spec 12):** QC-01 … QC-11, SM-06 ★, SM-10 ★, SM-04 and SM-16 (QC cells), SM-18 steps 11–14, SEC-10, SEC-12 (no issue details for customers), NOT-01 (`QC_REQUESTED`, `QC_FAILED`), NOT-02 (`QC_PASSED`), NOT-12 (QC viewers), SEED-06 (BF-SEED07's two rounds).
- **Proposed additions:**

| ID | Test |
|---|---|
| QC-12 | `GET …/qc/checklist` returns the five items in D46 order with spec 03 labels for every role; non-member → 404 |
| QC-13 | Missing, repeated and unknown keys → 422 with `checklist_incomplete` / `enum`; a failed item on pass → `checklist_item_failed` listing every failed item |
| QC-14 | `qc_round` and `open_qc_issues_count` through a fail loop: 0 before QC, 1 at `QC_PENDING`, 1 after the fail, 2 at the re-test; open issues 1 → 0 on resend |
| QC-15 | `fail-qc` without a checklist stores NULL; with one, the stored JSON has labels in template order and item notes |
| QC-16 | After a booking leaves QC, the inspector who inspected it still sees it and its history; another QC inspector gets 404 |
| QC-17 | Repository: inserting a second open inspection for a booking → mapped to 409 `ALREADY_PICKED` |

## Implementation checklist

1. `domain/checklist.py` (template + validation) with unit tests (QC-13).
2. `schemas.py` (`QcChecklistItemWrite` with the `QcChecklistKey` enum, item note ≤ 500).
3. `repository.py` (open round, rounds with issues, batch counts, inspected ids, inspector ids, resolve-all update).
4. Service write functions (T17–T20) and reads; `UserRef` names in one batch.
5. `router.py` with the checklist route, exported as `routers` (`wire_modules()` includes it, D89).
6. Bookings wiring (spec 14 PH6): executor calls for T17–T20; D21 predicate with `list_inspected_booking_ids` / `has_inspected`; `qc_round`, `open_qc_issues_count`; viewers with `list_inspector_ids`.
7. Tests above, including the SM-06 lock-gate test and the SM-10 scenario.

## Dependencies (specs)

- [17-decisions.md](../17-decisions.md) D16, D20, D21, D30, D46, D47, D63, D74, D75, D86, D87; [18-glossary.md](../18-glossary.md) §3, §4, §5, §6, §10, §11.
- [08-booking-state-machine.md](../08-booking-state-machine.md) T17–T20, "QC loop", metadata, SM-06, SM-10.
- [03-api-contracts.md](../03-api-contracts.md) §3.3 (derived fields, customer projection), §3.6, §4.8, §4.11, §5.2; [02-data-model.md](../02-data-model.md) §3.18, §3.19, §7.
- [04-auth-and-security.md](../04-auth-and-security.md) RBAC C and D; [06-workflows.md](../06-workflows.md) Q1–Q5, E4; [10-screens.md](../10-screens.md) QI-01, QI-02, T-02; [12-quality-and-testing.md](../12-quality-and-testing.md) QC, SM.
- Other modules: [bookings.md](bookings.md) (the only caller; it expects exactly these function names, §5.5, and records `SEND_TO_QC` metadata `{resolved_qc_issue_ids}` from `resolve_open_issues`), [identity.md](identity.md) (`get_users_by_ids`), [notifications.md](notifications.md) (QC notifications).

## Open questions

1. ✅ **Resolved in spec 01 (its open question 11): router.** `qc` has one router with `GET …/qc/checklist` (spec 03 §1.11, §4.11); spec 01's folder tree now says so.
2. ✅ **Resolved in spec 03 (§2.3, §3.6, §5.2): unknown checklist key.** A missing or repeated key → `checklist_incomplete` (field `checklist`); an unknown key → `enum` at `checklist.N.key`, because `key` is typed `QcChecklistKey` (a TypeScript union for the QI-02 form).
3. ✅ **Resolved by D92: `FAIL_QC` event note = the issue title.** Spec 08 does not say what note the `FAIL_QC` event carries, and `modules/bookings.md` currently writes none, so the `QC_FAILED` notification can only say "returned the job with an issue to fix". Storing the issue title as that note would let the technician's bell show it without notifications reading qc tables; customers never see that note (spec 03 §3.3). A small change for `modules/bookings.md`, if wanted.
4. **`REASSIGN_QC_INSPECTOR` and the open round (D87, planned).** Moving the open `qc_inspections` round to the new inspector (In scope, P1) is the simplest fit with `uq_qc_inspections_one_open_per_booking`; recording who first picked it lives only in the booking event. Confirm when D87 is implemented.

## Proposed glossary additions

| Kind | Name | Meaning |
|---|---|---|
| Service functions | `get_qc_summaries`, `list_inspected_booking_ids`, `has_inspected`, `list_inspector_ids` | Reads that let bookings compute `qc_round`, `open_qc_issues_count`, the D21 QC predicate and the glossary §11 QC viewers |
| Internal values | `QcSummary` (`inspections`, `open_issues`), `FailRecorded` (`qc_inspection_id`, `qc_issue_id`) | Return types of the functions above and of `record_fail` |
| File | `app/modules/qc/router.py` (checklist only) | ✅ spec 01 now lists it (its open question 11); glossary §7 says a module creates only the files it needs |
