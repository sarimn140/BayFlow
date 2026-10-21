# Module: identity

**Status:** Draft
**Package:** `app.modules.identity`
**Owns tables:** `users`

## 1. Purpose

Own user accounts and the session token: owner sign-up, login, logout, Argon2id password hashing, the per-account failure limiter, and the user look-ups every other module needs. Identity is the **lowest module** (spec 01 direction rules): it imports no other module and never reads memberships. That is why login and owner registration answer with the token and the account only, and the web then calls `GET /api/v1/me`, which the `shops` module serves (D81).

Brief sections satisfied:

- §7.1 "Owner sign up and login; staff login with credentials created by the Owner; customer login with the email and password given during booking"; "Secure password hashing, token or session based auth, role checks on every protected endpoint".
- §4 Access rules "Shop staff accounts are created by the Owner, never by self sign-up" (identity offers `create_user`, but only `shops.add_member` and the booking wizard call it; there is no staff sign-up route).
- FAQ "How does a customer log in? … If that email already exists, reuse the account instead of creating a duplicate" (identity provides the credential check the wizard reuses, D32).
- §9.4 "Input validation on all endpoints; consistent error responses; proper HTTP status codes".

## 2. Scope

| Priority | In scope |
|---|---|
| **P0** | `POST /api/v1/auth/register-owner`, `POST /api/v1/auth/login`, `POST /api/v1/auth/logout` (D81). Password policy 12–128 characters and Argon2id hashing with transparent rehash (D10). Login with a constant-time dummy hash and identical 401 bodies. Per-account failure limiter (primary) and per-IP ceilings (secondary) (D69). Session token issuing (`typ = session`) and the `bf_session` cookie (D8). The project `Email` type on every e-mail field (D62). Service functions for other modules: user look-ups, user creation, the shared credential check, `set_phone_if_empty` (D33). Internal account-maintenance functions used only by the seed's demo-cast reconciliation (D60). |
| **P1** | ~~Structured auth audit log lines~~ — superseded by D95: identity publishes audit events (§8) that the `audit` module stores in `audit_events` (spec 19 §3). The platform admin's account levers (spec 19, D94): `is_platform_admin`, the admin reads and the safeguarded `change_user_active` / `change_platform_admin`, the bootstrap script's `bootstrap_platform_admin`, and `lock_acting_platform_admin` for the shops levers. |
| **P2** | Nothing new. The bonus `calls` module reuses `get_user` / `get_users_by_ids` for caller verification and display names (spec 05). |
| **Out of scope** | Password change and `users.tokens_valid_after` (spec 04 Tier 2), password reset, e-mail verification, invitations, MFA (Tier 3); profile editing (no endpoint in spec 03); token revocation on logout (stateless JWT, spec 04); `GET /api/v1/me` (served by `shops`, D81); the WebSocket ticket (served by `notifications`, D70); any membership or role logic (`shops`). |

## 3. Key decisions

| D | What it means here |
|---|---|
| D8 | HS256 JWT with exactly `sub`, `iat`, `exp`, `typ = session`; delivered as the httpOnly cookie `bf_session` **and** in the body (`access_token`, `token_type`, `expires_in`). Signing and verification live in `app.core.security`; identity decides when a session is issued. |
| D9 | `get_active_user` re-reads `users.is_active` on every request (used by `app.shared.auth`); an inactive user is `None` → 401 everywhere. |
| D10 | Passwords are 12–128 characters, never trimmed, no composition rules, Argon2id via pwdlib, transparent rehash on a successful check. Login accepts 1–128 characters (the policy applies to new passwords only). |
| D17 | Owner registration creates a bare user, no membership; the owner then creates a shop through `shops`. |
| D18 | Identity never changes an existing account's password, name or phone on behalf of another module; `create_user` is only called for an e-mail that has no account. |
| D32 | The wizard's case C/D credential check is identity's `authenticate`; the bookings module maps its `INVALID_CREDENTIALS` to 409 `EMAIL_ALREADY_REGISTERED`. A failed wizard check counts for the per-account limiter exactly like a failed login. |
| D33 | `set_phone_if_empty` fills `users.phone` only when it is NULL. |
| D49 | Every error is an `AppError` from `app.core.errors`, rendered as problem+json. |
| D50 | User ids are UUID v4 generated in Python. |
| D52 | No demo special case anywhere in identity; the demo password and e-mails live only in seed data. |
| D60 | Identity exposes generic internal functions (`set_user_active`, `password_matches`, `set_password`) that the seed composes; identity itself knows nothing about the demo cast. |
| D61 | `Cache-Control: no-store` on every response (middleware; nothing module-specific). |
| D62 | Every e-mail field is the project `Email` type (`app.shared.email`): validated with `test_environment=True`, then lower-cased; all look-ups use that normalised value. |
| D63 | `last_login_at`, `created_at`, `updated_at`, and the JWT `iat`/`exp` come from `app.shared.clock.utcnow()`. Rate-limit windows are the documented exception (system time inside `limits`). |
| D69 | Failed password checks are limited per normalised e-mail (5 per 15 min, moving window, cleared on success, unknown e-mails counted like known ones); per-IP ceilings on login (30/min) and owner registration (20/h). |
| D81 | Identity owns `/api/v1/auth/*`. `login` and `register-owner` return `{access_token, token_type, expires_in, user}` and set the cookie; they do **not** include memberships. |
| D84 | As built: `Password` = `Secret[Annotated[str, StringConstraints(min_length=12, max_length=128)]]` in `app.core.security` (422 code `string_too_short`); the project `Phone` type lives in `app.shared.phone`. |
| D86 | Identity is the lowest module and imports no other module. It never needs a read port: modules above it call its look-ups directly; read ports such as shops' `ShopActivityReader` (`shops.service.register_activity_reader`) and inventory's `BookingRefReader` (`inventory.service.register_booking_ref_reader`) exist only for reads that go **up** the module graph. |

## 4. Files

| File | Contents |
|---|---|
| `models.py` | `User` (exists; spec 02 §3.1): `email` varchar(254) unique, `password_hash`, `full_name`, `phone`, `is_active`, `is_platform_admin` (D94, default false; partial index `ix_users_platform_admin`), `last_login_at`; checks `ck_users_email_lowercase`, `ck_users_email_shape`, `ck_users_full_name_not_blank`; P2 index `ix_users_phone`. |
| `repository.py` | `UserRepository(Repository)` (exists, extend): `get(user_id)` (fresh read, `populate_existing`), `get_by_email(email)`, `get_many(user_ids)`, `find_ids_by_name(q, limit)`, `add(user)`. A `uq_users_email` violation surfaces as 409 `EMAIL_ALREADY_REGISTERED` through the global constraint map (`app.core.db_errors.CONSTRAINT_CODES`, already in code). Users are global, so no `shop_id` argument. |
| `schemas.py` | The internal `UserRecord` other modules receive (`UserRead` + `is_active`; never `password_hash`; Open question 1); the wire schema `UserRead` of spec 03 §3.2 (`id`, `email`, `full_name`, `phone` — no `is_active`), used by `SessionRead.user`; `UserRef` (spec 03 §3.1, used by other modules for actors and authors); `OwnerRegistrationCreate`, `SessionCreate` (requests, `extra="forbid"`); `SessionToken` (`access_token`, `token_type = "bearer"`, `expires_in`); `SessionRead` (`SessionToken` + `user: UserRead`). |
| `service.py` | The use cases and look-ups of §5. Never imports `app.shared.auth` (spec 01 rule 8). |
| `router.py` | `APIRouter(prefix="/api/v1/auth", tags=["identity"])` with `register_owner`, `login`, `logout`; slowapi per-IP decorators (login, register-owner, logout); sets/clears the cookie through `app.shared.auth` helpers. |
| `events.py` | The audit events identity publishes (§8, spec 19 §3.3). |

No `domain/` or `handlers.py`: the password policy is the `Password` type in `app.core.security`, e-mail normalisation is `app.shared.email`, and identity subscribes to nothing.

## 5. Public service interface

Every function takes the request's `UnitOfWork` (`uow`, writes) or `AsyncSession` (`session`, reads) first (spec 01). "Nested" = joins the caller's transaction and never commits; "top-level" = commits.

| Function | Arguments → returns | Tx | Errors | Called by |
|---|---|---|---|---|
| `register_owner` | `(uow, *, email: str, full_name: str, password: SecretStr, phone: str \| None) → SessionRead` | top-level | 409 `EMAIL_ALREADY_REGISTERED` | identity router; seed Phase A (ignores the token) |
| `login` | `(uow, *, email: str, password: SecretStr) → SessionRead` | top-level | 401 `INVALID_CREDENTIALS`, 429 `RATE_LIMITED` | identity router |
| `authenticate` | `(uow, *, email: str, password: SecretStr, now: datetime \| None = None) → UserRecord` | nested; publishes nothing | 401 `INVALID_CREDENTIALS`, 429 `RATE_LIMITED` (with `Retry-After`) | `login`, `sign_in_for_booking` |
| `sign_in_for_booking` | `(uow, *, email: str, password: SecretStr, now: datetime) → UserRecord` | nested; a failure commits its audit row in **its own** transaction (D100) | as `authenticate` | `bookings.create_booking` (wizard cases C/D) |
| `logout` | `(uow, *, user_id: UUID \| None) → None` | top-level (commits only when it records) | — | identity router |
| `create_user` | `(uow, *, email: str, full_name: str, password: SecretStr, phone: str \| None) → UserRecord` | nested; **call without holding row locks** (Argon2) | 409 `EMAIL_ALREADY_REGISTERED` (race on `uq_users_email`) | `register_owner`; `shops.add_member` (new e-mail); `bookings.create_booking` (case B) |
| `issue_session` | `(user_id: UUID) → SessionToken` | none (pure; reads the clock and settings) | — | `register_owner`, `login`; `bookings.create_booking` (D32 token in the body) |
| `get_active_user` | `(session, user_id) → UserRecord \| None` | read | — | `app.shared.auth.get_current_user` / `get_optional_user` (exists, D9); `shops` (eligibility, `/me`) |
| `get_user` | `(session, user_id) → UserRecord \| None` (any status) | read | — | bookings, calls (P2) |
| `get_users_by_ids` | `(session, user_ids: Collection[UUID]) → dict[UUID, UserRecord]` (any status, one query) | read | — | shops (team list, `/me`), bookings, estimates, inventory, qc, notifications, reporting (names for `UserRef`) |
| `find_user_by_email` | `(session, email: str) → UserRecord \| None` | read | — | `shops.add_member`, `bookings.create_booking` |
| `find_user_ids_by_name` | `(session, *, q: str, limit: int = 1000) → list[UUID]` (case-insensitive substring on `full_name`, `%`/`_` escaped) | read | — | `bookings.list_staff_bookings` (`q` matches the customer name, spec 03 §4.8) |
| `set_phone_if_empty` | `(uow, *, user_id, phone: str) → bool` (True when written) | nested | — | `bookings.create_booking` (cases A, C; D33) |
| `set_user_active` *(internal, not over HTTP)* | `(uow, *, user_id, is_active: bool) → bool` (True when changed; publishes `UserActiveChanged` with no actor, audited as `SYSTEM`) | top-level | 404 `NOT_FOUND` (unknown id) | seed Phase R (D60) |
| `create_customer` | `(uow, *, email, full_name, password, phone, now) → UserRecord` (`create_user` that starts a session, publishes `CustomerAccountCreated`) | nested | as `create_user` | `bookings.create_booking` (case B) |
| `list_users_for_admin`, `get_user_for_admin`, `count_users`, `find_user_ids_by_email` | admin reads (E-61, E-66, E-67; spec 19 §4) | read | — | admin, shops (E-62 owner e-mail search) |
| `change_user_active`, `change_platform_admin` | `(uow, *, actor_user_id, user_id, …) → UserAdminRecord` with the spec 19 §1 safeguards under one `FOR UPDATE` of the target and every active admin | nested | 403, 404, 409, 422 (`path.user_id` `inactive_account`) | admin (E-68…E-71) |
| `lock_acting_platform_admin` | `(session, *, actor_user_id) → None`: the actor's row `FOR SHARE`, 403 unless an active platform admin | nested | 403 `FORBIDDEN` | `shops.suspend_shop` / `reactivate_shop` |
| `bootstrap_platform_admin` | `(uow, *, email, full_name, password) → (UserRecord, created, promoted)` (idempotent; commits) | top-level | 422 (password policy) | `app.scripts.create_platform_admin` |
| `password_matches` *(internal)* | `(session, *, user_id, password: SecretStr) → bool` (one Argon2 verify; **no limiter**, no rehash write) | read | — | seed Phase R (D60) |
| `set_password` *(internal)* | `(uow, *, user_id, new_password: SecretStr) → None` (hashes with Argon2id; D10 policy via the `Password` type) | top-level | 404 `NOT_FOUND` | seed Phase R (D60) |

Spec 01's catalogue lists `register_owner`, `create_user`, `authenticate`, `get_active_user`, `find_user_by_email`, `set_phone_if_empty`, `get_users_by_ids`; the other functions are proposed in the last section. The logout endpoint calls `logout` only to record `auth.logged_out` (§7.7): the session is a stateless JWT, so logout itself only clears the cookie.

## 6. Endpoints

Full schemas and errors: [spec 03 §4.3](../03-api-contracts.md) (D81). All three routes are **public**: they never read credentials (spec 03 §1.2).

| operationId | Method + path | Auth · roles | Success | Pri | Screens |
|---|---|---|---|---|---|
| `identity_register_owner` | `POST /api/v1/auth/register-owner` | public | 201 `SessionRead` + `Set-Cookie: bf_session` | P0 | P-05 · E-03 |
| `identity_login` | `POST /api/v1/auth/login` | public | 200 `SessionRead` + `Set-Cookie: bf_session` | P0 | P-04, P-03 inline login · E-01 |
| `identity_logout` | `POST /api/v1/auth/logout` | public (no body) | 204 + clearing `Set-Cookie` | P0 | S-01 user menu, X-04 · E-02 |

`GET /api/v1/me` is **served and tagged by the `shops` module** (`shops_get_me`, `shops.service.get_me`), because it combines the user with memberships and capabilities (spec 01, D66, D81; spec 03 §1.11). See `modules/shops.md`.

Request bodies (spec 03 §4.3, `extra="forbid"` everywhere):

- `OwnerRegistrationCreate`: `full_name` 1–120 (trimmed, not blank) · `email` Email · `password` `Password` (12–128, `Secret[str]`, never trimmed, D84) · `phone`? `Phone`.
- `SessionCreate`: `email` Email · `password` `SecretStr` 1–128.

Response `SessionRead` (D81, spec 03 §3.2): `access_token` · `token_type` `"bearer"` · `expires_in` (seconds; 604800 for `7d`) · `user` `UserRead` (`id`, `email`, `full_name`, `phone`). No memberships.

## 7. Domain rules and algorithms

### 7.1 Passwords (D10)

- Request type `Password = Secret[Annotated[str, StringConstraints(min_length=12, max_length=128)]]` from `app.core.security` (as built, D84; a short value reports `string_too_short`) for every **new** password (register-owner, `create_user` callers, `set_password`). Login uses `SecretStr` 1–128.
- `hash_password` / `verify_password` (`app.core.security`): Argon2id via `PasswordHash.recommended()`, run in a worker thread behind a 4-slot semaphore. `verify_password(pw, None)` verifies against a lazily computed dummy hash and returns `(False, None)`.
- A stored hash pwdlib cannot parse (corrupted row) is treated as a failed check and logged at WARNING with the user id (never the hash).
- Passwords and hashes never appear in logs, responses (SEC-44) or exception messages; `SecretStr` masks reprs.

### 7.2 E-mail (D62)

Every e-mail input is the `Email` type: stripped, validated with `validate_email(..., check_deliverability=False, test_environment=True)`, then fully lower-cased. Identity stores and looks up only that value, so `uq_users_email` is "unique on `lower(email)`" (spec 02 §3.1) and the limiter key is one per mailbox. `Fatima.Owner@BayFlow.TEST` → `fatima.owner@bayflow.test`; `x@localhost` → 422.

### 7.3 Register owner (`register_owner`, D17)

1. Per-IP ceiling `REGISTER_OWNER_IP_LIMIT` (20/hour) on the route (slowapi) → 429 + `Retry-After`.
2. `get_by_email(email)` → exists → 409 `EMAIL_ALREADY_REGISTERED`, detail "This e-mail already has a BayFlow account. Log in, then create your shop." (spec 03 §4.3).
3. `now = utcnow()`; `create_user(...)` (hash off the event loop, insert with `is_active = true`, `created_at = updated_at = now`), then `last_login_at = now` (a session starts).
4. Flush; a concurrent registration of the same e-mail hits `uq_users_email` → 409 `EMAIL_ALREADY_REGISTERED`.
5. Commit, then `issue_session(user.id)` (the token is issued only after the commit, so it never names a rolled-back user).
6. Return `SessionRead`; the router sets the cookie. No membership is created (brief §4).

### 7.4 Login (`login`) — constant time

```
key = email                                    # already normalised by the Email type
if not account_limiter().hit(FAILED_PASSWORD_LIMIT, "failed-password", key):   # reserve the attempt atomically,
    raise RateLimited(headers={"Retry-After": retry_after_seconds(...)})   # before any await, DB or hash work
user = repo.get_by_email(key)                  # fresh read, no row lock
valid, new_hash = await verify_password(password, user.password_hash if user else None)   # exactly ONE Argon2 call
if user is None or not valid or not user.is_active:
    raise InvalidCredentials                    # already counted above; identical body for unknown / wrong / inactive (SEC-22)
account_limiter().clear(FAILED_PASSWORD_LIMIT, "failed-password", key)
now = utcnow(); user.last_login_at = now
if new_hash: user.password_hash = new_hash     # transparent Argon2 parameter upgrade (OWASP)
commit → issue_session(user.id) → SessionRead
```

- **The attempt is reserved with one atomic `hit()` before the first `await`** (fixed 2026-10-09 after review): a `test()` → await → `hit()` order let a burst of parallel attempts all pass `test()` before any of them was counted (30 concurrent guesses gave 30 Argon2 checks). Now at most 5 attempts per 15 minutes reach the database or Argon2 whatever the concurrency; success `clear`s the counter, so a correct password still resets it. A blocked account gets 429 **even with the right password** (spec 04), and the 429 is not an enumeration signal because unknown e-mails are counted the same way. SEC-27 includes a concurrent-burst test.
- The per-IP ceiling `LOGIN_IP_LIMIT` (30/min) runs first, as a route decorator; it is only a secondary control because many visitors share Vercel's egress IPs (D69).
- An inactive user with the correct password still records a failure: login and the wizard (case D) treat "inactive" exactly like "wrong password".
- A user whose memberships are all inactive logs in normally (they may be a customer, spec 03 §4.3).

### 7.5 Shared credential check (`authenticate`)

`authenticate` is steps 1–5 of §7.4 without the commit and without issuing a token. It is the one implementation behind login and the wizard's cases C/D (spec 04), so the per-account limiter is shared (D69, SEC-27). The bookings module reaches it through `sign_in_for_booking` with the transaction it already holds and **no row locks taken yet** (spec 03 §4.6: "Argon2 never holds a row lock"), and maps `InvalidCredentials` to `EmailAlreadyRegistered`; `RateLimited` passes through as 429. `last_login_at` and a rehash become durable only when the booking commits (a booking always logs the customer in, D32).

`sign_in_for_booking` (D100) audits the wizard's sign-ins like logins: a success publishes `LoginSucceeded` in the booking's transaction (lost with a booking that fails later, accepted); `InvalidCredentials` publishes `LoginFailed` and `RateLimited` publishes `LoginRateLimited`, each in a short transaction of its own (a separate `AsyncSession` on the same engine, `uow.session.bind`), committed before the error is re-raised, so the attempt survives the booking's rollback and nothing of the booking commits. The limiter is untouched.

### 7.6 Session token and cookie (D8, D81)

- `issue_session(user_id)`: `issue_token(user_id, "session", utcnow())` → `SessionToken(access_token, "bearer", expires_in=settings.jwt_lifetime_seconds)`.
- The router sets the cookie through `app.shared.auth.set_session_cookie(response, token)` (already in code, next to `delete_session_cookie` and `session_cookie_clearing_headers()`): `bf_session=<jwt>; HttpOnly; Max-Age=<jwt_lifetime_seconds>; Path=/; SameSite=lax` (+ `Secure` when `COOKIE_SECURE=true`), host-only (no `Domain`). The bookings router uses the same helper after `POST /api/v1/bookings`.
- The web ignores the body token unless the D7 Bearer fallback is active; it routes from `GET /api/v1/me` (spec 09 §2.8).

### 7.7 Logout

`POST` only (a `GET` is 405 `METHOD_NOT_ALLOWED`, SEC-30). No body, no authentication, idempotent: always 204, with the cookie expired by `delete_session_cookie(response)` (`bf_session=""; Max-Age=0; Path=/; SameSite=lax; HttpOnly` + `Secure`). A copied Bearer token stays valid until `exp` (stateless JWT; accepted, spec 04). Per-IP ceiling `LOGOUT_IP_LIMIT` = 30 per minute (429; the cookie stays).

The router reads the credentials leniently with `app.shared.auth.session_user_id(request)` (the Bearer header wins, else the cookie; it never raises) and calls `logout(uow, user_id=…)`, which publishes `LoggedOut` and commits only for an active user. Recording is best effort: the router catches any exception, logs `auth.logout_not_recorded` with the exception type only (never the token or SQL parameters), rolls the unit of work back (a failing rollback is logged too) and still answers 204 with the cookie expired.

### 7.8 Create user (`create_user`)

Used for a brand-new e-mail only: `shops.add_member` (D18: the Owner typed the initial password) and the wizard's case B (D32). It hashes the password (Argon2, ~55 ms), inserts the row with `id = uuid4()` and the action's clock instant, and flushes. Callers must not hold row locks when calling it. `full_name` is trimmed; `phone` is the normalised `Phone` value.

### 7.9 Demo-cast reconciliation hook (D60)

Identity contains no list of demo accounts and no demo password (D52). The seed's Phase R calls, per seeded account that exists: `set_user_active(user_id, True)` when inactive, then `password_matches(user_id, demo_password)` and, when it returns `False`, `set_password(user_id, demo_password)`. Each function writes **only when the value differs** (no `updated_at` bump otherwise), so a run with nothing to repair writes no row (SEED-19). `password_matches` bypasses the per-account limiter, so Phase R never counts as failed logins (spec 11). These functions are never mounted on a route; `set_password` is also the building block of the Tier 2 password-change endpoint.

### 7.10 Phone (`Phone` type, D33)

The project `Phone` type (spec 03 §1.5; location `app.shared.phone`, D84, glossary §7): 7–20 characters of digits, spaces and hyphens with an optional leading `+`, stored without spaces and hyphens (`"+92 300 1234567"` → `"+923001234567"`). `set_phone_if_empty` writes only when `users.phone IS NULL` and never overwrites (D33, BK-05).

## 8. Events

Published for the platform audit log (D95, spec 19 §3.3), from `events.py`; identity never imports `audit`, which subscribes. None subscribed: identity is the bottom of the module graph.

| Event | Payload | Published by |
|---|---|---|
| `LoginSucceeded` | `user_id` | `login` (same transaction as `last_login_at`); `sign_in_for_booking` (the booking's transaction) |
| `LoginFailed` | `email` (normalised) | `login` (its transaction, committed before the 401); `sign_in_for_booking` (its own transaction, before the 409) |
| `LoginRateLimited` | `email` | per-account limiter only, as `LoginFailed` (429); per-IP slowapi refusals happen before the service and are not published |
| `LoggedOut` | `user_id` | `logout`, only for an active user |
| `OwnerRegistered` | `user_id` | `register_owner` |
| `CustomerAccountCreated` | `user_id` | `create_customer` (wizard case B) |
| `UserActiveChanged` | `user_id`, `is_active`, `actor_user_id` (None from the seed), `reason` | `change_user_active`; `set_user_active` (seed) |
| `PlatformAdminChanged` | `user_id`, `is_platform_admin`, `actor_user_id` (None from the script) | `change_platform_admin`; `bootstrap_platform_admin` |

Every event carries `occurred_at` (the action's one clock read, D63).

## 9. Permissions and visibility

| Route / function | Who |
|---|---|
| register-owner, login, logout | Anyone (public). Register-owner and the wizard are the only ways a user is created besides an Owner adding staff (spec 04 SEC-16). |
| `UserRecord` outside identity | Other modules receive `UserRecord` (never `password_hash`) and decide what to expose: e.g. bookings shows a customer's e-mail and phone only to `OWNER` / `SERVICE_ADVISOR` (spec 03 §3.3); calls never shows them (brief §8.1). |
| Internal functions (§7.9) | Not reachable over HTTP; only `app.scripts.seed` calls them (import-linter `seed-through-services` keeps the seed on the service layer). |

## 10. Errors

| Code | HTTP | Raised by / when |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Schema: bad e-mail (D62), password outside 12–128 on register (D10) or outside 1–128 on login, blank `full_name`, invalid phone, unknown fields (`role`, `shop_id`, `memberships` → `extra_forbidden`, SEC-16) |
| `EMAIL_ALREADY_REGISTERED` | 409 | `register_owner` with an existing e-mail; `create_user` losing the `uq_users_email` race |
| `INVALID_CREDENTIALS` | 401 | `login` / `authenticate`: unknown e-mail, wrong password or inactive user (identical bodies) |
| `RATE_LIMITED` | 429 | Per-account limiter (`login`, `authenticate`); per-IP ceilings on login, register-owner and logout. Always with `Retry-After` |
| `NOT_FOUND` | 404 | Internal `set_user_active` / `set_password` with an unknown id (seed only) |
| `METHOD_NOT_ALLOWED` | 405 | e.g. `GET /api/v1/auth/logout` (framework) |

`UNAUTHENTICATED` (401) is raised by `app.shared.auth` when `get_active_user` returns `None`, not by this module's routes.

## 11. Concurrency & transactions

- `register_owner`, `login`, `set_user_active`, `set_password` are top-level: one transaction each, committed in the service before the response is built.
- The platform admin's levers lock (spec 19 §1): `change_user_active` / `change_platform_admin` take the target and every active platform admin `FOR UPDATE` in one statement in `id` order (two admins demoting each other cannot deadlock; the loser re-reads and gets 409), and `lock_acting_platform_admin` takes the actor's row `FOR SHARE` for the shops levers (a concurrent revoke waits for the lever, or committed first and the lever answers 403).
- `logout` and a failed `login` commit their own (otherwise empty) transaction; `sign_in_for_booking` records a failure on a separate session (D100).
- No row locks on the sign-in path: login reads the user unlocked and updates `last_login_at` (last write wins between two parallel logins; harmless). Argon2 therefore never runs while a row lock is held — for the wizard this is the caller's job (bookings resolves the account before it takes the shop `FOR SHARE` and slot-counter locks, D32, D37).
- Races on a new e-mail are settled by `uq_users_email` (spec 02 §7.5) → 409 `EMAIL_ALREADY_REGISTERED`.
- Limiter counters are in-memory per process (one API replica, D14) and reset on redeploy; tests reset them with `reset_rate_limits()`.

## 12. Tests

Spec 12 / spec 04 IDs this module must make pass: **SEC-16** (no self-sign-up as staff), **SEC-17** (mass assignment on register), **SEC-22** (identical 401s, exactly one Argon2 verify per attempt), **SEC-23** (cookie flags; logout), **SEC-24** (token payload, `JWT_EXPIRES_IN`), **SEC-25**, **SEC-26** (token rejection — with `app.shared.auth`), **SEC-27** (per-account limit shared with the wizard and independent of IP; per-IP login ceiling; owner-registration ceiling), **SEC-29** (11/129-character passwords rejected, `BayFlow@2026` accepted), **SEC-30** (logout `GET` → 405; JSON-only bodies), **SEC-38** (log hygiene for auth bodies and tokens), **SEC-44** (only `$argon2id$` hashes stored; no password fields in responses), **SEC-47** *(P1, no demo bypass)*, **SEC-48** (`Email` type on register and login), **API-12 ★**, **SEED-07 ★**, **SEED-13**, **SEED-19** (identity half), **DEP-03**, **DEP-07**; and, through the wizard, **BK-01**, **BK-02**, **BK-03 ★**, **SEC-18**, **SEC-19**.

Proposed additional tests (module-local IDs for spec 12 to number):

| ID (proposed) | Test |
|---|---|
| IDN-01 | Register-owner: 201, cookie set, body `user` has no `memberships` key (D81), `last_login_at` set; a following `GET /api/v1/me` returns `memberships: []` |
| IDN-02 | Transparent rehash: a stored hash with outdated Argon2 parameters is replaced after a successful login and still verifies; a failed login never rewrites it |
| IDN-03 | Limiter cleared on success: 4 failures, 1 success, then 4 more failures still log in on the 5th try with the right password; the 5th failure blocks |
| IDN-04 | A user whose every membership is inactive logs in (200); an inactive user with the right password → 401 and counts as a failure |
| IDN-05 | Internal functions are idempotent: `set_user_active` / `set_password` on an already-correct account change no column (`updated_at` unchanged); `password_matches` never touches the limiter |
| IDN-06 | Logout is idempotent with no cookie, with an expired cookie and with a valid one (always 204 + clearing header); the Bearer token still works after logout (documented stateless caveat) |

## 13. Implementation checklist

1. Use `app.shared.phone.Phone` (the spec 03 §1.5 type; already built, D84). Reuse the existing `set_session_cookie` / `delete_session_cookie` of `app.shared.auth` (D8 attributes).
2. Schemas: `OwnerRegistrationCreate`, `SessionCreate` (`extra="forbid"`), `SessionToken`, `SessionRead`; separate the internal `UserRecord` (with `is_active`) from the wire `UserRead` of spec 03 §3.2 (Open question 1; as built).
3. Repository: `get_by_email`, `get_many`, `find_ids_by_name`, `add`; the `uq_users_email` race maps to 409 through `app.core.db_errors` (no local translation needed).
4. Service: `create_user` → `authenticate` (limiter + single verify + rehash) → `issue_session` → `register_owner`, `login` → look-ups (`get_user`, `get_users_by_ids`, `find_user_by_email`, `find_user_ids_by_name`, `set_phone_if_empty`) → internal `set_user_active`, `password_matches`, `set_password`.
5. Router `/api/v1/auth` with `@limiter.limit(LOGIN_IP_LIMIT)` / `@limiter.limit(REGISTER_OWNER_IP_LIMIT)` (route decorator above the limiter decorator; endpoints take `request: Request`), cookie set/clear, `tags=["identity"]` so operation IDs are `identity_register_owner`, `identity_login`, `identity_logout`.
6. Export the router as `routers` from `router.py` (`app.main.wire_modules()` includes it, D89; `app/main.py` is not edited); regenerate the OpenAPI snapshot and web types (`make gen-api`, D76).
7. Tests: §12 list, builders `make_user` (spec 12 §4.3) through `create_user`.

## 14. Dependencies (specs)

[17-decisions.md](../17-decisions.md) (D8–D10, D17, D18, D32, D33, D49, D50, D52, D60–D63, D69, D81), [18-glossary.md](../18-glossary.md) (§7, §9, §10, §12, §14), [01-architecture.md](../01-architecture.md) (layers, rule 8), [02-data-model.md](../02-data-model.md) §3.1, [03-api-contracts.md](../03-api-contracts.md) §1.2, §1.5, §1.9, §4.3, [04-auth-and-security.md](../04-auth-and-security.md) (flows, limiter, cookie, SEC tests), [09-frontend-and-ux.md](../09-frontend-and-ux.md) §2.8 (login → `/me`), [11-seed-data.md](../11-seed-data.md) (Phase A owners, Phase R), [12-quality-and-testing.md](../12-quality-and-testing.md). Used by `modules/shops.md` (add-member, `/me`), `modules/bookings.md` (wizard), every module that shows user names.

## Open questions

1. ✅ **Resolved as built: `UserRead` on the wire vs the internal user.** The D81 part: specs 03 (§3.2, §4.3, §8.1 E-01) and 04 say identity serves `/api/v1/auth/*` and the body is `{access_token, token_type, expires_in, user}`. The rest: `identity.schemas.UserRead` is spec 03 §3.2's wire schema (`id`, `email`, `full_name`, `phone`; also the base of `MeRead`), and the internal `UserRecord` (a subclass that adds `is_active`) is what the look-ups return to other modules and `app.shared.auth` — the same split as shops' internal `MembershipRecord` — so OpenAPI matches spec 03.
2. ✅ **Resolved (accepted by the coordinator, 2026-10-09): `last_login_at` scope.** As proposed: set whenever a password is verified successfully or a new account starts a session (register-owner, login, wizard cases B and C); not on wizard case A (the session already exists).
3. **`find_user_ids_by_name` bound.** Staff booking search by customer name needs user ids from identity (the bookings module may not join `users`). A cap of 1,000 ids is plenty for a hackathon; confirm, or drop "customer name" from `q`.

## Proposed glossary additions

| Kind | Name | Meaning |
|---|---|---|
| Shared type | ✅ merged — `app.shared.phone.Phone` (glossary §7, D84) | The project phone type of spec 03 §1.5 |
| Shared helpers (already in code, missing from glossary §7) | `app.shared.auth.set_session_cookie(response, token)`, `delete_session_cookie(response)`, `session_cookie_clearing_headers()` | Set / expire `bf_session` with the D8 attributes; used by the identity and bookings routers and by `get_current_user` |
| Schema | `SessionToken` (`access_token`, `token_type`, `expires_in`); `SessionRead.user` (D81; ✅ spec 03 §3.2 uses it); internal `UserRecord` (Open question 1, as built) | Token part shared by `SessionRead` and `BookingCreatedRead` |
| Service functions | `identity.service`: `login`, `issue_session`, `get_user`, `find_user_ids_by_name`; internal-only `set_user_active`, `password_matches`, `set_password` (D60) | Additions to spec 01's identity catalogue |
| Limiter identifiers | `"failed-password", <email>` | Namespaced keys in the shared `account_limiter()` storage |
