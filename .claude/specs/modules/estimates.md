# Module: estimates

**Status:** Draft
**Package:** `app.modules.estimates`
**Owns tables:** `estimates`, `estimate_lines`

## 1. Purpose

Own the cost estimate of a booking as a series of **versions** (`estimates` rows) with their **lines** (`estimate_lines`): the technician's draft, the Service Advisor's revisions, the version sent to the customer, and the customer's timestamped decision. This module computes every total on the server in whole rupees, enforces which version may change and which are frozen, decides which versions a customer may see, and hands the approved version's part requirements to inventory.

It has **no router**. Its HTTP surface is booking-scoped and served by `bookings` (spec 03 §1.11), which locks the booking, applies D21 visibility and spec 08's rule table, and then calls this module inside the same transaction. Estimates never imports `bookings` (module direction, spec 01): the caller passes the booking status, and this module defends its own invariants as a backstop.

Brief sections satisfied:

- §7.4 Technician: "add estimate line items (part, quantity, unit cost, labour); submit to SA"; Service Advisor: "review/edit estimate; send to customer".
- §7.5 "Estimate versioning or at least a revision count when SA edits before sending".
- §3 "Itemized estimate with parts and labour, sent to the customer, accepted in-app with timestamp"; §2 "Disputes over price ('I never agreed to that'), no audit trail" and "parts availability is unknown at estimate time".
- §7.3 customer dashboard "estimate detail with itemized parts and labour, accept/reject buttons"; §5.2 rows 4–7; §5.3 "Estimate rejected: SA is notified and can revise the estimate with the technician, or cancel the booking".
- §6 steps 5–7: v1 PKR 16,600 (coil 6,500 + filter 900 + oil 5,200 + labour 4,000) → Bilal edits labour to 3,500 → v2 PKR 16,100, approved by Ahmed.

## 2. Scope

| Priority | In scope |
|---|---|
| **P0** | `ensure_draft` (T05), `replace_lines` (O1: validation, pricing, new version on the first desk edit), `submit` (T06), `send` (T07), `approve` / `reject` (T08/T09, 409 `STALE_ESTIMATE`), `copy_rejected_to_draft` (T10/T11), `supersede_open_versions` (T22), `get_approved_part_requirements` (T12); reads: all versions with live stock (staff), summaries for booking lists, the customer view (latest customer-visible version and "revision in progress"). Whole-rupee arithmetic and the overflow guard (D41). |
| **P1** | Data for `GET /api/v1/me/bookings/{booking_id}/estimates` ("previous versions"); EST-19 event metadata (built by bookings from `EstimateSnapshot`). |
| **P2** | The AI agent's estimate view (spec 05 `GET …/bookings/{reference}/estimate`: only `SENT`, `APPROVED`, `REJECTED`) reuses `get_customer_view`. |
| **Out of scope** | Discounts, taxes, paisa (whole rupees only, D41); payments, invoices, PDF (brief §8.3, FAQ); partial approval of individual lines; estimate templates and labour-rate catalogues; editing a version after it was sent; deleting versions; stock reservation (inventory, at T13/T14 — estimates only **shows** live stock, D40); the edit endpoint itself, its locking, events and version bumps (bookings). |

## 3. Key decisions

| D | What it means here |
|---|---|
| D39 | One `estimates` row per version. The technician edits the `DRAFT` v1 while `INSPECTING`; `SUBMIT_ESTIMATE` → `SUBMITTED`. The first SA/Owner edit in `ESTIMATE_REVIEW` creates a new `DRAFT` (author = editor) and marks the `SUBMITTED` one `SUPERSEDED`; later desk edits update that draft. `SEND_ESTIMATE` → `SENT`; the customer decision → `APPROVED` / `REJECTED` with `decided_at`, `decided_by_user_id`. `REVISE_ESTIMATE` / `RETURN_TO_TECHNICIAN` copy the rejected version into a new `DRAFT`. `SENT`, `APPROVED`, `REJECTED`, `SUPERSEDED` are immutable. Customers only ever see `SENT`, `APPROVED`, `REJECTED`. |
| D40 | `PART` lines reference an **active** part of the same shop; unit price defaults to `parts.unit_cost` and is editable; `LABOUR` lines are free text × quantity × unit price; totals always recomputed on the server; the editor shows live stock per part line. (`inspection_notes` on `PUT …/estimate` are stored on the booking by `bookings`.) |
| D41 | PKR in whole rupees: unit prices whole numbers, each line total = quantity × unit price **rounded half-up** to whole rupees, `numeric(12,2)` always `.00`, Python `Decimal`, JSON decimal strings with 2 places. |
| D16 | The Owner edits, sends and revises exactly like a Service Advisor (`ESTIMATE_REVIEW`); never the technician's draft. |
| D23 | From `ESTIMATE_REJECTED`: revise (SA edits a new draft) or return to the technician (technician edits a new draft). |
| D24 | Cancellation turns the open version (`DRAFT`, `SUBMITTED` or `SENT`) into `SUPERSEDED`; `APPROVED` / `REJECTED` stay. |
| D30 | A plain draft save writes no booking event and bumps no `bookings.version`; only a save that **creates a version** does (bookings acts on `created_new_version`). |
| D20, D50, D63 | Every query carries `shop_id`; composite FKs keep estimates, lines and parts in one shop; ids are UUID v4 from Python; every timestamp is the action's clock instant passed in by the caller. |
| D21 | QC inspectors see estimate versions without stock fields (spec 04 §B); every other staff role that can see the booking sees all versions. |
| D86 | Estimates sits below bookings and never imports it: bookings passes the booking status in. If this module ever needs more bookings facts, it declares a read port that bookings registers from its `register_ports()` at start-up (D89), as shops does with `ShopActivityReader` (`shops.service.register_activity_reader`) and inventory with `BookingRefReader` (`inventory.service.register_booking_ref_reader`); today it needs none. |

## 4. Files

| File | Contents |
|---|---|
| `models.py` | `Estimate`, `EstimateLine` (exist; spec 02 §3.11–§3.12) with `uq_estimates_booking_id_version`, `uq_estimates_shop_id_id`, `uq_estimates_one_open_version_per_booking`, `uq_estimates_one_approved_per_booking`, `uq_estimate_lines_estimate_id_position`, the totals / whole-rupee / field-consistency checks and `ck_estimate_lines_line_total = round(quantity * unit_price)`. |
| `domain/lines.py` | The line rules in one place (as built): per-type field requirements and limits, 1–50 lines, used by both the `EstimateLineWrite` validator and `price_lines`, so every bad line is reported in one 422 on `lines.N.<field>`. |
| `domain/totals.py` | `line_total(quantity, unit_price)`, `estimate_totals(lines)`, `MAX_AMOUNT = Decimal("9999999999.00")`. Pure `Decimal`, `ROUND_HALF_UP`. |
| `domain/versions.py` | `OPEN_STATUSES = {DRAFT, SUBMITTED, SENT}`, `CUSTOMER_VISIBLE_STATUSES = {SENT, APPROVED, REJECTED}`, `FINAL_STATUSES = {APPROVED, REJECTED, SUPERSEDED}`, `EditDecision` (`IN_PLACE`, `NEW_VERSION`, `LOCKED`), `edit_target(booking_status, latest_status)`, `customer_shown(versions)`, `revision_in_progress(versions, shown)`. |
| `repository.py` | `EstimateRepository` (latest, by status, all versions of a booking, latest / latest-visible for many bookings, next version number, add, status updates, bulk supersede) and `EstimateLineRepository` (lines of many estimates in position order, bulk delete of one estimate's lines, add many, part requirements of one estimate). Every method takes `shop_id`. |
| `schemas.py` | Requests: `EstimateUpdate`, `EstimateLineWrite`. Responses (spec 03 §3.4): `EstimateRead`, `EstimateLineRead`, `EstimateEditRead`, `EstimateSummary`, `CustomerEstimateRead`, `CustomerEstimateLineRead`. Internal: `EstimateSnapshot`, `EstimateEdit`, `CustomerEstimateView` (part requirements reuse inventory's `PartQty`). |
| `service.py` | The functions of §5. |

No `router.py`, `events.py` or `handlers.py`.

## 5. Public service interface

All writes are **nested**: they run inside the caller's transaction, which already holds the booking row lock (spec 02 §7.2), and never commit. `now` is the caller's action instant (D63).

| Function | Arguments → returns | Errors | Caller (spec 08 row) |
|---|---|---|---|
| `ensure_draft` | `(uow, *, shop_id, booking_id, created_by_user_id, now) → EstimateSnapshot` | — | `START_INSPECTION` (T05) |
| `replace_lines` | `(uow, *, shop_id, booking_id, booking_status: BookingStatus, actor_user_id, lines: list[EstimateLineWrite], now) → EstimateEdit` (`estimate: EstimateRead`, `created_new_version: bool`) | 409 `ESTIMATE_LOCKED`, 422 `VALIDATION_ERROR` | `PUT …/estimate` (O1) |
| `submit` | `(uow, *, shop_id, booking_id, now) → EstimateSnapshot` | 422 `ESTIMATE_EMPTY`, 422 `VALIDATION_ERROR` (`lines.N.part_id`), 409 `ESTIMATE_LOCKED` (backstop) | `SUBMIT_ESTIMATE` (T06) |
| `send` | `(uow, *, shop_id, booking_id, sent_by_user_id, now) → EstimateSnapshot` | 422 `ESTIMATE_EMPTY`, 409 `ESTIMATE_LOCKED` (backstop) | `SEND_ESTIMATE` (T07) |
| `approve` | `(uow, *, shop_id, booking_id, estimate_id, decided_by_user_id, now) → EstimateSnapshot` | 409 `STALE_ESTIMATE` | `APPROVE_ESTIMATE` (T08) |
| `reject` | `(uow, *, shop_id, booking_id, estimate_id, decided_by_user_id, reason: str \| None, now) → EstimateSnapshot` | 409 `STALE_ESTIMATE` | `REJECT_ESTIMATE` (T09) |
| `copy_rejected_to_draft` | `(uow, *, shop_id, booking_id, created_by_user_id, now) → EstimateSnapshot` | 409 `ESTIMATE_LOCKED` (backstop) | `REVISE_ESTIMATE` (T10), `RETURN_TO_TECHNICIAN` (T11) |
| `supersede_open_versions` | `(uow, *, shop_id, booking_id, now) → list[UUID]` | — | `CANCEL` (T22) |
| `get_approved_part_requirements` | `(session, *, shop_id, booking_id) → list[PartQty]` (inventory's domain value `PartQty(part_id, qty)` from `inventory.domain.stock`, summed per part) | 500 if no `APPROVED` version (invariant) | `ASSIGN_PARTS_PERSON` (T12) → `inventory.create_booking_parts` |
| `list_versions` | `(session, *, shop_id, booking_id, include_stock: bool) → list[EstimateRead]` (ascending `version`) | — | `GET …/bookings/{booking_id}/estimates` |
| `get_estimate_summaries` | `(session, *, shop_id, booking_ids, audience: "staff" \| "customer") → dict[UUID, EstimateSummary]` | — | staff lists and details (one shop); details |
| `get_customer_estimate_summaries` | `(session, *, booking_keys: Collection[tuple[shop_id, booking_id]]) → dict[UUID, EstimateSummary]` — one query over every shop, customer audience only | — | the customer's booking list, which spans shops (no N+1 by shop, API-11) |
| `get_customer_view` | `(session, *, shop_id, booking_id) → CustomerEstimateView` (`estimate: CustomerEstimateRead \| None`, `revision_in_progress: bool`) | — | customer booking detail; P2 agent estimate view |
| `list_customer_versions` | `(session, *, shop_id, booking_id) → list[CustomerEstimateRead]` | — | P1 `GET /api/v1/me/bookings/{booking_id}/estimates` |

`EstimateSnapshot = {estimate_id, version, status, grand_total}` feeds the booking event metadata: `EstimateSnapshot.event_metadata()` → `{estimate_id, version, grand_total}` for `SUBMIT_ESTIMATE`, `SEND_ESTIMATE`, `APPROVE_ESTIMATE`, `REJECT_ESTIMATE` (spec 08); `EstimateSnapshot.event_ref()` → `{estimate_id, version}` for `START_INSPECTION`, `REVISE_ESTIMATE`, `RETURN_TO_TECHNICIAN`; `EstimateEdit.event_metadata()` → `{estimate_id, version, grand_total}` for an `EDIT_ESTIMATE` that created a version (`modules/bookings.md` §7.6). Spec 01's catalogue names every mutation above plus `get_current_estimate`; the reads `list_versions`, `get_estimate_summaries`, `get_customer_view` and `list_customer_versions` replace that single read (proposed below).

**Calls into other modules:** `inventory.get_parts_for_estimate(session, *, shop_id, part_ids, include_stock) → dict[UUID, PartStockRef]` (name, SKU, `unit_cost`, `is_active`, live `on_hand` / `reserved` / `available` / `reorder_level` / `stock_state`, stock fields null when `include_stock` is false); `identity.get_users_by_ids` for the `created_by`, `sent_by`, `decided_by` `UserRef`s.

## 6. Endpoints

None of its own. The routes that reach this module are served by `bookings` ([spec 03 §3.4, §4.8, §5.2, §5.3](../03-api-contracts.md)):

| operationId | Method + path | Who | Uses |
|---|---|---|---|
| `bookings_edit_estimate` | `PUT /api/v1/shops/{shop_id}/bookings/{booking_id}/estimate` | assigned T in `INSPECTING`; SA, O in `ESTIMATE_REVIEW` | `replace_lines` |
| `bookings_list_booking_estimates` | `GET …/bookings/{booking_id}/estimates` | member, D21 (QC without stock) | `list_versions` |
| `bookings_start_inspection`, `bookings_submit_estimate`, `bookings_send_estimate`, `bookings_my_approve_estimate`, `bookings_my_reject_estimate`, `bookings_revise_estimate`, `bookings_return_to_technician`, `bookings_assign_parts_person`, `bookings_cancel`, `bookings_my_cancel` | `POST …/actions/{slug}` | per spec 08 | the mutation of §5 for that row |
| `bookings_list_shop_bookings`, `bookings_get_shop_booking`, `bookings_list_my_bookings`, `bookings_get_my_booking` | lists and details | per D21 | `get_estimate_summaries`, `get_customer_view` |
| `bookings_list_my_booking_estimates` *(P1)* | `GET /api/v1/me/bookings/{booking_id}/estimates` | the booking's customer | `list_customer_versions` |

## 7. Domain rules and algorithms

### 7.1 Version lifecycle (D39)

| Version change | Triggered by | Notes |
|---|---|---|
| none → `DRAFT` v1 | `START_INSPECTION` (T05) → `ensure_draft` | Author = technician; totals 0 |
| `DRAFT` → `DRAFT` (lines replaced in place) | O1 by the technician in `INSPECTING`; O1 by SA/Owner in `ESTIMATE_REVIEW` when the latest is already a desk `DRAFT` | No booking event (D30) |
| `SUBMITTED` → `SUPERSEDED`, plus new `DRAFT` v+1 | First O1 by SA/Owner in `ESTIMATE_REVIEW` | Author = the editor; `created_new_version = true` → one `EDIT_ESTIMATE` event |
| `DRAFT` → `SUBMITTED` | `SUBMIT_ESTIMATE` (T06) | `submitted_at` |
| open (`SUBMITTED` or desk `DRAFT`) → `SENT` | `SEND_ESTIMATE` (T07) | `sent_at`, `sent_by_user_id` |
| `SENT` → `APPROVED` / `REJECTED` | `APPROVE_ESTIMATE` / `REJECT_ESTIMATE` (T08/T09, customer) | `decided_at`, `decided_by_user_id`; `customer_note` = reject reason |
| `REJECTED` stays; new `DRAFT` v+1 copies it | `REVISE_ESTIMATE` (T10) / `RETURN_TO_TECHNICIAN` (T11) | Author = the SA/Owner who acted; the technician then edits it in `INSPECTING` after T11 |
| `DRAFT` / `SUBMITTED` / `SENT` → `SUPERSEDED` | `CANCEL` (T22) | A superseded `SENT` version keeps its `sent_at` (allowed by `ck_estimates_sent_fields`) |
| `APPROVED`, `REJECTED`, `SUPERSEDED` | — | Final and immutable |

**Invariants** (DB-backed where noted, asserted by `assert_invariants`):

1. At most one open version (`DRAFT`, `SUBMITTED`, `SENT`) per booking — `uq_estimates_one_open_version_per_booking` (EST-16).
2. At most one `APPROVED` version per booking — `uq_estimates_one_approved_per_booking`.
3. Versions are `1, 2, 3, …` without gaps (`next = max(version) + 1` under the booking lock; `uq_estimates_booking_id_version`). "Revision n" in the UI is `version` (brief §7.5).
4. Cached totals equal the sums of the lines (DI-5); every money value is whole rupees (`ck_*_whole_rupees`).
5. No function changes the lines or status of a final version (EST-12).

**Booking status ↔ latest version** (a consistency table the scenario tests can assert):

| Booking status | Latest version |
|---|---|
| `PENDING`, `CONFIRMED`, `ASSIGNED` | none |
| `INSPECTING` | `DRAFT` |
| `ESTIMATE_REVIEW` | `SUBMITTED` or a desk `DRAFT` |
| `AWAITING_CUSTOMER` | `SENT` |
| `ESTIMATE_REJECTED` | `REJECTED` |
| `ESTIMATE_APPROVED` … `COMPLETED` | `APPROVED` |
| `CANCELLED` | none, `SUPERSEDED`, `APPROVED` or `REJECTED` |

### 7.2 Which version an edit touches (`domain.versions.edit_target`)

| Booking status (passed by bookings) | Latest version | Decision |
|---|---|---|
| `INSPECTING` | `DRAFT` | `IN_PLACE` |
| `ESTIMATE_REVIEW` | `SUBMITTED` | `NEW_VERSION` |
| `ESTIMATE_REVIEW` | `DRAFT` | `IN_PLACE` |
| any other combination | — | `LOCKED` → 409 `ESTIMATE_LOCKED` |

The role half of the rule (technician only in `INSPECTING`, SA/Owner only in `ESTIMATE_REVIEW`) is checked by bookings with spec 08's `EDIT_ESTIMATE` rule, which answers `INVALID_TRANSITION`; bookings maps that to 409 `ESTIMATE_LOCKED` for `PUT …/estimate` (EST-11, `modules/bookings.md` §7.6.1). This table is the backstop: whatever the caller, a final version is never edited.

### 7.3 Replacing the lines (`replace_lines`, O1)

```
latest = repo.latest(shop_id, booking_id)
decision = edit_target(booking_status, latest.status if latest else None)
if decision is LOCKED: raise EstimateLocked
parts = inventory.get_parts_for_estimate(shop_id, {l.part_id for PART lines}, include_stock=True)
priced, errors = price_lines(lines, parts)              # §7.4; every bad line reported at once
if errors: raise ValidationFailed(errors=errors)        # 422, fields lines.N.<field>
totals = estimate_totals(priced)                        # §7.5, incl. the MAX_AMOUNT guard
if decision is NEW_VERSION:
    latest.status = SUPERSEDED; latest.updated_at = now
    await session.flush()                               # supersede BEFORE insert (spec 02 §7.6)
    target = Estimate(id=uuid4(), shop_id, booking_id, version=latest.version + 1,
                      status=DRAFT, created_by_user_id=actor_user_id, created_at=now, updated_at=now)
else:
    target = latest
    DELETE FROM estimate_lines WHERE shop_id = :shop_id AND estimate_id = :target; flush   # before inserting
insert priced lines with position = index + 1, created_at = now
target.parts_total, target.labour_total, target.grand_total = totals; target.updated_at = now
return EstimateEdit(estimate=EstimateRead(target, lines with live PartStockRef), created_new_version=decision is NEW_VERSION)
```

- The request is the **full new list** in display order (1–50 lines); a repeated identical save is harmless (idempotent, spec 03 §1.7).
- The two statement-order rules are mandatory: PostgreSQL checks the partial unique index and `uq_estimate_lines_estimate_id_position` per statement and they cannot be deferred (spec 02 §7.6).
- Only lines of a `DRAFT` are ever deleted (the one hard delete in the schema, spec 02 §2).

### 7.4 Line rules (`EstimateLineWrite`, D40)

| Field | `PART` line | `LABOUR` line |
|---|---|---|
| `line_type` | `PART` | `LABOUR` |
| `part_id` | Required; an **active** part of this shop, else 422 `lines.N.part_id` `invalid_reference` (other shop, inactive, unknown — EST-07) | Not allowed (`not_allowed`) |
| `description` | Not allowed (`not_allowed`): the server stores `parts.name` at save time, so an approved estimate never changes when the catalogue is edited | Required, 1–255, trimmed, not blank |
| `quantity` | Whole number 1–9 999 (string or number, at most 2 decimals, integer-valued) | 0.01–999.99, at most 2 decimals (hours, or 1 for a flat fee) |
| `unit_price` | Optional `Money` (whole rupees ≥ 0); default `parts.unit_cost` (EST-09) | Required `Money` |
| Client totals | Not accepted: `line_total`, `parts_total`, `grand_total` → `extra_forbidden` (SEC-17) | same |

- One model with a `model_validator` that raises `PydanticCustomError` with the spec 03 §2.3 codes (`missing`, `not_allowed`, `not_whole_rupees`, `value_error`), so the 422 carries the documented codes rather than generic `extra_forbidden` for type-specific fields.
- The same part may appear on several lines; T12 sums them per part.
- An out-of-stock part can be added: the technician sees "Not in stock — the parts person will order it" (spec 06 T3); stock is never reserved here.
- `EstimateUpdate` = `lines` (1–50) · `inspection_notes`? ≤ 4000 (consumed by bookings: technician only) · `expected_version`? (checked by bookings).

### 7.5 Money and totals (D41)

```python
RUPEE, CENTS = Decimal("1"), Decimal("0.01")

def line_total(quantity: Decimal, unit_price: Decimal) -> Decimal:
    return (quantity * unit_price).quantize(RUPEE, rounding=ROUND_HALF_UP).quantize(CENTS)

def estimate_totals(lines) -> Totals:        # parts_total, labour_total, grand_total
    parts = sum(l.line_total for l in lines if l.line_type is PART)
    labour = sum(l.line_total for l in lines if l.line_type is LABOUR)
    return Totals(parts, labour, parts + labour)
```

- Half-up for non-negative values equals PostgreSQL's `round(numeric)` (ties away from zero), so `ck_estimate_lines_line_total` always holds; Python's default half-even must never be used (EST-20: `1.50 × 999 = 1,498.50 → "1499.00"`, half-even would give 1,498).
- The domain re-implements the one-line rounding with the standard library (the pure-domain contract forbids importing `app.shared.money`); a unit test asserts it equals `app.shared.money.round_rupees`.
- **Overflow guard:** any line total or the grand total above `MAX_AMOUNT` (9 999 999 999.00, the `numeric(12,2)` limit) → 422 `VALIDATION_ERROR` on `lines.N.quantity` (or `lines`), code `value_error`, "The amount is too large." — never a database 500.
- Worked example (spec 08, EST-05):

| Version | Lines | Parts total | Labour total | Grand total |
|---|---|---|---|---|
| v1 (Imran, `SUBMITTED` → `SUPERSEDED`) | coil 1 × 6,500; filter 1 × 900; oil 4 L 1 × 5,200; labour 1 × 4,000 | 12,600.00 | 4,000.00 | **16,600.00** |
| v2 (Bilal, `DRAFT` → `SENT` → `APPROVED`) | same parts; labour 1 × 3,500 | 12,600.00 | 3,500.00 | **16,100.00** |

### 7.6 Submit, send, decide, copy, supersede

- **`submit`** (T06): the latest version must be a `DRAFT` (backstop 409 `ESTIMATE_LOCKED`); ≥ 1 line, else 422 `ESTIMATE_EMPTY` (field `lines`, EST-10); every `PART` line's part must still be active in the shop, else 422 `lines.N.part_id` `invalid_reference` (spec 03 §5.2); recompute totals defensively; `status = SUBMITTED`, `submitted_at = now`.
- **`send`** (T07): the open version (`SUBMITTED`, or the desk's `DRAFT`) must have ≥ 1 line, else 422 `ESTIMATE_EMPTY`; `status = SENT`, `sent_at = now`, `sent_by_user_id`. Older versions were already superseded by O1, so the one-open-version index never blocks (spec 02 §3.11, EST-04).
- **`approve` / `reject`** (T08/T09): `current = the version with status SENT for this booking` (unique). `current` is `None` or `current.id ≠ estimate_id` → 409 `STALE_ESTIMATE` (superseded, another booking's or unknown id — EST-14, SM-14). Otherwise `status = APPROVED` / `REJECTED`, `decided_at = now`, `decided_by_user_id` = the customer; `reject` stores `customer_note = reason` (≤ 500, may be null). The approved version is the timestamped in-app acceptance of brief §3 and is locked from then on (EST-13).
- **`copy_rejected_to_draft`** (T10/T11): the latest version must be `REJECTED` (backstop 409); insert `DRAFT` `version + 1`, `created_by_user_id` = the acting SA/Owner, copying every line verbatim (position, type, part, stored description, quantity, unit price, line total) and the totals. The rejected version is unchanged (EST-15). The next save re-validates the copied lines (a part deactivated meanwhile → 422) and refreshes `PART` descriptions from the catalogue.
- **`supersede_open_versions`** (T22): `UPDATE estimates SET status = 'SUPERSEDED', updated_at = :now WHERE shop_id = :shop_id AND booking_id = :booking_id AND status IN ('DRAFT', 'SUBMITTED', 'SENT') RETURNING id`; `APPROVED` and `REJECTED` stay (EST-17).
- **`get_approved_part_requirements`** (T12): `SELECT part_id, SUM(quantity)::int FROM estimate_lines WHERE shop_id = :shop_id AND estimate_id = :approved_id AND line_type = 'PART' GROUP BY part_id ORDER BY part_id`; a labour-only estimate returns `[]` (D31). No `APPROVED` version → 500 (T12 runs only from `ESTIMATE_APPROVED`).

### 7.7 Customer-visible versions (D39)

- Visible statuses: `SENT`, `APPROVED`, `REJECTED` only. A technician's or SA's `DRAFT` / `SUBMITTED`, and any `SUPERSEDED` version — including a sent version superseded by a cancellation — are never shown to the customer (SEC-12, spec 06 C4).
- `get_customer_view`: `estimate` = the visible version with the highest `version` (or `None`); `revision_in_progress = estimate is not None and an open DRAFT or SUBMITTED version newer than it exists` — true after a rejection while the shop prepares the next revision, false before the first estimate is sent (the status label "Preparing your estimate" covers that) and false after a cancellation (all open versions are superseded).
- `CustomerEstimateRead`: `id`, `version`, `status`, `lines` (`CustomerEstimateLineRead`: `id`, `position`, `line_type`, `description`, `quantity`, `unit_price`, `line_total` — no SKU, no stock), `parts_total`, `labour_total`, `grand_total`, `sent_at`, `decided_at`, `customer_note`.
- Customer summaries (`audience="customer"`) describe the latest visible version (`estimate_id`, `version`, `status`, `grand_total`, `line_count`).

### 7.8 Staff views

- `list_versions`: every version ascending, each `EstimateRead` (`id`, `booking_id`, `version`, `status`, `lines`, `parts_total`, `labour_total`, `grand_total`, `created_by`, `created_at`, `submitted_at`, `sent_at`, `sent_by`, `decided_at`, `decided_by`, `customer_note`). `PART` lines carry `part` = `PartStockRef` with **live** stock (D40, EST-18; read at request time, never stored); for a QC caller (`include_stock = false`) the stock fields are `null` (spec 03 §3.4). `LABOUR` lines have `part = null`.
- Staff summaries (`audience="staff"`) describe the latest version.
- Every read is a fixed number of queries whatever the number of versions or bookings: versions, lines (`ORDER BY estimate_id, position`), part refs, users.

## 8. Events

None published, none subscribed. Booking events about estimates (`START_INSPECTION`, `EDIT_ESTIMATE` with a new version, `SUBMIT_ESTIMATE`, `SEND_ESTIMATE`, `APPROVE_ESTIMATE`, `REJECT_ESTIMATE`, `REVISE_ESTIMATE`, `RETURN_TO_TECHNICIAN`) are written by `bookings`, with metadata built from `EstimateSnapshot`; the notifications they cause (`ESTIMATE_SUBMITTED`, `ESTIMATE_SENT`, `ESTIMATE_APPROVED`, `ESTIMATE_REJECTED`, `ESTIMATE_RETURNED`) flow from `BookingActionApplied`.

## 9. Permissions and visibility

- **Who may change an estimate** is decided before this module runs: spec 08's rules (assigned technician edits and submits in `INSPECTING`; SA/Owner edit, send, revise and return; only the booking's customer approves or rejects) and D21 visibility, both applied by `bookings`. Estimates adds the version-state backstop of §7.2 and the stale-version check of §7.6.
- **Who may see what:** customers only `SENT` / `APPROVED` / `REJECTED` versions without SKU or stock (§7.7); staff who can see the booking see every version (spec 04 §C); QC inspectors see versions without stock fields (spec 04 §B).
- Every query is scoped by `shop_id`; composite FKs make an estimate of Shop A for a booking of Shop B, or a line pointing at Shop B's part, impossible in the database (SEC-45).

## 10. Errors

| Code | HTTP | When |
|---|---|---|
| `ESTIMATE_LOCKED` | 409 | `replace_lines` when §7.2 says `LOCKED`; backstops in `submit`, `send`, `copy_rejected_to_draft` (unreachable through the state machine) |
| `STALE_ESTIMATE` | 409 | `approve` / `reject` with an id that is not the current `SENT` version of this booking |
| `ESTIMATE_EMPTY` | 422 | `submit` / `send` with no lines (field `lines`) |
| `VALIDATION_ERROR` | 422 | Line errors (`lines.N.part_id` `invalid_reference`; `not_allowed`; `missing`; `not_whole_rupees`; quantity range; amount too large); `submit` with a part deactivated since it was added |
| `CONCURRENT_UPDATE` | 409 | Backstop mapping of `uq_estimates_*` violations (spec 03 §2.4) — cannot happen while the booking lock is held |
| `INTERNAL_ERROR` | 500 | Invariant breaches (`get_approved_part_requirements` without an approved version; `ensure_draft` finding a non-draft latest version) |

## 11. Concurrency & transactions

- Every write runs inside a bookings action that already holds the **booking row lock** (spec 02 §7.2: T05–T12, O1, T22 lock the booking only), so estimate writes for one booking are serialised and this module takes no further locks. Different bookings never touch the same estimate rows.
- Statement order inside one transaction: supersede, flush, then insert the new version; delete a draft's lines, flush, then insert the new lines (§7.3, spec 02 §7.6).
- Database backstops: `uq_estimates_one_open_version_per_booking`, `uq_estimates_one_approved_per_booking`, `uq_estimates_booking_id_version` (→ 409 `CONCURRENT_UPDATE`), the totals and whole-rupee CHECKs, `ck_estimate_lines_line_total`.
- Live stock on part lines is read without locks; it is display data only (reservations happen at T13/T14 under part locks).
- Timestamps: the single `now` the caller read after locking the booking (D63), so `sent_at < decided_at` follows the action order (stepping clock in scenario tests).

## 12. Tests

Spec 12 IDs this module must make pass: **EST-01**…**EST-20** (EST-05 ★; EST-12 and EST-20 have integration halves here; EST-19 P1), **SM-08 ★**, **SM-09**, **SM-14**, **SM-18 ★** (estimate steps v1 16,600 → v2 16,100, v1 `SUPERSEDED`), **SEC-12** (customers never see `DRAFT` / `SUBMITTED`), **SEC-17** (`grand_total` on `PUT …/estimate` → 422), **SEC-35**, **SEC-45** (`estimates` row for another shop's booking → SQLSTATE 23503), and the estimates part of `assert_invariants` (EST-16, DI-5).

Proposed additional tests:

| ID (proposed) | Layer | Test |
|---|---|---|
| EST-21 | A | Overflow guard: 9 999 × 9 999 999 999 → 422 `VALIDATION_ERROR`, never a 500; nothing written |
| EST-22 | A | `estimate_revision_in_progress` truth table: nothing sent yet → false; after rejection + revise → true; after send → false; after cancellation → false |
| EST-23 | A | `PART` description comes from the catalogue at save time; renaming the part later leaves `SENT` / `APPROVED` versions unchanged, and the next draft save shows the new name |
| EST-24 | A | One 422 lists every invalid line (`lines.0.part_id`, `lines.3.quantity`, …), not just the first |
| EST-25 | U + I | `line_total` equals PostgreSQL `round(quantity * unit_price)` and `app.shared.money.round_rupees` for a sample including every `.5` tie |
| EST-26 | S | The booking-status ↔ latest-version table of §7.1 holds after every scenario step (added to `assert_invariants`) |
| EST-27 | A | A `SENT` version superseded by a cancellation is absent from the customer detail, the customer estimates list (P1) and the agent view (P2) |

## 13. Implementation checklist

1. `domain/totals.py` and `domain/versions.py` with unit tests (EST-05, EST-20, EST-25, §7.2 table).
2. Schemas: `EstimateLineWrite` (single model + validator with custom error codes), `EstimateUpdate` (`extra="forbid"`), the read models, the internal types. `unit_price` uses the shared `Money` type, which already reports `not_whole_rupees` and rejects JSON floats (spec 03 §1.5); `quantity` uses a module `Quantity` type (`Decimal`, at most 2 places, string or number in, serialised with `app.shared.money.format_decimal(value, 2)` → `"1.50"`); timestamps use `app.shared.timestamps.Timestamp`.
3. Repositories (all methods keyed by `shop_id`; bulk delete of lines; `RETURNING` on the bulk supersede). `uq_estimates_*` violations already map to 409 `CONCURRENT_UPDATE` through `app.core.db_errors`.
4. Service mutations in lifecycle order — `ensure_draft` → `replace_lines` → `submit` → `send` → `approve` / `reject` → `copy_rejected_to_draft` → `supersede_open_versions` → `get_approved_part_requirements` — then the reads.
5. Wire into bookings (PH4): T05–T12, `edit_estimate`, `GET …/estimates`, the summaries in booking lists and details; T22 supersede.
6. Tests of §12 through the API with `drive_booking_to` (spec 12 §4.3).

## 14. Dependencies (specs)

[08-booking-state-machine.md](../08-booking-state-machine.md) (T05–T12, T22, O1, "Estimate versions"), [17-decisions.md](../17-decisions.md) (D16, D20, D21, D23, D24, D30, D39–D41, D50, D63, D86), [18-glossary.md](../18-glossary.md) (§1 Estimate, Estimate line, Revision; §5 `EstimateStatus`, `EstimateLineType`; §9 money and quantities; §10), [02-data-model.md](../02-data-model.md) §2.3, §3.11, §3.12, §6, §7.6, [03-api-contracts.md](../03-api-contracts.md) §1.5, §2.3, §3.4, §4.8, §5.2, §5.3, [04-auth-and-security.md](../04-auth-and-security.md) (RBAC C, threat 20), [06-workflows.md](../06-workflows.md) (C5, C6, S3, S4, T3, T4, E1), [12-quality-and-testing.md](../12-quality-and-testing.md) (EST group). Uses `modules/inventory.md` (`get_parts_for_estimate`) and identity look-ups; used by `modules/bookings.md`.

## Open questions

1. ✅ **Resolved in spec 12 (EST-11): where `ESTIMATE_LOCKED` is mapped.** The bookings edit-estimate use case maps the domain's `INVALID_TRANSITION` to 409 `ESTIMATE_LOCKED`; this module may not import `bookings.domain.state_machine` and raises `ESTIMATE_LOCKED` itself from §7.2 only as the backstop. The observable behaviour is identical.
2. **Send re-validation.** Spec 08 T07 checks only emptiness, so a part deactivated between the SA's save and the send still goes out at its saved price and name. Keep (the saved line is what the SA reviewed), or re-check active parts on send like T06 does?
3. ✅ **Resolved in spec 11: seed call.** Spec 11 now saves estimate lines through `bookings.service.edit_estimate` (it locks the booking and may write the `EDIT_ESTIMATE` event), which calls `replace_lines`; the seed never calls this module directly.

## Proposed glossary additions

| Kind | Name | Meaning |
|---|---|---|
| Domain files and constants | `estimates/domain/totals.py`, `versions.py`; `OPEN_STATUSES`, `CUSTOMER_VISIBLE_STATUSES`, `FINAL_STATUSES`, `MAX_AMOUNT`, `EditDecision` | Pure version and money rules |
| Internal types | `EstimateSnapshot` (`estimate_id`, `version`, `status`, `grand_total`), `EstimateEdit` (`estimate`, `created_new_version`), `CustomerEstimateView` (`estimate`, `revision_in_progress`); requirements reuse inventory's `PartQty` | Return types of §5 |
| Service functions | `estimates.service`: `list_versions`, `get_estimate_summaries`, `get_customer_view`, `list_customer_versions` (replacing spec 01's `get_current_estimate`) | Reads for bookings |
| Function required from inventory | `get_parts_for_estimate(..., include_stock)` returning `PartStockRef` | Live stock and catalogue data for part lines (D40); QC callers get no stock |
