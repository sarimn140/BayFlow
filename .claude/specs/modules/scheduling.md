# Module: scheduling

**Status:** Draft
**Package:** `app.modules.scheduling`
**Owns tables:** `slot_counters`

## 1. Purpose

Turn a shop's working hours, slot duration and capacity into bookable time slots, and make sure no slot is ever booked beyond its capacity. Slots are **computed, never stored** (D37): the grid is anchored at local midnight in the shop's timezone and steps by `slot_duration_minutes`; working hours select which grid slots are open; capacity is `shops.slot_capacity`. The only stored slot data is `slot_counters (shop_id, slot_start, booked_count)`, which booking creation increments under a row lock and cancellation/decline decrements.

Brief sections satisfied:

- §5.1 "See that shop's available time slots and pick one".
- §7.3 "Slot picker shows only available slots for the chosen date, per shop".
- §5.3 "Slot conflicts: two customers must not be able to book the same slot beyond its capacity (use a transaction or unique constraint)".
- FAQ "Does the slot system need to be complex? No. Per-shop working hours with fixed duration slots and a capacity is enough. Booked slots must not be double-booked."
- §7.7 "available slots" in the seed (computed from seeded hours; no slot rows to seed).

## 2. Scope

| Priority | In scope |
|---|---|
| **P0** | `GET /api/v1/public/shops/{shop_slug}/availability?date=` (D68). Pure slot-grid maths in the shop's timezone (D37, D38). Slot validation for booking creation (422 `INVALID_SLOT`). `reserve_slot` (insert-if-missing, `SELECT … FOR UPDATE`, capacity check, increment; 409 `SLOT_FULL`) and `release_slot` (decrement) for `bookings`. |
| **P1** | Nothing extra (the CON-03 and CON-05 concurrency tests are P1 in spec 12). |
| **P2** | `list_open_slots` (up to 12 open slots over 1–7 days) and `is_slot_open` for the AI Front Desk's `available-slots` route and reschedule requests (spec 05); they never hold or book a slot. |
| **Out of scope** | Stored slot rows; per-service slot lengths (`services.estimated_duration_minutes` is informational); bays or technician capacity; holidays and per-date exceptions; overnight hours; buffers between slots; holding a slot during the wizard; rescheduling (spec 08 has no such action); repairing counters (DI-4 is asserted by tests, never "fixed" by a job). |

## 3. Key decisions

| D | What it means here |
|---|---|
| D20 | `slot_counters` is shop-owned: every repository method takes `shop_id`; the row's FK proves the shop exists. |
| D24 | `DECLINE` and `CANCEL` free the place: `release_slot` decrements the counter in the same transaction. |
| D30 | The slot counter is the **last** lock of any transaction (booking → purchase order → parts → slot counter). |
| D37 | Grid anchored at local midnight, step `slot_duration_minutes`; working hours (on the grid) select open slots; a slot must end by closing time; capacity per slot = `slot_capacity`; only slots starting after now and within 30 days are offered; booking does `INSERT … ON CONFLICT DO NOTHING` then `SELECT … FOR UPDATE`, checks `booked_count < capacity`, increments. Booking creation reads the shop row `FOR SHARE` (through `shops.get_schedule_config(for_share=True)`) so a grid change and a booking never interleave. |
| D38 | Times are stored in UTC; availability and validation are computed in the shop's IANA timezone with `zoneinfo` (default `Asia/Karachi`, UTC+5, no DST). |
| D51 | The seed books through the normal path; it never writes `slot_counters` directly. |
| D63 | "Now" is `utcnow()` from the injected clock (frozen in tests, scripted in the seed). |
| D64, D68 | Public routes use the slug; free places in a slot are called `remaining` (never "available"). Availability answers for any **listed** shop (spec 03 §4.5); bookability (≥ 1 active service) is checked by booking creation. |
| D71 | A full slot (e.g. the worked example's Friday 10:00, capacity 2) is accepted shared-data drift; testers pick another slot. |
| D86 | Scheduling sits below bookings and never imports it (bookings calls `validate_slot`, `reserve_slot`, `release_slot`). A future upward read would use a read port that bookings registers from its `register_ports()` at start-up (D89), like shops' `ShopActivityReader` (`shops.service.register_activity_reader`) and inventory's `BookingRefReader` (`inventory.service.register_booking_ref_reader`); it needs none today. |

## 4. Files

| File | Contents |
|---|---|
| `models.py` | `SlotCounter` (exists; spec 02 §3.6): PK `(shop_id, slot_start)`, `booked_count ≥ 0` (`ck_slot_counters_booked_count_non_negative`), `created_at`, `updated_at`. |
| `domain/slots.py` | Pure grid maths: `BOOKING_HORIZON_DAYS = 30`, `GridSlot`, `SlotProblem`, `day_slots()`, `is_offered()`, `slot_problem()`. Imports `shops.domain.grid` (`ScheduleConfig`, `WorkingDay`, `minutes_of`) and the standard library only. |
| `repository.py` | `SlotCounterRepository(ShopScopedRepository)`: `counts_between(*, shop_id, first, last)`, `insert_if_missing(*, shop_id, slot_start, now)`, `lock(*, shop_id, slot_start)`, `increment(*, shop_id, slot_start, now)`, `decrement(*, shop_id, slot_start, now)`. |
| `schemas.py` | `SlotRead` (`slot_start`, `slot_end` as `app.shared.timestamps.Timestamp`, `remaining`), `AvailabilityRead` (`shop_id`, `date`, `timezone`, `slot_duration_minutes`, `slots`). |
| `service.py` | `list_availability`, `validate_slot`, `reserve_slot`, `release_slot`; P2 `list_open_slots`, `is_slot_open`. |
| `router.py` | `APIRouter(prefix="/api/v1/public/shops", tags=["scheduling"])`: `GET /{shop_slug}/availability` → function `get_availability`. |

No `events.py` or `handlers.py`.

## 5. Public service interface

| Function | Arguments → returns | Tx | Errors | Called by |
|---|---|---|---|---|
| `list_availability` | `(session, *, shop_slug: str, day: date) → AvailabilityRead` | read | 404 `NOT_FOUND` (unknown or unlisted slug) | scheduling router |
| `validate_slot` | `(config: ScheduleConfig, *, slot_start: datetime, now: datetime) → GridSlot` | none (pure wrapper) | 422 `INVALID_SLOT` (field `slot_start`) | `bookings.create_booking` (early check, before the account rule) |
| `reserve_slot` | `(uow, *, config: ScheduleConfig, slot_start: datetime, now: datetime) → GridSlot` | nested; **`config` must have been read under the shop's `FOR SHARE` lock in this transaction** | 422 `INVALID_SLOT`, 409 `SLOT_FULL` | `bookings.create_booking` (T01) |
| `release_slot` | `(uow, *, shop_id: UUID, slot_start: datetime, now: datetime) → None` | nested; called while the booking row is locked | 500 if the counter row is missing (DI-4 broken) | bookings `DECLINE` (T03), `CANCEL` (T22) |
| `list_open_slots` *(P2)* | `(session, *, shop_id, date_from: date, days: int, limit: int = 12) → list[SlotRead]` | read | — | calls (agent `available-slots`) |
| `is_slot_open` *(P2)* | `(session, *, shop_id, slot_start: datetime) → bool` | read | — | calls (reschedule request: "each start must still be available") |

`GridSlot(slot_start, slot_end)` is the domain value object (aware UTC datetimes; `slot_end = slot_start + slot_duration_minutes`). Spec 01 lists `list_availability`, `reserve_slot`, `release_slot`; `validate_slot` and the P2 helpers are proposed below. Schedule settings (`ScheduleConfig`) come from `shops.service.get_schedule_config`.

## 6. Endpoints

Contract: [spec 03 §3.2 (`SlotRead`, `AvailabilityRead`) and §4.5](../03-api-contracts.md).

| operationId | Method + path | Auth · roles | Success | Pri | Screens |
|---|---|---|---|---|---|
| `scheduling_get_availability` | `GET /api/v1/public/shops/{shop_slug}/availability?date=YYYY-MM-DD` | public (no credentials read) | 200 `AvailabilityRead` | P0 | P-03 W3 · E-09 |

- `date` is required and is a date in the **shop's** timezone; malformed → 422 `VALIDATION_ERROR` (`query.date`).
- Unknown slug, a UUID in the slug position, or `is_listed = false` → 404 (BK-27).
- Past dates, dates beyond the horizon and closed days → 200 with `slots: []`. Full slots are omitted (brief §7.3 "only available slots", BK-11).
- The wizard polls it every 15 s on the time step (D14, spec 03 §6.6); every response carries `Cache-Control: no-store` (D61).

## 7. Domain rules and algorithms

### 7.1 The grid of one day (`day_slots(config, day)`)

```
wd = config.days[day.weekday()]                        # 0 = Monday (glossary §5)
if wd.is_closed: return []
step = config.slot_duration_minutes
tz = ZoneInfo(config.timezone)
m = minutes_of(wd.opens_at)                            # on the grid (shops validates it, D37)
while m + step <= minutes_of(wd.closes_at):            # a slot must END by closing time
    local = datetime.combine(day, time(m // 60, m % 60), tzinfo=tz)      # fold = 0
    if local exists in tz:                             # skip a DST gap (round-trip check)
        start = local.astimezone(UTC)
        yield GridSlot(start, start + timedelta(minutes=step))
    m += step
```

- Grid times are wall-clock minutes since **local midnight**: `00:00 + k × step`. With 60-minute slots and hours 09:00–18:00, Lahore Auto Care offers 09:00 … 17:00 (9 slots); Friday 16 Oct 2026, 10:00 PKT is `2026-10-16T05:00:00Z` (BK-12).
- `slot_end` is the start plus the duration in absolute minutes, the same value `bookings.slot_end` stores (spec 02 §3.8).
- DST (not used by `Asia/Karachi`, but any IANA zone is accepted): a wall time that does not exist (spring-forward gap) is skipped; an ambiguous wall time (fall-back) uses its first occurrence (`fold = 0`). "Exists" is checked by converting to UTC and back and comparing the wall time.

### 7.2 Offered slots (`is_offered(slot, config, now)`)

A grid slot is offered when **all** hold:

1. `slot.slot_start > now` (strictly; a slot starting exactly now is not offered).
2. Horizon: its local date ≤ `today_local + BOOKING_HORIZON_DAYS` (30), where `today_local = now.astimezone(tz).date()`. The horizon is counted in whole local days, so it matches the wizard calendar, which enables "today … today + 30" in shop time (spec 10 P-03 W3).
3. `remaining = slot_capacity − booked_count > 0` (availability only; booked counts from `slot_counters`, 0 when no row exists).

A capacity lowered below the places already booked makes `remaining ≤ 0`: the slot is simply not offered (never a negative number on the wire).

### 7.3 Availability (`list_availability`)

1. `shop = shops.get_listed_shop(shop_slug)` → `None` → 404.
2. `config = shops.get_schedule_config(shop_id)` (unlocked read); `now = utcnow()`.
3. `candidates = [s for s in day_slots(config, day) if s.slot_start > now and within horizon]`; empty → `slots: []`.
4. One range scan on the primary key: `SELECT slot_start, booked_count FROM slot_counters WHERE shop_id = :shop_id AND slot_start BETWEEN :first AND :last`.
5. `slots = [SlotRead(s.slot_start, s.slot_end, capacity − count) for s in candidates if capacity − count > 0]`, ordered by `slot_start`.
6. Return `AvailabilityRead(shop_id, date, timezone, slot_duration_minutes, slots)`; timestamps serialise as UTC `Z` (glossary §9).

Cost per call: one shop look-up, 7 working-hours rows and one index range scan, which keeps the 15-second polling cheap.

### 7.4 Slot validation (`slot_problem` / `validate_slot`) for booking creation

The requested `slot_start` (an aware timestamp; naive values are rejected by the schema, spec 03 §1.5) is converted to the shop's local time; the **first** failing rule decides the field error. All of them are 422 `INVALID_SLOT` with one error on `slot_start` (spec 03 §2.3):

| Order | Rule | Field-error `code` | Message |
|---|---|---|---|
| 1 | Local wall time is `00:00 + k × step` (minutes since local midnight divisible by the step) with zero seconds and microseconds | `off_grid` | "This time is not one of the shop's slot start times." |
| 2 | `slot_start > now` | `in_past` | "This time slot has already started." |
| 3 | Local date ≤ `today_local + 30` | `beyond_horizon` | "Bookings open at most 30 days ahead." |
| 4 | The weekday is open | `closed_day` | "The shop is closed on this day." |
| 5 | `opens_at ≤ start` and `start + step ≤ closes_at` (wall-clock minutes) | `outside_hours` | "This time is outside the shop's working hours." |
| 6 | Consistency: the instant equals one element of `day_slots(config, local date)` (only fails in a DST gap or on the second occurrence of an ambiguous wall time) | `off_grid` | as rule 1 |

The reason codes are glossary §10's (`off_grid`, `in_past`, `beyond_horizon`, `closed_day`, `outside_hours`; spec 03 §2.3). `not_on_grid` is a different code: it belongs to working-hours validation in shops (`working_hours.N.opens_at`), never to `INVALID_SLOT`.

Returns `GridSlot(slot_start, slot_start + step)`. BK-08 covers rules 1–5 with a frozen clock; SCH-01 covers rule 6.

### 7.5 Reserving a place (`reserve_slot`, D37, spec 02 §7.4)

```
slot = validate_slot(config, slot_start, now)            # again, against the config read under FOR SHARE
INSERT INTO slot_counters (shop_id, slot_start, booked_count, created_at, updated_at)
VALUES (:shop_id, :slot_start, 0, :now, :now) ON CONFLICT (shop_id, slot_start) DO NOTHING;
SELECT booked_count FROM slot_counters
 WHERE shop_id = :shop_id AND slot_start = :slot_start FOR UPDATE;
if booked_count >= config.slot_capacity: raise SlotFull            # 409, whole transaction rolls back
UPDATE slot_counters SET booked_count = booked_count + 1, updated_at = :now
 WHERE shop_id = :shop_id AND slot_start = :slot_start;
return slot
```

- Two transactions creating the same new counter: `ON CONFLICT DO NOTHING` lets exactly one row exist; the `FOR UPDATE` then serialises them, and the second one sees the first one's increment after it commits (verified in spec 02 §7.4 on PostgreSQL 16).
- The capacity comes from the `ScheduleConfig` read under the shop row's `FOR SHARE` lock, so it cannot change before this transaction commits.
- `:now` is the action's clock instant (D63), never `now()` in SQL.
- Re-validating here is what makes CON-05 safe: if a grid change committed between the early check and the shop lock, the booking fails with `INVALID_SLOT` instead of landing on a grid that no longer exists.

### 7.6 Freeing a place (`release_slot`)

`UPDATE slot_counters SET booked_count = booked_count − 1, updated_at = :now WHERE shop_id = :shop_id AND slot_start = :slot_start RETURNING booked_count`. Exactly one row must be updated: every non-cancelled booking incremented its counter in the same transaction that created it (DI-4), so a missing row is a bug and raises (500), and the CHECK stops the count going below 0. Counter rows are never deleted; a fully freed slot keeps a row with `booked_count = 0`, which is offered again.

### 7.7 P2 helpers (spec 05)

- `list_open_slots(shop_id, date_from, days 1–7, limit 12)`: the §7.3 algorithm over consecutive local dates, one counter range scan for the whole window, first `limit` offered slots in time order.
- `is_slot_open(shop_id, slot_start)`: `validate_slot` passes and `remaining > 0` right now. No lock and no hold: a reschedule request records preferred times only.

## 8. Events

None published, none subscribed. Grid changes are guarded by `shops` (`ShopGridChanging`, vetoed by `bookings`); this module only computes from the current settings.

## 9. Permissions and visibility

| Surface | Who |
|---|---|
| `GET …/availability` | Anyone; no credentials are read. Only listed shops are answered; the response exposes slot times and free places, never who booked them. |
| `validate_slot`, `reserve_slot`, `release_slot` | Internal, only inside `bookings` action transactions (T01, T03, T22). There is no endpoint that changes a counter directly. |
| P2 helpers | Internal, only from the `calls` module, scoped to the call's shop (D58). |

## 10. Errors

| Code | HTTP | When |
|---|---|---|
| `NOT_FOUND` | 404 | Availability for an unknown or unlisted slug |
| `VALIDATION_ERROR` | 422 | Malformed `date` query parameter |
| `INVALID_SLOT` | 422 | `validate_slot` / `reserve_slot`: off the grid, not after now, beyond 30 days, closed day, outside hours or ending after closing (field `slot_start`, §7.4 codes) |
| `SLOT_FULL` | 409 | `reserve_slot` when `booked_count ≥ slot_capacity` |
| `INTERNAL_ERROR` | 500 | `release_slot` found no counter row, or the decrement violated `ck_slot_counters_booked_count_non_negative` (both mean DI-4 was broken) |

## 11. Concurrency & transactions

- **Lock order (D30, D37).** Booking creation: shop row `FOR SHARE` (taken by `shops.get_schedule_config(for_share=True)`) → vehicle upsert → **slot counter `FOR UPDATE`** → booking insert. Decline: booking `FOR UPDATE` → slot counter. Cancel: booking → reserved parts (ascending `id`) → slot counter. The counter is always last, so no cycle is possible.
- **Last place race (SM-07 ★).** Two customers for the last place of a slot: both block on the counter row; the first increments and commits; the second re-reads `booked_count = capacity` and gets 409 `SLOT_FULL`; its whole transaction (including a case-B account) rolls back. Also proven with an ungated burst of 6 requests on a counter row that does not exist yet (spec 12 §3.5).
- **Two cancellations in one slot (CON-03, P1):** each holds its own booking lock, then they queue on the counter row; `booked_count` drops by exactly 2.
- **Grid change vs booking (CON-05, P1):** serialised on the shop row (`FOR UPDATE` vs `FOR SHARE`); see `modules/shops.md` §11.
- Availability reads take no locks; a slot shown with `remaining = 1` may be gone by the time the customer confirms, which is exactly the 409 `SLOT_FULL` path the wizard handles (spec 10 P-03 W5).

## 12. Tests

Spec 12 IDs this module must make pass: **SM-07 ★** (lock gate + ungated burst), **BK-08** (each `INVALID_SLOT` case, frozen clock), **BK-09** (capacity 2 → third booking 409), **BK-10** (cancel/decline free the place; never below 0), **BK-11** (only on-grid, future, ≤ 30-day slots with `remaining > 0`), **BK-12** (timezone and `Z` serialisation), **BK-27** (slug addressing, `remaining`, no `available` key), **BK-30** (midnight-anchored grid; U + A), **SEED-03** (bookable slots in the next 7 days for every seeded shop), **SEED-17**, **CON-03** *(P1)*, **CON-05** *(P1)*, the slot invariant of `assert_invariants` (DI-4), **DEP-08** (Friday slots open), **FD-06** *(P2)*.

Proposed additional tests:

| ID (proposed) | Layer | Test |
|---|---|---|
| SCH-01 | U | DST zone (`Europe/London`, spring-forward date, hours 00:00–04:00, 60-minute slots): the non-existent 01:00 local slot is skipped; every `slot_end = slot_start + duration` |
| SCH-02 | U + A | Horizon boundary: the last slot of `today + 30` (local) is offered and bookable; any slot on `today + 31` → `slots: []` and 422 `INVALID_SLOT` `beyond_horizon` |
| SCH-03 | U | A slot starting exactly at `now` is neither offered nor bookable (`in_past`) |
| SCH-04 | A | Capacity lowered below `booked_count` → slot omitted (no negative `remaining`); raising it again reopens the slot |
| SCH-05 | A | Availability of a listed shop with no active service returns its slots (spec 03 §4.5); an unlisted shop → 404 |
| SCH-06 | I | `release_slot` on a missing counter raises (500); a double release cannot drive the count below 0 |
| SCH-07 | U | Reason precedence of §7.4 (e.g. an off-grid time in the past → `off_grid`; a past on-grid time on a closed day → `in_past`; an on-grid time after closing → `outside_hours`) |

## 13. Implementation checklist

1. `domain/slots.py`: `GridSlot`, `SlotProblem` (`off_grid`, `in_past`, `beyond_horizon`, `closed_day`, `outside_hours`; glossary §10), `day_slots`, `is_offered`, `slot_problem`, `BOOKING_HORIZON_DAYS`; unit tests BK-30, SCH-01, SCH-02, SCH-03, SCH-07. Depends only on `shops.domain.grid` and the standard library (pure-domain contract).
2. Schemas `SlotRead`, `AvailabilityRead` (timestamps with `Z`; `date` as `YYYY-MM-DD`).
3. `SlotCounterRepository` with the statements of §7.5–§7.6 (`with_for_update()`, `on_conflict_do_nothing`), all keyed by `shop_id`.
4. Service: `list_availability`, `validate_slot` (raises `InvalidSlot` with the field error), `reserve_slot`, `release_slot`.
5. Router `get_availability` (operationId `scheduling_get_availability`), exported as `routers` (`wire_modules()` includes it, D89).
6. Concurrency tests with the lock gate on the counter row (SM-07) and the ungated burst; CON-03 later.
7. P2 helpers only when the bonus starts (D36).

## 14. Dependencies (specs)

[17-decisions.md](../17-decisions.md) (D20, D24, D30, D37, D38, D51, D63, D64, D68, D71, D86), [18-glossary.md](../18-glossary.md) (§1 Slot, Slot capacity, §5 `Weekday`, §9, §10), [02-data-model.md](../02-data-model.md) §3.6, §6 (slot availability, DI-4), §7.4, [03-api-contracts.md](../03-api-contracts.md) §1.5, §3.2, §4.5, §4.6, [08-booking-state-machine.md](../08-booking-state-machine.md) (T01, T03, T22), [05-calling-and-ai-front-desk.md](../05-calling-and-ai-front-desk.md) (P2 `available-slots`), [10-screens.md](../10-screens.md) P-03 W3, [12-quality-and-testing.md](../12-quality-and-testing.md) §3.5. Uses `modules/shops.md` (`get_listed_shop`, `get_schedule_config`, `shops.domain.grid`). Used by `modules/bookings.md`.

## Open questions

1. **What "within 30 days" means.** This spec counts whole local days (`slot date ≤ today + 30` in shop time), matching the wizard calendar. The alternative (`slot_start ≤ now + 30 × 24 h`) would hide the afternoon of day 30. Confirm in D37's wording.
2. ✅ **Resolved by glossary §10 and spec 03 §2.3: `INVALID_SLOT` field-error codes** — `off_grid`, `in_past`, `beyond_horizon`, `closed_day`, `outside_hours` (the off-grid reason is `off_grid`; `not_on_grid` stays the working-hours code).
3. ✅ **Resolved in spec 02 §7.2: lock list.** Its `CREATE` row now starts with the shop row `SELECT … FOR SHARE` (D37) before the vehicle upsert and the slot counter.

## Proposed glossary additions

| Kind | Name | Meaning |
|---|---|---|
| Constant | `BOOKING_HORIZON_DAYS = 30` (`scheduling.domain.slots`) | The D37 horizon, inclusive, in local days |
| Value objects | `GridSlot`, `SlotProblem` | A computed slot (`slot_start`, `slot_end`) and the reason a requested slot is invalid |
| Field-error codes (spec 03 §2.3) | ✅ merged (glossary §10) — `off_grid`, `in_past`, `beyond_horizon`, `closed_day`, `outside_hours` | Reasons carried by 422 `INVALID_SLOT` |
| Service functions | `scheduling.service.validate_slot`; P2 `list_open_slots`, `is_slot_open` | Additions to spec 01's scheduling catalogue |
