# 19 — Platform administration (super admin) and the audit log

## Purpose

BayFlow is a multi-tenant SaaS: shops are tenants, and someone has to run the platform. This spec
defines the **platform admin** ("super admin") role, the platform-wide **audit log**, **shop
suspension**, the admin API (E-61…E-75) and the admin console (screens A-01…A-08). Decisions
D94–D100 (spec 17) summarise it; this file is authoritative for the details. Added on 2026-10-10 at
the owner's request; the brief does not ask for it, so it is P1 and never blocks a P0 path.

## 1. Roles and principles

| | Rule |
|---|---|
| **Who** | A platform admin is a BayFlow operator: a `users` row with `is_platform_admin = true` (D94). It is **not** a shop role (`MembershipRole` keeps its five values, D15). A platform admin may also hold shop memberships; each hat is used separately. |
| **How one is made** | Never by sign-up. The first admin comes from `python -m app.scripts.create_platform_admin --email … --full-name …` (password from the `PLATFORM_ADMIN_PASSWORD` environment variable or a prompt; idempotent: an existing user is promoted, nothing else changes) or from the seed's demo account (§8). After that, admins grant or revoke the flag in the console (E-70/E-71). |
| **What "full control" means** | Read everything across tenants (shops, users, bookings with their timelines, the audit log, platform KPIs) and use the platform's levers: suspend or reactivate a shop, deactivate or reactivate any account, grant or revoke platform admin. Tenants' own data (bookings, estimates, stock) is changed by tenants, never by an admin silently (least privilege): there is no impersonation, no booking edit and no hard delete (spec 02: deactivate, never delete). |
| **Safeguards** | No admin can revoke their own admin flag or deactivate themselves (403 `FORBIDDEN`). The last active platform admin can be neither revoked nor deactivated (409 `CONFLICT`, "BayFlow needs at least one active platform admin."). Granting requires an active account (422 `VALIDATION_ERROR`, field `path.user_id`, code `inactive_account`). Every admin write takes a reason where it restricts someone (suspend, deactivate). Every lever re-checks, under row locks, that the acting admin is still an active platform admin (403 otherwise), so an admin revoked or deactivated by a concurrent request cannot act: the account levers lock the target and every active admin `FOR UPDATE` in one statement (`id` order); the shop levers lock the acting admin's row `FOR SHARE` before the shop row (§7). |
| **Accountability** | Every admin write, and every admin read of a person's or a booking's detail (A-05, A-07), writes an audit event (D95). The audit log is append-only: no API changes it and a database trigger rejects `UPDATE` and `DELETE` on `audit_events`. Because those reads write on `GET`, the admin API refuses cross-site requests (D98, §4). |

## 2. Shop suspension (D96)

A platform admin suspends a shop with a reason (5–500 characters); reactivation clears it. While a
shop is suspended:

| Surface | Behaviour |
|---|---|
| Public directory, shop detail, availability, booking creation (E-06…E-10) | The shop is treated exactly like an unlisted one: absent from lists and cities, 404 on detail, availability and `POST /bookings`. A booking already past the unlocked check re-checks after taking the shop row `FOR SHARE` and gets the same 404 (§7). |
| Staff routes (everything behind `require_shop_member`, incl. reporting's overview) | 403 `SHOP_SUSPENDED` for every member, the Owner included, before the role check; non-members keep their 404. Detail: "This shop is suspended. Contact BayFlow support." Every shop-scoped route declares 403 in OpenAPI. |
| `GET /api/v1/me` | Each membership gains `shop_suspended: boolean` (`MembershipRead` is flat, spec 03 §3.2), so the POS can show the suspended state without calling a blocked route. Internally the shops read model `ShopBrief` carries `is_suspended`. |
| `GET /api/v1/me/owner-summary` | The suspended shop is left out (D99); `/me` is where the web shows it. |
| Customer routes (`/me/bookings…`) | Reads keep working. Actions return 403 `SHOP_SUSPENDED`, except `cancel`, so a customer is never stuck with a booking at a closed shop; the customer's `allowed_actions` hold `cancel` only (when the state machine allows it). |
| Notifications and realtime | Unchanged (D99): rows are still written and pushed to the shop's staff (a customer's `cancel` reaches its Service Advisors), and `/me/notifications` and the realtime ticket are not shop routes, so they keep working. |
| Data | Nothing is deleted or changed: bookings, stock and memberships stay as they are and resume on reactivation. |

Columns (spec 02): `shops.suspended_at`, `shops.suspended_reason`, `shops.suspended_by_user_id`
(FK `users`, `RESTRICT`), all null or all set (`ck_shops_suspension_complete`). Suspending a
suspended shop or reactivating an active one is 409 `CONFLICT`.

## 3. The audit log (D95)

### 3.1 Table `audit_events` (owned by the new `audit` module)

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `uuid` | no | PK |
| `occurred_at` | `timestamptz` | no | The action's clock instant (D63) |
| `category` | `varchar(32)` | no | `AUTH`, `USER`, `SHOP`, `MEMBERSHIP`, `BOOKING`, `ADMIN` (`AuditCategory`; D29: a named CHECK, never a native enum type) |
| `action` | `varchar(64)` | no | Dotted, lower snake case, from the catalogue below (e.g. `shop.suspended`); CHECK `ck_audit_events_action_format` (`^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`) |
| `summary` | `varchar(300)` | no | One human sentence, no secrets (e.g. "Areeba Hashmi suspended Raza Auto Works") |
| `actor_user_id` | `uuid` | yes | FK `users` `RESTRICT`; null for anonymous and system events |
| `actor_role` | `varchar(32)` | yes | `PLATFORM_ADMIN`, a `MembershipRole`, `CUSTOMER`, `SYSTEM` or `ANONYMOUS` (`AuditActorRole`, CHECK); null when no single role applies (§3.3) |
| `shop_id` | `uuid` | yes | FK `shops` `RESTRICT`; the tenant the event belongs to |
| `target_type` | `varchar(32)` | yes | `USER`, `SHOP`, `MEMBERSHIP`, `BOOKING` (`AuditTargetType`, CHECK) |
| `target_id` | `uuid` | yes | No FK (polymorphic) |
| `target_label` | `varchar(200)` | yes | What a human recognises: a booking reference, a shop name, an e-mail |
| `metadata` | `jsonb` | no | Default `{}`, always an object (CHECK `ck_audit_events_metadata_object`); e.g. `{reason}`, `{from_status, to_status}`, `{changes: {field: {from, to}}}`. Never a password, token or hash. |
| `ip` | `inet` | yes | `app.core.security.client_ip` of the request (trusted-proxy rules of the rate limiter) |
| `user_agent` | `varchar(255)` | yes | Truncated |
| `request_id` | `varchar(64)` | yes | The `X-Request-ID` (spec 03 §1.8) |

Indexes: `(occurred_at DESC, id DESC)`, `(shop_id, occurred_at DESC)`, `(actor_user_id,
occurred_at DESC)`, `(category, occurred_at DESC)`, `(target_type, target_id)`. Trigger
`trg_audit_events_append_only` raises on `UPDATE` and `DELETE` (it reuses the baseline's
`forbid_mutation()`; `TRUNCATE` is not a row event, so test cleanup still works). There is no
`created_at` or `updated_at`: a row is never updated, and `occurred_at` is its only time. Migration
revision `339df51b764d`. Retention is open (spec 16).

### 3.2 How rows are written

- **Event driven.** Modules publish domain events on the bus (spec 01 "Event bus"); the `audit`
  module's handlers turn each into one row **in the same transaction**, so the row commits
  together with the change or not at all. Modules never import `audit`.
- **Request context.** The HTTP middleware puts the client IP, user agent and request ID in context
  variables (`app.core`); the audit handlers read them. Scripts and the seed have none (nulls).
- **Failed logins.** `login` publishes `LoginFailed` / `LoginRateLimited` and commits that
  transaction (which holds nothing else) before raising, so the attempt is recorded although the
  login fails. The e-mail is stored lower-cased in `metadata.email`. The per-IP slowapi ceiling's
  refusals (spec 04) are not audited: they answer 429 before the identity service runs.
- **Wizard sign-ins (D100).** The booking wizard's cases C/D sign in through identity's
  `sign_in_for_booking`: a success publishes `LoginSucceeded` in the booking's transaction (so the
  row is lost when the booking fails later, e.g. 409 `SLOT_FULL`, which is accepted); a wrong
  password or inactive account (409) and a blocked account (429) publish `LoginFailed` /
  `LoginRateLimited` in a short transaction of their own, on a separate session, committed before
  the error is raised, so the attempt survives the booking's rollback and nothing else commits.
- **Logout** reads the Bearer token or else the cookie leniently (never rejecting) and publishes
  `LoggedOut` only for an active user. Recording is best effort: any failure is logged (without
  the token), rolled back, and the route still answers 204 with the cookie expired.
- **Booking activity** comes from the existing `BookingActionApplied` event: one row per
  transition or operation, so the admin sees all tenants' activity in one place. `booking_events`
  stays the booking's own history (D22); the two are written in the same transaction.

### 3.3 Catalogue

| Category | Action | Published by | Actor (`actor_role`) | Target | Metadata |
|---|---|---|---|---|---|
| `AUTH` | `auth.login_succeeded` | identity `LoginSucceeded` (login; wizard case C, D100) | the user (null: a user's role is per shop) | `USER` | — |
| `AUTH` | `auth.login_failed` | identity `LoginFailed` (login; wizard case D) | none (`ANONYMOUS`) | — | `{email}` |
| `AUTH` | `auth.login_rate_limited` | identity `LoginRateLimited` (per-account limiter only) | none (`ANONYMOUS`) | — | `{email}` |
| `AUTH` | `auth.logged_out` | identity `LoggedOut` (when the Bearer token or cookie names an active user) | the user (null) | `USER` | — |
| `AUTH` | `auth.owner_registered` | identity `OwnerRegistered` | the new user (null) | `USER` | — |
| `USER` | `user.customer_created` | identity `CustomerAccountCreated` (booking wizard) | the new user (`CUSTOMER`) | `USER` | — |
| `USER` | `user.deactivated` / `user.reactivated` | identity `UserActiveChanged` | admin (`PLATFORM_ADMIN`); none (`SYSTEM`) from the seed | `USER` | `{reason}` (deactivate by an admin) |
| `USER` | `user.platform_admin_granted` / `…_revoked` | identity `PlatformAdminChanged` | admin (`PLATFORM_ADMIN`); none (`SYSTEM`) from `create_platform_admin` | `USER` | — |
| `SHOP` | `shop.created` | shops `ShopCreated` | the owner (`OWNER`) | `SHOP` | — |
| `SHOP` | `shop.updated` | shops `ShopUpdated` | the owner (`OWNER`) | `SHOP` | `{changes}` (only changed fields) |
| `SHOP` | `shop.working_hours_replaced` | shops `WorkingHoursReplaced` | the owner (`OWNER`) | `SHOP` | — |
| `SHOP` | `shop.suspended` / `shop.reactivated` | shops `ShopSuspensionChanged` | admin (`PLATFORM_ADMIN`) | `SHOP` | `{reason}` (suspend) |
| `MEMBERSHIP` | `membership.added` | shops `MembershipAdded` | the owner (`OWNER`) | `MEMBERSHIP` | `{role, member_email}` |
| `MEMBERSHIP` | `membership.role_changed` | shops `MembershipRoleChanged` | the owner (`OWNER`) | `MEMBERSHIP` | `{from, to}` |
| `MEMBERSHIP` | `membership.deactivated` / `…reactivated` | shops `MembershipActiveChanged` | the owner (`OWNER`) | `MEMBERSHIP` | — |
| `BOOKING` | `booking.<action slug>` (e.g. `booking.approve_estimate`) | bookings `BookingActionApplied` | the actor (the event's role: `OWNER`, a staff role, `CUSTOMER` or `SYSTEM`) | `BOOKING` (label = reference) | `{from_status, to_status, version}` (+ `note` when set) |
| `ADMIN` | `admin.user_viewed`, `admin.booking_viewed` | admin module (E-67, E-73) | admin (`PLATFORM_ADMIN`) | `USER` / `BOOKING` | — |
| `ADMIN` | `admin.audit_exported` | admin module (E-75) | admin (`PLATFORM_ADMIN`) | — | `{filters, rows}` |

The events live in `identity/events.py` (`LoginSucceeded`, `LoginFailed`, `LoginRateLimited`,
`LoggedOut`, `OwnerRegistered`, `CustomerAccountCreated`, `UserActiveChanged`,
`PlatformAdminChanged`) and `shops/events.py` (`ShopCreated`, `ShopUpdated`,
`WorkingHoursReplaced`, `ShopSuspensionChanged`, `MembershipAdded`, `MembershipRoleChanged`,
`MembershipActiveChanged`). Summaries are one line (whitespace collapsed), cut to 300 characters,
labels to 200.

## 4. API (E-61…E-75, tag `admin`, operation IDs `admin_*`)

All routes are under `/api/v1/admin`, behind two router-level dependencies, in this order:

1. `refuse_cross_site_requests` (D98): a request whose `Sec-Fetch-Site` header is present and is
   not `same-origin` or `none` is 403 `FORBIDDEN` ("Admin requests must come from the BayFlow
   app.") before anything else runs. `SameSite=Lax` still sends the cookie on a cross-site
   top-level GET, and E-67, E-73 and E-75 write audit rows on GET. The web calls the API
   same-origin through the Vercel rewrite (D7); a request without the header (curl, Swagger,
   tests, server-to-server) passes.
2. `require_platform_admin` (401 when not logged in, 403 `FORBIDDEN` when the user is not a
   platform admin).

Every route declares 401 and 403. Lists are `Page[T]` (spec 03 §1.6).

| ID | Method and path | Notes |
|---|---|---|
| E-61 | `GET /overview` | `PlatformOverviewRead`: shop counts (total, active, suspended, listed, new in 30 days); user counts (total, customers, staff, platform admins, inactive, new in 30 days); bookings (today, last 7 and 30 days, open, completed and cancelled in 30 days, open per `StatusPhase`); bookings per day for 14 days (shop time zone, D38); top 5 shops by bookings in 30 days; the 10 latest audit events |
| E-62 | `GET /shops` | Filters `q` (name, slug, city, owner e-mail), `status` (`ACTIVE`, `SUSPENDED`), `listed`, `city`; sort `-created_at` (default), `name`, `-bookings_30d`. Row: shop ref, city, created_at, is_listed, suspension, owners `[{name, email}]`, active members, bookings in 30 days |
| E-63 | `GET /shops/{shop_id}` | Profile, suspension (`at`, `reason`, `by`), members by role, booking counts by phase, the 10 latest bookings, the 10 latest audit events of the shop |
| E-64 | `POST /shops/{shop_id}/suspend` | Body `{reason}` (5–500). 409 when already suspended. Returns E-63's body |
| E-65 | `POST /shops/{shop_id}/reactivate` | 409 when not suspended. Returns E-63's body |
| E-66 | `GET /users` | Filters `q` (name, e-mail, phone), `kind` (`CUSTOMER` = no active membership, `STAFF`, `PLATFORM_ADMIN`), `status` (`ACTIVE`, `INACTIVE`); sort `-created_at` (default), `name`, `-last_login_at`. Row: id, name, e-mail, phone, is_active, is_platform_admin, created_at, last_login_at, memberships `[{shop ref, role, is_active}]` |
| E-67 | `GET /users/{user_id}` | Row + bookings as customer (count and 10 latest) + the 10 latest audit events by or about the user. Writes `admin.user_viewed` |
| E-68 | `POST /users/{user_id}/deactivate` | Body `{reason}` (5–500). Self → 403; last active admin → 409; already inactive → 409. The user's tokens stop working at their next request (D9). Returns E-67's body (`AdminUserDetail`) without writing `admin.user_viewed`, like E-69…E-71 |
| E-69 | `POST /users/{user_id}/reactivate` | Already active → 409 |
| E-70 | `POST /users/{user_id}/grant-platform-admin` | Inactive account → 422 `VALIDATION_ERROR` (field `path.user_id`, code `inactive_account`); already admin → 409 |
| E-71 | `POST /users/{user_id}/revoke-platform-admin` | Self → 403; last active admin → 409; not an admin → 409 |
| E-72 | `GET /bookings` | All tenants. Filters `q` (reference, plate, customer name or e-mail), `shop_id`, `status` (repeatable), `date_from`/`date_to` (inclusive slot dates in each shop's own zone; `date_from` after `date_to` → 422 `query.date_to`); sort `-slot_start` (default), `slot_start`, `-created_at` |
| E-73 | `GET /bookings/{booking_id}` | The staff projection (no `allowed_actions`: read-only) and its events. Writes `admin.booking_viewed` |
| E-74 | `GET /audit-events` | Filters `category` (repeatable), `action`, `actor_user_id`, `shop_id`, `target_type`, `target_id`, `from` (inclusive), `to` (exclusive; aware timestamps, `from` ≥ `to` → 422 `query.to`), `q` (summary and target label); sort `-occurred_at` (default), `occurred_at` |
| E-75 | `GET /audit-events/export` | `text/csv; charset=utf-8` (no BOM, header row, CRLF, RFC 4180 quoting; cells starting with `=`, `+`, `-`, `@`, a tab or a carriage return prefixed with `'` against CSV injection; the header is never prefixed), `Content-Disposition: attachment; filename="bayflow-audit-<UTC instant>.csv"`, same filters, at most 10 000 rows (newest first). The rows are read first, then `admin.audit_exported` is committed, so an export never contains its own row |

`GET /api/v1/me` (E-04) adds `is_platform_admin` and, per membership, `shop_suspended` (§2). `GET
/api/v1/me/owner-summary` leaves suspended shops out (D99). New error code: `SHOP_SUSPENDED` (403,
glossary §10), declared on every shop-scoped route and on every customer action but `cancel`.

## 5. Console (screens A-01…A-08, route group `(admin)`, path `/admin`)

The app's one design language (D101, `apps/web/DESIGN.md`) with its own shell: the light 64 px app
bar of the POS (sidebar toggle, the logo with a dark "Platform admin" pill, the account menu) and a
collapsible side nav (Overview, Shops, Users, Bookings, Audit log); page titles read "{Page} ·
Platform admin · BayFlow". Only platform admins see it; anyone else gets `ForbiddenState` ("This
area is for BayFlow platform admins."). Logging in as a platform admin without memberships lands on
`/admin`; one with memberships gets "Platform admin" in the public header's account menu.

| ID | Route | Content |
|---|---|---|
| A-01 | `/admin` | KPI tiles (shops, users, bookings today, open bookings), bookings per day (14 days), open bookings by phase, top shops, suspended shops needing attention, latest audit events |
| A-02 | `/admin/shops` | Search and filters (status, listed, city); table with status badges; row → A-03 |
| A-03 | `/admin/shops/:shopId` | Profile, owners and team, booking counts by phase, latest bookings, shop audit trail; **Suspend** (dialog with a required reason and the consequences listed) / **Reactivate** |
| A-04 | `/admin/users` | Search and filters (kind, status); table with role chips; row → A-05 |
| A-05 | `/admin/users/:userId` | Profile, memberships, bookings as customer, the user's audit trail; **Deactivate** (reason, warns when the user is a shop's only active owner) / **Reactivate**; **Grant / Revoke platform admin**; self and last-admin cases disabled with the reason shown |
| A-06 | `/admin/bookings` | Search and filters (shop, status, dates); table; row → A-07 |
| A-07 | `/admin/bookings/:bookingId` | Read-only booking: status, customer, vehicle, services, estimate total, the full timeline |
| A-08 | `/admin/audit` | Filters (category, shop, actor, period, text), newest first, a detail sheet with the metadata, and **Export CSV** |

Every destructive action uses an `AlertDialog` with a reason field and a toast on success; every
list has loading skeletons, an empty state and an error state.

Built (2026-10-10, on the mock store of D102): A-01's "Open bookings" leaves completed bookings out,
open bookings per phase are labelled rows (not a colour-only bar) and the 14-day chart has a table
twin; the suspend and deactivate dialogs list "What happens" above a required reason with a live
counter, and every action dialog shows an API refusal inside itself; A-05's blocked actions say why
(self, last admin, inactive); A-06 flags a From date after To inline; A-07 says the view is audited; A-08's detail
sheet adds a security note, the raw JSON and "Copy JSON".

## 6. Module placement (spec 01, D97)

- `audit` (new): owns `audit_events`; `handlers.py` subscribes to the events in §3.3;
  `service.py` exposes list and count reads. It sits in the top layer with notifications and
  reporting: `notifications | reporting | audit`.
- `admin` (new): owns no table; its router serves E-61…E-75 and its service composes the read and
  write ports of identity, shops, bookings and audit. It is the new top layer, above everything.
- `MODULES` (D89) becomes `identity, shops, scheduling, inventory, qc, estimates, bookings,
  notifications, reporting, audit, admin, calls`.
- `app.shared.auth` gains `require_platform_admin` (`PlatformAdminDep`) and
  `refuse_cross_site_requests` (D98), checks suspension in `require_shop_member` (shops read port
  `get_shop_suspension`), and `shop_scoped_router()` declares 403.
- identity adds `lock_acting_platform_admin` (the acting admin's row `FOR SHARE`, 403 unless an
  active platform admin), which the shops levers call before locking the shop row, and
  `sign_in_for_booking` (D100), which the bookings wizard calls for cases C/D.

## 7. Edge cases

| Case | Behaviour |
|---|---|
| An admin who is also an Owner | Uses `/admin` and the POS separately; suspending their own shop locks their POS too |
| Deactivating a shop's only active owner | Allowed; A-05 warns first. The shop keeps working for its other staff |
| Two admins act on the same shop at once | Each write locks the row (`FOR UPDATE`); the second gets 409 (already suspended / not suspended) |
| An admin is revoked or deactivated while their lever runs | The lever re-reads the admin under a lock (§1): a shop lever holds the admin's row `FOR SHARE` before the shop row, so the revoke waits for it, or committed first and the lever answers 403; the account levers lock the target and all active admins together, and two admins demoting each other leave one 200 and one 409 |
| A booking races a suspension or an unlisting | Both write the shop row; the wizard takes it `FOR SHARE` and checks bookability again under that lock: closed first → 404 and everything rolls back (a case-B account too); booking first → it commits and the suspension follows (the customer may still `cancel`) |
| A wrong password in the booking wizard | 409 `EMAIL_ALREADY_REGISTERED`; `auth.login_failed` is committed on its own (D100) |
| Logout while the audit write fails | 204 with the cookie expired; the failure is logged and rolled back |
| A link on another site to an admin URL | 403 `FORBIDDEN` from the Fetch Metadata check (D98); nothing is read or written |
| An admin is deactivated by another while signed in | Their next request is 401 (D9) and the console sends them to `/login?reason=expired` |
| Unknown IDs | 404 `NOT_FOUND` as everywhere |
| CSV with commas, quotes, newlines or formula prefixes | RFC 4180 quoting; formula prefixes neutralised |

## 8. Seed and demo (D52, spec 11)

The seed adds the platform admin **Areeba Hashmi**, `admin@bayflow.test`, password
`BayFlow@2026`, no memberships, listed with the other demo accounts on the login page and in the
README.

## 9. Tests (spec 12)

- Authorization: every E-61…E-75 route is 401 anonymous and 403 for each shop role and customers;
  cross-site and same-site requests are 403 and write nothing, while `same-origin`, `none` and no
  header pass (D98); every route that can answer 403 declares it in OpenAPI.
- Safeguards: self-revoke, self-deactivate, last-admin revoke and deactivate, double suspend and
  reactivate, grant to an inactive account; lock-gate races (two admins demoting each other, two
  admins suspending one shop, a revoke racing its admin's suspension in both orders, a booking
  racing a suspension or an unlisting).
- Suspension: every surface in §2, incl. customer `cancel` still allowed, and reactivation restoring
  access.
- Audit: one row per catalogue action in the same transaction (a rolled-back action leaves none);
  failed and rate-limited logins persist, from login and from the wizard (D100); a wizard sign-in
  is recorded with its booking and lost with a failed one; logout answers 204 when recording
  fails; the append-only trigger rejects `UPDATE` and `DELETE`; request context captured; no
  secrets in metadata.
- CSV export: quoting, formula neutralisation and the 10 000-row cap.
- Web: the console's guards, lists, dialogs and the mock data flows.

## Dependencies

17 (D94–D100), 01, 02, 03, 04, 10, 11, 12, 16, 18.
