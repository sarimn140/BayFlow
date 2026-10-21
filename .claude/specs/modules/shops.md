# Module: shops

**Status:** Draft
**Package:** `app.modules.shops`
**Owns tables:** `shops`, `shop_working_hours`, `shop_memberships`, `services`

## 1. Purpose

Own the tenants and everything an Owner configures: shops (profile, listing, slot settings), the 7 weekly working-hours rows on the midnight-anchored slot grid, the team (one membership and one role per user per shop), and the service catalogue. Shops also answers the questions every other module asks about a tenant: is this caller an active member (the D20 dependency), who are "the SAs of the shop", is this user an eligible assignee, what is this shop's slot configuration. It serves the public directory (by slug) and `GET /api/v1/me` with server-computed capabilities, and it is the only place that decides whether a shop change touches the slot grid (D37: it publishes `ShopGridChanging`, which `bookings` may veto).

Brief sections satisfied:

- §7.2 Owner: "Create a shop (name, address, city, phone, working hours, slot duration/capacity, logo optional)"; "Add team members to a shop with a role (SA, Technician, QC, Parts Person); edit or deactivate them"; "Create additional shops later; each shop has an independent team, services, slots and inventory"; "Shop switcher in the dashboard for owners with multiple shops"; "Configure the service catalog (name, description, estimated duration, base price optional)".
- §7.3 Landing: "list or grid of all shops (name, city, rating placeholder, services offered), basic search or city filter".
- §3 "What multi-tenant means here" and §7.1 "Tenant isolation enforced server side" (the membership look-up behind `require_shop_member`); §4 Access rules ("Roles are scoped per shop", "Shop staff accounts are created by the Owner, never by self sign-up", "An Owner can do everything inside their own shops").
- §6 step 0 (Fatima creates Lahore Auto Care and adds Bilal, Imran, Sara, Usman); FAQ "How do multiple shops work for one owner?", "Can one person have multiple roles?", "Does the slot system need to be complex?" (per-shop hours, fixed duration, capacity).

## 2. Scope

| Priority | In scope |
|---|---|
| **P0** | Shop create (with 7 working-hours rows and the `OWNER` membership in one transaction), read, update; working-hours replace with grid validation; the D37 grid-change guard (`ShopGridChanging`); slug generation (immutable); team list / add (D18) / role change, deactivate, reactivate (D19); service catalogue list / create / update; public directory, cities and shop detail by slug (D64, D68); `GET /api/v1/me` with capabilities (D66); rate limits for shop and member creation (D69); look-ups used by `app.shared.auth`, scheduling, bookings, notifications, reporting, inventory and qc; internal `set_rating` for the seed (D56). |
| **P1** | Shop suspension (D96, spec 19 §2): the suspension columns, `suspend_shop` / `reactivate_shop` for the admin module, the `get_shop_suspension` read port behind `require_shop_member`, suspended shops treated as unlisted publicly, `shop_suspended` on `/me`; the audit events of §8 (D95); the admin reads of spec 19 §4 (E-61…E-63, E-66). The multi-shop summary is `reporting`. |
| **P2** | `tasks.manage` capability for Owner and SA when calling is enabled (glossary §2.4); `get_shop_profile` for the AI agent's `GET /api/v1/internal/calls/{call_id}/shop` (spec 05). |
| **Out of scope** | Deleting shops, memberships or services (never; deactivate instead, spec 02 §2); changing a slug; setting `rating` over HTTP (seed only, D56); logo file upload (URL only, D55); editing a user's name, e-mail or password through a membership (identity owns accounts, D18); invitations / consent for attaching an existing account (Tier 3); transferring ownership or a second `OWNER`; per-date holidays, split shifts, overnight hours; per-service slot lengths (`estimated_duration_minutes` is informational). |

## 3. Key decisions

| D | What it means here |
|---|---|
| D9 | `get_active_membership` re-reads the membership on every request; a deactivated membership is invisible at once (404 on that shop's routes). |
| D15 | One membership (one role) per user per shop, enforced by `uq_shop_memberships_shop_id_user_id`; exactly one `OWNER` per shop (created with the shop; `uq_shop_memberships_one_owner_per_shop`). |
| D16 | The Owner manages shop settings, hours, team and services (`shop.manage`, `team.manage`, `services.manage`) and the parts catalogue (`parts.manage`, inventory). |
| D17 | Any logged-in user may create a shop and becomes its `OWNER`; other memberships are untouched. |
| D18 | Owner adds staff: new e-mail → account created with the Owner's password; existing e-mail → **only** a membership, the account's password, name and phone are never modified. |
| D19 | Any non-owner membership may be deactivated, reactivated or re-roled at any time; the `OWNER` membership never (403 `FORBIDDEN`); bookings assigned to the member stay assigned. |
| D20 | `require_shop_member` (in `app.shared.auth`, attached by `shop_scoped_router()`, D80) calls `get_active_membership`; every repository method on shop data takes `shop_id`; `shop_id` comes only from the path. |
| D26 | "SAs of the shop" = active `SERVICE_ADVISOR` members with an active account; none → the `OWNER` (`list_active_member_ids` + `get_owner_user_id`). |
| D34 | `snapshot_services` returns name and base price for the booking's snapshot; deactivating a service hides it from the wizard and directory but never touches existing bookings. |
| D37 | The slot grid is anchored at local midnight and steps by `slot_duration_minutes`; opening and closing times must lie on it; a slot ends by closing time. Changing `slot_duration_minutes` or `timezone` locks the shop row `FOR UPDATE` and publishes `ShopGridChanging` (bookings vetoes with 409 `CONFLICT` while future non-cancelled bookings exist); capacity and working-hours changes are always allowed. |
| D38 | `timezone` is an IANA name (default `Asia/Karachi`), validated with `zoneinfo`; times of day are shop-local wall-clock `time` values. |
| D41 | `services.base_price` is whole rupees (`Money`). |
| D55, D56 | `logo_url` optional, `https://` only; `rating` is a seeded placeholder (null → "New"). |
| D60 | The seed repairs demo memberships through `update_member` as the shop's Owner. |
| D62 | `MemberCreate.email` is the project `Email` type. |
| D63 | Every timestamp comes from the clock, read once per action after the action's row lock. |
| D64 | The public directory and booking creation accept only shops with `is_listed = true` **and** at least one active service. |
| D66 | `GET /api/v1/me` returns each active membership with server-computed `capabilities` from one role table (`domain/capabilities.py`). |
| D68 | Public routes address shops by slug. |
| D69 | Shop creation: 10 per user per day; member creation: 30 per shop per hour → 429 `RATE_LIMITED`. |
| D80 | Staff routes are built with `app.shared.auth.shop_scoped_router()`. |
| D81 | `GET /api/v1/me` is served and tagged by this module (operation `shops_get_me`, spec 03 §1.11); login returns no memberships, so the web always calls `/me` after it. |
| D86 | Shops declares the read port `ShopActivityReader` and `shops.service.register_activity_reader()` (§5.3); bookings implements it (`bookings.service.shop_activity_reader`) and registers it from its own `service.register_ports()` (glossary §7.1a). Shops never imports bookings. Inventory follows the same pattern with `BookingRefReader` and `inventory.service.register_booking_ref_reader()`. |
| D89 | `router.py` exports `routers` (the four routers of §4); `app.main.wire_modules()` includes them and runs bookings' `register_ports()` at start-up. Shops has no `handlers.py` and never edits `app/main.py`. |
| D87 | A QC pick held by a deactivated inspector is un-stuck by the planned P1 bookings operation `REASSIGN_QC_INSPECTOR`, which uses `require_eligible_member(…, role=QC_INSPECTOR)`; until it ships, the Owner reactivates the inspector. |

## 4. Files

| File | Contents |
|---|---|
| `models.py` | `Shop`, `ShopWorkingHours`, `ShopMembership`, `Service` (exist; spec 02 §3.2–§3.5) with their checks (`Shop` adds `suspended_at`, `suspended_reason` varchar(500), `suspended_by_user_id` FK `users` `RESTRICT`, `ck_shops_suspension_complete` and the `is_suspended` property, D96), `uq_shops_slug`, `uq_shop_working_hours_shop_id_weekday`, `uq_shop_memberships_shop_id_user_id`, `uq_shop_memberships_one_owner_per_shop`, `uq_services_shop_id_id`, `uq_services_active_name`, `ix_shops_listed_city_name`, `ix_shop_memberships_user_active`, `ix_shop_memberships_shop_role_active`. |
| `repository.py` | `ShopRepository` (get, get_for_update, get_for_share, get_by_slug, slug look-up, directory page + count, cities, briefs), `WorkingHoursRepository` (list for shops, upsert 7 rows), `MembershipRepository` (exists: `get_active`; add: get_for_update by `(shop_id, membership_id)`, list by shop with filters, active ids by role, owner id, by user), `ServiceRepository` (page, active by ids, duplicate-name check, active services of many shops). Every shop-data method takes keyword-only `shop_id`. `uq_shops_slug` is caught locally (savepoint retry, §7.3); `uq_shop_memberships_shop_id_user_id` and `uq_services_active_name` already map to 409 `CONFLICT` through the global constraint map (`app.core.db_errors`). |
| `schemas.py` | Requests: `ShopCreate`, `ShopUpdate`, `WorkingHoursWrite`, `WorkingHoursUpdate`, `MemberCreate`, `MemberUpdate`, `ServiceCreate`, `ServiceUpdate`. Responses (spec 03 §3.2): `ShopRead`, `WorkingHoursRead`, `ShopPublicSummary`, `ShopPublicDetail`, `ServiceRead`, `MemberRead`, `MemberCreatedRead`, `MeRead` (+ `is_platform_admin`), `MembershipRead` (+ `shop_suspended`). Internal (`ShopBrief` + `is_suspended`; admin records `ShopSuspension`, `AdminShopRecord`, `AdminMembershipRecord`, `ShopStats`): `MembershipRecord` (today's internal `MembershipRead`: `id`, `shop_id`, `user_id`, `role`, `is_active`), `ShopBrief`, `ServiceSnapshot`, `MemberRef`, `TeamMember`. |
| `events.py` | `ShopGridChanging` (glossary §7.1) and the audit events of §8 (spec 19 §3.3). |
| `domain/capabilities.py` | `Capability` (`StrEnum`: `shop.manage`, `team.manage`, `services.manage`, `parts.manage`, `stock.manage`, `tasks.manage`), `CAPABILITY_ROLES`, `capabilities_for(role, *, tasks_enabled)`. |
| `domain/grid.py` | Value objects `WorkingDay`, `ScheduleConfig`; `minutes_of`, `is_on_grid`, `week_problems`, `hours_fit_grid` (D37). Pure; scheduling's slot maths imports it. |
| `domain/slugs.py` | `slugify(name)`, `slug_candidates(base)`. |
| `service.py` | Use cases and look-ups of §5; the `ShopActivityReader` port. Never imports `app.shared.auth` (spec 01 rule 8). |
| `router.py` | Four routers, exported as `routers` (D89): `public_router` (`/api/v1/public`, tag `shops`), `me_router` (`/api/v1`, tag `shops`, so `GET /me` is `shops_get_me`), `shops_router` (`/api/v1/shops`, `POST` only), `shop_router = shop_scoped_router(tags=["shops"])`. |

No `handlers.py`: shops subscribes to nothing.

## 5. Public service interface

`uow` = write (top-level functions commit), `session` = read. Owner-only writes also re-check the actor's role in the service (defence in depth, and so seed calls are validated exactly like HTTP calls): no active membership → 404, wrong role → 403.

### 5.1 Use cases (top-level, behind the routes and the seed)

| Function | Arguments → returns | Errors |
|---|---|---|
| `create_shop` | `(uow, *, actor_user_id, data: ShopCreate) → ShopRead` | 422 (schema, `working_hours.N.*`, `timezone`), 429 |
| `update_shop` | `(uow, *, shop_id, actor_user_id, data: ShopUpdate) → ShopRead` | 403, 409 `CONFLICT` (grid veto), 422 `hours_not_on_grid` |
| `replace_working_hours` | `(uow, *, shop_id, actor_user_id, data: WorkingHoursUpdate) → ShopRead` | 403, 422 |
| `get_shop` | `(session, *, shop_id) → ShopRead` | — (membership already checked) |
| `list_members` | `(session, *, shop_id, caller_role, roles, is_active, page) → Page[MemberRead]` | 403 (T, PP, QC) |
| `add_member` | `(uow, *, shop_id, actor_user_id, data: MemberCreate) → MemberCreatedRead` | 403, 409 `CONFLICT`, 409 `EMAIL_ALREADY_REGISTERED` (race), 422 (`password` `missing`), 429 |
| `update_member` | `(uow, *, shop_id, actor_user_id, membership_id, data: MemberUpdate) → MemberRead` | 403 (`OWNER` row or non-owner caller), 404 |
| `list_services` | `(session, *, shop_id, include_inactive, page) → Page[ServiceRead]` | — |
| `create_service` / `update_service` | `(uow, *, shop_id, actor_user_id, [service_id,] data) → ServiceRead` | 403, 404, 409 `CONFLICT` (duplicate active name) |
| `list_public_shops` | `(session, *, q, city, page) → Page[ShopPublicSummary]` | — |
| `list_public_cities` | `(session) → list[str]` | — |
| `get_public_shop` | `(session, *, shop_slug) → ShopPublicDetail` | 404 |
| `get_me` | `(session, *, user_id) → MeRead` (with `is_platform_admin`, D94, and each membership's `shop_suspended`, D96) | 401 (user vanished) |
| `set_rating` *(internal, seed only)* | `(uow, *, shop_id, rating: Decimal \| None) → None` | 404 |

### 5.2 Look-ups for other modules (reads, nested)

| Function | Arguments → returns | Used by |
|---|---|---|
| `get_active_membership` | `(session, *, shop_id, user_id) → MembershipRecord \| None` (fresh read, D9) | `app.shared.auth.require_shop_member` (exists) |
| `list_memberships_for_user` | `(session, *, user_id, roles=None) → list[MembershipRecord]` (active only) | `get_me`; reporting owner summary (`roles={OWNER}`) |
| `get_listed_shop` | `(session, *, shop_slug) → ShopBrief \| None` (listed **and** not suspended, D96) | scheduling availability (spec 03 §4.5: 404 for unknown, unlisted or suspended) |
| `get_bookable_shop` | `(session, *, shop_id) → ShopBrief \| None` (listed, not suspended **and** ≥ 1 active service, D64, D96) | bookings T01, twice: before the account rule and again under the shop row's `FOR SHARE` (404 otherwise; spec 19 §7) |
| `get_shop_briefs` | `(session, *, shop_ids) → dict[UUID, ShopBrief]` (any listing or suspension state; `ShopBrief.is_suspended`) | bookings customer views, notifications, reporting (the owner summary leaves suspended shops out, D99) |
| `get_shop_suspension` | `(session, *, shop_id) → ShopSuspension \| None` (`suspended_at`, `reason`, `suspended_by_user_id`) | `app.shared.auth.require_shop_member` (403 `SHOP_SUSPENDED`); bookings customer actions and `allowed_actions` |
| `suspend_shop` / `reactivate_shop` | `(uow, *, shop_id, actor_user_id[, reason]) → None`, nested: reason 5–500 → `identity.lock_acting_platform_admin` (actor row `FOR SHARE`, 403) → shop row `FOR UPDATE` (404) → 409 on the wrong state → write, publish `ShopSuspensionChanged` | admin (E-64, E-65) |
| `list_shops_for_admin`, `list_shop_ids_for_admin`, `get_admin_shop_records`, `count_shops`, `count_staff_users`, `list_staff_user_ids`, `list_memberships_everywhere`, `get_shop_timezones` | admin reads across tenants (spec 19 §4) | admin, bookings (E-72's per-zone dates) |
| `get_schedule_config` | `(session, *, shop_id, for_share: bool = False) → ScheduleConfig` | scheduling (availability, slot validation); bookings T01 with `for_share=True` (D37) |
| `snapshot_services` | `(session, *, shop_id, service_ids) → list[ServiceSnapshot]` (request order) | bookings T01 (D34); 422 `service_ids.N` `invalid_reference` for unknown, inactive or other-shop ids |
| `require_eligible_member` | `(session, *, shop_id, user_id, role, field) → MemberRef` | bookings T04, T12, O4, O5; 422 `MEMBER_NOT_ELIGIBLE` |
| `list_active_member_ids` | `(session, *, shop_id, roles) → list[UUID]` (active membership **and** active account) | notifications ("SAs of the shop", `QC_REQUESTED`), bookings viewer ids |
| `get_owner_user_id` | `(session, *, shop_id) → UUID` | notifications (D26 fallback), bookings viewer ids |
| `get_member_refs` | `(session, *, shop_id, user_ids) → dict[UUID, MemberRef]` (any status; `is_active` = the membership) | bookings (`technician`, `parts_person`, `qc_inspector`), qc, inventory |
| `list_team` | `(session, *, shop_id) → list[TeamMember]` (`membership_id`, `user_id`, `full_name`, `role`, `is_active`) | reporting overview (adds `open_jobs` from bookings) |
| `get_setup_flags` | `(session, *, shop_id) → SetupFlags` (`has_services`, `has_team`, `is_listed`) | reporting overview `setup` |
| `get_shop_profile` *(P2)* | `(session, *, shop_id) → ShopPublicDetail` | calls (agent `GET …/shop`) |

### 5.3 Read port for bookings facts (`ShopActivityReader`)

`ShopRead.has_future_bookings` and `MemberRead.open_jobs` (spec 03 §3.2) are bookings data, but shops may not import bookings (spec 01 rule 3). Shops therefore declares a port and the app wires the bookings implementation at start-up:

```python
# app/modules/shops/service.py
class ShopActivityReader(Protocol):
    async def has_future_bookings(self, session: AsyncSession, *, shop_id: UUID, now: datetime) -> bool: ...
    async def count_open_jobs(self, session: AsyncSession, *, shop_id: UUID,
                              user_ids: Collection[UUID]) -> Mapping[UUID, int]: ...

def register_activity_reader(reader: ShopActivityReader) -> None: ...   # called by bookings.service.register_ports() (D89)
```

Bookings' `service.register_ports()` calls `shops.service.register_activity_reader(shop_activity_reader)`, and `app.main.wire_modules()` runs it at start-up, in tests and in the seed (D89; no import-time side effect, spec 01 rule 5). Until a reader is registered, calling it raises `RuntimeError` (fail loud in a mis-wired test, never silently report "no bookings"). The real guard for grid changes is still the `ShopGridChanging` veto; `has_future_bookings` is only the UI hint that locks the duration field (O-04).

## 6. Endpoints

Full schemas and validation: [spec 03 §3.2, §4.4, §4.5, §4.9](../03-api-contracts.md). Paths below `/api/v1/shops/{shop_id}` are shortened to `…`; every `…` route is on `shop_scoped_router()` (404 for non-members, D20). Role guards use `require_roles(*CAPABILITY_ROLES[...])`, so the routes and `GET /me` can never disagree (D66).

| operationId | Method + path | Auth · roles | Success | Pri | Screens |
|---|---|---|---|---|---|
| `shops_list_public_shops` | `GET /api/v1/public/shops` | public | 200 `Page[ShopPublicSummary]` | P0 | P-01, P-03 W1 · E-06 |
| `shops_list_public_cities` | `GET /api/v1/public/cities` | public | 200 `ItemList[string]` | P0 | P-01 · E-07 |
| `shops_get_public_shop` | `GET /api/v1/public/shops/{shop_slug}` | public | 200 `ShopPublicDetail` | P0 | P-02, P-03 · E-08 |
| `shops_get_me` | `GET /api/v1/me` | session | 200 `MeRead` | P0 | every screen · E-04 |
| `shops_create_shop` | `POST /api/v1/shops` | session (any user, D17) | 201 `ShopRead` | P0 | S-03, O-05 · E-21 |
| `shops_get_shop` | `GET …` | member (any role) | 200 `ShopRead` | P0 | O-04, S-01 · E-22 |
| `shops_update_shop` | `PATCH …` | O (`shop.manage`) | 200 `ShopRead` | P0 | O-04 · E-23 |
| `shops_replace_working_hours` | `PUT …/working-hours` | O (`shop.manage`) | 200 `ShopRead` | P0 | O-04 · E-24 |
| `shops_list_members` | `GET …/members` | O; SA (active T and PP only) | 200 `Page[MemberRead]` | P0 | O-02, SA-02 pickers, O-01, T-01 · E-25 |
| `shops_add_member` | `POST …/members` | O (`team.manage`) | 201 `MemberCreatedRead` | P0 | O-02 · E-26 |
| `shops_update_member` | `PATCH …/members/{membership_id}` | O (`team.manage`) | 200 `MemberRead` | P0 | O-02 · E-27 |
| `shops_list_services` | `GET …/services` | member | 200 `Page[ServiceRead]` | P0 | O-03 · E-28 |
| `shops_create_service` | `POST …/services` | O (`services.manage`) | 201 `ServiceRead` | P0 | O-03 · E-29 |
| `shops_update_service` | `PATCH …/services/{service_id}` | O (`services.manage`) | 200 `ServiceRead` | P0 | O-03 · E-30 |

`POST /api/v1/shops` is the only `/shops` route outside `shop_scoped_router()`. Public routes never read credentials. `GET /api/v1/public/shops/{shop_slug}/availability` is served by `scheduling` (tag `scheduling`).

## 7. Domain rules and algorithms

### 7.1 Working hours on the midnight-anchored grid (D37, D38)

Value objects (`domain/grid.py`, pure):

```python
@dataclass(frozen=True, slots=True)
class WorkingDay:
    weekday: int                 # 0 = Monday … 6 = Sunday (glossary §5; Python date.weekday())
    is_closed: bool
    opens_at: time | None        # shop-local wall clock, None when closed
    closes_at: time | None

@dataclass(frozen=True, slots=True)
class ScheduleConfig:
    shop_id: UUID
    timezone: str                # IANA name
    slot_duration_minutes: int   # 15–240, multiple of 15
    slot_capacity: int           # 1–50
    days: tuple[WorkingDay, ...] # exactly 7, index = weekday
```

Validation of a submitted week (`week_problems(days, step)`), each problem a `(field, code)` reported as `working_hours.N.<field>` where `N` is the index in the request list:

| Rule | Field · code |
|---|---|
| Exactly 7 entries | `working_hours` · `too_short` / `too_long` (schema) |
| Weekdays distinct (0–6) | `working_hours.N.weekday` · `duplicate` |
| Open day has both times | `working_hours.N.opens_at` / `.closes_at` · `missing` |
| Times are `HH:MM`, 24-hour, no seconds | schema · `value_error` |
| `minutes_of(t) % slot_duration_minutes == 0` (grid anchored at local midnight) | `working_hours.N.opens_at` / `.closes_at` · `not_on_grid` |
| `closes_at > opens_at` (overnight hours not supported; closing at midnight is not expressible) | `working_hours.N.closes_at` · `invalid_range` |

- A closed day stores `opens_at = closes_at = NULL`; times sent for a closed day are ignored.
- Because both times are on the grid and `closes_at > opens_at`, every open day has at least one full slot, and the last slot ends exactly at `closes_at`.
- Example (BK-30): 45-minute slots → 09:00 (12 × 45) and 18:00 (24 × 45) are valid, 09:30 is `not_on_grid`.
- `create_shop` validates the week against the body's own `slot_duration_minutes` in the service (as built: every problem is reported at once on exact `working_hours.N.<field>` paths, so it runs after the creation rate limit and an invalid week counts against it); `replace_working_hours` validates against the shop's current duration; `update_shop` changing the duration checks `hours_fit_grid(current days, new step)`.

### 7.2 Create a shop (`create_shop`, D17)

1. Rate limit `SHOP_CREATION_LIMIT` (10/day) with `account_limiter().hit(item, "shop-create", str(actor_user_id))` → 429 + `Retry-After` when exhausted.
2. Schema and week validation (§7.1); `timezone` must load with `zoneinfo.ZoneInfo` (422 `timezone` `value_error`); `logo_url` must be `https://…` ≤ 2048.
3. `now = utcnow()`; slug from the name (§7.3).
4. Insert the `shops` row (`rating = NULL`), its 7 `shop_working_hours` rows and the caller's `OWNER` membership (`is_active = true`, `created_by_user_id = actor`), all with `created_at = updated_at = now`.
5. Commit. Return `ShopRead` (`has_future_bookings = false`, no reader call needed).
6. The caller's other memberships are untouched (SEC-40). The shop appears in the directory only once it has an active service (D64).

### 7.3 Slugs (immutable, D68)

- `slugify(name)`: Unicode NFKD → ASCII (drop the rest) → lower-case → every run of characters outside `[a-z0-9]` becomes `-` → trim `-` → cut to 72 characters (trim a trailing `-`) → empty → `shop`. The result always matches `ck_shops_slug_format` (`^[a-z0-9]+(-[a-z0-9]+)*$`).
- Candidates `base`, `base-2`, `base-3`, …: read the taken slugs `base` / `base-%` once, take the first free one, insert inside `session.begin_nested()`; a concurrent creation that wins `uq_shops_slug` makes this one retry with the next candidate (≤ 5 retries, then 500). A name clash is **never** a 409 (spec 03 §4.9).
- The slug never changes after creation, even when the shop is renamed (public links stay valid). The seed asserts the slug it gets equals the expected one (spec 11).

### 7.4 Update a shop (`update_shop`) and the grid-change guard (D37)

1. Route guard: Owner. Service: re-check the actor is this shop's `OWNER`.
2. `SELECT … FROM shops WHERE id = :shop_id FOR UPDATE`, then `now = utcnow()`.
3. Compute the fields that **actually change** (value differs from the stored one). `slug` and `rating` are not in `ShopUpdate` (unknown field → 422). `logo_url: null` clears the logo.
4. If `slot_duration_minutes` or `timezone` changes:
   1. `await uow.publish(ShopGridChanging(shop_id, changed_fields, actor_user_id, occurred_at=now))`. The bookings handler raises 409 `CONFLICT` when the shop has a booking with `slot_start > now` and `status <> 'CANCELLED'`; the whole change rolls back.
   2. If the duration changes and the current working hours are not all on the new grid → 422 `VALIDATION_ERROR`, field `slot_duration_minutes`, code `hours_not_on_grid` (the Owner first moves the hours, then changes the duration).
5. Apply the changes, `updated_at = now`, commit, return `ShopRead` (with `has_future_bookings` from the reader).

`slot_capacity` changes never publish anything and never touch existing bookings: a slot booked above the new capacity is simply shown as full (spec 06 O1). Setting `is_listed = false` removes the shop from the directory, from public detail and availability (404) and from booking creation (404); existing bookings continue.

### 7.5 Replace working hours (`replace_working_hours`)

Lock the shop row `FOR UPDATE`; validate the 7 entries against the shop's current duration (§7.1); update the 7 rows in place by `(shop_id, weekday)`; set `shops.updated_at = now`; commit; return `ShopRead`. Always allowed: bookings already placed outside the new hours are kept, and their slots are simply no longer offered (D37). Replace semantics make the call idempotent (spec 03 §1.7). Taking the shop row lock serialises with booking creation's `FOR SHARE` (D37), so a booking is validated either entirely against the old hours or entirely against the new ones.

### 7.6 Team: list, add, edit, deactivate (D15, D18, D19)

**List** (`GET …/members`): `OWNER` sees every membership including inactive ones and the `OWNER` row. `SERVICE_ADVISOR` sees only active `TECHNICIAN` and `PARTS_PERSON` members whose account is also active (the assign pickers, spec 04 §A; as built, so the picker never offers someone `require_eligible_member` would refuse); the `role` / `is_active` filters intersect with that set (an SA asking for `QC_INSPECTOR` gets an empty page). T, PP, QC → 403. The shop's members are few, so the service loads the filtered memberships, fetches their users in one `identity.get_users_by_ids` call, sorts by (role in glossary order `OWNER`, `SERVICE_ADVISOR`, `TECHNICIAN`, `PARTS_PERSON`, `QC_INSPECTOR`; `lower(full_name)`; `membership_id`) and slices `limit`/`offset` in memory (`total` = the filtered count). `open_jobs` comes from `ShopActivityReader.count_open_jobs` for the page (bookings not `READY_FOR_PICKUP`, `COMPLETED` or `CANCELLED` where the member is technician, parts person or current QC picker).

**Add** (`add_member`):

1. Route guard Owner; service re-check; rate limit `MEMBER_CREATION_LIMIT` (30/h) keyed `"member-create", str(shop_id)` → 429.
2. `role` is a `StaffRole` (`OWNER` → 422 at the schema).
3. `existing = identity.find_user_by_email(email)` (normalised by the `Email` type, D62).
4. Existing account: if it has any membership in this shop (active or not) → 409 `CONFLICT` ("Already a member of this shop — change the role or reactivate instead"). Otherwise create **only the membership**; `password`, `full_name` and `phone` in the body are ignored (D18, SEC-21); `account_created = false`. An existing but deactivated account can be attached; it still cannot log in until reactivated.
5. New e-mail: `password` is required (422 `password` `missing`); `identity.create_user(email, full_name, password, phone)` (Argon2 — this use case holds no row lock), then the membership; `account_created = true`. The Owner hands the password over privately.
6. Membership: `role`, `is_active = true`, `created_by_user_id = actor`, clock timestamps. `uq_shop_memberships_shop_id_user_id` is the race backstop (409 `CONFLICT`).
7. Commit; return `MemberCreatedRead` (`open_jobs = 0`: a new membership cannot have assignments, since assignment FKs point at the membership).

**Edit / deactivate / reactivate** (`update_member`, body `{role?: StaffRole, is_active?: bool}`, at least one):

1. `SELECT … FROM shop_memberships WHERE id = :membership_id AND shop_id = :shop_id FOR UPDATE` → none → 404 (another shop's membership is invisible).
2. The row is the `OWNER` membership → **403 `FORBIDDEN`**, whoever asks and whatever the body (D19, SEC-15).
3. Apply only real changes (`updated_at = now`); commit; return `MemberRead` with `open_jobs`.
4. Effect is immediate on the member's next request (D9): a deactivated member gets 404 on this shop's routes, disappears from `/me`, from "SAs of the shop" and from realtime fan-out; their open bookings stay assigned (D19) and the SA moves them with `reassign-*` (P1). A role change likewise applies on the next request.

### 7.7 Service catalogue (D34, D64)

- List: `include_inactive` (default `false`), ordered by `lower(name)`, `id`.
- Create / update: `name` 1–120, `description` ≤ 1000 (nullable on PATCH), `estimated_duration_minutes` 5–10 080, `base_price` `Money` (whole rupees, nullable = "Price after inspection"), `is_active`.
- Duplicate **active** name in the same shop, case-insensitive → 409 `CONFLICT` (pre-check, backstop `uq_services_active_name`); a deactivated duplicate is allowed; reactivating into a duplicate → 409; another shop may reuse the name. A service of another shop → 404.
- Deactivation hides the service from the directory and the wizard; deactivating the last active service removes the shop from the directory (D64); existing bookings keep their snapshots (D34).

### 7.8 Public directory and shop page (D64, D68)

- **List:** shops with `is_listed` **and** `EXISTS (active service)` (served by `ix_shops_listed_city_name` + `uq_services_active_name`, spec 02 §3.2). `city` = case-insensitive exact match. `q` (≤ 100) = case-insensitive substring of the shop name, city or any active service name, with `%`, `_` and `\` escaped. Order `name`, `id`; `COUNT(*)` with the same filters. Each item's `services` = its active services `{id, name}` by name (one batched query for the page) plus `services_count`.
- **Cities:** one entry per case-insensitive city among directory shops (`GROUP BY lower(city)`, keeping one spelling), alphabetical.
- **Detail:** by slug; unknown slug or `is_listed = false` → 404. A listed shop with no active service is returned with `services: []` and `is_bookable: false` (spec 03 §4.5), so the page can say "not taking online bookings yet"; it is absent from the list and booking creation answers 404.

### 7.9 `GET /api/v1/me` and capabilities (D66, D81)

`get_me(user_id)`: the active user from `identity.get_active_user` plus the user's **active** memberships joined with their shops, sorted by shop name (case-insensitive, then `shop_id`); a pure customer gets `memberships: []`. Each item: `membership_id`, `shop_id`, `shop_name`, `shop_slug`, `role`, `capabilities`. Never inactive memberships, `password_hash` or another user's data.

| Role | `capabilities` (sorted alphabetically) |
|---|---|
| `OWNER` | `parts.manage`, `services.manage`, `shop.manage`, `team.manage` (+ `tasks.manage`) |
| `SERVICE_ADVISOR` | none (+ `tasks.manage`) |
| `PARTS_PERSON` | `parts.manage`, `stock.manage` |
| `TECHNICIAN`, `QC_INSPECTOR` | none |

`CAPABILITY_ROLES` is the single role table: `GET /me` derives `capabilities` from it, and every non-booking route guard (`shops`, `inventory`, bonus `calls`) is written as `require_roles(*CAPABILITY_ROLES[Capability.X])`, so a capability shown in the UI always matches a route the server allows (SEC-46). `tasks.manage` is included only when calling is enabled (`Settings.calling_enabled`, spec 05 "present only when the calls module is enabled"). Capabilities are hints: every route still re-checks the membership and role per request (D9).

### 7.10 Look-up rules used by other modules

- `require_eligible_member`: passes only when the user has an **active** membership with exactly the required role in this shop **and** an active account (`identity.get_active_user`). Wrong role, inactive membership or account, another shop's user or an unknown id all give 422 `MEMBER_NOT_ELIGIBLE` with one field error (`technician_user_id` or `parts_person_user_id`, code `invalid_reference`) (spec 03 §5.1, BK-21).
- `list_active_member_ids(roles)`: active memberships with those roles whose account is also active (filtered with one `identity.get_users_by_ids` call), sorted by user id for deterministic recipient lists.
- `snapshot_services`: every id must be an active service of this shop; all bad ids are reported at once (`service_ids.N`, `invalid_reference`); returns `ServiceSnapshot(service_id, name, base_price)` in request order.
- `get_schedule_config(for_share=True)`: `SELECT … FROM shops WHERE id = :shop_id FOR SHARE`, then the 7 hours rows (unlocked: every hours writer holds the shop row `FOR UPDATE` first, §7.5). This is booking creation's first lock (D37).

## 8. Events

| Event | Direction | Payload | When | Subscriber and effect |
|---|---|---|---|---|
| `ShopGridChanging` | published | `shop_id`, `changed_fields` (subset of `slot_duration_minutes`, `timezone`), `actor_user_id`, `occurred_at` | `update_shop`, after the shop row is locked `FOR UPDATE`, before anything is written, only when one of the two fields really changes | `bookings.handlers.on_shop_grid_changing` → 409 `CONFLICT` while a booking with `slot_start > occurred_at` and `status <> 'CANCELLED'` exists; the exception rolls the change back |

Published for the platform audit log (D95, spec 19 §3.3); shops never imports `audit`, which subscribes:

| Event | Payload | Published by |
|---|---|---|
| `ShopCreated` | `shop_id`, `actor_user_id` | `create_shop`, after the flush |
| `ShopUpdated` | `shop_id`, `actor_user_id`, `changes` (`{field: {from, to}}`, only the fields that really changed) | `update_shop`, only when something changed |
| `WorkingHoursReplaced` | `shop_id`, `actor_user_id` | `replace_working_hours`, only when the week changed |
| `ShopSuspensionChanged` | `shop_id`, `actor_user_id`, `suspended`, `reason` | `suspend_shop` / `reactivate_shop` |
| `MembershipAdded` | `shop_id`, `actor_user_id`, `membership_id`, `user_id`, `role` | `add_member`, after the flush |
| `MembershipRoleChanged` | `shop_id`, `actor_user_id`, `membership_id`, `user_id`, `from_role`, `to_role` | `update_member` |
| `MembershipActiveChanged` | `shop_id`, `actor_user_id`, `membership_id`, `user_id`, `is_active` | `update_member` |

Every event carries `occurred_at`. Nothing subscribed. Realtime and notification recipients are still resolved from live membership state at publish time (spec 01, D14); the membership events exist for the audit log only.

## 9. Permissions and visibility

| Capability (spec 04 RBAC A) | CUSTOMER | OWNER | SA | T | PP | QC |
|---|---|---|---|---|---|---|
| Create a shop (becomes `OWNER`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| View shop profile and hours (`GET …`) | 404 | ✅ | 👁 | 👁 | 👁 | 👁 |
| Update settings, set working hours | 404 | ✅ | 403 | 403 | 403 | 403 |
| View team | 404 | ✅ all | 👁 active T and PP only | 403 | 403 | 403 |
| Add member, change role, deactivate, reactivate | 404 | ✅ (never the `OWNER` row: 403) | 403 | 403 | 403 | 403 |
| Services: view | public directory | ✅ | 👁 | 👁 | 👁 | 👁 |
| Services: create, update, deactivate | 404 | ✅ | 403 | 403 | 403 | 403 |

404 for every `…` route when the caller has no **active** membership in `{shop_id}` (customers, other tenants, deactivated members), identical whether the shop exists or not (D20, SEC-01…SEC-03). Public routes expose only listed shops and active services, never staff, e-mails or memberships.

## 10. Errors

| Code | HTTP | When |
|---|---|---|
| `NOT_FOUND` | 404 | Non-member on any `…` route; a membership or service of another shop; unknown, unlisted or suspended slug (public detail) |
| `SHOP_SUSPENDED` | 403 | Any member on any `…` route of a suspended shop, before the role check (`require_shop_member`, D96); every shop-scoped route declares 403 |
| `FORBIDDEN` | 403 | Non-owner on owner routes; T/PP/QC listing members; **any** change to the `OWNER` membership; `suspend_shop` / `reactivate_shop` by anyone but an active platform admin |
| `CONFLICT` | 409 | Duplicate membership (active or inactive); duplicate active service name; grid change blocked by future bookings (raised by the bookings handler); suspending a suspended shop or reactivating an active one |
| `EMAIL_ALREADY_REGISTERED` | 409 | `add_member` losing the race to create the same new e-mail (from `identity.create_user`) |
| `MEMBER_NOT_ELIGIBLE` | 422 | `require_eligible_member` (called by bookings) |
| `VALIDATION_ERROR` | 422 | Schema errors; `working_hours.N.*` (`duplicate`, `missing`, `not_on_grid`, `invalid_range`); `slot_duration_minutes` `hours_not_on_grid`; `timezone`; `password` `missing` for a new member; `service_ids.N` `invalid_reference` (from `snapshot_services`) |
| `RATE_LIMITED` | 429 | Shop creation (10/day per user), member creation (30/h per shop), with `Retry-After` |

## 11. Concurrency & transactions

- Every use case in §5.1 is one transaction committed in the service. Look-ups in §5.2 never commit.
- **Shop row:** `update_shop` and `replace_working_hours` take `SELECT … FOR UPDATE` on the `shops` row first; booking creation takes `FOR SHARE` on it first (D37, via `get_schedule_config(for_share=True)`). A grid change and a booking therefore never interleave: either the booking commits first and the change is vetoed (409), or the change commits first and the booking is validated against the new grid (CON-05). No other transaction locks the shop row, and it is always the first lock of the transactions that take it, so it adds no cycle to D30's order (booking → purchase order → parts → slot counter).
- **Membership row:** `update_member` locks it `FOR UPDATE`; concurrent PATCHes serialise.
- **Suspension:** `suspend_shop` / `reactivate_shop` lock the acting admin's `users` row `FOR SHARE` (identity's `lock_acting_platform_admin`) and then the `shops` row `FOR UPDATE`, always in that order. Two admins acting on one shop queue on the shop row and the second gets 409; a concurrent revoke or deactivation of the acting admin waits for the lever, or committed first and the lever answers 403 (spec 19 §1, §7). Unlisting (`update_shop`) and suspension both write the shop row, so booking creation's `FOR SHARE` sees either the closed shop (404) or commits first.
- **Inserts:** races are settled by `uq_shops_slug` (retry with the next suffix in a savepoint), `uq_shop_memberships_shop_id_user_id` and `uq_services_active_name` (409 `CONFLICT`), `uq_users_email` (409 `EMAIL_ALREADY_REGISTERED`).
- `add_member` runs Argon2 (new accounts) without holding any row lock.
- Clock: one `utcnow()` per use case, read after the row lock.

## 12. Tests

Spec 12 / spec 04 IDs this module must make pass: **SEC-01 ★**, **SEC-02**, **SEC-03** (membership dependency on every shop route), **SEC-05** (management matrix), **SEC-13**, **SEC-14** (deactivate/reactivate effect), **SEC-15** (`OWNER` membership immutable; no second owner), **SEC-17** (mass assignment on member PATCH), **SEC-21** (existing e-mail; duplicate add → 409), **SEC-27** (shop- and member-creation limits), **SEC-40** (any user creates a shop, owns only it), **SEC-46** (`/me` capabilities), **API-12 ★** (member creation with `.test` e-mails), **BK-16** (directory), **BK-26** (shop without active service — see Open question 2), **BK-27** (slug routes), **BK-29** (grid change blocked — with bookings), **BK-30** (grid validation of hours), **CON-05** *(P1)*, **SEED-01**, **SEED-07 ★**, **SEED-08**, **SEED-19** (membership half), **WEB-09** (the `capabilities` it relies on), **DEP-02**, **DEP-07**.

Proposed additional tests:

| ID (proposed) | Test |
|---|---|
| SHP-01 | Slugs: "Lahore Auto Care" → `lahore-auto-care`; a second shop with the same name → `lahore-auto-care-2`; an Urdu-only name → `shop`; renaming never changes the slug |
| SHP-02 | Shop creation is atomic: an invalid working-hours row → 422 and no `shops`, `shop_working_hours` or `shop_memberships` row exists; a valid one creates exactly 1 + 7 + 1 rows |
| SHP-03 | Working-hours validation codes: duplicate weekday, missing times, `closes_at ≤ opens_at`, off-grid time, closed day with times (accepted, stored NULL), 6 or 8 entries |
| SHP-04 | Duration change without future bookings: hours on the new grid → 200; hours off it → 422 `hours_not_on_grid`; with a future booking → 409 even when the hours would fit |
| SHP-05 | Services: duplicate active name (case-insensitive) → 409; a deactivated duplicate is allowed; reactivating it → 409; the same name in another shop → 201 |
| SHP-06 | Members list: Owner sees all incl. inactive and `OWNER`; SA sees only active T and PP; T/PP/QC → 403; order role → name |
| SHP-07 | `open_jobs` counts bookings where the member is technician, parts person or current QC picker, excluding `READY_FOR_PICKUP`, `COMPLETED`, `CANCELLED` |
| SHP-08 | Cities list: one entry per case-insensitive city of directory shops only (unlisted or service-less shops excluded) |
| SHP-09 | `/me` excludes inactive memberships, sorts by shop name, and capabilities equal `CAPABILITY_ROLES` for each role; `tasks.manage` absent while calling is disabled |
| SHP-10 | Route guards and capabilities agree: every route guarded with `CAPABILITY_ROLES[c]` returns 403 for exactly the roles whose `/me` lacks `c` (generated) |

## 13. Implementation checklist

1. Rename the internal schema `MembershipRead` in `shops/schemas.py` to `MembershipRecord` (spec 03 reserves `MembershipRead` for the `/me` item); `app.shared.auth.require_shop_member` keeps using `.id` and `.role` (no behaviour change).
2. `domain/capabilities.py`, `domain/grid.py`, `domain/slugs.py` with unit tests (BK-30 domain half, SHP-01).
3. Schemas (requests with `extra="forbid"`; `HH:MM` time fields; `Money`, `Email`, `Phone`).
4. Repositories (+ constraint-name mapping for the three unique keys).
5. `events.py` (`ShopGridChanging`).
6. Service: look-ups of §5.2 (needed by auth, scheduling and bookings) → public directory → `create_shop` → `update_shop` (+ veto event) → `replace_working_hours` → team → services → `get_me` → `set_rating`; `ShopActivityReader` + `register_activity_reader`.
7. Routers: `public_router`, `me_router` (tag `shops`, function `get_me` → `shops_get_me`), `shops_router`, `shop_router`; guards from `CAPABILITY_ROLES`.
8. Export `routers` from `router.py`; `wire_modules()` includes them (D89, `app/main.py` is not edited). The bookings side — `register_ports()` registering `shop_activity_reader`, and the `ShopGridChanging` handler — is plain reads of bookings' own tables, so it is built in PH1 together with this module (the veto has nothing to block until PH2 creates bookings).
9. Tests of §12, builders `make_shop`, `add_member`, `make_team`, `make_services` (spec 12 §4.3); `make gen-api`.

## 14. Dependencies (specs)

[17-decisions.md](../17-decisions.md) (D9, D15–D20, D26, D34, D37, D38, D41, D55, D56, D60, D62–D64, D66, D68, D69, D80, D81, D86, D87, D89), [18-glossary.md](../18-glossary.md) (§2, §5, §7, §7.1, §9, §10, §14), [01-architecture.md](../01-architecture.md) (rule 3, rule 8, D37 guard), [02-data-model.md](../02-data-model.md) §3.2–§3.5, §7, [03-api-contracts.md](../03-api-contracts.md) §1.3, §3.2, §4.4, §4.5, §4.9, [04-auth-and-security.md](../04-auth-and-security.md) (RBAC A, capabilities, staff accounts), [06-workflows.md](../06-workflows.md) O1–O5, [10-screens.md](../10-screens.md) P-01, P-02, S-01, S-03, O-02–O-05, [11-seed-data.md](../11-seed-data.md) (Phase A, Phase R), [12-quality-and-testing.md](../12-quality-and-testing.md). Uses `modules/identity.md`. Used by `modules/scheduling.md`, `modules/bookings.md` and every module behind `require_shop_member`.

## Open questions

1. ✅ **Resolved by D86: bookings facts on shops routes.** `ShopActivityReader` + `shops.service.register_activity_reader()` (§5.3), implemented by `bookings.service.shop_activity_reader` and registered through bookings' `register_ports()`, which `wire_modules()` calls (D89); spec 01 describes the mechanism (its open question 10).
2. ✅ **Resolved by D64 (amended): shop without an active service — public detail.** 200 with `services: []` and `is_bookable: false` (spec 03 §4.5); spec 12 BK-26 now expects the same, and booking creation answers 404.
3. ✅ **Resolved in spec 10: slug clash.** S-03 now says a taken slug is never an error (`-2`, `-3` …, spec 03 §4.9).
4. ✅ **Resolved in spec 04: where the capability table lives.** Spec 04 ("Capabilities") now places it in the shops domain (`shops/domain/capabilities.py`), with route guards reading `CAPABILITY_ROLES`.
5. ✅ **Resolved by D87 (planned, P1): QC picker deactivated mid-inspection.** The bookings operation `REASSIGN_QC_INSPECTOR` will move the pick; until it ships, the Owner reactivates the inspector. `open_jobs` counts the current pick, so O-02 can warn before deactivating.
6. **`tasks.manage` switch.** "Calls module enabled" is read as `Settings.calling_enabled` (all `CALL_PROVIDER_*` set). Confirm with spec 05.
7. **Switcher city.** `MembershipRead` has no `shop_city` / `shop_timezone` (spec 03 Open question 3); S-01 wants the city. Not added here; `ShopScope` loads `GET /api/v1/shops/{shop_id}`.

## Proposed glossary additions

| Kind | Name | Meaning |
|---|---|---|
| Enum (code, not stored) | `Capability` in `app.modules.shops.domain.capabilities`, with `CAPABILITY_ROLES` and `capabilities_for()` | The glossary §2.4 values as a `StrEnum`; the one role table behind `/me` and the route guards |
| Value objects | `WorkingDay`, `ScheduleConfig` (`shops.domain.grid`) | Pure D37 inputs shared with scheduling |
| Port | ✅ merged (glossary §7.1a, D86) — `ShopActivityReader`, `shops.service.register_activity_reader()`; bookings' implementation `bookings.service.shop_activity_reader` | Read access to bookings facts without an upward import |
| Internal schemas | `MembershipRecord` (renamed from today's internal `MembershipRead`), `ShopBrief`, `ServiceSnapshot`, `TeamMember`, `SetupFlags` | Return types of the §5.2 look-ups |
| Service functions | `get_bookable_shop`, `get_shop_briefs`, `get_member_refs`, `get_setup_flags`, `set_rating` (internal), `get_shop_profile` (P2), plus the use-case names of §5.1 | Additions to spec 01's shops catalogue |
| Limiter identifiers | `"shop-create", <user_id>`, `"member-create", <shop_id>` | Keys in the shared `account_limiter()` storage |
