# Module: audit

**Status:** Draft — built with spec 19 (2026-10-10)
**Package:** `app.modules.audit`
**Owns tables:** `audit_events` (spec 19 §3.1, spec 02 §3.22)
**Priority:** P1 (D36, D95): it never blocks a P0 path, but every core action writes its row in its own transaction once the module is wired.

## Purpose

One place to answer "who did what, where and when" across every tenant (D95): an append-only log of sign-ins (failed and rate-limited ones included), account levers, shop and team changes, every booking transition and operation, and the platform admin's reads of a person's or a booking's detail. Spec 19 §3 is authoritative; this file records how the module is built.

Nobody calls this module to log something: like `notifications`, it subscribes to the domain events the other modules already publish (spec 01 "Event bus") and writes one row per event **in the publisher's transaction**, so a row commits with the change or not at all. The only caller is the `admin` module, for the three `admin.*` entries nothing below it may publish (spec 19 §3.3). `booking_events` stays each booking's own history (D22); the two are written in the same transaction.

## In scope

- **P1:** the `audit_events` table with its five indexes and the append-only trigger `trg_audit_events_append_only`; one handler per catalogue event (16 events of identity, shops and bookings); the request context (IP, user agent, request id) on every row; the reads behind E-61, E-63, E-67, E-74 and the E-75 export iterator.

## Out of scope

Any HTTP route (the admin module serves E-74 and E-75); updating, deleting or archiving rows (append-only, spec 02 §8); a retention policy (open, spec 16 C.1); per-tenant audit views for Owners; push or e-mail alerts; logging reads other than E-67 / E-73 / E-75; the per-IP slowapi ceilings' refusals (they answer 429 before the identity service runs, so `auth.login_rate_limited` records the per-account limiter only, spec 19 §3.2).

## Key decisions

| D | What it means here |
|---|---|
| D95 | Append-only `audit_events`, rows written by event handlers in the same transaction; a trigger rejects `UPDATE` / `DELETE`. |
| D97 | Top layer next to `notifications` and `reporting` (`notifications | reporting | audit`); it may import every module below; only `admin` imports it. `MODULES` lists it after `reporting`, so its handlers run after the notifications handlers. |
| D29, D74 | `category`, `actor_role` and `target_type` are stored enums (`AuditCategory`, `AuditActorRole`, `AuditTargetType` in `app.shared.enums`) rendered as `VARCHAR(32)` + one named CHECK each. |
| D63 | `occurred_at` is the event's `occurred_at`, i.e. the action's single clock instant; there is no `created_at` (spec 19 §3.1). |
| D89, D90 | `handlers.register(bus)` is the only wiring; handlers write rows only and queue nothing after commit, so the seed and scripts (no `app_state`) behave exactly like requests, minus the request context. |
| D9 | Names in summaries are resolved at write time through `identity.service.get_users_by_ids` and `shops.service.get_shop_briefs`; the read side shows today's names (`actor_name`, `shop_name`). |
| D62 | Failed and rate-limited sign-ins store the normalised, lower-cased e-mail in `metadata.email`. |

## Files

| File | Contents |
|---|---|
| `models.py` | `AuditEvent` (`audit_events`): CHECKs `ck_audit_events_category`, `_actor_role`, `_target_type` (enums), `_action_format` (`^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`), `_metadata_object` (`jsonb_typeof = 'object'`); FKs `actor_user_id → users`, `shop_id → shops` (`RESTRICT`); `ip inet`; indexes `ix_audit_events_occurred_at_id` (`occurred_at DESC, id DESC`), `ix_audit_events_shop_id_occurred_at`, `ix_audit_events_actor_user_id_occurred_at`, `ix_audit_events_category_occurred_at` (each with `occurred_at DESC`), `ix_audit_events_target_type_target_id`. |
| `repository.py` | `AuditEventRepository`: `add` (inherited), `page(filters, sort, limit, offset)`, `newest(filters, limit, before)` (keyset paging for the export). No update or delete. |
| `schemas.py` | `AuditEventRead` (wire), `AuditFilters` (E-74 filters + `involving_user_id` for E-67), `AuditSort`, `AuditEntry` (internal row to write). |
| `domain/catalogue.py` | The action names, `booking_action_name`, `category_of`, `ROLE_LABELS`, `BOOKING_PHRASES` (one phrase per `BookingAction`), `summary`, `label`, `cut`, `changed_fields` (pure). |
| `service.py` | `record` and the `record_*` function of every catalogue entry; `list_events`, `latest_events`, `export_events`. |
| `handlers.py` | `register(bus)`: 16 subscriptions, each a one-line call into the service. |

The migration is revision `339df51b764d` (spec 02 §9): table, indexes and `CREATE TRIGGER trg_audit_events_append_only BEFORE UPDATE OR DELETE … EXECUTE FUNCTION forbid_mutation()` (the baseline's function, spec 02 §8).

## Public service interface

**Write (nested — the publisher's transaction, never a commit).**

| Function | Use |
|---|---|
| `record(uow, entry: AuditEntry) → UUID` | Inserts one row with `app.core.request_context.current_request_context()` (IP, user agent, request id; all `None` outside a request), cuts `summary` to 300 and `target_label` to 200 characters, and flushes so a database error fails the action that caused it. |
| `record_login_succeeded`, `record_login_failed`, `record_login_rate_limited`, `record_logged_out`, `record_owner_registered`, `record_customer_created`, `record_user_active_changed`, `record_platform_admin_changed`, `record_shop_created`, `record_shop_updated`, `record_working_hours_replaced`, `record_shop_suspension_changed`, `record_membership_added`, `record_membership_role_changed`, `record_membership_active_changed`, `record_booking_action` `(uow, event)` | One per subscribed event (table below). |
| `record_user_viewed(uow, *, admin_user_id, user_id, occurred_at)` | E-67 (called by `admin`). |
| `record_booking_viewed(uow, *, admin_user_id, booking_id, shop_id, reference, occurred_at)` | E-73 (called by `admin`); the row belongs to the booking's shop. |
| `record_audit_exported(uow, *, admin_user_id, filters, rows, occurred_at)` | E-75 (called by `admin`): `{filters, rows}`. |

**Read.**

| Function | Returns |
|---|---|
| `list_events(session, *, filters, sort, page)` | `Page[AuditEventRead]` (E-74) |
| `latest_events(session, *, filters, limit=10)` | the newest rows (E-61, E-63 shop trail, E-67 "by or about" trail) |
| `export_events(session, *, filters, limit=10_000)` | `AsyncIterator[AuditEventRead]`, newest first, read in keyset batches of 1 000 (E-75) |

Reads it composes: `identity.service.get_users_by_ids` (actor and target names, e-mail labels), `shops.service.get_shop_briefs` (shop names).

## Domain rules

### Row per event (spec 19 §3.3)

| Event (publisher) | `action` | Actor · `actor_role` | Shop | Target · label | Metadata |
|---|---|---|---|---|---|
| `LoginSucceeded` (identity `login`; `sign_in_for_booking`, D100) | `auth.login_succeeded` | the user · null | — | `USER` · e-mail | — |
| `LoginFailed` (identity `login`; `sign_in_for_booking`) | `auth.login_failed` | — · `ANONYMOUS` | — | — | `{email}` |
| `LoginRateLimited` (identity `login`; `sign_in_for_booking`) | `auth.login_rate_limited` | — · `ANONYMOUS` | — | — | `{email}` |
| `LoggedOut` (identity `logout`) | `auth.logged_out` | the user · null | — | `USER` · e-mail | — |
| `OwnerRegistered` (identity `register_owner`) | `auth.owner_registered` | the new user · null | — | `USER` · e-mail | — |
| `CustomerAccountCreated` (identity `create_customer`, wizard case B) | `user.customer_created` | the new user · `CUSTOMER` | — | `USER` · e-mail | — |
| `UserActiveChanged` | `user.deactivated` / `user.reactivated` | admin · `PLATFORM_ADMIN` (none · `SYSTEM` for the seed) | — | `USER` · e-mail | `{reason}` (deactivate) |
| `PlatformAdminChanged` | `user.platform_admin_granted` / `…_revoked` | admin · `PLATFORM_ADMIN` (none · `SYSTEM` for the bootstrap script) | — | `USER` · e-mail | — |
| `ShopCreated` | `shop.created` | the owner · `OWNER` | the shop | `SHOP` · name | — |
| `ShopUpdated` | `shop.updated` | the owner · `OWNER` | the shop | `SHOP` · name | `{changes: {field: {from, to}}}` (changed fields only) |
| `WorkingHoursReplaced` | `shop.working_hours_replaced` | the owner · `OWNER` | the shop | `SHOP` · name | — |
| `ShopSuspensionChanged` | `shop.suspended` / `shop.reactivated` | admin · `PLATFORM_ADMIN` | the shop | `SHOP` · name | `{reason}` (suspend) |
| `MembershipAdded` | `membership.added` | the owner · `OWNER` | the shop | `MEMBERSHIP` · member e-mail | `{role, member_email}` |
| `MembershipRoleChanged` | `membership.role_changed` | the owner · `OWNER` | the shop | `MEMBERSHIP` · member e-mail | `{from, to}` |
| `MembershipActiveChanged` | `membership.deactivated` / `…reactivated` | the owner · `OWNER` | the shop | `MEMBERSHIP` · member e-mail | — |
| `BookingActionApplied` (bookings) | `booking.<action>` in lower snake case | the event's actor · its `actor_role` (or `SYSTEM`) | the booking's shop | `BOOKING` · reference | `{from_status, to_status, version}` + `note` when set |
| — (admin E-67) | `admin.user_viewed` | admin · `PLATFORM_ADMIN` | — | `USER` · e-mail | — |
| — (admin E-73) | `admin.booking_viewed` | admin · `PLATFORM_ADMIN` | the booking's shop | `BOOKING` · reference | — |
| — (admin E-75) | `admin.audit_exported` | admin · `PLATFORM_ADMIN` | — | — | `{filters, rows}` |

A sign-in, sign-out or owner registration is done in no shop role, so its `actor_role` is null (the column is nullable, spec 19 §3.1).

### Summaries

One English sentence per row from a fixed template (`domain/catalogue.py`), e.g. "Areeba Hashmi suspended Raza Auto Works.", "Bilal Ahmed approved the estimate of BF-7K2M9Q at Lahore Auto Care.", "Failed sign-in for ahmed@mail.com.". Names are substituted, never re-parsed as templates; whitespace is collapsed to one line; the result is cut to 300 characters with "…". The system actor is "BayFlow". Summaries, labels and metadata never hold a password, a token or a hash: events carry ids and primitives only, and no password-bearing value is ever copied into them.

### Request context

`app.core.request_context` (spec 19 §3.2): the request-context middleware binds the client IP — `app.core.security.client_ip` (the rate limiter's trusted-proxy rule), kept only when it parses as an address so the `inet` column never receives a spoofed header — and the user agent (NUL characters dropped, at most 255 characters) next to the request id. Scripts, the seed and unit tests have none (nulls).

### Failed sign-ins

`identity.service.login` publishes `LoginFailed` / `LoginRateLimited` and commits that transaction (which holds nothing else) before re-raising the 401 / 429, so the row persists. The booking wizard signs in through `identity.service.sign_in_for_booking` (D100): a success publishes `LoginSucceeded` in the booking's transaction (the row is lost with a booking that fails later, accepted); a failure publishes `LoginFailed` / `LoginRateLimited` on a separate session in a short transaction of its own, committed before the 409 / 429, so the row survives the booking's rollback while nothing of the booking commits. `authenticate` itself publishes nothing and never commits.

### Logout

`auth.logged_out` is written only when the request's Bearer token or else its cookie names an active user. The identity router treats recording as best effort: any failure (this module's insert included) is logged without the token, rolled back, and logout still answers 204 with the cookie expired (spec 04, spec 19 §3.2).

## Events

| Event | Publisher | Handler | In the transaction | After commit |
|---|---|---|---|---|
| The 16 events of the table above | identity, shops, bookings | `on_<event>` → `service.record_<…>` | one `audit_events` row | — |

Publishes nothing.

## Permissions and visibility

No route. The admin module exposes the rows to platform admins only (`require_platform_admin`, D94). Nothing changes a row: no API, and the trigger refuses `UPDATE` / `DELETE` for every client (a superuser's `session_replication_role = replica` is the only, manual, way around it — spec 02 §8).

## Errors

None of its own. A handler error (e.g. a database error) propagates and rolls the publisher's action back (spec 01 event rule 2); the trigger's `P0001` stays an unmapped 500 (spec 02 §7.6) because only a bug can reach it.

## Concurrency and transactions

Rows are inserted in the publisher's transaction under whatever locks it already holds; they take no lock of their own and no row is ever updated, so the module adds no lock-order edge (D30). One flush per row surfaces errors inside the action. Reads run at READ COMMITTED. The export reads at most 10 000 rows newest first in keyset batches (`(occurred_at, id) < last`), so it never scans an `OFFSET`.

## Tests

`tests/modules/audit/test_catalogue.py` (every catalogue action writes exactly one row; actor, role, shop, target, metadata; one row per `booking_events` row through a whole job incl. `RECEIVE_PARTS`; a rolled-back action — service-level and a wizard `SLOT_FULL` — leaves no row; failed and rate-limited logins persist with the lower-cased e-mail; failed and blocked wizard sign-ins persist on their own while nothing of the booking does, and a wizard sign-in is recorded with its booking and lost with a failed one (D100); logout recorded only for an active user's credentials; request context captured and a malformed IP dropped; scripts leave the context empty; no password, token or hash in any row; `shop.updated` holds only the changed fields), `tests/db/test_audit_events.py` (the trigger refuses `UPDATE` and `DELETE` with `P0001`, `TRUNCATE` works; every CHECK; the migration's own round trip), `tests/unit/audit/test_catalogue.py` (names, phrases for every `BookingAction`, truncation, template safety), `tests/unit/core/test_request_context.py`. Export and list behaviour: `modules/admin.md`.

## Dependencies (specs)

[19-platform-admin.md](../19-platform-admin.md) §3 (authoritative), [17-decisions.md](../17-decisions.md) D22, D29, D63, D74, D89, D90, D95, D97, D100, [01-architecture.md](../01-architecture.md) (event bus, rule 4-like subscription, dependency rules), [02-data-model.md](../02-data-model.md) §3.22, §8, §9, [identity.md](identity.md), [shops.md](shops.md), [bookings.md](bookings.md) §8, [admin.md](admin.md).

## Open questions

1. ✅ **Resolved: `identity.md` / `shops.md` events.** Both module specs now list the events they publish (identity §8, shops §8).
2. ✅ **Resolved as documented behaviour (spec 19 §3.2): per-IP refusals.** slowapi's per-IP ceilings answer 429 before the identity service runs, so only the per-account limiter produces `auth.login_rate_limited`. A slowapi hook would be needed to audit them.
3. ✅ **Resolved by D100: booking-wizard sign-ins** are audited (success in the booking's transaction, failures on their own).
4. **Retention.** The log grows forever; partitioning or archiving is a post-hackathon decision (append-only forbids deleting rows through the app). Tracked in spec 16 C.1.

## Proposed glossary additions

| Kind | Name | Meaning |
|---|---|---|
| Stored enums (§5) | `AuditCategory`, `AuditActorRole`, `AuditTargetType` | `audit_events.category`, `.actor_role`, `.target_type` |
| Python module | `app.core.request_context` | Client IP, user agent and request id of the current request (spec 19 §3.2) |
| Events (§7.1) | identity `LoginSucceeded`, `LoginFailed`, `LoginRateLimited`, `LoggedOut`, `OwnerRegistered`, `CustomerAccountCreated`, `UserActiveChanged`, `PlatformAdminChanged`; shops `ShopCreated`, `ShopUpdated`, `WorkingHoursReplaced`, `ShopSuspensionChanged`, `MembershipAdded`, `MembershipRoleChanged`, `MembershipActiveChanged` | Spec 19 §3.3 |
| DB trigger | `trg_audit_events_append_only` | Rejects `UPDATE` / `DELETE` on `audit_events` (reuses `forbid_mutation()`) |
