# 04 — Auth & Security

**Status:** Draft

## Purpose

Define how BayFlow knows **who** is calling (authentication), **what that caller may do in which shop** (authorization: RBAC, tenant isolation, booking visibility), and how the platform resists the realistic attacks against a multi-tenant web app built in a hackathon. Every rule in this spec is enforced **by the API**. The web app mirrors rules only for UX (hidden buttons, redirects) and is never a security boundary.

Names come from [18-glossary.md](18-glossary.md); locked choices from [17-decisions.md](17-decisions.md) (D7–D10, D14–D21, D30, D32, D33, D39, D40, D44, D47, D49, D52, D58, the consolidation's D60–D63, D66, D67, D69, D70, and D80–D83); actors, guards and the error check order from [08-booking-state-machine.md](08-booking-state-machine.md). Library and platform facts were verified on 2026-10-09 against official docs and by executing the D11 library versions — see [Verified facts and sources](#verified-facts-and-sources).

### Security goals

| # | Goal | Brief | Proven by |
|---|---|---|---|
| G1 | **Tenant isolation**: staff of Shop A can never read or change Shop B data, "even by guessing IDs" | §3, §7.1 acceptance test | SEC-01…SEC-03, SEC-45 |
| G2 | **Role separation**: roles are per shop, and "no role can perform another role's action" | §4, §7.5, §7.8 | [RBAC matrix](#rbac-matrix), SEC-05…SEC-11, SEC-46, SEC-50 |
| G3 | **Credential safety**: secure password hashing, token/session auth, staff accounts created only by the Owner | §7.1, §4 | Argon2id, httpOnly cookie, SEC-16, SEC-18…SEC-27, SEC-44, SEC-48 |
| G4 | **Immediate revocation**: deactivated staff lose access on their next request | §7.2 "edit or deactivate them" | D9, SEC-13 |
| G5 | **Least exposure**: customers see only their own bookings, technicians only assigned ones | §4 access rules | D21, SEC-08…SEC-12 |
| G6 | **Robust surface**: validation everywhere, consistent errors, no stack traces, no committed secrets | §9.1, §9.4 | SEC-17, SEC-28, SEC-29, SEC-37 |

These goals carry the brief's 10 % "Multi-tenancy and security" criterion (§10) and part of the 20 % "Architecture and code quality" criterion ("tenant isolation, validation").

---

## Identity model

```
                 ┌───────────────────────────────────┐
                 │ users  (global identity)           │
                 │ id · email · password_hash ·       │
                 │ full_name · phone · is_active      │
                 └─────────┬──────────────┬───────────┘
   shop_memberships        │              │  bookings.customer_user_id
   (one per user per shop, │              │  (a customer is simply the user a booking
    role · is_active)      ▼              ▼   belongs to; no membership involved)
                 ┌──────────────┐   ┌───────────────────────────┐
                 │ shops         │◀──│ bookings (shop-owned)      │
                 │ (tenants)     │   └───────────────────────────┘
                 └──────────────┘
```

Rules (D15, D17):

1. **Users are global.** One `users` row per person, one e-mail, one password, usable at every shop.
2. **Roles live only in `shop_memberships`.** One membership (one `MembershipRole`) per user per shop; a user can hold different roles in different shops. Exactly one `OWNER` per shop.
3. **"Customer" is not a membership role.** Any user is the customer of the bookings whose `customer_user_id` is theirs (glossary §1). Customers never have a membership because of booking.
4. **Tokens identify the user, never a role or a shop** (D9). The role is resolved on every request from the `shop_id` in the URL plus the caller's membership row. Switching shops never needs a new token.
5. **The endpoint family decides the actor role** (spec 08 "Who is the actor?"): `/api/v1/me/...` acts as `CUSTOMER`, `/api/v1/shops/{shop_id}/...` acts with the membership role in that shop. `SYSTEM` is not a login role: no token can act as `SYSTEM`.

### One user, many hats

| User (demo cast, glossary §14) | Customer of | Memberships | What the POS shows |
|---|---|---|---|
| Fatima Raza | any booking she makes | `OWNER` @ Lahore Auto Care, `OWNER` @ Raza Auto Works (glossary §14) | Shop switcher with both shops |
| Bilal | his own car's bookings, if any | `SERVICE_ADVISOR` @ Lahore Auto Care | SA dashboard, plus "My bookings" |
| Imran, after opening his own garage *(hypothetical, D17)* | — | `TECHNICIAN` @ Lahore Auto Care, `OWNER` @ his garage | Technician view in one shop, owner view in the other |
| Ayesha Khan | her seeded bookings | none | Customer area only |

### Invariants this spec needs from spec 02

| Invariant | Enforcement |
|---|---|
| E-mail unique, case-insensitive | Every e-mail in a request goes through the project `Email` type (D62, [E-mail addresses](#e-mail-addresses-d62)): validated, then lower-cased before every lookup and insert; unique index and lower-case CHECK on `users.email` (spec 02 §3.1) |
| One membership per user per shop (D15) | Unique `(shop_id, user_id)` on `shop_memberships` |
| Exactly one `OWNER` per shop (D15) | At most one: partial unique index on `shop_memberships (shop_id) WHERE role = 'OWNER'`. At least one: the shop and its `OWNER` membership are inserted in one transaction and no API path changes or deactivates that row (D19) |
| Memberships are never deleted | No DELETE endpoint; deactivate only (D19), so `booking_events.actor_user_id` history stays meaningful |
| Assignees belong to the shop | Service check (422 `MEMBER_NOT_ELIGIBLE`) **plus** the composite FKs `(shop_id, technician_user_id)`, `(shop_id, parts_person_user_id)`, `(shop_id, qc_inspector_user_id)` → `shop_memberships (shop_id, user_id)` (spec 02 §4.4) |
| `password_hash` never leaves the identity module | Excluded from every read schema; only the identity module reads it, to pass it to `app.core.security` for verification |

---

## Authentication flows

### Endpoint summary

| Endpoint | Caller | Purpose | Success | Main errors |
|---|---|---|---|---|
| `POST /api/v1/auth/register-owner` | anonymous | Create an account (D17) | 201, sets `bf_session`, body = login body | 409 `EMAIL_ALREADY_REGISTERED`, 422, 429 |
| `POST /api/v1/auth/login` | anonymous | Log in | 200, sets `bf_session`, body `{access_token, token_type, expires_in, user}` — no memberships (D81) | 401 `INVALID_CREDENTIALS`, 422, 429 |
| `POST /api/v1/auth/logout` | anyone | Clear the cookie; record `auth.logged_out` when the credentials name an active user (spec 19 §3.3) | 204 | 429 (per IP) |
| `GET /api/v1/me` | session | Profile + `is_platform_admin` (D94) + active memberships, each with server-computed `capabilities` (D66; routing, shop switcher, non-booking buttons) and `shop_suspended` (D96). Served by the shops module; the web calls it right after login and registration (D81) | 200 | 401 |
| `POST /api/v1/shops` | session | Create a shop; caller becomes its `OWNER` (D17) | 201 | 422, 429 |
| `POST /api/v1/shops/{shop_id}/members` | `OWNER` of `shop_id` | Add a staff member (D18) | 201 | 403, 404, 409 `CONFLICT`, 422, 429 |
| `PATCH /api/v1/shops/{shop_id}/members/{membership_id}` | `OWNER` of `shop_id` | Change role, deactivate, reactivate (D19) | 200 | 403 `FORBIDDEN` (the `OWNER` membership), 404, 422 |
| `POST /api/v1/bookings` | anonymous or session | Booking wizard incl. the account rule (D32) | 201; every successful booking sets `bf_session` **and** returns `access_token`, `expires_in` and `account_created` in the body (D32) | 409 `EMAIL_ALREADY_REGISTERED`, 409 `SLOT_FULL`, 422, 429 |
| `GET /api/v1/realtime/ticket` | session | Short-lived WebSocket ticket, served by the notifications module, which runs the hub (D70, glossary §11). **P1** with the hub (D88) | 200 `{ticket, expires_in: 60}` | 401 (the session has expired) |
| `wss://<api-host>/api/v1/ws?ticket=<ticket>` | ticket | Realtime channel (glossary §11). **P1** (D88); the P0 app stays current by polling (D14) | 101 | handshake refused: the server closes with 1008 (D70); browsers report 1006 ([WebSocket ticket](#websocket-ticket--get-apiv1realtimeticket)) |

Every `/api/*` response — these endpoints, every other authenticated endpoint and the public ones alike, errors and 500s included — carries `Cache-Control: no-store`, and so does `/health` (D61; spec 03 §1.8; OWASP Session Management; see [CDN caching](#security-headers-tier-1-values)). The three `/api/v1/auth/*` routes belong to the identity module (D81). Exact request/response schemas are owned by spec 03; this spec fixes the security-relevant fields.

### Owner registration — `POST /api/v1/auth/register-owner`

1. Body `{full_name, email, password, phone?}`: `email` is the project `Email` type (D62), `password` follows the D10 policy (12–128 characters). The schema uses `extra="forbid"`, so `role`, `shop_id`, `is_active` or `memberships` cannot be smuggled in (422, verified).
2. Per-IP ceiling check ([Rate limiting](#rate-limiting)); there is no account yet, so the per-IP limit is the only one here (D69).
3. The e-mail is already normalised by the `Email` type. If a user exists → **409 `EMAIL_ALREADY_REGISTERED`** with a neutral message ("This e-mail already has a BayFlow account. Log in, then create your shop."). An existing customer becomes an owner by logging in and creating a shop (D17).
4. Hash the password (Argon2id, off the event loop) and insert the user with `is_active = true`. The unique index decides races (→ 409).
5. Issue a session token, set `bf_session`, return the login body: the token fields and the new `user`, no memberships (D81).
6. The web calls `GET /api/v1/me` (`memberships: []`) and sends the new user to "create your first shop", which calls `POST /api/v1/shops`.

Registration never creates a membership, and there is no "register as staff" endpoint anywhere (brief §4: staff accounts are "created by the Owner, never by self sign-up").

### Login — `POST /api/v1/auth/login`

1. Body `{email, password}`; the `Email` type (D62) validates and lower-cases the address.
2. **Per-account limiter** (key = normalised e-mail, shared with the wizard; the primary control, D69): 5 failed password checks in 15 minutes → 429 `RATE_LIMITED` with `Retry-After`, before any database or hash work. A per-IP ceiling applies too, as a secondary limit.
3. Load the user. **Unknown e-mail → still verify the password against a constant dummy hash** so the response time does not reveal whether the account exists (the pattern in FastAPI's security tutorial) → record a failure → 401 `INVALID_CREDENTIALS`.
4. `verify_and_update(password, user.password_hash)`. Wrong → record a failure → 401 `INVALID_CREDENTIALS`.
5. `users.is_active = false` → 401 `INVALID_CREDENTIALS` with the same generic message (OWASP: do not reveal disabled accounts).
6. If pwdlib returns an updated hash (hash parameters changed), store it: transparent upgrade on login (OWASP Password Storage).
7. Clear the account's failure counter, issue the session token, set `bf_session`, return 200:

```json
{ "access_token": "<jwt>", "token_type": "bearer", "expires_in": 604800,
  "user": { "id": "6f1c0d3e-…", "email": "fatima.owner@bayflow.test", "full_name": "Fatima Raza", "phone": null } }
```

The body carries the account (`user`) but **no memberships** (D81): `/api/v1/auth/*` belongs to the identity module, the lowest module, which cannot read memberships (spec 01 dependency rules). The web calls `GET /api/v1/me` right after login and routes from that answer (spec 09 §2.8).

The `access_token` in the body exists for Swagger, curl and tests (D8); register-owner returns the same body, and booking creation the same token fields (D32). **The web app ignores it**: it never writes tokens to `localStorage` or `sessionStorage`, and the browser holds only the httpOnly cookie. If the day-1 check of D7 fails (cookie does not survive the rewrite), the fallback keeps the token **in memory only** and sends it as `Authorization: Bearer`.

A user whose memberships are all deactivated can still log in (they may be a customer); their `GET /api/v1/me` simply lists no memberships.

### Logout — `POST /api/v1/auth/logout`

1. POST only (never GET, so a link or `<img>` cannot trigger it; a GET gets 405 `METHOD_NOT_ALLOWED`). The API calls `delete_cookie("bf_session", path="/", secure=…, httponly=True, samesite="lax")` and returns 204. Verified header: `bf_session=""; expires=<past date>; HttpOnly; Max-Age=0; Path=/; SameSite=lax; Secure`. Idempotent: works with a missing or expired session.
2. The web clears its TanStack Query cache, closes the WebSocket and navigates to the landing page.
3. **Audit, best effort.** Logout never requires or rejects credentials, but reads them leniently: when the Bearer header (which wins) or else the cookie decodes to an active user, it publishes `LoggedOut` and the audit log records `auth.logged_out` (spec 19 §3.3); a missing, malformed or expired token is simply ignored. Any failure while recording (a database blip, an audit write) is caught, logged without the token (only the exception type), rolled back, and the route still answers 204 with the cookie expired.
4. **Rate limit.** 30 per minute per client IP (slowapi, like login; [Rate limiting](#rate-limiting)). A 429 leaves the cookie in place; the user retries.
5. **Stateless-JWT caveat.** Logout deletes the cookie; it does not revoke the token. A copy of the token (for example a Bearer token pasted into curl) stays valid until `exp`. Accepted for the hackathon because the browser's token is httpOnly (scripts cannot copy it), the web never stores the body token, and deactivation is still immediate (D9). Tier 2 adds `users.tokens_valid_after` for password change and "log out everywhere".

### Current user — `GET /api/v1/me`

```json
{
  "id": "6f1c0d3e-…",
  "email": "fatima.owner@bayflow.test",
  "full_name": "Fatima Raza",
  "phone": null,
  "memberships": [
    {
      "membership_id": "a0b1…", "shop_id": "c2d3…", "shop_name": "Lahore Auto Care",
      "shop_slug": "lahore-auto-care", "role": "OWNER",
      "capabilities": ["shop.manage", "team.manage", "services.manage", "parts.manage"]
    }
  ]
}
```

- Served by the shops module (`shops.service.get_me`, operation `shops_get_me`), because it combines the user with memberships (D66, D81; spec 03 §4.4). The web calls it on app load and right after login, owner registration and the booking wizard.
- Lists **active** memberships only. Drives post-login routing (memberships → POS of the chosen shop; none → customer area), the shop switcher and role-aware navigation.
- **`capabilities` (D66, glossary §2.4)** are computed on the server from the membership's role by one function, following the RBAC matrix that the route guards enforce ([Capabilities](#capabilities-d66)). The UI shows non-booking buttons (team, services, parts, stock, tasks) only from `capabilities`, and booking buttons only from `allowed_actions`; it never re-implements a permission rule. The bonus capability `tasks.manage` (Owner, SA) appears with the bonus `calls` module.
- The list and its capabilities are a **UX hint**: every shop route re-checks the membership and role on every request (D9), so a stale list can never grant access.
- Never contains `password_hash`, inactive memberships or another user's data. Each membership item is `{membership_id, shop_id, shop_name, shop_slug, role, capabilities}`; the exact schema belongs to spec 03.

### Shop creation — `POST /api/v1/shops` (D17)

Any authenticated user may create a shop. One transaction inserts the `shops` row and the caller's `shop_memberships` row (`role = OWNER`, `is_active = true`). The body has no owner or membership fields. The caller's memberships in other shops are untouched: a technician who opens their own garage is `OWNER` there and still only `TECHNICIAN` elsewhere (SEC-40). A per-user creation limit applies ([Rate limiting](#rate-limiting)).

### Staff accounts — created by the Owner (D18, D19)

`POST /api/v1/shops/{shop_id}/members`, body `{email, full_name, role, password?, phone?}`. `role` is a **`StaffRole`**: `SERVICE_ADVISOR`, `TECHNICIAN`, `PARTS_PERSON` or `QC_INSPECTOR`. The schema does not accept `OWNER` (422).

| Situation | Behaviour |
|---|---|
| E-mail not registered | `password` required (policy D10). User (Argon2id) and membership created in one transaction. The Owner hands the initial password to the person out of band. |
| E-mail belongs to an existing user with no membership in this shop | **Only the membership is created.** The user's `password_hash`, `full_name` and `phone` are never modified; a supplied `password` is ignored. The response flag `account_created: false` lets the UI say "they sign in with their existing password". The user is not asked for consent: a known gap accepted for the hackathon (D18); an invitation flow is Tier 3 (threat #12). |
| The user already has a membership here (active or inactive) | 409 `CONFLICT`: use PATCH to change the role or reactivate. |
| Caller is a member but not `OWNER` | 403 `FORBIDDEN` |
| Caller is not a member of `shop_id` | 404 `NOT_FOUND` |

`PATCH /api/v1/shops/{shop_id}/members/{membership_id}`, body `{role?: StaffRole, is_active?: bool}`:

- the membership must belong to `shop_id` (else 404);
- target is the `OWNER` membership → **403 `FORBIDDEN`**, whoever asks: it cannot be deactivated or re-roled (D19);
- deactivation takes effect on the member's **next request** (D9) and in realtime fan-out; their open bookings stay assigned (D19) until the SA uses `reassign-technician` / `reassign-parts-person` (P1);
- identity fields (e-mail, name, password) are not editable through memberships: they belong to the global user.

### Customer account inside the booking wizard — `POST /api/v1/bookings` (D32)

| Case | Session (cookie or Bearer) | E-mail in body | Password | Outcome |
|---|---|---|---|---|
| A | valid | ignored | ignored (field hidden in the UI) | Booking for the session user. Only `phone` may fill an empty `users.phone` (D33). Session re-issued (`account_created: false`). |
| B | none | not registered | required, policy D10 | User and booking created in one transaction; logged in (`account_created: true`). |
| C | none | registered, active account | correct | Account reused (rehash if needed); booking created; logged in (`account_created: false`). |
| D | none | registered | wrong, or the account is inactive | **409 `EMAIL_ALREADY_REGISTERED`; nothing is created**; counts as a failed password check for the per-account limiter. |

Security-relevant order inside the endpoint:

1. Rate-limit checks (D69): the per-account limiter for cases C and D is primary; per-IP (anonymous) and per-user (case A) limits are secondary ceilings.
2. Payload validation with `extra="forbid"`: `status`, `customer_user_id`, `reference`, `version` cannot be supplied; the e-mail is the `Email` type (D62).
3. Resolve the account. Password verification runs **before** the transaction takes the slot-counter lock, so Argon2 (~55 ms) never holds a row lock.
4. One transaction: create the user (case B), upsert the vehicle, lock and increment the slot counter, insert the booking … (spec 08 T01).
5. On **any** failure (409 `SLOT_FULL`, 422 `INVALID_SLOT`, …) the whole transaction rolls back, so case B never leaves an orphan account.
6. After commit, log the customer in (D32), in every successful case: set `bf_session` **and** return `access_token`, `expires_in` and `account_created` in the 201 body, so the Bearer fallback of D7 also works right after the wizard. The web app ignores the body token, exactly as after login.

Notes:

- `shop_id` in this body is the customer's **choice of shop**, not an authorization claim: it must be a listed shop, every service must belong to it (422, backed by the composite FK `booking_services` → `services`) and the slot must be on its grid. D20's "never trust a `shop_id` in a request body" is about staff authorization, which this endpoint never grants.
- Credentials that are present but invalid (for example an expired cookie) → 401 `UNAUTHENTICATED`, never a silent downgrade to cases B–D. The web keeps the wizard state and asks the user to log in again.
- The 409 in case D reveals that the e-mail is registered. This is an accepted trade-off: see [Threat model](#threat-model) #11.

### WebSocket ticket — `GET /api/v1/realtime/ticket`

1. The browser calls the ticket endpoint through the same-origin rewrite (cookie auth). The endpoint belongs to the **notifications** module, which runs the realtime hub (D70); it mints the ticket with `app.core.security.issue_token`.
2. The API returns `{ "ticket": "<jwt>", "expires_in": 60 }` with `Cache-Control: no-store`. The ticket is a JWT signed with `JWT_SECRET` carrying exactly `sub`, `iat`, `exp = iat + 60`, `typ = "ws"` (D70).
3. The browser opens `wss://<api-host>/api/v1/ws?ticket=<ticket>` **directly** (`NEXT_PUBLIC_WS_URL`, D7). The cookie does not exist on that host.
4. Before `accept()` the API: (a) rejects any `Origin` header other than `CLIENT_URL` (Cross-Site WebSocket Hijacking defence; clients that send no `Origin`, such as tests, still need a valid ticket); (b) decodes the ticket and requires `typ == "ws"`; (c) loads the user and checks `is_active`. Any failure → `close(code=1008)` (policy violation) before accept, which fails the handshake (verified). **Browsers do not see that 1008:** a close before accept makes the server refuse the upgrade with HTTP 403, which "may present on some browsers as … 1006, Abnormal Closure" ([ASGI spec, `websocket.close`](https://asgi.readthedocs.io/en/latest/specs/www.html)). Only a server-side client observes 1008: Starlette's `TestClient.websocket_connect` raises `WebSocketDisconnect` with code 1008 (verified on FastAPI 0.143.0 / Starlette 1.7.0), so SEC-33 and SEC-42 assert 1008 with that client, never with a browser. The web client therefore treats any failed open the same way: fetch a new ticket and retry with backoff (D70, spec 09).
5. After accept the socket is registered under the user's id. The ticket is used **only for the handshake** (D70): an accepted socket outlives the ticket's 60 seconds. Client → server messages are limited to `{"type": "ping"}`.
6. Every reconnect fetches a fresh ticket (D70). A 401 from the ticket endpoint means the session has expired, so the client runs the session-expired flow. Pushes sent while a socket was down are not replayed: after a reconnect the client refetches (spec 09 "Catch-up"), and the 15-second polling of D14 is the safety net.

**Why a ticket and not the cookie or the session JWT:** the cookie lives on the web host and is never sent to the API host; putting the 7-day session JWT in a URL would leak a long-lived credential into logs, because uvicorn logs the full path **including the query string** when it accepts a WebSocket (verified in uvicorn 0.54 source). A 60-second `typ = ws` ticket is useless for HTTP calls (`typ` mismatch → 401) and useless after a minute. OWASP prefers sending the token in the first WebSocket message; D70 locks the query-string form with these mitigations: 60-second lifetime, handshake-only use, redaction from logs (Tier 1) and single use (Tier 2).

**Realtime authorization is evaluated at publish time.** Recipients are computed after commit (D14) from live database state (active memberships, booking visibility). `booking.updated` — pushed after every booking event and after a parts change that writes none, such as a partial PO receipt reserving stock (D83) — goes **only** to the booking's customer and to shop members who can see the booking under D21 (SAs, the Owner, its technician, its parts person, QC inspectors while it is `QC_PENDING` / `QC_IN_PROGRESS` or if they inspected it; glossary §11). `notification.created` goes only to its recipient; bonus `call.*` and `task.created` follow spec 05 §8.4. A deactivated member's still-open socket therefore receives nothing new (Tier 1); Tier 2 also closes it.

---

## Tokens and cookies

### JWT format

| Item | Value |
|---|---|
| Algorithm | HS256 with `JWT_SECRET`. Decoding pins `algorithms=["HS256"]`; PyJWT refuses to decode without that list, and `alg: none` or any other algorithm is rejected (verified) |
| Header | `{"alg": "HS256", "typ": "JWT"}` (PyJWT default) |
| Payload | exactly `sub`, `iat`, `exp`, `typ` (D9). No e-mail, roles, shop IDs or permissions |
| `sub` | the user's UUID as a **string** (PyJWT 2.15 rejects a non-string `sub` — verified) |
| `iat`, `exp` | integer seconds since the epoch (UTC); `exp = iat + lifetime` |
| `typ` | `session` (cookie or Bearer) or `ws` (WebSocket ticket) |
| Lifetime | `session`: `JWT_EXPIRES_IN` (default `7d`); `ws`: 60 s |
| Validation | signature; all four claims required through `options={"require": ["sub", "iat", "exp", "typ"]}` (custom claims are supported — verified); `exp` in the future and `iat` not in the future, **both compared with the app clock** (D63; no leeway — the same server issues and checks); `typ` equals what the endpoint expects; `sub` parses as a UUID. Any failure → 401 `UNAUTHENTICATED`. PyJWT's built-in `exp`/`iat` checks use the system time (verified: a token issued under a frozen or simulated clock is judged against real time), so they are switched off with `verify_exp` / `verify_iat` = `False` (`require` still rejects a missing claim, and the signature is still checked — verified) and `decode_token` does them against the `now` it is given. `app.core` may not import `app.shared` (spec 01 rule 8), so `issue_token(…, now)` and `decode_token(token, now, expected_typ)` take `now` as an argument and every caller passes `app.shared.clock.utcnow()` |

```python
# app/core/security.py — sketch (AppError subclasses from app.core.errors, spec 01)
from datetime import datetime
from typing import Literal
from uuid import UUID

import jwt

from app.core.errors import Unauthenticated
# No import from app.shared (spec 01 rule 8): callers pass now = app.shared.clock.utcnow() (D63).

TokenType = Literal["session", "ws"]

def issue_token(user_id: UUID, typ: TokenType, lifetime_s: int, now: datetime) -> str:
    iat = int(now.timestamp())
    claims = {"sub": str(user_id), "iat": iat, "exp": iat + lifetime_s, "typ": typ}
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")

def decode_token(token: str, now: datetime, expected_typ: TokenType) -> UUID:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            # PyJWT would compare exp/iat with the system time; D63 compares them with the given `now` below
            options={"require": ["sub", "iat", "exp", "typ"], "verify_exp": False, "verify_iat": False},
        )
        ts = int(now.timestamp())
        if claims["exp"] <= ts or claims["iat"] > ts:
            raise jwt.InvalidTokenError("expired or not yet valid")
        if claims["typ"] != expected_typ:
            raise jwt.InvalidTokenError("unexpected token type")
        return UUID(claims["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:  # every PyJWT error subclasses InvalidTokenError
        raise Unauthenticated() from exc
```

### `JWT_EXPIRES_IN`

- Format: `<integer><unit>` with unit `s`, `m`, `h` or `d` (`7d`, `12h`, `90m`, `45s`), or a bare integer meaning seconds (`3600`). Pattern `^(\d+)([smhd]?)$`.
- Bounds: 300 s ≤ lifetime ≤ 30 days. Anything else (`""`, `0`, `7days`, `1w`, `-1d`) → the API refuses to start with a clear message.
- One parsed integer feeds both `exp` and the cookie's `Max-Age`, so cookie and token always expire together. The default `7d` gives 604800.

### The `bf_session` cookie (D8)

| Attribute | Value | Why |
|---|---|---|
| Name / value | `bf_session` = session JWT | glossary §9 |
| `HttpOnly` | always | JavaScript, including injected script, cannot read it |
| `Secure` | when `COOKIE_SECURE=true` (production must be `true`; startup check) | sent over HTTPS only |
| `SameSite` | `Lax` | not attached to cross-site POST, `fetch` or iframe requests; still attached to top-level GET navigations, so a link in an e-mail opens a logged-in page (with `Strict` it would not) |
| `Path` | `/` | the whole web origin |
| `Domain` | **not set** (host-only) | bound to the exact web host; required for the rewrite to work |
| `Max-Age` | token lifetime in seconds | cookie and token expire together |

Starlette call: `response.set_cookie("bf_session", token, max_age=lifetime_s, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax")`. Verified header (Starlette 1.7): `bf_session=<jwt>; HttpOnly; Max-Age=604800; Path=/; SameSite=lax; Secure`.

### Why the cookie only works through the same-origin rewrite (D7)

```
Browser ──HTTPS──▶ https://<web-host>/api/v1/auth/login        same origin as the page
                       │  Next.js rewrite → Vercel external rewrite (reverse proxy) to API_BASE_URL
                       ▼
                   https://<api-host>/api/v1/auth/login        Railway
                       │  Set-Cookie: bf_session=…; HttpOnly; Path=/; SameSite=Lax; Secure   (no Domain)
                       ▼
Browser stores bf_session for <web-host> and sends it on every later /api/* request to <web-host>.
The WebSocket goes straight to <api-host>: no cookie there → ticket instead.
```

- The browser only ever talks to the web origin, and `fetch` sends cookies to the same origin by default (`credentials: "same-origin"`). The API's `Set-Cookie` arrives in a response the browser attributes to `<web-host>`; without a `Domain` attribute the cookie is host-only for that host.
- Called directly, `<api-host>` would never receive the cookie (different host), and a cookie set by `*.up.railway.app` would be cross-site for pages on `*.vercel.app` (different registrable domains), which `SameSite=Lax` keeps off `fetch` requests.
- Day-1 verification (D7, spec 16): `Set-Cookie` passes through the rewrite and is stored host-only; the `Origin` header reaches the API unchanged (needed by the Tier 2 Origin check); which client IP the API sees (needed by [Rate limiting](#rate-limiting)).

### Cookie or Bearer — how the API chooses

| Request carries | Token used | Notes |
|---|---|---|
| `Authorization: Bearer <jwt>` (with or without the cookie) | the Bearer token | invalid → 401; **never falls back to the cookie** |
| `Authorization` with another scheme, or malformed | — | 401 `UNAUTHENTICATED` |
| only the `bf_session` cookie | the cookie | invalid or expired → 401, and the response clears the stale cookie |
| neither | — | 401 on protected routes; public routes never read credentials |

- Swagger UI (`/docs`) documents only the Bearer scheme (`HTTPBearer(auto_error=False)`): call login, copy `access_token`, click "Authorize". The cookie is read from `request.cookies`.
- Bearer requests cannot be forged cross-site: browsers never attach an `Authorization` header on their own.
- `/api/v1/internal/*` (bonus, D58) never accepts a session: it requires `AGENT_SERVICE_TOKEN` **and** the per-call `X-Agent-Call-Token`, and the service token is rejected everywhere else (SEC-36). See [Bonus: AI agent and LiveKit webhook](#bonus-ai-agent-and-livekit-webhook-d58).

### Expiry and the web client

- An expired or invalid token yields 401 `UNAUTHENTICATED` on the next API call.
- The central API client (spec 09) handles 401 for every call except the login form itself: clear the query cache, close the WebSocket, redirect to the login page with `next=<current relative path>`.
- After login, `next` is honoured only if it is a same-origin relative path: starts with `/`, does not start with `//`, contains no `\`. Anything else falls back to the default landing route (open-redirect defence, SEC-39).
- Next.js `proxy.ts` may redirect visitors without a `bf_session` cookie away from POS pages as a UX shortcut. It cannot validate the JWT (the web never holds `JWT_SECRET`) and is never relied on for security.

### Secrets and rotation

- `JWT_SECRET` is random and at least 32 bytes: RFC 7518 §3.2 requires an HS256 key of at least 256 bits, and PyJWT emits `InsecureKeyLengthWarning` below 32 bytes (verified). Generate with `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
- Startup checks when `APP_ENV=production`: refuse to start if `JWT_SECRET` is shorter than 32 bytes or **contains** a placeholder marker — `change-me` (the brief's sample), `replace-me` (`.env.example`'s `local-dev-secret-replace-me-with-random-chars`), `dev-only` (the built-in development secret) or `placeholder` (CI's `ci-placeholder-…`) (D85) — or if `COOKIE_SECURE` is not `true`. In development, log a warning instead.
- Rotation: change `JWT_SECRET` in the Railway variables and redeploy. Every session and ticket becomes invalid at once; users see one 401 and log in again. This is the "panic button" if the secret may have leaked. Graceful dual-key rotation (`kid`) is Tier 3.
- `AGENT_SERVICE_TOKEN` (bonus) is rotated in the `api` and `agent` services together.

### Bonus: AI agent and LiveKit webhook (D58)

Neither the AI agent nor LiveKit is a user: they never get a session or a membership, each has its own credential, and the **API, not the prompt, enforces the scope** (spec 05 §5.1, §8.5, §13).

**Internal routes `/api/v1/internal/calls/{call_id}/…`** — agent only. The router is not mounted when `AGENT_SERVICE_TOKEN` is blank, is excluded from the public OpenAPI schema (`include_in_schema=False`), and the web app's `/api/*` rewrite never proxies it (spec 07). Every request must pass all of these checks:

| Check | Rule | On failure |
|---|---|---|
| Service token | `Authorization: Bearer <AGENT_SERVICE_TOKEN>`, compared in constant time (`hmac.compare_digest`). Session JWTs are rejected here | 401 `UNAUTHENTICATED` |
| Per-call token | `X-Agent-Call-Token` must hash (SHA-256) to the call's `call_logs.ai_call_token_hash`. The random token travels only in the dispatch metadata; the API stores only its hash (D58, spec 02 §3.21) | 404 `NOT_FOUND` |
| AI call | The call has an AI leg (`ai_dispatched_at IS NOT NULL`) | 404 `NOT_FOUND` |
| Time window | Data and task endpoints only while the AI leg is open; `summary` until `ai_ended_at` + 10 minutes | 409 `CALL_NOT_ACTIVE` |
| Identity gate | Booking, estimate and reschedule endpoints require `ai_identity_verified_at` (set by `verify-caller`; locked after 3 failed attempts) | 403 `IDENTITY_NOT_VERIFIED` |
| Scope | Every query uses the `shop_id` and `customer_user_id` **read from the `call_logs` row**; bodies never carry them, and every ID the agent sends except the path's `call_id` is ignored | 404 `NOT_FOUND` |

A leaked `AGENT_SERVICE_TOKEN` alone therefore reads nothing, and a leaked per-call token works for one call, one customer, one shop and a few minutes. The agent sees only customer-visible estimate versions, can create tasks, and can never change a booking (spec 05 §13).

**Webhook `POST /api/v1/webhooks/livekit`** — no cookie; LiveKit Cloud calls the API host directly, not through Vercel. LiveKit puts a JWT in the `Authorization` header, signed with the project's API secret and carrying the SHA-256 of the body ([LiveKit webhooks](https://docs.livekit.io/home/server/webhooks/)). The handler reads the **raw** body and calls `WebhookReceiver(TokenVerifier(CALL_PROVIDER_API_KEY, CALL_PROVIDER_API_SECRET)).receive(body, authorization)` from `livekit-api` (D11): `TokenVerifier` decodes the JWT with HS256, the API key as required issuer and a required `exp`; `receive()` then compares the body's SHA-256 with the token's `sha256` claim and raises if the claim is missing or differs ([webhook.py](https://github.com/livekit/python-sdks/blob/main/livekit-api/livekit/api/webhook.py), [access_token.py](https://github.com/livekit/python-sdks/blob/main/livekit-api/livekit/api/access_token.py)). Any failure → 401 `UNAUTHENTICATED`, nothing processed. Handlers are idempotent and webhooks are only a safety net (spec 05 §3.6), so replaying a valid event changes nothing.

---

## Per-request checks (D9, D20, D21)

### Order

```
staff request  /api/v1/shops/{shop_id}/…
  0 route          the path exists in this endpoint family (e.g. no staff approve-estimate)  ✗ 404 NOT_FOUND
  1 authenticate   get_current_user: token → users row (fresh read) → is_active            ✗ 401 UNAUTHENTICATED
  2 tenant         require_shop_member(shop_id): caller's ACTIVE membership in shop_id       ✗ 404 NOT_FOUND
  2b suspension    the shop is suspended (D96), for every member, the Owner included        ✗ 403 SHOP_SUSPENDED
  3 role           require_roles(...) on management routes                                   ✗ 403 FORBIDDEN
  4 visibility     booking queries carry the D21 predicate                                    ✗ 404 NOT_FOUND
  5 booking rule   spec 08: actor role → assignment guard → status → data guards              ✗ 403 FORBIDDEN / 403 NOT_ASSIGNED / 409 / 422

customer request  /api/v1/me/…
  0 route (a staff-only slug such as confirm has no customer route → 404) → 1 authenticate
  → own-scope query (customer_user_id = caller, else 404) → suspended shop: every action but
  cancel → 403 SHOP_SUSPENDED (D96) → spec 08 rule for CUSTOMER

admin request  /api/v1/admin/…
  0 Fetch Metadata  Sec-Fetch-Site present and not same-origin / none (D98)               ✗ 403 FORBIDDEN
  1 authenticate    get_current_user                                                          ✗ 401 UNAUTHENTICATED
  2 platform admin  require_platform_admin: the re-read user's is_platform_admin (D94)        ✗ 403 FORBIDDEN
```

Step 0 is routing, before any dependency runs: action routes exist per endpoint family only for the slugs that family's actors can perform (spec 03 §5.1), so a slug outside the caller's family is an unknown path → 404, never 403.

D9 means two indexed reads per request (user by primary key, membership by `(shop_id, user_id)`; they may be one join) and **no caching across requests**.

### Dependencies (sketch)

```python
# app/shared/auth.py — sketch (spec 18 §7: app.shared holds the auth/tenant dependencies)
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import Forbidden, NotFound, Unauthenticated
from app.core.security import decode_token
from app.shared.clock import utcnow           # the single source of "now" (D63); app.core takes it as an argument

bearer_scheme = HTTPBearer(auto_error=False)  # documents "Authorize: Bearer" in Swagger

async def get_current_user(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: DbSession,
) -> User:
    if request.headers.get("authorization") is not None:
        if creds is None:                       # wrong scheme or malformed header
            raise Unauthenticated()
        token = creds.credentials               # Bearer wins; never fall back to the cookie
    else:
        token = request.cookies.get("bf_session")
        if token is None:
            raise Unauthenticated()
    user_id = decode_token(token, utcnow(), expected_typ="session")
    user = await identity_service.get_active_user(db, user_id)  # fresh read on every request (D9); None if missing or inactive
    if user is None:
        raise Unauthenticated()
    return user

@dataclass(frozen=True)
class ShopContext:
    shop_id: UUID
    user: User
    membership: ShopMembership
    role: MembershipRole

async def require_shop_member(
    shop_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: DbSession,
) -> ShopContext:
    membership = await shops_service.get_active_membership(db, shop_id=shop_id, user_id=user.id)
    if membership is None:      # unknown shop, other tenant, inactive membership, customer: all identical
        raise NotFound()
    return ShopContext(shop_id=shop_id, user=user, membership=membership, role=membership.role)

def require_roles(*roles: MembershipRole):
    async def dependency(ctx: Annotated[ShopContext, Depends(require_shop_member)]) -> ShopContext:
        if ctx.role not in roles:
            raise Forbidden()                   # the shop is visible to the caller; the role is wrong
        return ctx
    return dependency

def shop_scoped_router(**kwargs: Any) -> APIRouter:
    """Factory for every staff route group (D80): the prefix plus a router-level tenant check (D20)."""
    extra = list(kwargs.pop("dependencies", []))
    return APIRouter(prefix="/api/v1/shops/{shop_id}",
                     dependencies=[Depends(require_shop_member), *extra], **kwargs)

# app/modules/inventory/router.py:  router = shop_scoped_router(tags=["inventory"])
# Each module builds its own staff router this way, so no shop route can forget the tenant check.
# POST /api/v1/shops (create a shop) is the only /shops route outside it (spec 03 §1.3).
```

Verified behaviour (FastAPI 0.143):

- A dependency declared on the router runs for **every** route of that router, even a route that does not declare it itself.
- When the endpoint also declares `Depends(require_shop_member)` to receive the `ShopContext`, the dependency still executes **once** per request (per-request dependency cache).
- It raises 404 **before** body validation, so a cross-tenant probe never receives 422 details about the target, and the tenant sweep test (SEC-02) can call every route with an empty body.
- `get_optional_user` (for `POST /api/v1/bookings`) returns `None` when no credentials are sent and raises 401 when credentials are present but invalid.

Services receive `ShopContext` explicitly; they never read `shop_id` or a role from a request body.

### Booking visibility predicate (D21)

One function returns the SQL condition used by the list, detail and action-loading queries, so list and detail can never disagree:

| Caller | Condition (in addition to `bookings.shop_id = :shop_id`) |
|---|---|
| `OWNER`, `SERVICE_ADVISOR` | none — all bookings of the shop |
| `TECHNICIAN` | `technician_user_id = :me` |
| `PARTS_PERSON` | `parts_person_user_id = :me` |
| `QC_INSPECTOR` | `status IN ('QC_PENDING', 'QC_IN_PROGRESS')`, or a `qc_inspections` row of this booking was created by `:me` |
| Customer endpoints | `customer_user_id = :me` (no shop filter) |

Consequences that tests rely on:

- A technician or parts person never sees an unassigned booking → **404**, not 403 `NOT_ASSIGNED`. After a `reassign-*` the previous assignee gets 404.
- 403 `NOT_ASSIGNED` appears only where the booking is visible but the caller is not the assignee — in practice a QC inspector trying `pass-qc` or `fail-qc` on a job someone else picked.
- Visible booking, wrong role → 403 `FORBIDDEN` (Owner trying `start-inspection`; technician trying `confirm` on their own assigned booking).

---

## RBAC matrix

| Symbol | Meaning |
|---|---|
| ✅ | Allowed. In the `CUSTOMER` column always limited to the caller's **own** bookings. |
| ✅ (assigned only) | Allowed only for the booking's assigned technician / parts person, or the QC inspector who picked it. |
| 👁 | Read-only. |
| ❌ | Denied: 403 `FORBIDDEN` if the caller can see the resource, otherwise 404 `NOT_FOUND`. Every `/api/v1/shops/{shop_id}/…` route answers 404 to non-members (customers, staff of other shops). In table D, a slug that has no route in the caller's endpoint family is also 404: every staff-only slug in the `CUSTOMER` column, and `approve-estimate` / `reject-estimate` in the staff columns (spec 03 §5.1). |
| — | Not applicable (see the row's note). |

Columns are the caller's role **in the shop concerned**. A user with several hats is evaluated per request with the hat that the endpoint family and `shop_id` select.

### A. Account and shop management

| Capability | CUSTOMER | OWNER | SERVICE_ADVISOR | TECHNICIAN | PARTS_PERSON | QC_INSPECTOR |
|---|---|---|---|---|---|---|
| Log in / log out / `GET /api/v1/me` / own notifications / WS ticket | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Create a shop — caller becomes its `OWNER` (D17); other memberships unchanged | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| View shop profile and working hours in the POS | ❌ | ✅ | 👁 | 👁 | 👁 | 👁 |
| Update shop settings (name, address, phone, slot duration/capacity, logo URL, listing) | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Set working hours | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| View team | ❌ | ✅ (all, incl. inactive) | 👁 (active technicians and parts persons only, for the assign pickers) | ❌ | ❌ | ❌ |
| Add team member (D18) | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Change role / deactivate / reactivate a non-owner membership (D19) | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Change or deactivate the `OWNER` membership | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Services catalogue: create / update / deactivate | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Services catalogue: view | 👁 (public directory) | ✅ | 👁 | 👁 | 👁 | 👁 |
| Owner overview (bookings by status, team list, inventory summary) and multi-shop summary (P1) | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |

### B. Inventory and procurement (D44)

| Capability | CUSTOMER | OWNER | SERVICE_ADVISOR | TECHNICIAN | PARTS_PERSON | QC_INSPECTOR |
|---|---|---|---|---|---|---|
| Parts catalogue: create / edit (SKU, name, unit cost, reorder level, active) — never `on_hand` or `reserved` | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ |
| View parts with stock (on hand, reserved, available, low/out) | ❌ | 👁 | 👁 (estimate part picker, D40) | 👁 (estimate part picker, D40) | ✅ | ❌ |
| Stock adjustment (`ADJUST` movement, P0 by D82; opening stock too, since new parts start at 0 — never below `reserved` or 0: 409 `INSUFFICIENT_STOCK`, spec 02 §3.13) | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Create purchase order (general restock) | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Receive purchase order (`RECEIVE`; may fire `RECEIVE_PARTS`) | ❌ | ❌ | ❌ | ❌ | ✅ (any active Parts Person) | ❌ |
| View purchase orders and the stock-movement ledger | ❌ | 👁 | ❌ | ❌ | ✅ | ❌ |

### C. Booking visibility (D21) and dashboards

| Capability | CUSTOMER | OWNER | SERVICE_ADVISOR | TECHNICIAN | PARTS_PERSON | QC_INSPECTOR |
|---|---|---|---|---|---|---|
| List / view bookings (vehicle, services, estimates, history) | ✅ own, via `/api/v1/me/…` | ✅ all of the shop | ✅ all of the shop | ✅ (assigned only) | ✅ (assigned only) | ✅ QC queue (`QC_PENDING`, `QC_IN_PROGRESS`) + bookings they inspected |
| QC queue | ❌ | 👁 | 👁 | ❌ | ❌ | ✅ |
| Technician / Parts / QC dashboards (D16 support views) | ❌ | 👁 | — | ✅ own | ✅ own | ✅ own |

Data-exposure rules inside a visible booking: customers see only `SENT`, `APPROVED` and `REJECTED` estimate versions (never a technician's or SA's unsent `DRAFT`/`SUBMITTED`), and a status timeline without internal notes or `metadata` (customer-facing reasons such as a decline reason stay visible). Staff who can see a booking see all versions. Spec 03 defines the audience-specific schemas.

### D. Booking actions (glossary §4, rules in spec 08)

| Action (slug) | CUSTOMER | OWNER | SERVICE_ADVISOR | TECHNICIAN | PARTS_PERSON | QC_INSPECTOR |
|---|---|---|---|---|---|---|
| `CREATE` (`POST /api/v1/bookings`) | ✅ | — | — | — | — | — |
| `confirm` | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `decline` | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `assign-technician` | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `start-inspection` | ❌ | ❌ | ❌ | ✅ (assigned only) | ❌ | ❌ |
| `edit-estimate` (`PUT …/estimate`) | ❌ | ✅ in `ESTIMATE_REVIEW` | ✅ in `ESTIMATE_REVIEW` | ✅ (assigned only) in `INSPECTING` | ❌ | ❌ |
| `submit-estimate` | ❌ | ❌ | ❌ | ✅ (assigned only) | ❌ | ❌ |
| `send-estimate` | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `approve-estimate` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `reject-estimate` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `revise-estimate` | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `return-to-technician` | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `assign-parts-person` | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `order-parts` | ❌ | ❌ | ❌ | ❌ | ✅ (assigned only) | ❌ |
| `mark-parts-ready` | ❌ | ❌ | ❌ | ❌ | ✅ (assigned only) | ❌ |
| `RECEIVE_PARTS` (via PO receive) | ❌ | ❌ | ❌ | ❌ | ✅ (any active Parts Person) | ❌ |
| `allocate-parts` | ❌ | ❌ | ❌ | ❌ | ✅ (assigned only) | ❌ |
| `start-repair` | ❌ | ❌ | ❌ | ✅ (assigned only) | ❌ | ❌ |
| `send-to-qc` | ❌ | ❌ | ❌ | ✅ (assigned only) | ❌ | ❌ |
| `pick-qc` | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ (any active QC Inspector; not the booking's technician, D47) |
| `pass-qc` | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ (assigned only = the picker) |
| `fail-qc` | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ (assigned only = the picker) |
| `notify-ready` | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `complete` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `cancel` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `reassign-technician` (P1) | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `reassign-parts-person` (P1) | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |

Notes:

- The Owner column equals the SA column for every SA action and is ❌ for every technician, parts and QC action (D16, spec 08 SM-16). The Owner sees every booking, so those denials are 403 `FORBIDDEN`.
- `CREATE` is not a staff capability: staff book their own car through the customer flow, as customers (spec 08 "Who is the actor?").
- **A slug that does not exist in the caller's endpoint family is 404 `NOT_FOUND`, not 403** (spec 03 §5.1): the customer family (`/api/v1/me/bookings/{booking_id}/actions/…`) has routes only for `approve-estimate`, `reject-estimate`, `cancel` and `complete`, and the staff family has none for `approve-estimate` or `reject-estimate`. So a customer calling `confirm` on their own booking, or an SA or the Owner calling `approve-estimate`, gets 404 before any check runs. 403 `FORBIDDEN` stays for a wrong role inside a family (a technician calling `confirm`, the Owner calling `pick-qc`); another customer's booking is 404 as always.
- Each booking response's `allowed_actions` is computed from the same rule table (spec 08), so the UI shows exactly the ✅ cells for the current status. Non-booking buttons follow `capabilities` ([Capabilities](#capabilities-d66)).
- Bonus calls, AI summaries and tasks are in [E](#e-calls-and-tasks-bonus-d21) and reuse these dependencies. The AI agent never acts as a user: it has no session or membership and reaches data only through the internal routes ([Bonus: AI agent and LiveKit webhook](#bonus-ai-agent-and-livekit-webhook-d58)).

### E. Calls and tasks (bonus, D21)

Spec 05 §8 owns the endpoints; this is who may use them.

| Capability | CUSTOMER | OWNER | SERVICE_ADVISOR | TECHNICIAN | PARTS_PERSON | QC_INSPECTOR |
|---|---|---|---|---|---|---|
| Start a call from a booking | ✅ own booking (to the shop) | ✅ (to the customer) | ✅ (to the customer) | ❌ | ❌ | ❌ |
| Accept / decline a ringing call | ✅ calls from the shop to them | ✅ customer calls to the shop **only when the shop has no active SA** — the Owner is then the eligible callee (spec 05 §3.3, D26) | ✅ customer calls to the shop (any active SA is an eligible callee, rung or not) | ❌ | ❌ | ❌ |
| Hang up | ✅ as a participant | ✅ as a participant | ✅ as a participant | ❌ | ❌ | ❌ |
| View call logs | ✅ own calls on own bookings | ✅ all calls of the shop | ✅ all calls of the shop | ❌ | ❌ | ❌ |
| View AI call summaries and transcripts | ❌ | 👁 | 👁 | ❌ | ❌ | ❌ |
| View tasks, mark a task done (`tasks.manage`) | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |

- Technicians, Parts Persons and QC Inspectors get 403 `FORBIDDEN` on the call and task collections and 404 on single items (spec 05 §8.2): calls and tasks are not their work (D21).
- Customers reach calls only through `/api/v1/me/…`, scoped by `call_logs.customer_user_id`; another customer's call or booking → 404. They do not see AI summaries or transcripts.
- No call or task object contains a phone number or e-mail (brief §8.1, spec 05 §8.3).

### Capabilities (D66)

`GET /api/v1/me` returns, per membership, the capabilities computed on the server from its role (glossary §2.4). Each one names a group of ✅ cells above; read-only (👁) views are not capabilities, and booking buttons come only from `allowed_actions`.

| Capability | Granted to | RBAC cells it stands for | Route guard |
|---|---|---|---|
| `shop.manage` | `OWNER` | A: update shop settings, set working hours | `require_roles(OWNER)` |
| `team.manage` | `OWNER` | A: full team list, add a member, change role / deactivate / reactivate | `require_roles(OWNER)` |
| `services.manage` | `OWNER` | A: create / update / deactivate services | `require_roles(OWNER)` |
| `parts.manage` | `OWNER`, `PARTS_PERSON` | B: parts catalogue create / edit | `require_roles(OWNER, PARTS_PERSON)` |
| `stock.manage` | `PARTS_PERSON` | B: stock adjustment, create PO, receive PO | `require_roles(PARTS_PERSON)` |
| `tasks.manage` *(bonus)* | `OWNER`, `SERVICE_ADVISOR` | E: view tasks, mark done | `require_roles(OWNER, SERVICE_ADVISOR)` |

The role → capability table lives in the shops domain (`shops/domain/capabilities.py`, spec 01), because `shops.service.get_me` computes it and the shops service may not import `app.shared.auth` (spec 01 rule 8); its role sets are exactly the ones the route guards pass to `require_roles`. Capabilities are hints like the membership list: the routes keep their guards and re-check every request (D9), so a stale or forged capability grants nothing (SEC-46).

---

## Tenant isolation — defence in depth (D20)

| Layer | Where | Guarantees | Why it fails safe |
|---|---|---|---|
| 1. Route dependency | `require_shop_member`, attached at router level by `app.shared.auth.shop_scoped_router()` to every `/api/v1/shops/{shop_id}` router (D80) | The caller has an **active** membership in the path's shop, re-read on every request | Declared on the router by the factory: a new route cannot forget it |
| 2. Repositories | Every repository method on shop-owned tables takes a keyword-only, non-optional `shop_id` (e.g. `get_for_update(*, shop_id, booking_id)`) | All SQL on shop data includes `WHERE shop_id = :shop_id`; there is no "get by id" without a shop | mypy flags a missing argument; review rule: no unscoped query on shop-owned tables |
| 3. Database | Composite FKs `(shop_id, parent_id) → parent (shop_id, id)` (spec 02) | A Shop A row cannot reference a Shop B booking, service, part, PO or member, even if application code is wrong | PostgreSQL enforces it on every write |
| 4. Tests | Tenant-isolation suite SEC-01…SEC-03 | Every shop route returns 404 for another tenant | Routes are enumerated from the OpenAPI schema, so new routes are covered automatically |
| + Realtime, notifications | Recipients computed at publish time (glossary §11); each notification row is addressed to one user and stores that user's `recipient_role` and a server-computed relative `link` (D67) | No cross-tenant pushes; a link never comes from input and still passes every route check when opened (a booking the user can no longer see → 404) | Uses live membership state |

**Why 404 and not 403.** The brief accepts either (§7.1). BayFlow returns 404 `NOT_FOUND` for everything outside the caller's tenant or visibility, with an **identical body** whether the record does not exist or belongs to someone else, so status codes cannot be used to learn which shop or booking IDs exist. 403 is reserved for resources the caller can already see (glossary §10 check order). Timing does not differ either: the lookup is one query already scoped by `shop_id` and visibility; BayFlow never loads a record globally and compares tenants afterwards.

**IDs.** All primary keys are UUID v4 (122 random bits), which makes guessing impractical, but **security never relies on unguessable IDs**: OWASP's IDOR guidance treats random identifiers as defence in depth, not access control, and the brief demands isolation "even by guessing IDs". The isolation tests therefore use the other tenant's **real** IDs. Booking references (`BF-XXXXXX`, 30 bits) and PO numbers are human identifiers, not secrets: no endpoint grants access because the caller knows a reference (bonus AI lookups are scoped to the call's customer, D58).

**Not isolated by design.** Users are global: the owners of a shop where a user is staff or customer see that user's name and contact details as needed for the job. Customers' vehicles are global (D35) but only reachable through the customer's own endpoints or a visible booking.

---

## Threat model

| # | Threat | Example against BayFlow | Mitigation | Tests |
|---|---|---|---|---|
| 1 | IDOR / guessed IDs | Imran (technician) requests a booking assigned to another technician, using an ID copied from a notification or guessed | D21 predicate in every booking query → 404; UUID v4 is only an extra layer; references are not secrets | SEC-08…SEC-11, SEC-34 |
| 2 | Cross-tenant access | Bilal (SA, Lahore Auto Care) swaps `shop_id` for another shop, or keeps his `shop_id` and uses a Shop B booking ID | Router-level membership dependency (404); `shop_id`-scoped repositories; composite FKs | SEC-01…SEC-03 |
| 3 | Privilege escalation via request body (mass assignment) | `{"role": "OWNER"}` on register-owner; a member PATCH with `role: OWNER`; a booking body with `status` or `customer_user_id`; a part with `on_hand` | One DTO per use case with `extra="forbid"` (OWASP Mass Assignment); `StaffRole` excludes `OWNER`; status changes only through actions; role and shop always come from the database, never the body (D20) | SEC-15…SEC-17 |
| 4 | Staff self-sign-up | Someone signs up claiming to be a Lahore Auto Care technician | No endpoint creates a non-owner membership except the Owner-only add-member; register-owner and the wizard create bare users | SEC-16 |
| 5 | Deactivated staff with a valid 7-day token | A dismissed technician keeps using the app | D9: membership and `is_active` re-read per request; realtime recipients from live state | SEC-13 |
| 6 | Owner-membership removal or a second owner | Owner deactivates or re-roles their own `OWNER` membership; a second `OWNER` is added | 403 `FORBIDDEN` on the `OWNER` membership; `StaffRole` schema; partial unique index; no DELETE | SEC-15 |
| 7 | Escalation through D17 | A technician creates their own shop hoping to gain owner rights in Lahore Auto Care | Ownership is per shop: the new `OWNER` membership covers only the new shop | SEC-40 |
| 8 | CSRF with cookie auth (incl. login/logout CSRF) | `evil.example` auto-submits a form to `https://<web-host>/api/v1/me/bookings/{id}/actions/cancel`; a link on another site opens `https://<web-host>/api/v1/admin/users/{id}` in a signed-in admin's browser (a `GET` that writes `admin.user_viewed`) | `SameSite=Lax`; no state change on GET except the admin API's audited reads, which refuse cross-site requests (D98: `Sec-Fetch-Site` present and not `same-origin`/`none` → 403 `FORBIDDEN` on every `/api/v1/admin/*` route); JSON-only bodies (FastAPI strict content type); CORS allowlist; Tier 2 Origin/Fetch-Metadata check for the rest — see [CSRF in detail](#csrf-in-detail) | SEC-23, SEC-30, SEC-31, SEC-41; `tests/modules/admin/test_authorization.py` (cross-site) |
| 9 | XSS → token theft or forged actions | `<script>` in `customer_notes`, a shop name, a QC issue or an AI call summary | React escapes rendered text; `dangerouslySetInnerHTML` banned (ESLint `react/no-danger`); user and AI text rendered as text only; `logo_url` limited to `https://`; httpOnly cookie; CSP (baseline Tier 1, full Tier 2) | SEC-23, SEC-32 |
| 10 | Brute force / credential stuffing | A script tries passwords for `fatima.owner@bayflow.test`, or uses the wizard's password check as an oracle | Per-account failure limiter shared by login and wizard (primary, D69); per-IP ceilings (secondary); Argon2id cost; generic errors | SEC-22, SEC-27 |
| 11 | User enumeration and account squatting | Probing which e-mails exist via login, wizard 409, register-owner 409, add-member; or booking first with someone else's e-mail | Login: generic 401 plus dummy-hash timing. Wizard, register-owner and add-member **disclose existence by necessity** (the brief requires reuse-by-e-mail; OWASP notes registration-style enumeration cannot always be avoided) — rate-limited, and the per-account limiter treats unknown e-mails like known ones. No e-mail verification in scope → squatting accepted; Tier 3 adds verification and reset | SEC-22, SEC-27 |
| 12 | Unconsented staff attach (D18) | A malicious owner adds `victim@…` as staff to learn the name or spam notifications | Owner-only, rate-limited per shop; the membership gives the attacker nothing beyond the victim's name; password untouched. **Accepted for the hackathon (D18)**; Tier 3: invitation acceptance | SEC-21, SEC-27 |
| 13 | SQL injection | `?status=PENDING' OR '1'='1` | SQLAlchemy bound parameters only; enum and allowlist validation for filters and sort keys (column names cannot be bound) | SEC-29 |
| 14 | Sensitive data in logs | Password echoed in a logged 422; JWT in a logged header; ticket in the WS accept log; SQL parameters | See [Logging, errors and secrets](#logging-errors-and-secrets) | SEC-29, SEC-38 |
| 15 | Secret leakage | `.env` committed; placeholder `JWT_SECRET` in production; a secret in a `NEXT_PUBLIC_*` variable | `.env` git-ignored; placeholders only in `.env.example`; production startup checks; nothing secret is ever `NEXT_PUBLIC_*` | SEC-37 |
| 16 | Forged or replayed tokens | `alg: none`; a token signed with HS512; a WS ticket used as a session; a stolen Bearer token | Pinned algorithm, required claims, `typ` separation; httpOnly cookie; short ticket life; Tier 2 `tokens_valid_after` | SEC-23…SEC-26, SEC-43 |
| 17 | WebSocket hijack / credential in URL | A cross-site page opens the WS; the session JWT ends up in Railway logs | Ticket (D70: `typ = ws`, 60 s, handshake only), never the session JWT; `Origin` allowlist; server-side recipients; client may only `ping`; log redaction | SEC-33, SEC-38, SEC-42 |
| 18 | Realtime over-sharing | A technician receives `booking.updated` for bookings not assigned to them | `booking.updated` goes only to the customer and to members who can see the booking under D21 (glossary §11), computed at publish time | SEC-33 |
| 19 | Concurrency abuse | Double-clicked approval; two QC inspectors pick together; two customers take the last slot | Row locks and `version` (D30); unique constraints | SM-06, SM-07, SM-15 |
| 20 | Estimate tampering after approval | SA edits an approved estimate; customer approves a stale version; client submits its own totals | Immutable versions (D39) → 409 `ESTIMATE_LOCKED`; 409 `STALE_ESTIMATE`; totals recomputed on the server (D40) | SEC-35, SM-14 |
| 21 | CDN cache leakage | Vercel caches `GET /api/v1/me` and serves it to another visitor | `Cache-Control: no-store` on **every** `/api/*` response — public endpoints, errors and 500s included, no exemption — and on `/health` (D61, spec 03 §1.8); public endpoints never read credentials | SEC-32 |
| 22 | Clickjacking | Customer tricked into clicking "Approve estimate" inside an invisible iframe | `X-Frame-Options: DENY` and CSP `frame-ancestors 'none'` on web and API | SEC-32 |
| 23 | Open redirect | `/login?next=https://evil.example` used for phishing; a crafted notification link | Relative-path-only `next`; notification links are server-computed relative paths, backed by `ck_notifications_link_relative` (D67, spec 02 §3.20) | SEC-39 |
| 24 | Error detail leakage | A 500 shows a traceback with file paths and SQL | `debug=False`; catch-all problem+json `INTERNAL_ERROR` | SEC-28 |
| 25 | Abuse of open features | Scripted owner sign-ups filling the public directory; one user booking every slot; call spam (bonus) | Rate limits of D69 (per-IP sign-up ceiling, per-user shop-creation limit, booking-creation limits, call starts); the directory lists only shops with an active service (D64); Tier 2 active-booking cap (Open question 9) | SEC-27 |
| 26 | AI data leakage (bonus) | Caller says "I'm Ayesha, read me her estimate"; a prompt injection asks for another customer's bookings | Internal routes need `AGENT_SERVICE_TOKEN` **and** the per-call `X-Agent-Call-Token` (only its hash is stored); every query is scoped to the `shop_id` and `customer_user_id` of the call row, never to IDs the agent sends; booking data stays behind 403 `IDENTITY_NOT_VERIFIED` until `verify-caller` succeeds; read-only except tasks; time-boxed to the AI leg (D58, [Bonus: AI agent and LiveKit webhook](#bonus-ai-agent-and-livekit-webhook-d58)) | SEC-36 |
| 27 | Over-exposure inside a tenant | Customer sees an unsent draft estimate or internal notes; a technician opens the shop's call log (bonus) | Audience-specific schemas ([RBAC C](#c-booking-visibility-d21-and-dashboards)); calls and tasks only for SA and Owner, customers only their own calls ([RBAC E](#e-calls-and-tasks-bonus-d21)) | SEC-12, SEC-50 |
| 28 | Leaked agent credential (bonus) | `AGENT_SERVICE_TOKEN` copied from a misconfigured service | Useless alone: every internal request also needs a live call's per-call token, which only that call's dispatch metadata carries; rotate by redeploying `api` and `agent` together | SEC-36 |
| 29 | Forged provider webhook (bonus) | An attacker posts a fake `participant_left` / `room_finished` to end calls | `WebhookReceiver` checks the HS256 JWT (API key as issuer, API secret as key) and the body's SHA-256 → 401 on any mismatch; handlers idempotent; webhooks are only a safety net | SEC-49 |

### CSRF in detail

1. **`SameSite=Lax`, set explicitly.** Browsers do not attach `bf_session` to cross-site POST/PUT/PATCH/DELETE, `fetch` or iframe requests — only to top-level GET navigations. Chrome's two-minute "Lax+POST" exception applies only to cookies set **without** a SameSite attribute, so it does not apply here. `vercel.app` is on the Public Suffix List, so other Vercel-hosted apps are cross-site.
2. **No state change on GET.** Every mutating endpoint uses POST/PUT/PATCH/DELETE (OWASP: Lax does not protect state-changing GETs); a method that a path does not support gets 405 `METHOD_NOT_ALLOWED` (glossary §10). The WS ticket GET creates no server state. The one exception is the admin API's audited reads (E-67, E-73, E-75 write an audit row on GET, D95), so the whole admin router refuses cross-site requests (point 6).
3. **JSON-only bodies.** FastAPI's default `strict_content_type=True` (since 0.132) parses a body only when `Content-Type` is `application/json` or `application/*+json`. `text/plain`, form-encoded and missing content types are rejected with 422 (verified). A cross-origin page can only send a JSON body with `fetch`, which triggers a CORS preflight. Never set `strict_content_type=False`.
4. **CORS allowlist.** `CORSMiddleware(allow_origins=[CLIENT_URL], allow_credentials=True, allow_methods=[…explicit…], allow_headers=["Content-Type", "Authorization"])` — explicit lists, because wildcards are not allowed with credentials (FastAPI docs). Preflights from other origins receive no `Access-Control-Allow-Origin`, so the browser never sends the real request. Note (verified): CORS **does not stop a simple cross-origin request from executing** — it only hides the response — which is why points 1–3 carry the protection.
5. **Tier 2 — Origin / Fetch Metadata check.** For unsafe methods authenticated by the cookie (no `Authorization` header), reject with 403 `FORBIDDEN` when `Sec-Fetch-Site: cross-site`, or when an `Origin` header is present and not equal to `CLIENT_URL` (including `null`). Browsers send `Origin` on same-origin POST/PUT/PATCH/DELETE (MDN), so our own `fetch` calls pass; Swagger runs on the API host without the cookie, so it is unaffected. This closes login/logout CSRF and attacks from sibling subdomains if a custom domain is ever used.
6. **Built — the admin API's Fetch Metadata check (D98).** Every `/api/v1/admin/*` route, whatever the method or credential, runs `app.shared.auth.refuse_cross_site_requests` first: a `Sec-Fetch-Site` header that is present and is not `same-origin` or `none` (so `cross-site`, `same-site`, or any other value) → 403 `FORBIDDEN`, "Admin requests must come from the BayFlow app.", before authentication and before anything is read or written. The web calls the API same-origin through the Vercel rewrite (D7), so its requests carry `same-origin`; an address typed in the bar sends `none`; clients that send no Fetch Metadata (curl, Swagger, tests, server-to-server) pass. Browsers that predate Fetch Metadata are covered by points 1–4 for writes; for the audited GETs only the admin's own click on a crafted link remains, which costs one audit row and no data.

---

## Rate limiting

D69: login, logout, owner registration, booking creation, shop creation, member creation and (bonus) call starts are rate-limited → 429 `RATE_LIMITED`. **Per-account (e-mail) failure limits are the primary control**; per-IP limits are only a secondary ceiling, because behind the Vercel rewrite many users can share egress IPs.

| Limiter | Key | Starting limit | Applies to | Implemented with |
|---|---|---|---|---|
| Failed password checks | normalised e-mail | 5 failures / 15 min (moving window); cleared on success | login; wizard cases C and D; Tier 2 password change | `limits` (`MovingWindowRateLimiter` + `MemoryStorage`) called directly in the identity service |
| Login requests | client IP | 30 / minute | `POST /api/v1/auth/login` | slowapi decorator |
| Logout requests | client IP | 30 / minute | `POST /api/v1/auth/logout` (it writes an audit row; a 429 leaves the cookie in place) | slowapi decorator |
| Owner sign-up | client IP | 20 / hour | `POST /api/v1/auth/register-owner` | slowapi decorator |
| Anonymous booking creation | client IP | 20 / minute | `POST /api/v1/bookings` without a session | slowapi decorator |
| Authenticated booking creation | user id | 30 / hour | wizard case A | `limits` in the bookings service |
| Shop creation | user id | 10 / day | `POST /api/v1/shops` | `limits` in the shops service |
| Member creation | shop id | 30 / hour | `POST /api/v1/shops/{shop_id}/members` | `limits` in the shops service |
| *(bonus)* Call starts | caller (user id) | 5 / 10 minutes | `POST …/bookings/{booking_id}/calls` (customer and staff) | Counted from `call_logs` in the calls service (spec 05 §11.3), so it survives restarts |

- **Response:** 429 `application/problem+json` with `code: RATE_LIMITED` and a `Retry-After` header — a custom handler for slowapi's `RateLimitExceeded` (verified), and `get_window_stats(...).reset_time` for the `limits` counters.
- **A blocked account gets 429 even for the correct password** until the window frees (otherwise the limiter is useless). Unknown e-mails are counted exactly like known ones, so the 429 is not an enumeration signal. The window is short and there is no permanent lockout, bounding the lock-out-a-victim abuse (OWASP: tie lockout to the account, avoid permanent lockout).
- **Storage** is in memory: one API replica (D14). Counters reset on redeploy, which is acceptable. Scaling out means Redis storage, which both libraries support.
- **Client IP** = `X-Real-IP`, which Railway's edge sets to the client's IP (Railway docs) and overwrites when a caller supplies it (Railway moderator answer — community-confirmed, not official docs); fallback `request.client.host` locally. **Caveat:** requests through the Vercel rewrite reach Railway from Vercel's servers, so `X-Real-IP` may be a Vercel egress address shared by many visitors. Per-IP limits are therefore generous ceilings, never the primary brute-force control — the per-account limiter is. Day-1 check: log the observed `X-Real-IP` / `X-Forwarded-For` for one request through the rewrite and one direct, then tune (spec 16).
- **slowapi caveats** (docs): the endpoint must take `request: Request`; the route decorator goes above `@limiter.limit`; WebSockets are not supported (the handshake is protected by the ticket instead). slowapi 0.1.10 (released 2026-06-13) works with FastAPI 0.143 (verified).
- Limits are constants in `app.core.security`, not environment variables.
- **Time source.** slowapi and `limits` keep their windows on the system time (`limits` 5.8.0 `MemoryStorage` calls `time.time()` — checked in its source), not on the D63 clock. They are infrastructure counters, not stored business times, so tests reset them (`clear()` or a fresh storage) instead of moving the clock; see Open question 14.

---

## Hardening tiers

### Tier 1 — must ship

| # | Item | Where |
|---|---|---|
| 1 | Argon2id via `pwdlib` `PasswordHash.recommended()`; hashing off the event loop with a small concurrency cap; dummy-hash timing equalisation; rehash on login | `app.core.security` |
| 2 | JWT HS256 with pinned algorithm, required claims and `typ` separation; `iat`/`exp` issued and checked with the D63 clock; production startup checks for `JWT_SECRET` and `COOKIE_SECURE`; strict `JWT_EXPIRES_IN` parsing | `app.core.security`, `app.core.config` |
| 3 | `bf_session` cookie flags exactly as above; Bearer for tools; web never stores tokens | identity module, web API client |
| 4 | Per-request D9 checks; router-level `require_shop_member` through `shop_scoped_router()` (D80); `require_roles`; D21 predicate; spec 08 guards | `app.shared.auth`, modules |
| 5 | Validation: per-use-case Pydantic DTOs with `extra="forbid"`, `StaffRole`, the `Email` type (D62), length limits; FastAPI strict JSON content type kept on | all routers, `app.shared.email` |
| 6 | Rate limiting as in [Rate limiting](#rate-limiting) (D69) | identity, shops, bookings; calls (bonus) |
| 7 | Security headers on web and API, incl. `Cache-Control: no-store` on every `/api/*` response and on `/health` (D61) | `next.config.ts`, API middleware |
| 8 | CORS allowlist `[CLIENT_URL]` with credentials and explicit methods/headers | API app factory |
| 9 | Errors: RFC 9457 problem+json; `debug=False`; 422 without `input`; unhandled exceptions rendered as 500 by the request-context middleware itself, so the 500 keeps `Cache-Control` and `X-Request-ID` (the `Exception` handler is only a backstop) | `app.core.errors`, `app.core.error_handlers`, `app.core.middleware` |
| 10 | Log hygiene: no auth bodies or credential headers; ticket redaction filter; SQLAlchemy `hide_parameters=True`; uvicorn `--no-server-header` | `app.core.logging`, `app.core.database`, Dockerfile |
| 11 | Secrets in environment variables only; `.env` git-ignored; `.env.example` placeholders | repo root (spec 07) |
| 12 | WebSocket ticket (D70: `typ = ws`, 60 s, handshake only, 1008 on rejection, new ticket per reconnect, redacted from logs), `Origin` allowlist, publish-time recipients filtered by visibility (glossary §11), `wss://` in production. The realtime layer is **P1** (D88): these rules are mandatory from the moment `/api/v1/ws` ships, never a later hardening step | notifications module (ticket endpoint and realtime hub, D70) |
| 13 | SEC-01…SEC-40, SEC-44…SEC-46 and SEC-48 green in CI (SEC-33 and the ticket part of SEC-38 once the P1 WebSocket ships, D88; bonus SEC-36, SEC-49, SEC-50 with the bonus; SEC-47 is P1) | spec 12 |
| 14 | Request-body size cap: 64 KiB, 256 KiB for the bonus agent summary route → 413 `PAYLOAD_TOO_LARGE` (part of the API contract, spec 03 §1.10) | small pure-ASGI middleware |

### Tier 2 — if time permits

| # | Item |
|---|---|
| 1 | Full CSP: ship as `Content-Security-Policy-Report-Only`, walk the demo script with DevTools open, fix violations, then enforce |
| 2 | Origin / `Sec-Fetch-Site` check for cookie-authenticated unsafe requests → 403 `FORBIDDEN` (SEC-41). Already built for `/api/v1/admin/*` (D98, [CSRF in detail](#csrf-in-detail) point 6) |
| 3 | ~~Auth audit trail as structured log events (no new table)~~ — superseded by D95: the persisted `audit_events` log (spec 19 §3) records these, admin actions and booking activity |
| 4 | Password change `POST /api/v1/me/password` (current + new password, per-account limiter) that sets `users.tokens_valid_after` to the clock's now (D63) so tokens with an older `iat` are rejected, then re-issues the caller's cookie (SEC-43). A judge who changes a demo password locks the others out until the next seed run, which restores the demo password hash (D60) |
| 5 | Single-use WS tickets (D70 makes them Tier 2): in-memory set of consumed ticket hashes until expiry (one replica, D14) — no new claim needed (SEC-42) |
| 6 | Realtime hub closes a user's sockets when a membership is deactivated, and every socket older than the session lifetime |
| 7 | Common-password blocklist (small local list; NIST SP 800-63B-4 makes a blocklist a SHALL); the demo password must not be on it |
| 8 | *(Moved to Tier 1 #14: the request-body size cap is part of the API contract, spec 03 §1.10.)* |
| 9 | CI: secret scanning of the git history (e.g. gitleaks) and dependency audit (`pip-audit`, `pnpm audit`) |
| 10 | Active-booking cap per customer per shop against slot hoarding — if the product owner agrees (Open question 9) |

### Tier 3 — deferred (documented, not built)

- Password reset by e-mail with single-use, short-lived tokens (SMTP is optional).
- E-mail verification for new accounts (closes account squatting).
- Invitation acceptance before an existing user becomes staff (closes threat #12).
- MFA (TOTP) for owners.
- Short-lived access tokens with refresh-token rotation and reuse detection.
- Account lockout with an unlock flow, beyond the sliding-window limiter.
- Nonce-based CSP via `proxy.ts` (forces dynamic rendering of every page — Next.js docs).
- JWT key rotation with `kid` and a dual-key window.
- `__Host-` cookie prefix (requires renaming `bf_session`, a glossary change).
- Redis-backed rate limits and WebSocket hub for more than one replica.
- Session/device list and "log out everywhere" UI.

### Security headers (Tier 1 values)

**Web** — `apps/web/next.config.ts` (headers apply to every path, including the rewritten `/api/*`):

```ts
import type { NextConfig } from 'next'

const securityHeaders = [
  { key: 'X-Frame-Options', value: 'DENY' },
  // Only directives that cannot break the app; the full policy is Tier 2.
  { key: 'Content-Security-Policy', value: "frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'" },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' }, // bonus calling: microphone=(self)
]

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async headers() {
    return [{ source: '/(.*)', headers: securityHeaders }]
  },
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${process.env.API_BASE_URL}/api/:path*` }]
  },
}

export default nextConfig
```

- HSTS: Vercel serves deployments over HTTPS only and already sends `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload` on `*.vercel.app` (verified). Set it explicitly only for a custom domain.
- Values follow the OWASP HTTP Headers Cheat Sheet (`DENY`, `nosniff`, `strict-origin-when-cross-origin`). Keep `strict-origin-when-cross-origin` on the web origin: `no-referrer` can turn `Origin` into `null` on plain form posts (MDN), which the Tier 2 Origin check would reject. Our `fetch` calls are not affected.

**API** — one middleware:

| Header | Value | On |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | all responses |
| `X-Frame-Options` | `DENY` | all responses (also protects `/docs`) |
| `Referrer-Policy` | `no-referrer` | all responses |
| `Cache-Control` | `no-store` | every `/api/*` response with no exemption — public endpoints, errors, 429s and 500s included (D61) — and `/health`, which is outside `/api/*` and never proxied by Vercel but sends it too (spec 03 §1.8) |
| `Server` | removed (uvicorn `--no-server-header`) | all responses |

`Cache-Control: no-store` is Tier 1 here for a platform reason (D61): Vercel caches external-rewrite responses that carry cache headers **by default for projects created on or after 2026-04-06** (verified). A response that looks cacheable could be served from the CDN to another user, and personal data must never be cached at the edge. D61 makes no exception for public endpoints. One verified pitfall: Starlette's `ServerErrorMiddleware` is always the outermost layer, so a 500 for an unhandled exception never passes back through user middleware and would leave without `Cache-Control` and `X-Request-ID`; the request-context middleware therefore catches unhandled exceptions and renders the 500 itself (spec 03 §1.8, spec 01). Whether Vercel's `x-vercel-enable-rewrite-caching: 0` opt-out can also be set from `next.config` `headers()` is unverified (Open question 12).

**Tier 2 full CSP** (static, no nonces — the Next.js "Without Nonces" pattern):

```
default-src 'self';
script-src 'self' 'unsafe-inline';
style-src 'self' 'unsafe-inline';
img-src 'self' blob: data: https:;
font-src 'self';
connect-src 'self' <origin of NEXT_PUBLIC_WS_URL>;
object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none';
upgrade-insecure-requests;
```

`img-src https:` because shop logos are external URLs (D55). The bonus adds LiveKit endpoints to `connect-src` (exact hosts from spec 05; unverified here). In development Next.js additionally needs `'unsafe-eval'` (Next.js docs). `'unsafe-inline'` scripts weaken XSS protection; removing it needs nonces, hence Tier 3.

---

## Password policy and hashing (D10)

**Policy** — the same for owners, staff (initial passwords set by the Owner) and customers:

- **12–128 characters** (D10); any Unicode characters, including spaces; **no composition rules**; never trimmed or truncated (only e-mails are trimmed).
- Validated server-side with the as-built `Password = Secret[Annotated[str, StringConstraints(min_length=12, max_length=128)]]` in `app.core.security` (D84). `Secret` prints as `**********` in reprs and tracebacks; length is counted in characters; a short password reports Pydantic's `string_too_short` ("String should have at least 12 characters", spec 03 §2.5), which a `SecretStr` with `Field(min_length=…)` would not.
- The web mirrors it with Zod (`z.string().min(12).max(128)`) for instant feedback only.
- The demo password `BayFlow@2026` is exactly 12 characters, so it passes; an 11-character password is rejected with 422 (SEC-29). Every seeded account and every password typed in the demo script must respect the same minimum (spec 11).
- Current guidance is stricter for single-factor passwords — NIST SP 800-63B-4 and the OWASP Authentication Cheat Sheet ask for at least 15 characters without MFA (8 is their floor *with* MFA). D10 settles on 12: above the MFA floor, closer to the single-factor guidance, and still compatible with the published demo password. The per-account limiter, Argon2id and the Tier 2 blocklist cover the rest.
- The 128-character maximum bounds hashing input (NIST: allow at least 64).

**Hashing** — pwdlib `PasswordHash.recommended()` → Argon2id, stored in PHC format `$argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>`: 64 MiB memory, 3 iterations, 4 lanes, 16-byte random salt, 32-byte hash. These are argon2-cffi's RFC 9106 low-memory profile defaults and exceed OWASP's minimum (19 MiB, t=2, p=1). Measured ≈ 55 ms per hash or verify on a developer laptop (verified).

```python
# app/core/security.py — sketch
import asyncio

from fastapi.concurrency import run_in_threadpool
from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("timing-equaliser-not-a-real-password")
_hash_slots = asyncio.Semaphore(4)   # at most 4 × 64 MiB of Argon2 memory in flight

async def hash_password(password: str) -> str:
    async with _hash_slots:
        return await run_in_threadpool(password_hash.hash, password)

async def verify_password(password: str, stored_hash: str | None) -> tuple[bool, str | None]:
    """Returns (valid, new_hash_or_None). Always does one Argon2 verify, even for unknown users."""
    async with _hash_slots:
        if stored_hash is None:
            await run_in_threadpool(password_hash.verify, password, DUMMY_HASH)
            return False, None
        return await run_in_threadpool(password_hash.verify_and_update, password, stored_hash)
```

- `run_in_threadpool` keeps the event loop responsive: argon2-cffi releases the GIL while hashing (verified: a Python loop on the main thread kept ~97 % of its speed while hashes ran in another thread).
- If Railway memory turns out to be tight, switch to `PasswordHash((Argon2Hasher(time_cost=2, memory_cost=19456, parallelism=1),))` (OWASP minimum). `verify_and_update` returns a fresh hash for any stored hash whose parameters differ, so existing hashes migrate on the next login (verified).
- Hashes are never logged, returned or compared outside pwdlib.

---

## E-mail addresses (D62)

Every e-mail in a request (register-owner, login, the wizard, add-member) uses **one project type, `Email`** in `app.shared.email`, never Pydantic's `EmailStr`:

```python
# app/shared/email.py — sketch
from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator

def _normalise(value: str) -> str:
    try:
        result = validate_email(value.strip(), check_deliverability=False, test_environment=True)
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc            # → 422 VALIDATION_ERROR
    return result.normalized.lower()                   # email-validator lower-cases only the domain

Email = Annotated[str, AfterValidator(_normalise)]
```

- **Why not `EmailStr`.** Every demo account uses the reserved `.test` domain (`fatima.owner@bayflow.test`, glossary §14), and email-validator rejects special-use names such as `test` by default. `EmailStr` calls it with those defaults, so it would reject every demo login (checked: Pydantic 2.12 `EmailStr` fails on `fatima.owner@bayflow.test` with "a special-use or reserved name"). `test_environment=True` means "DNS-based deliverability checks are disabled and `test` and `**.test` domain names are permitted" ([email-validator README](https://github.com/JoshData/python-email-validator); executed with email-validator 2.3.0).
- **No DNS.** `check_deliverability=False`: no network lookup on login or booking, as the README advises for login forms.
- **Normalisation.** Surrounding spaces are stripped first (email-validator rejects them: "invalid characters … SPACE", checked); the whole address is lower-cased, matching `ck_users_email_lowercase` (spec 02 §3.1). Login and the per-account limiter therefore see one key per mailbox.
- Reserved domains stay safe for e-mail sending: the sender never e-mails `.test`, `.example`, `.invalid` or `.localhost` (D26).

---

## Logging, errors and secrets

- **Never log** passwords, `password_hash`, JWTs, WS tickets, `Authorization` / `Cookie` / `Set-Cookie` headers, request bodies of `/api/v1/auth/*`, `POST /api/v1/bookings` and member creation, `DATABASE_URL`, `AGENT_SERVICE_TOKEN`, `LLM_API_KEY`, and for the bonus the `X-Agent-Call-Token` header, `CALL_PROVIDER_API_SECRET`, LiveKit access tokens and call transcripts (spec 05 §13) (OWASP Logging Cheat Sheet "data to exclude").
- **WS ticket redaction.** Uvicorn logs `"WebSocket /api/v1/ws?ticket=…" [accepted]` on the `uvicorn.error` logger at INFO (verified, uvicorn 0.54), so `--no-access-log` alone would not hide it. A `logging.Filter` on `uvicorn.error` and `uvicorn.access` rewrites `ticket=<value>` to `ticket=[redacted]`.
- **SQL parameters.** SQLAlchemy engine with `echo=False` and `hide_parameters=True` in production, so parameters such as password hashes never appear in logs or `StatementError` strings (verified in SQLAlchemy 2.1).
- **422 responses.** FastAPI's default 422 includes the submitted `input` (verified: a too-short password is echoed back). The custom `RequestValidationError` handler returns problem+json `VALIDATION_ERROR` whose `errors[]` items are `{field, message, code}` (spec 03 §2.3), built from Pydantic's `loc`, `msg` and `type` only — `input` and `ctx` are dropped.
- **500 responses.** `FastAPI(debug=False)`. Starlette's `ServerErrorMiddleware` is always the outermost layer, so its 500 never passes back through user middleware (verified, spec 03 §1.8). The request-context middleware therefore catches unhandled exceptions itself and renders `application/problem+json` with `code: INTERNAL_ERROR`, a generic `detail`, `Cache-Control: no-store` and `X-Request-ID`; the `Exception` handler is only a backstop that sets the same headers. The traceback is logged server-side with the request ID and Railway's `X-Railway-Request-Id` for correlation.
- **Secrets** live only in Railway/Vercel environment variables and the git-ignored local `.env`; `.env.example` holds placeholders (brief §9.1, §9.3). Anything prefixed `NEXT_PUBLIC_` is inlined into the browser bundle at build time (Next.js docs), so only `NEXT_PUBLIC_WS_URL` and `NEXT_PUBLIC_CALL_PROVIDER_URL` use it; `API_BASE_URL` stays server-only.
- **Links in e-mails** are built from `CLIENT_URL`, never from the request's `Host` header.
- **Demo accounts** (D52) are ordinary accounts with a published password: no bypass, no auto-login code path, no special-casing in auth logic.

---

## Acceptance tests

pytest + httpx against a real PostgreSQL (D54), seeded with at least two shops with full teams. "Shop A" = Lahore Auto Care; "Shop B" = another seeded shop **not** owned by Fatima. Tests SEC-41…SEC-43 apply only if the Tier 2 item ships; SEC-36, SEC-49 and SEC-50 only with the bonus. SEC-44…SEC-47 were proposed by spec 12 and are adopted here. Time-dependent checks (token expiry, ticket lifetime) move the injected test clock (D63) instead of sleeping; rate-limit windows are reset instead (see [Rate limiting](#rate-limiting)).

| ID | Test | Expected |
|---|---|---|
| SEC-01 | **Brief §7.1 acceptance.** Bilal (SA, Shop A) token: `GET /api/v1/shops/{B}/bookings`; `GET /api/v1/shops/{B}/bookings/{booking_B}`; `GET /api/v1/shops/{A}/bookings/{booking_B}` | 404 `NOT_FOUND` for all three (brief allows 403/404; we return 404) with identical bodies |
| SEC-02 | Cross-tenant sweep: every operation under `/api/v1/shops/{shop_id}/…` enumerated from `openapi.json`, called by an active Shop A member with Shop B's ID, real Shop B IDs for other path params and an empty JSON body | 404 for every operation; never 2xx, 403 or 422 |
| SEC-03 | Non-members: Ayesha (customer) and an owner of a different shop call Shop A routes | 404 |
| SEC-04 | No token, garbage token, expired token on protected routes; `/api/v1/public/*` and `/health` anonymously | 401 `UNAUTHENTICATED`; public routes 200 |
| SEC-05 | Management matrix (RBAC A): SA, technician, parts person, QC call shop update, working hours, member add/update and service create/update | 403 `FORBIDDEN`; Owner succeeds |
| SEC-06 | Inventory matrix (RBAC B): Owner calls stock adjustment, PO create, PO receive; SA/technician/QC create or edit a part; Owner and parts person create a part | 403 for the denied calls; 2xx for Owner and parts person catalogue edits |
| SEC-07 | Booking-action matrix (RBAC D): every slug × every role, with the booking in the slug's `from` status, generated from the rule table (extends SM-03, SM-04, SM-16, SM-19); each role calls through its own endpoint family | Each cell's expected status: 2xx, 403 `FORBIDDEN`, 403 `NOT_ASSIGNED` or 404. A slug with no route in the caller's family — a staff-only slug on the customer route, `approve-estimate` / `reject-estimate` on the staff route — is 404 `NOT_FOUND`, never 403 (spec 03 §5.1) |
| SEC-08 | Technician Imran vs a Shop A booking assigned to another technician: list, detail, every action, `PUT …/estimate` | Absent from list; 404 for the rest |
| SEC-09 | Parts person vs a booking assigned to another parts person | Absent from list; 404 |
| SEC-10 | QC: sees `QC_PENDING` / `QC_IN_PROGRESS` and previously inspected bookings; other bookings 404; non-picker `pass-qc` / `fail-qc` | 404 outside the queue; 403 `NOT_ASSIGNED` for the non-picker |
| SEC-11 | Customer vs another customer's booking: detail, actions, estimate | 404 (SM-17) |
| SEC-12 | Customer booking detail while a `DRAFT` / `SUBMITTED` estimate exists; customer timeline | Only `SENT`/`APPROVED`/`REJECTED` versions; no internal notes or `metadata` |
| SEC-13 | **Deactivated staff blocked immediately.** Imran's token works; Fatima deactivates his membership; the same token on the next request; `GET /api/v1/me`; a later `booking.updated` in Shop A | 404 on Shop A routes; membership absent from `/me`; no realtime message delivered |
| SEC-14 | Reactivation with the same token | Access restored without logging in again |
| SEC-15 | **Owner can't deactivate or re-role her own `OWNER` membership** (PATCH `is_active=false`, PATCH `role=TECHNICIAN`); member add/PATCH with `role=OWNER`; a repository test inserting a second `OWNER` row | 403 `FORBIDDEN`, row unchanged; 422 `VALIDATION_ERROR`; database rejects the second `OWNER` |
| SEC-16 | No staff self-sign-up: register-owner and wizard with extra `role`, `shop_id`, `memberships`; a successful registration, then `GET /api/v1/me` | 422; the sign-up body carries no memberships (D81) and `/me` returns `memberships = []` |
| SEC-17 | Mass assignment: `user_id`/`shop_id` on member PATCH; `on_hand`/`reserved` on part create/update; `status`/`customer_user_id`/`reference` on booking create; `grand_total` on `PUT …/estimate` | 422 `VALIDATION_ERROR`; nothing changed |
| SEC-18 | **Wizard wrong password creates nothing.** Existing e-mail + wrong password | 409 `EMAIL_ALREADY_REGISTERED`; row counts unchanged for `users`, `vehicles`, `bookings`, `booking_services`, `booking_events`, `notifications`; slot counter unchanged; no `Set-Cookie` |
| SEC-19 | Wizard, existing e-mail + correct password; wizard with a new e-mail | 201; booking on the existing user; `password_hash` unchanged (unless rehashed); `Set-Cookie: bf_session`; body carries `access_token`, `expires_in` and `account_created: false` — `true` for the new e-mail (D32); the body token works as `Authorization: Bearer` |
| SEC-20 | Wizard while logged in with another e-mail/password in the body; wizard with an expired cookie | Booking belongs to the session user; expired cookie → 401 `UNAUTHENTICATED` |
| SEC-21 | Owner adds staff with an existing e-mail and a password; adds the same person again | Membership created, `account_created: false`, `password_hash` byte-identical, the owner-supplied password fails login; second add → 409 `CONFLICT` |
| SEC-22 | Login with unknown e-mail, wrong password, deactivated user | Identical 401 `INVALID_CREDENTIALS` bodies; exactly one Argon2 verify per attempt (spy) |
| SEC-23 | **Cookie flags** on login, register-owner and wizard (`COOKIE_SECURE=true`); logout | `HttpOnly`, `Secure`, `SameSite=lax`, `Path=/`, `Max-Age` = parsed `JWT_EXPIRES_IN`, no `Domain`; logout sends `Max-Age=0` |
| SEC-24 | Token payload; `JWT_EXPIRES_IN` parser (`7d`, `12h`, `90m`, `3600`, `0`, `1w`, `7days`) | Keys exactly `{sub, iat, exp, typ}`, `typ = session`, `exp − iat` = lifetime; invalid values fail config loading |
| SEC-25 | Token rejection: expired (test clock moved past `exp`); `iat` later than the clock's now; tampered signature; `alg: none`; HS512; missing `typ`; ticket used as Bearer; non-UUID `sub` | 401 `UNAUTHENTICATED` for each |
| SEC-26 | Valid cookie + invalid Bearer; invalid cookie alone | 401 (no fallback); invalid cookie → 401 and a clearing `Set-Cookie` |
| SEC-27 | **Rate limit (D69).** Five failed checks for one e-mail (mixing login and wizard, and sent from two different client IPs), then a sixth attempt even with the correct password; same for an unknown e-mail; per-IP ceiling on login; owner registration, shop creation and member creation over their limits; **booking creation** over its limits (anonymous `POST /api/v1/bookings` per IP, a logged-in customer per user — ≙ spec 12 BK-32); limiter reset | 429 `RATE_LIMITED` with `Retry-After`; the per-account limit applies whatever the IP; identical for unknown e-mails; an over-limit booking creates nothing and leaves the slot counter unchanged; success after the reset |
| SEC-28 | **No stack trace in 500.** A test-only route (or monkeypatched service) raises | 500 `application/problem+json`, `code: INTERNAL_ERROR`; body contains no traceback, file path or exception text; the response still carries `Cache-Control: no-store` and `X-Request-ID` (rendered by the request-context middleware, spec 03 §1.8) |
| SEC-29 | Validation responses: an 11-character and a 129-character password, and `BayFlow@2026` (12 characters, D10); `?status=PENDING' OR '1'='1`; search text with quotes | 422 without `input`/`ctx` for 11 and 129 characters; 12 accepted; enum injection → 422; quoted search returns normal results |
| SEC-30 | CSRF: an unsafe request with a JSON body sent as `text/plain`, form-encoded and with no `Content-Type`; a GET on a POST-only route (logout) | 422; no side effect; the GET → 405 `METHOD_NOT_ALLOWED` (problem+json) |
| SEC-31 | CORS preflight from `https://evil.example` and from `CLIENT_URL` | No `Access-Control-Allow-Origin` for the foreign origin; `CLIENT_URL` echoed with credentials allowed |
| SEC-32 | Headers: a web page (Playwright P1 or a config unit test) and API responses | Web: `X-Frame-Options: DENY`, CSP `frame-ancestors 'none'`, `nosniff`, `Referrer-Policy`, no `X-Powered-By`. API: `nosniff`, `X-Frame-Options: DENY`, `Cache-Control: no-store` on every `/api/*` response — public ones, a 404, a 422, a 429 and a 500 included (D61) — and on `/health`; no `Server` header |
| SEC-33 | WebSocket, with Starlette's `TestClient.websocket_connect` (a browser would report 1006): valid ticket; missing, expired (test clock > 60 s), tampered or `typ = session` ticket; foreign `Origin`; deactivated user; a technician's socket while an unassigned booking of the shop changes | Valid → accepted, and the socket stays open after the ticket expires; the others closed with 1008 before accept; no `booking.updated` for bookings the user cannot see (glossary §11) |
| SEC-34 | Notifications: list and mark-read with another user's notification ID | Only own notifications listed; foreign ID → 404 |
| SEC-35 | Estimate integrity: `PUT …/estimate` in `AWAITING_CUSTOMER` and `ESTIMATE_APPROVED`; approve a superseded version | 409 `ESTIMATE_LOCKED`; 409 `STALE_ESTIMATE` (SM-14); totals always server-computed |
| SEC-36 | Bonus internal API: no or wrong `AGENT_SERVICE_TOKEN`; a session JWT on `/api/v1/internal/*`; the service token on a user route; missing or wrong `X-Agent-Call-Token`; a call without an AI leg; a booking endpoint before `verify-caller`; the same after the AI leg ended; a reference of another customer at the same shop, and of the same customer at another shop | 401, 401, 401, 404, 404, 403 `IDENTITY_NOT_VERIFIED`, 409 `CALL_NOT_ACTIVE`, 404, 404 (≙ spec 05 FD-01, FD-02, FD-04, FD-12; D75 renamed AI-xx) |
| SEC-37 | Production config guards (`APP_ENV=production` with a 9-byte secret; a 40-byte secret containing each placeholder marker of D85 — `change-me`, `replace-me`, `dev-only`, `placeholder` — including `.env.example`'s value; `COOKIE_SECURE=false`); CI check that no `.env` file is tracked | Startup fails with a clear message for each; check passes |
| SEC-38 | Log hygiene: capture logs during the auth, wizard and WebSocket tests (and the bonus internal and webhook tests) | No password, no `eyJ…` JWT, no `ticket=` value, no `Authorization` or `X-Agent-Call-Token` header |
| SEC-39 | `next` sanitiser: `https://evil.example`, `//evil.example`, `/\evil.example`, `/pos` | Only `/pos` is honoured |
| SEC-40 | Imran (technician, Shop A) creates a shop | `OWNER` of the new shop only; Owner-only calls on Shop A still 403 |
| SEC-41 | *(Tier 2)* Cookie-authenticated POST with `Origin: https://evil.example` or `Sec-Fetch-Site: cross-site` | 403 `FORBIDDEN`; Bearer requests unaffected |
| SEC-42 | *(Tier 2)* Same WS ticket used twice within 60 s (TestClient) | Second handshake closed with 1008 |
| SEC-43 | *(Tier 2)* Password change | Tokens issued before the change → 401; the caller's new cookie works |
| SEC-44 | Passwords at rest and in responses (D10): after register-owner, add-member and the wizard, read `users.password_hash`; scan every response schema in `openapi.json` | Only `$argon2id$…` PHC strings stored; no `password` or `password_hash` field in any response |
| SEC-45 | Composite FKs (D20, spec 02 §4): insert under Shop A's `shop_id` a `booking_parts` row pointing at Shop B's part, and an `estimates` row for Shop B's booking | Both rejected by PostgreSQL (SQLSTATE `23503`) |
| SEC-46 | `GET /api/v1/me` for Fatima (Owner of two shops), Bilal (SA), Usman (Parts Person), Ayesha (customer); then Bilal calls an Owner-only route despite his capabilities | Fatima: both shops with the `OWNER` capabilities of glossary §2.4; Bilal: no core capability (bonus `tasks.manage` only); Usman: `parts.manage`, `stock.manage`; Ayesha: `memberships = []`; no inactive memberships; Bilal's call → 403 `FORBIDDEN` (capabilities are hints, D66) |
| SEC-47 | *(P1)* No demo bypass (D52): CI grep of `apps/api` and `apps/web` | The demo password and demo e-mails appear only in seed data, README and the login page; no auth code path special-cases them |
| SEC-48 | `Email` type (D62): register-owner, login and the wizard with ` Fatima.Owner@BayFlow.TEST ` (spaces, mixed case), `x@localhost`, `bad@@x`; CI grep for `EmailStr` | The first is accepted and stored or matched as `fatima.owner@bayflow.test`; the others → 422 `VALIDATION_ERROR`; no `EmailStr` in `apps/api` |
| SEC-49 | *(bonus)* `POST /api/v1/webhooks/livekit`: no `Authorization`; a JWT signed with another secret; a valid JWT whose `sha256` does not match the body; a valid `participant_left` for a connected caller; the same event again | 401, 401, 401 with nothing changed; 200 and the call ends; 200 and nothing changes (≙ spec 05 CALL-13) |
| SEC-50 | *(bonus)* Calls and tasks ([RBAC E](#e-calls-and-tasks-bonus-d21)): technician, parts person and QC inspector on the shop's call and task lists, a call detail and `mark-done`; a customer on another customer's booking calls; SA and Owner on the same routes | 403 `FORBIDDEN` on the collections and 404 on single items (spec 05 §8.2); 404 for the customer; 2xx for SA and Owner (≙ spec 05 CALL-10) |

Related state-machine tests owned by spec 08: SM-03, SM-04, SM-05, SM-06, SM-07, SM-14, SM-15, SM-16, SM-17, SM-19.

---

## Verified facts and sources

Executed on 2026-10-09 in a scratch virtualenv (Python 3.12.3) with the D11 versions: fastapi 0.143.0, starlette 1.7.0, pydantic 2.14.0, pwdlib 0.3.1 (argon2-cffi 25.1.0), pyjwt 2.15.1, slowapi 0.1.10, limits 5.8.0, uvicorn 0.54.0, sqlalchemy 2.1.4.

| Fact used above | Source | How verified |
|---|---|---|
| `PasswordHash.recommended()` uses Argon2; `hash`, `verify`, `verify_and_update`; install `pwdlib[argon2]` | [pwdlib guide](https://frankie567.github.io/pwdlib/guide/) | Docs + executed: `$argon2id$v=19$m=65536,t=3,p=4`, hash_len 32, salt_len 16; `verify_and_update` returns a new hash when parameters differ; ~55 ms; GIL released |
| Dummy-hash timing mitigation; pwdlib + PyJWT in FastAPI's tutorial | [FastAPI OAuth2 + JWT tutorial](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/) | Docs |
| HS256 encode/decode, `algorithms` list required, `exp` → `ExpiredSignatureError`, `leeway`, `require` option | [PyJWT usage](https://pyjwt.readthedocs.io/en/stable/usage.html) | Docs + executed: custom claim in `require`; future `iat` → `ImmatureSignatureError`; non-string `sub` → `InvalidSubjectError`; `none`/HS512 → `InvalidAlgorithmError`; all subclass `InvalidTokenError`; `InsecureKeyLengthWarning` below 32 bytes |
| HS256 key ≥ 256 bits | [RFC 7518 §3.2](https://www.rfc-editor.org/rfc/rfc7518#section-3.2) | Cited by PyJWT's warning text |
| `set_cookie` / `delete_cookie` parameters, `samesite` default `"lax"` | [Starlette responses](https://www.starlette.dev/responses/) | Docs + executed header output |
| Strict JSON `Content-Type` by default since FastAPI 0.132 (CSRF rationale) | [FastAPI strict content type](https://fastapi.tiangolo.com/advanced/strict-content-type/) | Docs + executed: `text/plain`, form-encoded, missing → 422 |
| CORS: no wildcards with credentials | [FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/) | Docs + executed: simple cross-origin POST still executes; foreign preflight → 400 without ACAO |
| Router-level dependency on every route; once per request; 404 before body validation; path params in dependencies | FastAPI 0.143.0 | Executed. Note: `include_router` now adds a lazy internal `_IncludedRouter`, so walking `app.routes` misses included routes — enumerate via `openapi.json` |
| `extra="forbid"` → `extra_forbidden`; `SecretStr` with length constraints masks reprs; 422 echoes `input` | Pydantic 2.14.0 / FastAPI 0.143.0 | Executed |
| slowapi setup, `request` parameter, decorator order, memory/redis storage, no WebSocket support | [slowapi docs](https://slowapi.readthedocs.io/en/latest/), [PyPI](https://pypi.org/project/slowapi/) (0.1.10, 2026-06-13) | Docs + executed with a custom 429 problem handler |
| `MovingWindowRateLimiter`, `MemoryStorage`, `parse`, `hit`/`test`/`get_window_stats`/`clear` | limits 5.8.0 | Executed (docs not fetched) |
| WS accept log includes the query string on `uvicorn.error`; `--no-server-header`, `--proxy-headers` | uvicorn 0.54.0 source | Read source |
| `hide_parameters` | SQLAlchemy 2.1.4 `create_engine` docstring | Read source |
| `headers()`, header examples, `poweredByHeader`, rewrites to external URLs, CSP (nonces via `proxy.ts` need dynamic rendering; static policy with `'unsafe-inline'`), `NEXT_PUBLIC_` inlining | Next.js 16.4 docs: [headers](https://nextjs.org/docs/app/api-reference/config/next-config-js/headers), [CSP](https://nextjs.org/docs/app/guides/content-security-policy), [rewrites](https://nextjs.org/docs/app/api-reference/config/next-config-js/rewrites), [poweredByHeader](https://nextjs.org/docs/app/api-reference/config/next-config-js/poweredByHeader), [env vars](https://nextjs.org/docs/app/guides/environment-variables) | Docs |
| External rewrites forward `x-real-ip` / `x-forwarded-for`; upstream cache headers honoured by default for projects created on/after 2026-04-06; `x-forwarded-for` overwritten to prevent spoofing; HTTPS-only and HSTS on `*.vercel.app` | [Vercel rewrites](https://vercel.com/docs/routing/rewrites), [request headers](https://vercel.com/docs/headers/request-headers), [encryption](https://vercel.com/docs/cdn-security/encryption) | Docs |
| `X-Real-IP` = client IP; WebSockets exempt from Railway timeouts | [Railway specs & limits](https://docs.railway.com/networking/public-networking/specs-and-limits) | Docs |
| Railway edge overwrites caller-supplied `X-Real-IP` / `X-Forwarded-For` | [Railway Station answer by a moderator](https://station.railway.com/questions/which-client-address-headers-does-the-ra-fb9e36d7) | Community source — **not official docs** |
| `vercel.app` and `up.railway.app` are public suffixes | [Public Suffix List](https://publicsuffix.org/list/public_suffix_list.dat) | Downloaded and searched |
| Lax+POST exception only for cookies without a SameSite attribute | [Chromium SameSite notes](https://www.chromium.org/updates/same-site/test-debug/) | Docs |
| Browsers send `Origin` on same-origin POST/PUT/PATCH/DELETE; `fetch` credentials default `same-origin` | MDN [Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Origin), [RequestInit](https://developer.mozilla.org/en-US/docs/Web/API/RequestInit) | Docs |
| `react/no-danger` rule | [eslint-plugin-react](https://github.com/jsx-eslint/eslint-plugin-react/blob/master/docs/rules/no-danger.md) | Docs |
| Argon2id minimums; rehash on login | [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) | Docs |
| Length 8 with MFA / 15 without, max ≥ 64, no composition rules, generic errors, lockout tied to account | [OWASP Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html), [NIST SP 800-63B-4 §3.1.1.2](https://pages.nist.gov/800-63-4/sp800-63b.html) | Docs |
| SameSite is defence in depth; JSON/preflight; Origin verification; Fetch Metadata; no state-changing GET; login CSRF | [OWASP CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) | Docs |
| Random IDs are not access control | [OWASP IDOR Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html) | Docs |
| Cookie attributes, no `Domain`, `__Host-`, `Cache-Control: no-store` | [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) | Docs |
| WS: avoid tokens in query strings, validate `Origin`, per-message authorization, close on revocation | [OWASP WebSocket Security](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html) | Docs |
| DTOs / allowlists against mass assignment | [OWASP Mass Assignment](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html) | Docs |
| Data to exclude from logs; security events to log | [OWASP Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) | Docs |
| Header values | [OWASP HTTP Headers](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html) | Docs |
| `test_environment=True` disables DNS-based deliverability checks and permits `test` / `*.test`; special-use names are rejected by default; `check_deliverability=False` for login forms; `normalized` lower-cases only the domain | [email-validator README](https://github.com/JoshData/python-email-validator) | Docs + executed (email-validator 2.3.0, 2026-10-09): `Fatima.Owner@BayFlow.TEST` rejected by default, accepted with `test_environment=True` as `Fatima.Owner@bayflow.test`; surrounding spaces rejected; the `Email` sketch above returns `fatima.owner@bayflow.test` |
| Pydantic `EmailStr` rejects `fatima.owner@bayflow.test` ("special-use or reserved name") | Pydantic | Executed on Pydantic 2.12.5 (the D11 pin is 2.14.x — re-check when the lockfile exists; D62 removes `EmailStr` either way) |
| PyJWT's built-in `exp` / `iat` checks use the system time; `options={"verify_exp": False, "verify_iat": False}` keeps `require` (missing claim → `MissingRequiredClaimError`) and the signature check | [PyJWT usage](https://pyjwt.readthedocs.io/en/stable/usage.html) | Executed with PyJWT 2.15.1: a token issued by a frozen clock 30 days back → `ExpiredSignatureError` by default; the `decode_token` sketch with a frozen clock accepts it, rejects it after the clock passes `exp`, and still rejects `alg: none`, HS512, a missing `typ`, a wrong `typ` and a non-UUID `sub` |
| `limits` keeps its windows on `time.time()` | limits 5.8.0 `storage/memory.py` | Read source |
| `websocket.close` before accept → the server refuses the handshake with HTTP 403, which "may present on some browsers as … 1006" | [ASGI spec (HTTP & WebSocket)](https://asgi.readthedocs.io/en/latest/specs/www.html) | Docs |
| A close with code 1008 before accept is seen by Starlette's `TestClient.websocket_connect` as `WebSocketDisconnect(code=1008)` | FastAPI 0.143.0 / Starlette 1.7.0 | Executed |
| LiveKit webhooks: `Authorization` header holds a JWT containing the body's SHA-256; `Content-Type: application/webhook+json`; "no guarantees around delivery" | [LiveKit webhooks](https://docs.livekit.io/home/server/webhooks/) | Docs (they show Node, Go and Java receivers, no Python one) |
| Python receiver: `WebhookReceiver(TokenVerifier(api_key, api_secret)).receive(body: str, auth_token: str)`; `TokenVerifier.verify` decodes with HS256, `issuer = api_key`, `require: ["exp"]`; `receive` compares `sha256(body)` with the `sha256` claim and raises on a missing claim or a mismatch | [webhook.py](https://github.com/livekit/python-sdks/blob/main/livekit-api/livekit/api/webhook.py), [access_token.py](https://github.com/livekit/python-sdks/blob/main/livekit-api/livekit/api/access_token.py) | Read source (main branch, 2026-10-09; D11 pins `livekit-api` 1.2.x) |

**Unverified — check on day 1 (spec 16):** `Set-Cookie` survives the Vercel rewrite and is stored host-only (D7); the `Origin` header reaches the API unchanged; which client IP the API sees through Vercel → Railway; whether `x-vercel-enable-rewrite-caching` can be set from `next.config`; LiveKit hosts for the CSP (spec 05).

---

## Dependencies

- **Depends on:** [18-glossary.md](18-glossary.md) (names), [17-decisions.md](17-decisions.md) (D7–D10, D14–D21, D30, D32, D33, D35, D39, D40, D44, D47, D49, D51, D52, D54, D55, D58, D60–D63, D66, D67, D69, D70, D75, D80–D85, D88), [08-booking-state-machine.md](08-booking-state-machine.md) (actors, guards, error order, `allowed_actions`, SM tests).
- **Needs from other specs:** 02 (unique and partial unique indexes on `users` / `shop_memberships`, composite FKs incl. assignee → membership, `notifications.recipient_role` / `link`, `call_logs.ai_call_token_hash`), 03 (exact paths and schemas, problem+json shape, audience-specific booking/estimate schemas, the `/me` membership schema), 01 (`app.core` / `app.shared` placement incl. `app.shared.clock` and `app.shared.email`, event bus, realtime hub), 05 (internal API checks §5.1, webhook §8.5, calls/tasks access §8.2, CALL-/FD- tests), 07 (env vars, `.env.example` placeholder, uvicorn flags, Vercel/Railway config, no rewrite of `/api/v1/internal/*`), 09/10 (API client 401 handling, `next` sanitiser, `proxy.ts` UX redirect, headers config, capability-driven buttons, WebSocket reconnect), 11 (every demo account satisfies the policy; D60 reconciliation), 12 (SEC tests in CI; SEC-44…SEC-47 adopted from its proposals), 16 (day-1 checks).
- **Used by:** `modules/identity.md`, `modules/shops.md`, every module spec (route dependencies and visibility), 06, 12, 15.

## Open questions

1. ✅ **Resolved by D10:** passwords are 12–128 characters; the demo password `BayFlow@2026` (12) passes ([Password policy](#password-policy-and-hashing-d10), SEC-29).
2. ✅ **Resolved by glossary §11:** `booking.updated` goes only to the booking's customer and to members who can see the booking under D21; SEC-33 asserts it.
3. ✅ **Resolved by D70:** the query-string ticket stays — 60 seconds, handshake only, close 1008 on rejection (browsers see 1006), a new ticket on every reconnect, redacted from logs; single use is Tier 2.
4. ✅ **Resolved by D69:** per-account (e-mail) limits are primary and per-IP limits only a secondary ceiling; the day-1 measurement (spec 16) just tunes the ceilings.
5. ✅ **Resolved by D18:** the consent gap is accepted for the hackathon (rate-limited, grants no data); the invitation flow is Tier 3.
6. ✅ **Resolved by D85 and spec 07: `.env.example` placeholder.** `.env.example` uses the letters-and-hyphens placeholder `local-dev-secret-replace-me-with-random-chars` (glossary §12), and production refuses any `JWT_SECRET` shorter than 32 bytes or containing `change-me`, `replace-me`, `dev-only` or `placeholder` ([Secrets and rotation](#secrets-and-rotation), SEC-37).
7. ✅ **Resolved by D60:** every seed run reconciles the demo cast (users active, memberships active with their canonical role, demo password hash restored). Judge-made changes to bookings, stock or shop settings are accepted drift (D71).
8. ✅ **Resolved by D19:** any change to the `OWNER` membership → 403 `FORBIDDEN`.
9. **Slot hoarding.** ✅ The directory half is resolved by D64 (listed only with `is_listed` and at least one active service). Still open: should active bookings per customer per shop be capped (Tier 2 item 10)? Product rule for `modules/bookings.md`.
10. **Vercel preview deployments.** `CLIENT_URL` is a single origin, so CORS and the Tier 2 Origin check reject preview hosts. Acceptable (judging uses production) unless previews must talk to the production API; avoid regex allowlists (OWASP).
11. **`__Host-` cookie prefix.** It would bind the cookie to `Secure`, `Path=/` and no `Domain` at browser level, but requires renaming `bf_session`. Deferred to Tier 3 unless the owner wants it now.
12. **Vercel rewrite caching opt-out.** D61 makes the API's `Cache-Control: no-store` the control. Should spec 07 also set `x-vercel-enable-rewrite-caching: 0` for `/api/:path*` (in `vercel.json` if `next.config` headers cannot)? Unverified; a spec 07 day-1 check.
13. ✅ **Resolved by glossary §10 / D69:** `RATE_LIMITED` now covers login, owner registration, booking creation, shop creation, member creation and (bonus) call starts.
14. ✅ **Resolved by D63:** rate-limit windows are kept by the rate-limit library on system time — the one documented exception to the injected clock; tests reset the limiter instead of moving the clock ([Rate limiting](#rate-limiting)).
15. ✅ **Resolved by glossary §10:** `CALL_NOT_ACTIVE` now also covers "an internal agent request for a call outside its active window", so the internal routes keep 409 `CALL_NOT_ACTIVE` after the AI leg's window (bonus).

## Proposed glossary additions

✅ **Merged into the glossary on 2026-10-09** (removed from the table below): the path patterns `/api/v1/auth/...` (`register-owner`, `login`, `logout`), `/api/v1/me`, the realtime ticket, `/api/v1/webhooks/...` and `/api/v1/internal/...` (§9; individual endpoints belong to spec 03, the authoritative catalogue); JWT `typ` values `session`, `ws` (§9); `StaffRole` (§2.1); capabilities (§2.4); `app.shared.auth` and `app.core.security` identifiers and the `Email` type in `app.shared.email` (§7); `users` key columns (§8); WebSocket close code `1008` (§11); the `RATE_LIMITED` scope (§10). Later the same day: `CALL_NOT_ACTIVE` widened to internal agent requests outside the active window (§10, Open question 15); `app.shared.clock.get_clock()` / `utcnow()` (§7, D63); `shop_scoped_router()` in `app.shared.auth` (§7, D80); the auth path note "identity module; login returns token + user, then the web calls `GET /api/v1/me`" (§9, D81). The "browsers observe 1006" note lives in D70 rather than glossary §11.

Still pending:

| Kind | Proposed name(s) | Notes |
|---|---|---|
| Response fields (spec 03) | login / register-owner: `access_token`, `token_type` (`"bearer"`), `expires_in` (seconds), `user` (D81); booking creation: the same token fields + `account_created` (also on member creation); `GET /api/v1/me` membership items `membership_id`, `shop_id`, `shop_name`, `shop_slug`, `role`, `capabilities`; ticket: `ticket`, `expires_in` | Spec 03 settled on `account_created` for member creation (spec 10 had `existing_user`) and lists these fields in its own proposals |
| Key column (§8) | Tier 2: `users.tokens_valid_after` | Only if Tier 2 item 4 ships |
| Header (§9) | `X-Agent-Call-Token` (bonus per-call agent token) | Also proposed by spec 05; §9 mentions the "per-call token" without its header |

## Change log

- **2026-10-09 consolidation** (decisions D10, D18, D19, D21, D32, D58, D60–D63, D66, D67, D69, D70, D75; glossary §2.4, §7, §9–§11; spec 05 §5.1, §8):
  - Passwords 12–128 characters everywhere (policy, Pydantic and Zod limits, SEC-29) (D10).
  - New section [E-mail addresses (D62)](#e-mail-addresses-d62): the project `Email` type replaces `EmailStr`; why (`.test` demo domain); stripping and lower-casing.
  - `Cache-Control: no-store` on every `/api/*` response, public ones included (D61): endpoint summary, headers table, threat #21, SEC-32.
  - `GET /api/v1/me` memberships carry `capabilities` and `shop_slug` (D66); new [Capabilities](#capabilities-d66) table; SEC-46.
  - Booking creation returns `access_token`, `expires_in`, `account_created` and sets the cookie in every successful case (D32); SEC-19.
  - Rate limiting restated per D69 (per-account primary, per-IP secondary; bonus call starts); library time source noted (Open question 14).
  - WebSocket ticket per D70 (handshake only, new ticket per reconnect); 1008 is server-side only, browsers see 1006 (ASGI spec), so SEC-33/SEC-42 use the Starlette TestClient; `booking.updated` fan-out per glossary §11.
  - JWT `iat`/`exp` issued and checked with the D63 clock (PyJWT's own time checks disabled; executed with PyJWT 2.15.1).
  - Notifications carry `recipient_role` and a server-computed `link` (D67): tenant-isolation table, threat #23.
  - Bonus: new [AI agent and LiveKit webhook](#bonus-ai-agent-and-livekit-webhook-d58) section (service token **and** per-call token, scope from the call row, 403 `IDENTITY_NOT_VERIFIED`, signed webhook); RBAC [E. Calls and tasks](#e-calls-and-tasks-bonus-d21) (D21); threats #26–#29; SEC-36 extended, SEC-49, SEC-50.
  - Error codes per glossary §10: 405 `METHOD_NOT_ALLOWED` (logout, CSRF, SEC-30), 413 `PAYLOAD_TOO_LARGE` (Tier 2 body cap), `RATE_LIMITED` scope.
  - SEC-44…SEC-47 adopted from spec 12's proposals; SEC-48 (`Email` type) added.
  - Open questions 1–5, 7, 8, 13 resolved (D10, glossary §11, D70, D69, D18, D60, D19, glossary §10); 9 and 12 partly; 14 and 15 added. Proposed glossary additions trimmed to the pending ones.
- **2026-10-09 alignment with spec 03** (decisions D61, D63, D69, D70, D80–D83):
  - Login and owner registration return `{access_token, token_type, expires_in, user}` without memberships; the identity module owns `/api/v1/auth/*`; the web calls `GET /api/v1/me` (shops module, `shops_get_me`) right after (D81): endpoint summary, registration and login flows, SEC-16.
  - `Cache-Control: no-store` with no exemption: every `/api/*` response incl. errors and 500s, plus `/health` (D61): headers table, threat #21, Tier 1 #7, SEC-32. Unhandled-exception 500s are rendered by the request-context middleware so they keep `Cache-Control` and `X-Request-ID` (Starlette's `ServerErrorMiddleware` bypasses user middleware; spec 03 §1.8): logging section, Tier 1 #9, SEC-28.
  - A slug outside the caller's endpoint family is 404, not 403 (spec 03 §5.1): per-request order (step 0), RBAC legend and notes, SEC-07.
  - `issue_token(…, now)` and `decode_token(token, now, expected_typ)` take `now`, because `app.core` cannot import `app.shared` (D63, spec 01 rule 8); sketches use the `AppError` subclasses of `app.core.errors` and `identity.service.get_active_user`.
  - `shop_scoped_router()` factory in `app.shared.auth` replaces the single `shop_router` (D80); the role → capability table sits in the shops domain (spec 01).
  - The WebSocket ticket endpoint belongs to the notifications module (D70): ticket flow, Tier 1 #12. `booking.updated` also follows parts changes without a booking event (D83).
  - Stock adjustments are P0 (D82): RBAC B. The request-body cap moves from Tier 2 #8 to Tier 1 #14 (spec 03 §1.10: 64 KiB, 256 KiB for the agent summary).
  - SEC-27 also covers the booking-creation limits (D69; ≙ spec 12 BK-32).
  - Open questions 14 and 15 resolved (D63, glossary §10); proposed glossary additions updated.
- **2026-10-09 final consistency sweep** (decisions D84, D85, D88):
  - Production secret guard: refuse any `JWT_SECRET` containing a placeholder marker (`change-me`, `replace-me`, `dev-only`, `placeholder`), not only a `change-me` prefix (D85): secrets section, SEC-37; Open question 6 resolved.
  - `Password` is the as-built `Secret[Annotated[str, StringConstraints(min_length=12, max_length=128)]]` (D84).
  - The WebSocket ticket and `/api/v1/ws` are P1 (D88): endpoint summary, Tier 1 #12 and #13 (SEC-33 applies once the socket ships).
  - RBAC E aligned with spec 05 §3.3 (authoritative for the bonus): the Owner accepts or declines a customer → shop call only when the shop has no active SA; any active SA may, rung or not.
