# Module: reporting

**Status:** Draft
**Package:** `app.modules.reporting`
**Owns tables:** none — read-only queries (glossary §7)
**Priority:** P0 for the per-shop overview; P1 for the owner multi-shop summary (D36). Nothing in P2.

## Purpose

Give the Owner one screen per shop with what brief §7.4 asks of the Owner dashboard: "Overview of each shop: bookings by status, team list, inventory summary". The P1 multi-shop summary answers brief §2 "Multiple branches — each branch keeps separate notebooks → Owner has no visibility across locations" and §3 "Multi-branch chaos". Both serve the §2 core problem "No visibility". The last part of the §7.4 Owner row ("can open any role view for support") is served by the other modules' read-only screens (D16, spec 10 O-06), not here.

The module owns no tables and runs no SQL of its own: it composes read functions of shops, bookings and inventory in the request's session (spec 01 rule 5, ADR driver 5).

## In scope

- **P0:** `GET /api/v1/shops/{shop_id}/overview` → `OverviewRead`: shop block, bookings by status (all 17), today's counts, team list with open jobs, inventory summary, the top five low-stock parts and the setup checklist (spec 03 §3.7, §4.13).
- **P1:** `GET /api/v1/me/owner-summary` → `OwnerSummaryRead`: one row per shop the caller owns that is not suspended (D99).
- **P2:** none.

## Out of scope

Revenue, average turnaround time and QC fail rate (brief §8.3 "Owner analytics" is optional; spec 13), history or time series, exports, caching or materialised views, platform-wide statistics, and the five most recent bookings (the web reads them from `GET …/bookings?sort=-updated_at&limit=5`, spec 03 §4.13).

## Key decisions

| D | What it means here |
|---|---|
| D16 | The overview is Owner-only; the Owner sees every booking of the shop, so counts cover all of them. |
| D19, D20 | Every read is scoped by `shop_id`; the summary lists only shops where the caller holds the `OWNER` membership (which can never be inactive). |
| D21 | No visibility filter is applied to the Owner's counts (the Owner sees the whole shop). |
| D36 | Overview P0, multi-shop summary P1. |
| D38, D63 | "Today" is the shop-local date of `utcnow()` in `shops.timezone`; the window is computed by a pure function that receives `now`. |
| D41 | `stock_value` is whole rupees (`Money`). |
| D45 | `LOW` / `OUT` as in inventory; `low_stock_count` counts both (spec 03 §3.7). |
| D14 | No push of its own: the overview is one of the views the web polls every 15 s (spec 03 §6.6); `booking.updated` triggers a refetch. |
| D3 | Composition happens in-process, in one session: no API calls between modules (spec 01 ADR). |
| D86 | The reads it needs from bookings are ordinary service calls (reporting sits above bookings in the module direction); no read port is needed here. Read ports — shops' `ShopActivityReader` (`shops.service.register_activity_reader`) and inventory's `BookingRefReader` (`inventory.service.register_booking_ref_reader`) — exist only for lower modules reading bookings facts. |

## Files

| File | Contents |
|---|---|
| `router.py` | `shop_scoped_router(tags=["reporting"])` with `GET /overview` (`require_roles(OWNER)`), and an `APIRouter(prefix="/api/v1/me", tags=["reporting"])` with `GET /owner-summary` (`get_current_user`). |
| `schemas.py` | `OverviewRead`, `OwnerShopSummary`, `OwnerSummaryRead` (spec 03 §3.7) and their nested objects (`OverviewShop`, `OverviewToday`, `OverviewTeamMember`, `OverviewInventory`, `OverviewSetup`, `OwnerShopRef`); reuses `PartRead` from inventory. |
| `service.py` | `get_owner_overview`, `get_owner_summary`. |
| `domain/kpis.py` | `SA_ACTION_STATUSES`, `IN_PROGRESS_STATUSES`, `local_day_window(now, tz)` (pure). |

No `repository.py` or `models.py` (no tables), no `events.py` or `handlers.py`.

## Public service interface

Both functions are top-level **reads**: they take the request's `AsyncSession`, write nothing and never commit.

| Function | Returns | Raises |
|---|---|---|
| `get_owner_overview(session, ctx: ShopContext)` | `OverviewRead` | 403 `FORBIDDEN` when `ctx.role` is not `OWNER` (the route already checks; the service re-checks) |
| `get_owner_summary(session, user: CurrentUser)` | `OwnerSummaryRead` (`items: []` when the caller owns no open shop; suspended shops are left out, D99) | — |

Reads it composes:

| Module | Function | Used for |
|---|---|---|
| shops | `get_shop_briefs(session, *, shop_ids)` ([shops.md](shops.md) §5.2) | `shop` block, `timezone` |
| shops | `get_setup_flags(session, *, shop_id)` ([shops.md](shops.md) §5.2) | `setup.has_services`, `setup.has_team`, `setup.is_listed` |
| shops | `list_team(session, *, shop_id)` (spec 01, [shops.md](shops.md)) | `team[]`: every membership, active or not, with the user's full name |
| shops | `list_memberships_for_user(session, *, user_id, roles={OWNER})` (spec 01, [shops.md](shops.md)) | the shops the caller owns (P1) |
| bookings | `count_by_status(session, *, shop_id)` (spec 01, [bookings.md](bookings.md) §5.3) | `status_counts`, owner-summary groups |
| bookings | `count_open_jobs(session, *, shop_id, user_ids)` ([bookings.md](bookings.md) §5.3) | `team[].open_jobs` |
| bookings | `count_day_activity(session, *, shop_id, start, end) → DayActivity(bookings, completed)` ([bookings.md](bookings.md) §5.3) | `today.bookings`, `today.completed`, `today_bookings` |
| inventory | `get_stock_summary(session, *, shop_id)` ([inventory.md](inventory.md)) | `inventory`, `low_stock`, `setup.has_parts` |
| inventory | `count_low_stock(session, *, shop_ids)` (P1, [inventory.md](inventory.md)) | `low_stock_count` per owned shop |

## Endpoints

| Method | Path | `operationId` | Auth · roles | Success | Pri |
|---|---|---|---|---|---|
| GET | `/api/v1/shops/{shop_id}/overview` | `reporting_get_overview` | member (else 404) · O (else 403) | 200 `OverviewRead` | P0 |
| GET | `/api/v1/me/owner-summary` | `reporting_get_owner_summary` | session | 200 `OwnerSummaryRead` | P1 |

Contracts: [spec 03 §3.7 and §4.13](../03-api-contracts.md). Neither route takes a body or query parameters.

## Domain rules and algorithms

### The "today" window (`domain/kpis.py`)

`local_day_window(now, tz) -> (date, start, end)`: `date = now.astimezone(tz).date()`; `start` = local midnight of `date`; `end` = local midnight of the next date; both converted to UTC. `now` is read once per request with `utcnow()` (D63). Counting uses half-open intervals `[start, end)`. With `Asia/Karachi` (UTC+5, no DST), Friday 16 Oct 2026 is `[2026-10-15T19:00:00Z, 2026-10-16T19:00:00Z)`.

### `OverviewRead` (spec 03 §3.7 "Reporting definitions")

| Field | Definition |
|---|---|
| `shop` | `{id, slug, name, city, is_listed}` |
| `status_counts` | `[{status, count}]` for all 17 `BookingStatus` values in glossary §3 order, zeros included (same rule as `StatusCountsRead`), over every booking of the shop |
| `today.date` | The shop-local date (`YYYY-MM-DD`) |
| `today.bookings` | Bookings not `CANCELLED` whose `slot_start` is in today's window |
| `today.ready_for_pickup` | Bookings currently `READY_FOR_PICKUP`, whatever their date |
| `today.completed` | Bookings whose `completed_at` is in today's window |
| `team[]` | Every membership of the shop — the `OWNER` row and inactive members included — as `{membership_id, user_id, full_name, role, is_active, open_jobs}`, ordered by role in glossary §2.1 order, then name. `open_jobs` = bookings not in `READY_FOR_PICKUP`, `COMPLETED` or `CANCELLED` where the member is the technician, the parts person or the current QC picker (the `MemberRead.open_jobs` definition) |
| `inventory.parts_count` | Active parts |
| `inventory.low_stock_count` | Active parts whose `stock_state` is `LOW` **or** `OUT` |
| `inventory.out_of_stock_count` | Active parts with available = 0 |
| `inventory.stock_value` | Σ `on_hand × unit_cost` over active parts. As built it is `MoneyTotal`: the same wire form as `Money` (whole rupees, 2-decimal string) without `Money`'s 10-digit cap, because a sum can exceed 9,999,999,999 and `Money` would turn the overview into a 500 |
| `inventory.open_purchase_orders` | POs `ORDERED` or `PARTIALLY_RECEIVED` |
| `low_stock[]` | Up to 5 active `LOW`/`OUT` parts as `PartRead`: `OUT` first, then by available ascending, then by SKU |
| `setup` | `has_services` = ≥ 1 active service; `has_team` = ≥ 1 active non-owner membership; `has_parts` = ≥ 1 active part; `is_listed` = `shops.is_listed` (drives spec 10 O-01's checklist) |

Inactive parts are left out of every inventory figure: they are no longer stocked, and counting them as `OUT` would be noise. The web's KPI tiles ("Needs SA action", "In progress") are summed from `status_counts` with the same groups as the owner summary below. The web shows "Low" as `low_stock_count − out_of_stock_count` and "Out" as `out_of_stock_count`.

**Check against the seed** (spec 11, Lahore Auto Care right after seeding): 9 bookings — `PENDING`, `AWAITING_CUSTOMER`, `PARTS_ORDERED`, `IN_REPAIR`, `QC_PENDING`, `READY_FOR_PICKUP`, `COMPLETED` 1 each, `CANCELLED` 2; team of 7 (open jobs: Imran 4, Usman 3, everyone else 0); 16 parts, `out_of_stock_count` 3, `low_stock_count` 6 (3 `OUT` + 3 `LOW`), `stock_value` 286,400.00, 2 open POs; `low_stock` = front brake disc, ignition coil, wiper blades, front brake pads, cabin AC filter.

### `OwnerSummaryRead` (P1)

One row per shop where the caller holds the `OWNER` membership, ordered by shop name, then id; `items: []` for everyone else (RPT-02).

| Field | Definition |
|---|---|
| `shop` | `{id, slug, name, city}` |
| `today_bookings` | As `today.bookings`, in that shop's timezone |
| `needs_sa_action` | Bookings in `SA_ACTION_STATUSES` = `PENDING`, `CONFIRMED`, `ESTIMATE_REVIEW`, `ESTIMATE_APPROVED`, `ESTIMATE_REJECTED`, `READY_FOR_PICKUP` (the statuses whose step owner is the SA, glossary §3) |
| `in_progress` | Bookings in `IN_PROGRESS_STATUSES` = every other non-terminal status: `ASSIGNED`, `INSPECTING`, `AWAITING_CUSTOMER`, `PARTS_PENDING`, `PARTS_ORDERED`, `PARTS_READY`, `IN_REPAIR`, `QC_PENDING`, `QC_IN_PROGRESS` |
| `ready_for_pickup` | Bookings currently `READY_FOR_PICKUP` (also counted in `needs_sa_action`) |
| `low_stock_count` | Active parts that are `LOW` or `OUT` |

The 6 SA statuses, the 9 in-progress statuses and the 2 terminal statuses partition all 17; a unit test asserts it.

### Consistency and cost

- About nine read statements in one session at READ COMMITTED; a count may straddle a concurrent action by milliseconds, and the next 15 s poll converges. No locks, no writes.
- Every count is an indexed aggregate (`ix_bookings_shop_id_status_slot_start`, `ix_bookings_shop_id_slot_start`, `uq_parts_shop_id_sku`, `ix_purchase_orders_shop_id_status_created_at`).
- The owner summary calls `count_by_status` and `count_day_activity` once per owned shop (owners have few shops; shop creation is limited to 10 per day) and `count_low_stock` once for all of them.

## Events

None published, none subscribed.

## Permissions and visibility

- Overview: the router-level `require_shop_member` answers 404 to non-members and other tenants; `require_roles(OWNER)` answers 403 `FORBIDDEN` to SA, technician, parts person and QC inspector (RPT-03, spec 04 RBAC A). Its data never mixes shops (RPT-01).
- Owner summary: any logged-in user; only shops the caller owns appear (RPT-02); a customer or pure staff member gets `items: []`, never a 403. A suspended shop is left out (D99, read from `ShopBrief.is_suspended`): its staff views, which these figures summarise, are closed (403 `SHOP_SUSPENDED`, D96), and `GET /api/v1/me` still lists the membership with `shop_suspended: true`, which is where the web shows it.
- Overview of a suspended shop: 403 `SHOP_SUSPENDED` from the router-level `require_shop_member`, before `require_roles` (D96).
- The team list shows only the shop's own members, which the Owner manages anyway; no customer data appears beyond counts.

## Errors

| Code | HTTP | When |
|---|---|---|
| `UNAUTHENTICATED` | 401 | No or invalid session |
| `NOT_FOUND` | 404 | Not an active member of `shop_id` (overview) |
| `FORBIDDEN` | 403 | A member whose role is not `OWNER` (overview) |
| `SHOP_SUSPENDED` | 403 | Any member of a suspended shop (overview, D96) |
| `VALIDATION_ERROR` | 422 | Malformed `shop_id` in the path |

## Concurrency and transactions

Read-only: no row locks, no `commit()`; the session dependency closes the session (and rolls back the implicit read transaction). The module cannot deadlock with any write path.

## Tests

- **Must pass (spec 12):** RPT-01, RPT-03, RPT-02 (P1), SEC-02 (route sweep includes the overview), SEC-03, API-13 (`no-store`).
- **Proposed additions:**

| ID | Test |
|---|---|
| RPT-04 | `status_counts` lists all 17 statuses in glossary §3 order, zeros included, and sums to the shop's bookings |
| RPT-05 | Today window in the shop's timezone with a frozen clock at `2026-10-15T19:30:00Z` (16 Oct 00:30 PKT): a booking at `2026-10-16T05:00:00Z` counts, one at `2026-10-15T18:00:00Z` does not; a cancelled one never counts; `completed` follows `completed_at` |
| RPT-06 | Inventory: `stock_value` = Σ on hand × cost over active parts; an inactive part is excluded; `low_stock` order `OUT` first, then available, max 5; `low_stock_count` counts `LOW` + `OUT` |
| RPT-07 | Team: inactive members and the `OWNER` row are listed; `open_jobs` counts technician, parts-person and current-picker roles and ignores `READY_FOR_PICKUP`, `COMPLETED`, `CANCELLED` |
| RPT-08 | Setup flags on a brand-new shop (`has_services`, `has_team`, `has_parts` false; `is_listed` true), then each flips after the matching action |
| RPT-09 | Owner summary: SA + in-progress + terminal groups partition all statuses (unit); the summary of an owner of two shops who is staff in a third has exactly two rows |

## Implementation checklist

1. `domain/kpis.py` (status groups, `local_day_window`) with unit tests (RPT-09 unit half, RPT-05 window).
2. Agree the reads with the owning module specs: shops `get_shop_briefs`, `get_setup_flags`, `list_team`, `list_memberships_for_user`; bookings `count_by_status`, `count_open_jobs`, and the new `count_day_activity`; inventory `get_stock_summary`, `count_low_stock`.
3. `schemas.py` (`Money` for `stock_value`, `PartRead` for `low_stock`).
4. `get_owner_overview` + the overview route; export both routers as `routers` (`wire_modules()` includes them, D89; spec 14 PH6).
5. P1: `get_owner_summary` + route.
6. Tests above.

## Dependencies (specs)

- [17-decisions.md](../17-decisions.md) D3, D14, D16, D19, D20, D21, D36, D38, D41, D45, D63, D86; [18-glossary.md](../18-glossary.md) §2.1, §3, §7.
- [03-api-contracts.md](../03-api-contracts.md) §3.2 (`MemberRead.open_jobs`), §3.7, §4.13, §6.6; [01-architecture.md](../01-architecture.md) rule 5, module catalogue; [04-auth-and-security.md](../04-auth-and-security.md) RBAC A.
- [06-workflows.md](../06-workflows.md) O6; [10-screens.md](../10-screens.md) O-01, O-07; [11-seed-data.md](../11-seed-data.md) first-login table; [12-quality-and-testing.md](../12-quality-and-testing.md) RPT.
- Other modules: [shops.md](shops.md), [bookings.md](bookings.md), [inventory.md](inventory.md).

## Open questions

1. **`low_stock_count` vs the UI.** Spec 03 counts `LOW` and `OUT` together; the web shows "Low" as `low_stock_count − out_of_stock_count` and "Out" as `out_of_stock_count` (see above). Confirm, or split the field in spec 03.
2. ✅ **Resolved in `modules/bookings.md` §5.3: `count_day_activity`.** It returns `DayActivity(bookings, completed)` for one shop and one UTC window. A variant that takes several shops is needed only if API-11's statement-count guard is applied to the owner summary (P1).

## Proposed glossary additions

| Kind | Name | Meaning |
|---|---|---|
| Domain constants | `SA_ACTION_STATUSES`, `IN_PROGRESS_STATUSES` | Spec 03 §3.7's `needs_sa_action` and `in_progress` groups, in one place for the API and the tests |
| Cross-module read | bookings `count_day_activity(session, *, shop_id, start, end)` (✅ adopted in `modules/bookings.md` §5.3) | Non-cancelled bookings starting in the window and bookings completed in it |
| OpenAPI component names | `OverviewShop`, `OverviewToday`, `OverviewTeamMember`, `OverviewInventory`, `OverviewSetup`, `OwnerShopRef` | Nested objects of spec 03 §3.7, so the generated TypeScript types have stable names |
