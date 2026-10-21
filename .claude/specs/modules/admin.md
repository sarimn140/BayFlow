# Module: admin

**Status:** Draft — built with spec 19 (2026-10-10)
**Package:** `app.modules.admin`
**Owns tables:** none (D97)
**Priority:** P1 (D36): the brief does not ask for it; it never blocks a P0 path.

## Purpose

The platform admin API, E-61…E-75 (spec 19 §4): read everything across tenants — shops, accounts, bookings with their timelines, the audit log, platform KPIs — and pull the platform's levers: suspend or reactivate a shop (D96), deactivate or reactivate an account, grant or revoke platform admin (D94). Tenants' own data (bookings, estimates, stock) is never changed here: no impersonation, no booking edit, no hard delete (least privilege, spec 19 §1). Spec 19 is authoritative; this file records how the module is built.

The module owns no table and writes nothing itself: every use case composes the read and write ports of identity, shops, bookings and audit (D97). It is the top layer of the module direction (`admin` → `notifications | reporting | audit` → …), so it may import every module and none imports it.

## In scope

- **P1:** the 15 routes E-61…E-75 behind `refuse_cross_site_requests` (D98) and `require_platform_admin`; the spec 19 §1 safeguards (enforced by identity under row locks); the shop suspension levers (enforced by shops under the shop row lock); the audited reads E-67, E-73 and the CSV export E-75; the bootstrap script `app.scripts.create_platform_admin` (D94, uses identity only).

## Out of scope

Impersonation, editing a tenant's booking, estimate or stock, deleting anything (spec 02 §2), bulk actions, admin roles finer than the flag, notifying people of an admin action (a suspended shop's staff find out through 403 `SHOP_SUSPENDED` and `/me`), the console screens A-01…A-08 (web, spec 19 §5), the seed's demo admin (spec 19 §8; the seed has no data yet).

## Key decisions

| D | What it means here |
|---|---|
| D94 | A platform admin is `users.is_platform_admin`; `app.shared.auth.require_platform_admin` (`PlatformAdminDep`) admits only them: 401 when not logged in, 403 `FORBIDDEN` otherwise ("This area is for BayFlow platform admins."). The flag is re-read with the user on every request (D9). |
| D95 | E-67, E-73 and E-75 write `admin.user_viewed`, `admin.booking_viewed`, `admin.audit_exported` through `audit.service`; every lever is audited by the lower module's event. |
| D96 | Suspension and reactivation are `shops.service.suspend_shop` / `reactivate_shop` (shop row `FOR UPDATE`, 409 on the wrong state, reason 5-500 characters). |
| D97 | No table; composes identity, shops, bookings and audit; `MODULES` lists it after `audit`. |
| D98 | `app.shared.auth.refuse_cross_site_requests` runs first on every route: `Sec-Fetch-Site` present and not `same-origin` / `none` → 403 `FORBIDDEN` ("Admin requests must come from the BayFlow app."), because E-67, E-73 and E-75 write audit rows on GET and `SameSite=Lax` sends the cookie on a cross-site top-level navigation. No header (curl, Swagger, tests) passes. |
| D99 | The Owner summary (reporting) leaves suspended shops out; `/me` carries `shop_suspended`. Notifications and realtime to a suspended shop's staff are unchanged. |
| D21 | Cross-tenant booking reads are explicit admin functions of the bookings module (`list_admin_bookings`, `get_admin_booking`): a read-only projection without `allowed_actions`; the D21 predicate of staff and customer reads is never touched. |
| D38, D63 | "Today", the last 7 / 30 days and the 14-day series are `Asia/Karachi` local days (the shops' default zone), from one `utcnow()`. E-72's `date_from` / `date_to` are read in each shop's own zone. |
| D81 | Identity never reads memberships: E-66's `kind` asks shops for the users with an active membership and passes them to identity as an id filter. |

## Files

| File | Contents |
|---|---|
| `router.py` | One `APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(refuse_cross_site_requests), Depends(require_platform_admin)], responses=problem_responses(401, 403))` with the 15 routes; exported as `routers` (D89). |
| `schemas.py` | Requests `ShopSuspendRequest`, `UserDeactivateRequest` (`reason` 5-500, trimmed, `extra="forbid"`); responses `PlatformOverviewRead` (+ `ShopCounts`, `UserCounts`, `BookingCounts`, `PhaseCount`, `DayCount`, `TopShop`), `AdminShopRow`, `AdminShopDetail` (+ `RoleMembers`, `AdminMemberRead`, `ShopSuspensionRead`), `AdminUserRow`, `AdminUserDetail` (+ `AdminMembershipRead`, `CustomerBookings`); wire enums `AdminShopStatus`, `AdminUserKind`, `AdminUserStatus`; sorts `AdminShopSort`; re-exports of bookings' `AdminBookingSummary`, `AdminBookingDetail`, `AdminBookingFilters`, `AdminBookingSort`, audit's `AuditEventRead`, `AuditFilters`, `AuditSort`, shops' `ShopRead`, identity's `UserAdminSort`, `QueryDate`. |
| `service.py` | The use cases below. |
| `domain/phases.py` | `StatusPhase` (glossary §5) and `PHASE_OF` for the 17 statuses; `counts_by_phase` (pure). |
| `domain/periods.py` | `local_midnight`, `last_days(now, zone, days)` (pure). |
| `domain/csv_export.py` | `neutralise`, `csv_line`, `csv_lines`: RFC 4180 with formula neutralisation (pure). |

No `repository.py`, `models.py`, `events.py` or `handlers.py`.

## Public service interface

| Function | Tx | Ports it composes |
|---|---|---|
| `get_overview(session)` | read | shops `count_shops`, `count_staff_users`, `get_shop_briefs`; identity `count_users`; bookings `platform_booking_stats`; audit `latest_events` |
| `list_shops(session, *, q, status, listed, city, sort, page)` | read | shops `list_shops_for_admin` / `list_shop_ids_for_admin` + `get_admin_shop_records`; bookings `count_created_by_shop`; identity `get_users_by_ids` |
| `get_shop(session, *, shop_id)` | read | shops `get_shop`, `get_admin_shop_records`, `list_team`; identity; bookings `count_by_status`, `list_admin_bookings`; audit `latest_events` |
| `suspend_shop` / `reactivate_shop(uow, admin, *, shop_id[, reason])` | top-level | shops `suspend_shop` / `reactivate_shop`, then E-63's body |
| `list_users(session, *, q, kind, status, sort, page)` | read | shops `list_staff_user_ids`, `list_memberships_everywhere`; identity `list_users_for_admin` |
| `view_user(uow, admin, *, user_id)` | top-level (audit row) | identity `get_user_for_admin`; shops; bookings `list_admin_bookings`; audit `latest_events`, `record_user_viewed` |
| `deactivate_user` / `reactivate_user` / `grant_platform_admin` / `revoke_platform_admin(uow, admin, *, user_id[, reason])` | top-level | identity `change_user_active` / `change_platform_admin`, then E-67's body (not recorded as a view) |
| `list_bookings(session, *, filters, sort, page)` | read | bookings `list_admin_bookings` |
| `view_booking(uow, admin, *, booking_id)` | top-level (audit row) | bookings `get_admin_booking`; audit `record_booking_viewed` |
| `list_audit_events(session, *, filters, sort, page)` | read | audit `list_events` |
| `export_audit_events(uow, admin, *, filters) → AuditExport` | top-level (audit row) | audit `export_events`, `record_audit_exported` |

## Endpoints

All under `/api/v1/admin`, tag `admin`; 403 from `refuse_cross_site_requests` (D98), then 401 / 403 from `require_platform_admin`; lists are `Page[T]` (spec 03 §1.6, `limit` 1-100, default 20).

| ID | Method + path | `operationId` | Success | Notes |
|---|---|---|---|---|
| E-61 | `GET /overview` | `admin_get_overview` | 200 `PlatformOverviewRead` | Below |
| E-62 | `GET /shops` | `admin_list_shops` | 200 `Page[AdminShopRow]` | `q` (name, slug, city, owner e-mail), `status` (`ACTIVE`, `SUSPENDED`), `listed`, `city`; sort `-created_at` (default), `name`, `-bookings_30d` |
| E-63 | `GET /shops/{shop_id}` | `admin_get_shop` | 200 `AdminShopDetail` | 404 unknown |
| E-64 | `POST /shops/{shop_id}/suspend` | `admin_suspend_shop` | 200 `AdminShopDetail` | `{reason}` 5-500; already suspended → 409 |
| E-65 | `POST /shops/{shop_id}/reactivate` | `admin_reactivate_shop` | 200 `AdminShopDetail` | not suspended → 409 |
| E-66 | `GET /users` | `admin_list_users` | 200 `Page[AdminUserRow]` | `q` (name, e-mail, phone), `kind`, `status`; sort `-created_at` (default), `name`, `-last_login_at` (nulls last) |
| E-67 | `GET /users/{user_id}` | `admin_get_user` | 200 `AdminUserDetail` | writes `admin.user_viewed` after reading |
| E-68 | `POST /users/{user_id}/deactivate` | `admin_deactivate_user` | 200 `AdminUserDetail` | `{reason}` 5-500; self 403; last active admin 409; already inactive 409 |
| E-69 | `POST /users/{user_id}/reactivate` | `admin_reactivate_user` | 200 `AdminUserDetail` | already active 409 |
| E-70 | `POST /users/{user_id}/grant-platform-admin` | `admin_grant_platform_admin` | 200 `AdminUserDetail` | already admin 409; inactive 422 on `path.user_id` (code `inactive_account`) |
| E-71 | `POST /users/{user_id}/revoke-platform-admin` | `admin_revoke_platform_admin` | 200 `AdminUserDetail` | self 403; not an admin 409; last active admin 409 |
| E-72 | `GET /bookings` | `admin_list_bookings` | 200 `Page[AdminBookingSummary]` | `q` (reference, plate, customer name or e-mail), `shop_id`, `status` (repeatable), `date_from` / `date_to` (slot date in the shop's zone; inverted → 422 `query.date_to`); sort `-slot_start` (default), `slot_start`, `-created_at` |
| E-73 | `GET /bookings/{booking_id}` | `admin_get_booking` | 200 `AdminBookingDetail` | writes `admin.booking_viewed` |
| E-74 | `GET /audit-events` | `admin_list_audit_events` | 200 `Page[AuditEventRead]` | `category` (repeatable), `action`, `actor_user_id`, `shop_id`, `target_type`, `target_id`, `from` (inclusive) / `to` (exclusive), aware timestamps (`from ≥ to` → 422 `query.to`), `q` (summary, target label); sort `-occurred_at` (default), `occurred_at` |
| E-75 | `GET /audit-events/export` | `admin_export_audit_events` | 200 `text/csv; charset=utf-8` | E-74's filters; ≤ 10 000 rows newest first; `Content-Disposition: attachment; filename="bayflow-audit-<UTC instant>.csv"`; writes `admin.audit_exported` |

## Domain rules

### E-61 overview

`now = utcnow()`; `today` = the `Asia/Karachi` date of `now`; the last 30 local days as 31 UTC midnights. Shops: `total`, `active` (not suspended), `suspended`, `listed` (the `is_listed` flag), `new_30d`. Accounts: `total`, `staff` (with an active membership), `customers` (= total − staff, E-66's definition), `platform_admins` (the flag), `inactive`, `new_30d`. Bookings, by when they were **placed** (`created_at`): `today`, `last_7_days`, `last_30_days`; `open` (not `COMPLETED` / `CANCELLED`, now), `completed_30d` / `cancelled_30d` (by `completed_at` / `cancelled_at`), `open_by_phase` (all 7 phases, zeros included); `bookings_per_day` for the 14 local days ending today, oldest first; `top_shops`: the 5 shops with the most bookings placed in the 30 days; `latest_audit_events`: the 10 newest rows.

### Safeguards (spec 19 §1) — in identity and shops

Under `SELECT … FROM users WHERE id = :target OR (is_platform_admin AND is_active) ORDER BY id FOR UPDATE` (one statement, one lock order, so two admins cannot deadlock or demote each other): self → 403; unknown → 404; no-op → 409; grant to an inactive account → 422; last active admin → 409 "BayFlow needs at least one active platform admin."; then the actor must still be an active admin under the locks (403) — after the last-admin rule, so two admins demoting each other at once give the loser 409. The shop levers do the same through identity's `lock_acting_platform_admin`: the acting admin's row `FOR SHARE` before the shop row `FOR UPDATE`, so a concurrent revoke or deactivation of that admin waits for the lever, or committed first and the lever answers 403.

### Suspension (D96) — in shops

`suspend_shop`: reason 5-500 → actor is an active platform admin (403) → shop `FOR UPDATE` (404) → already suspended 409 → `suspended_at = now`, reason, by → `ShopSuspensionChanged`. While suspended (spec 19 §2): public list, cities, detail, availability and `POST /bookings` treat it as unlisted (404); `require_shop_member` answers 403 `SHOP_SUSPENDED` to every member before any role check (non-members keep their 404); `/me` sets `shop_suspended`; customer reads work, customer actions other than `cancel` are 403 `SHOP_SUSPENDED` and `allowed_actions` hold `cancel` only. Nothing is deleted or changed; reactivation restores everything.

### CSV export (E-75, spec 19 §7)

Header `occurred_at, category, action, summary, actor_user_id, actor_name, actor_role, shop_id, shop_name, target_type, target_id, target_label, metadata, ip, user_agent, request_id`; CRLF line ends; a field with a comma, a double quote or a line break is quoted and its quotes doubled (RFC 4180); a cell starting with `=`, `+`, `-`, `@`, a tab or a carriage return gets a leading `'`; `None` is an empty cell; `metadata` is compact JSON; UTF-8 without BOM. The rows are read first (at most 10 000, newest first), then `admin.audit_exported` `{filters, rows}` is committed, so an export never contains its own row; the response streams the prepared lines.

## Permissions and visibility

Platform admins only (D94), from BayFlow's own pages or a typed URL (D98), for every route; a platform admin who also holds memberships uses the POS separately (spec 19 §7). Admin reads see every tenant; they never change what staff or customers can see.

## Errors

| Code | HTTP | When |
|---|---|---|
| `UNAUTHENTICATED` | 401 | Not logged in, or the admin's account was deactivated (D9) |
| `FORBIDDEN` | 403 | A cross-site or same-site browser request (D98, before authentication); not a platform admin; deactivating or revoking yourself; an actor who lost the flag under the locks |
| `NOT_FOUND` | 404 | Unknown shop, user or booking |
| `CONFLICT` | 409 | Already suspended / not suspended; already inactive / already active; already admin / not admin; the last active platform admin |
| `VALIDATION_ERROR` | 422 | Reason outside 5-500; unknown filter or sort value; naive `from` / `to`; inverted periods; grant to an inactive account (`path.user_id`) |

## Concurrency and transactions

Every lever is one transaction committed by this module after the nested port ran under its row locks (the acting admin's row `FOR SHARE` then the shop row `FOR UPDATE`, or the target + active admins `FOR UPDATE`). Two admins suspending one shop at once: the second waits on the shop row, re-reads it and gets 409. A revoke of the acting admin racing a suspension: whichever locks the admin's row first wins; the suspension then either completes before the revoke, or answers 403. A booking racing a suspension re-checks the shop under its `FOR SHARE` (bookings T01 step 10). Reads run at READ COMMITTED; the overview's counts are separate statements and may straddle a concurrent action by milliseconds (like reporting, D14 polling converges).

## Tests

`tests/modules/admin/`: `test_authorization.py` (the 15 operations and their tags; every route 401 anonymous and 403 for the Owner, each staff role, another shop's staff and a customer, with nothing written; cross-site and same-site requests 403 on GET and POST routes with nothing written, `same-origin` / `none` / no header allowed (D98); the flag re-read per request; unknown ids 404), `test_users_api.py` (E-66 rows, filters, kinds, sorts, paging; E-67 and its audit row; E-68/E-69; E-70/E-71; every safeguard; two admins demoting each other through the lock gate → one 200, one 409), `test_shops_api.py` (E-62 rows, filters, sorts incl. `-bookings_30d`; E-63; E-64/E-65 incl. reason bounds and 409s; two admins suspending at once; the service re-checks the admin; a revoke racing its admin's suspension in both orders through the lock gate), `test_suspension_surfaces.py` (every surface of spec 19 §2, customer `cancel` allowed, the owner summary leaves the shop out (D99), reactivation restores, nothing changed; every route that can answer 403 declares it in OpenAPI), `test_bookings_api.py` (E-72 filters incl. a Los Angeles shop's local dates, sorts, read-only; E-73 and its audit row; staff and customer predicates unchanged), `test_overview_api.py` (every E-61 figure on known days; Karachi's "today"), `test_audit_api.py` (E-74 filters, sorts, names; E-75 quoting, neutralisation, headers, its audit row, the 10 000-row cap); `tests/unit/admin/test_admin_domain.py`; `tests/scripts/test_create_platform_admin.py`; `tests/modules/bookings/test_concurrency.py::test_a_booking_waiting_on_the_shop_row_sees_it_closed` (suspension or unlisting vs booking creation).

## Dependencies (specs)

[19-platform-admin.md](../19-platform-admin.md) (authoritative), [17-decisions.md](../17-decisions.md) D9, D21, D36, D38, D63, D81, D89, D94-D100, [01-architecture.md](../01-architecture.md), [03-api-contracts.md](../03-api-contracts.md) §1.6, §2, [audit.md](audit.md), [identity.md](identity.md), [shops.md](shops.md), [bookings.md](bookings.md).

## Open questions

1. ✅ **Resolved (spec 03 §3.2, spec 19 §2): `/me` fields.** `MembershipRead` is flat, so the flag is `shop_suspended`; `MeRead.is_platform_admin` is listed too.
2. ✅ **Resolved (spec 19 §4): E-68…E-71 responses.** They answer E-67's body (`AdminUserDetail`) without recording a view.
3. **The 30-day windows of E-62.** `bookings_30d` uses the platform's `Asia/Karachi` local days for every shop (like E-61), not each shop's own zone. Confirm.
4. **Seed (spec 19 §8).** The seed has no data yet ("no seed data defined yet"), so the demo admin Areeba Hashmi (`admin@bayflow.test`) is not seeded; `python -m app.scripts.create_platform_admin` covers the bootstrap. Tracked in spec 16 C.1.
5. ✅ **Resolved by D99: owner summary.** Suspended shops are left out of `GET /api/v1/me/owner-summary`.
6. **The OpenAPI snapshot** `apps/web/src/lib/api/openapi.json` and `schema.d.ts` must be regenerated with `make gen-api` (D76) for the new routes, fields and 403 declarations.

## Proposed glossary additions

| Kind | Name | Meaning |
|---|---|---|
| Dependency | `require_platform_admin`, `PlatformAdminDep` (`app.shared.auth`) | 401 / 403 gate of `/api/v1/admin/*` |
| Dependency | `refuse_cross_site_requests` (`app.shared.auth`, D98) | Fetch Metadata check of `/api/v1/admin/*`: 403 unless `Sec-Fetch-Site` is absent, `same-origin` or `none` |
| Wire enums | `AdminShopStatus`, `AdminUserKind`, `AdminUserStatus`, `StatusPhase` (now on the wire) | E-62 / E-66 filters, E-61 / E-63 phases |
| Script | `app.scripts.create_platform_admin` | Bootstrap of the first platform admin (D94) |
| Response field | `MembershipRead.shop_suspended`, `MeRead.is_platform_admin` | `/me` (spec 19 §2, §4) |
