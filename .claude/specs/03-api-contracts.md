# 03 — API Contracts

**Status:** Draft

## Purpose

The single, authoritative catalogue of BayFlow's HTTP and realtime interface: every path and method, who may call it (auth, role, visibility), its request and response schemas with validation rules, its error codes, its side effects (events, notifications, pushes), its priority and the screens it serves. Module specs (`modules/*.md`) and the code are built from this file.

FastAPI generates `/docs` (Swagger UI) and `/openapi.json` from the same routers and Pydantic schemas that implement this contract. `python -m app.scripts.export_openapi` writes that schema to `apps/web/src/lib/api/openapi.json`, and `openapi-typescript` generates `apps/web/src/lib/api/schema.d.ts` from it (D50, D76); CI fails when either file is stale. A contract change therefore breaks the web build instead of the running UI. When code and this spec disagree, this spec is corrected first.

Names come from [18-glossary.md](18-glossary.md). [17-decisions.md](17-decisions.md) and [08-booking-state-machine.md](08-booking-state-machine.md) win every conflict. "Brief §n" is the hackathon brief (`helping-folder/Web Dev - Virtual.pdf`, v1.1); "Tnn"/"On" are rule rows of spec 08; "E-nn" and screen IDs (P-, C-, S-, SA-, T-, PP-, QI-, O-, X-, B-) come from [10-screens.md](10-screens.md). Every FastAPI, Starlette, Pydantic and uvicorn behaviour stated here was checked on 2026-10-09 by running scratch apps on the D11 versions (FastAPI 0.143.0, Starlette 1.7.0, Pydantic 2.14.0, uvicorn 0.54.0) and against official docs; sources are in §9.

---

## 1. Conventions

### 1.1 Base path, documents, media types

| Item | Rule |
|---|---|
| Base path | `/api/v1` for every route except `GET /health` (unversioned, infrastructure only). A breaking change would add `/api/v2`; none is planned. |
| Who calls which host | Browsers call `https://<web-host>/api/*`, which Next.js rewrites to Railway (D7). Swagger, curl, tests and the bonus agent call `https://<api-host>` directly. The WebSocket and the LiveKit webhook go straight to `<api-host>`. `/api/v1/internal/*` is for the agent only (§4.14). Locally the web is `http://localhost:3000` and the API `http://localhost:4000`, with the same rewrite (D73). |
| OpenAPI | `GET /openapi.json` and Swagger UI `GET /docs`. `info.version` is the fixed string `1.0.0`, so the committed snapshot changes only when the contract changes. Swagger documents the Bearer scheme only (`HTTPBearer(auto_error=False)`, spec 04). The webhook, the internal routes and the WebSocket are excluded (`include_in_schema=False`; FastAPI does not document WebSocket routes). |
| Request bodies | `Content-Type: application/json` only. FastAPI's default `strict_content_type=True` refuses to parse a body sent as `text/plain`, form-encoded or without a content type, which ends as 422 (verified). This is part of the CSRF defence (spec 04). |
| Responses | Success: `application/json` (204 has no body). Errors: `application/problem+json` (§2). |

### 1.2 Authentication transport (D8, D9, spec 04)

- The session token is an HS256 JWT with exactly `sub`, `iat`, `exp` and `typ = "session"`. `POST /api/v1/auth/login`, `POST /api/v1/auth/register-owner` and `POST /api/v1/bookings` deliver it twice: as the httpOnly cookie `bf_session` (`HttpOnly; Max-Age=<JWT_EXPIRES_IN in s>; Path=/; SameSite=lax`, plus `Secure` when `COOKIE_SECURE=true`, no `Domain`) and in the body as `access_token`, `token_type` (`"bearer"`) and `expires_in` (seconds; 604800 for `7d`). The web app ignores the body token unless the D7 Bearer fallback is active (spec 09), and it routes from `GET /api/v1/me` (spec 09 §2.8), which it calls right after login and owner registration because those bodies carry the `user` but no memberships (D81).
- How the API picks the token:

| The request carries | Token used | On failure |
|---|---|---|
| `Authorization: Bearer <jwt>` (with or without the cookie) | the Bearer token | 401; never falls back to the cookie |
| `Authorization` with another scheme, or malformed | — | 401 |
| only the `bf_session` cookie | the cookie | 401, and the response clears the stale cookie |
| neither | — | 401 on protected routes |

- Every authenticated request re-reads `users.is_active`: an inactive user gets 401 `UNAUTHENTICATED` everywhere (D9).
- Token types never mix: a `typ = "ws"` ticket used as a session → 401; a session token never opens the WebSocket.
- Public routes (`/api/v1/public/*`, `/health`, the three `/api/v1/auth/*` routes) never require or reject credentials. Only `POST /api/v1/auth/logout` reads them, leniently: when the Bearer header (which wins) or else the cookie decodes to an active user, the sign-out is recorded as `auth.logged_out` (spec 19 §3.3); anything absent, malformed or expired is ignored, and the answer is 204 whatever happens. `POST /api/v1/bookings` reads them optionally: none → anonymous wizard; present but invalid, expired or belonging to an inactive user → 401, never a silent downgrade to the anonymous path (spec 04 case A).
- `/api/v1/internal/*` (bonus) accepts only `Authorization: Bearer <AGENT_SERVICE_TOKEN>` plus `X-Agent-Call-Token` (spec 05 §5.1). Session JWTs are rejected there, and the service token is rejected everywhere else.
- Every 401 carries `WWW-Authenticate: Bearer` (RFC 9110 §15.5.2 requires a challenge; a `Bearer` challenge never opens a browser login prompt).

### 1.3 Endpoint families, tenancy and visibility

| Family | Paths | Actor | Scope; what is outside it |
|---|---|---|---|
| Public | `/api/v1/public/*` | anonymous | Listed shops only (D64, D68); anything else → 404 |
| Current user | `/api/v1/me`, `/api/v1/me/*`, `/api/v1/realtime/ticket` | the caller; `CUSTOMER` for booking reads and actions | Queries filtered by `customer_user_id` / `recipient_user_id` / owner of the vehicle = caller; anything else → 404 |
| Wizard | `POST /api/v1/bookings` | `CUSTOMER` | The body's `shop_id` only selects where to book; it is never an authorization claim (D20) |
| Staff | `/api/v1/shops/{shop_id}/*` | the caller's membership role in `shop_id` | Every staff route group is built with `app.shared.auth.shop_scoped_router()` (prefix `/api/v1/shops/{shop_id}`, D80), which attaches `require_shop_member` at router level: it loads the caller's **active** membership or answers 404 on every route, whether the shop doesn't exist, belongs to another tenant, or the membership is inactive (D9, D20); a member of a **suspended** shop gets 403 `SHOP_SUSPENDED` on every route, the Owner included (D96), so the router declares 403 for all of them. `POST /api/v1/shops` is the only `/shops` route outside it. |
| Platform admin (P1) | `/api/v1/admin/*` | a platform admin (`require_platform_admin`, D94), from BayFlow's own pages (D98: a `Sec-Fetch-Site` header other than `same-origin` or `none` → 403 `FORBIDDEN`) | Every tenant; E-61…E-75 in spec 19 §4 |
| Agent (P2) | `/api/v1/internal/calls/{call_id}/*` | the AI Front Desk | The call's shop and customer, read from `call_logs` (spec 05 §5.1) |

- **Management routes** add `require_roles(...)`: a member with another role gets 403 `FORBIDDEN`. Each route's roles are listed in §4.
- **Booking reads and actions** add the D21 predicate to the query: `OWNER` and `SERVICE_ADVISOR` see every booking of the shop; `TECHNICIAN` only `technician_user_id = me`; `PARTS_PERSON` only `parts_person_user_id = me`; `QC_INSPECTOR` bookings in `QC_PENDING` or `QC_IN_PROGRESS` plus those with a `qc_inspections` row by them. A booking outside the predicate is 404 on item routes and simply absent from lists.
- **D16:** the Owner passes every Service Advisor rule and no technician, parts or QC rule, and can read every role's views. **D44:** parts catalogue edits are Owner and Parts Person; stock operations (adjustments, purchase orders, receipts, reservations, allocation) are Parts Person only.
- **D66:** `GET /api/v1/me` returns, per membership, the `capabilities` that mirror the non-booking rules of this spec (§3.2). Booking buttons come only from `allowed_actions` (spec 08).

### 1.4 Check order

```text
staff route     401 auth → 404 membership → 403 SHOP_SUSPENDED (D96) → 403 require_roles (management routes only) → 422 request schema
                → 404 visibility (D21) → 403 FORBIDDEN (role not in the rule) → 403 NOT_ASSIGNED (guard)
                → 409 status (INVALID_TRANSITION, or ESTIMATE_LOCKED / ALREADY_PICKED) → 409 CONCURRENT_UPDATE
                → 422 / 409 data guards → side effects, commit, response
customer route  401 auth → 422 request schema → 404 own booking → 403 SHOP_SUSPENDED (every action but cancel, D96)
                → 403 FORBIDDEN → 409 status → 409 version → guards
admin route     403 FORBIDDEN cross-site (D98) → 401 auth → 403 FORBIDDEN not a platform admin → 422 → 404 → 409 / 422
```

This is glossary §10's order with two framework facts made explicit (both verified on FastAPI 0.143.0):

1. Router dependencies (authentication, membership, `require_roles`) run **before** the body is validated. A non-member therefore gets 404 even with an empty or invalid body, and a member with the wrong role gets 403. The one exception is a body that is **not valid JSON**: FastAPI rejects it with 422 (`json_invalid`) before any dependency runs.
2. The request schema (types, required fields, lengths, unknown fields) is checked **before** the service runs. Inside a shop, a schema-invalid body gets 422 even when the booking is not visible or the role is wrong. A 422 says nothing about the target, so nothing leaks. Tests that probe 403 or 404 send schema-valid bodies.

Unknown routes, including an action slug that does not exist in that endpoint family (§5.1), are 404 `NOT_FOUND`; a wrong method on a known path is 405 `METHOD_NOT_ALLOWED` with `Allow` (§2.4).

### 1.5 JSON encoding

| Kind | Rule |
|---|---|
| Keys | `snake_case`, no aliases. Never a map keyed by enum values: counts come as `[{status, count}]`. |
| Unknown request fields | Every request schema sets `extra="forbid"` → 422 `extra_forbidden` (mass-assignment defence, spec 04 SEC-17). Response schemas may gain fields; clients ignore unknown ones. |
| Absent values | Response fields are always present; "no value" is `null`. Optional request fields may be omitted or sent as `null`. In a PATCH, omitted means unchanged and `null` clears a nullable field. |
| IDs | UUID v4 strings. Human references `BF-XXXXXX` and `PO-XXXXXX` are separate fields and never path keys (except the agent's internal routes). |
| Timestamps | UTC ISO 8601 with `Z`: `"2026-10-16T05:00:00Z"`. Milliseconds appear only when non-zero (`"…T05:00:00.123Z"`); microseconds are dropped by the serializer (Pydantic alone would print six digits). Requests must carry `Z` or an offset; naive values → 422. |
| Dates | `YYYY-MM-DD`, in the shop's timezone (availability `date`, list filters, overview `today`). |
| Wall-clock times | `HH:MM`, 24-hour, shop-local (working hours). |
| Money (D41) | Responses: a decimal string with exactly two places holding whole rupees (`"16100.00"`). A dedicated `Money` type serializes it, because Pydantic prints `Decimal("16100")` as `"16100"` (verified). Requests: a JSON string (`"6500"` or `"6500.00"`) or integer, 0 to 9 999 999 999, whole rupees; anything else → 422 `not_whole_rupees`. Pydantic alone would accept `6500.5` (verified), so the type checks it. |
| Quantities | Stock quantities are integers. An estimate line's `quantity` is a decimal string with two places in responses (`"1.00"`, `"1.50"`); requests send a string or number with at most two decimals: `PART` lines a whole number 1–9 999, `LABOUR` lines 0.01–999.99. |
| Rating | `rating` is a JSON number with one decimal (`4.7`) or `null`, shown as "New" (D56). It is display data, not money. |
| Text | Trimmed (passwords never). Required text must not be blank. Maximum lengths equal the database column sizes (spec 02) and are listed per field. |
| E-mail | The project `Email` type (D62): `email_validator.validate_email(…, check_deliverability=False, test_environment=True)`, then lower-cased; at most 254 characters. It accepts `@bayflow.test` and `ahmed@mail.com` (spec 12 API-12). Pydantic's `EmailStr` is never used. |
| Phone | The project `Phone` type: 7–20 characters of digits, spaces and hyphens with an optional leading `+`; stored without spaces and hyphens (`"+92 300 1234567"` → `"+923001234567"`). |
| Enums | Values exactly as glossary §3–§6 (`AWAITING_CUSTOMER`). Action slugs are lower-kebab (`approve-estimate`); capabilities are dotted (`stock.manage`). |

### 1.6 Lists

- **Paginated collections** (lists that can grow without bound) return `Page[T]` = `{items, total, limit, offset}`. `?limit=` is 1–100 (default 20) and `?offset=` is 0–2 147 483 647 (as built: a larger offset overflowed asyncpg's int64 encoder and answered 500); anything else → 422 (verified). Every collection has a deterministic order that ends in `id`, except the stock ledger, which ends in `seq` (D63, D79).
- **Bounded lists** (the children of one booking, PO or configuration: a booking's events, estimate versions, booking parts and QC rounds; the QC checklist; directory cities; a customer's vehicles) return `ItemList[T]` = `{items}` in full, without pagination parameters. A worked-example booking has 21 events, which a default `limit=20` would cut.
- **Filters** are query parameters named after the field. Multi-value filters repeat the key (`?status=PENDING&status=CONFIRMED`; verified). Enum values are validated, so `?status=PENDING' OR '1'='1` is 422 (spec 04 SEC-29). Free text `q` is at most 100 characters, matched case-insensitively as a substring with `%` and `_` escaped. Date ranges `date_from` and `date_to` are inclusive shop-local dates; `date_from > date_to` → 422.
- **Sorting:** `?sort=<field>` ascending or `?sort=-<field>` descending, from a per-endpoint allowlist; any other value → 422. Each endpoint states its default.
- Unknown query parameters are ignored (FastAPI default).

### 1.7 Versions, concurrency and idempotency (D30)

- Every booking action body and `PUT …/estimate` accept an optional `expected_version` (integer ≥ 1); the web always sends the version it rendered. A mismatch → 409 `CONCURRENT_UPDATE`, checked after the status check. `bookings.version` increases whenever a `booking_events` row is written; plain estimate-draft saves write no event and are last-write-wins.
- Every action locks the booking row first (lock order booking → purchase order → parts by ascending `id` → slot counter). A double click is therefore harmless: the second `confirm` finds `CONFIRMED` → 409 `INVALID_TRANSITION`; a second `pick-qc` → 409 `ALREADY_PICKED`. Repeatable operations (`notify-ready`, `start-repair`) are de-duplicated by `expected_version`: the first call bumps the version and the second gets 409.
- Idempotent by design: `POST /api/v1/auth/logout`, marking notifications read, `PUT …/estimate` and `PUT …/working-hours` (replace semantics; the first SA save of an estimate creates a version, later identical saves don't), and the bonus `…/end` and `…/mark-done`.
- A PO receipt may send `expected_received_qty` per item, which turns a duplicated receipt into 409 `CONCURRENT_UPDATE` (§5.3).
- `POST /api/v1/bookings` is not idempotent (Open question 2). The wizard disables its button while the request is pending.

### 1.8 Headers

| Header | Direction | Rule |
|---|---|---|
| `Authorization` | request | `Bearer <jwt>`, optional (§1.2) |
| `X-Request-ID` | both | Reused when it matches `^[A-Za-z0-9._-]{1,64}$`, otherwise replaced by a new UUID4; echoed on **every** response and written to every log line (spec 01) |
| `Cache-Control: no-store` | response | On **every** `/api/*` response and on `/health`: public routes, errors and 500s included (D61) |
| `Set-Cookie` | response | Set by login, register-owner and booking creation; cleared by logout and by any 401 caused by an invalid cookie |
| `Retry-After` | response | Seconds, on every 429 |
| `Allow` | response | On every 405 (RFC 9110 §15.5.6) |
| `WWW-Authenticate: Bearer` | response | On every 401 |
| `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` | response | Every response (spec 04) |
| `X-Agent-Call-Token` | request | Internal routes only (P2) |

Verified pitfall: Starlette's `ServerErrorMiddleware` is always the outermost layer, so the 500 produced for an unhandled exception never passes back through user middleware. In the test app it arrived without `Cache-Control` and without `X-Request-ID`. The request-context middleware therefore catches unhandled exceptions itself and renders the 500 problem with every header above; the `Exception` handler is only a backstop that sets the same headers.

### 1.9 Rate limits (D69)

| Limiter | Key | Limit | Applies to |
|---|---|---|---|
| Failed password checks (primary) | normalised e-mail | 5 per 15 min, moving window; cleared on success. A blocked account gets 429 even with the right password; unknown e-mails count like known ones. | `POST /api/v1/auth/login`; `POST /api/v1/bookings` cases C and D |
| Login | client IP | 30 per min | `POST /api/v1/auth/login` |
| Logout | client IP | 30 per min | `POST /api/v1/auth/logout` (a 429 leaves the cookie in place; spec 04) |
| Owner sign-up | client IP | 20 per hour | `POST /api/v1/auth/register-owner` |
| Anonymous booking | client IP | 20 per min | `POST /api/v1/bookings` without a session |
| Authenticated booking | user | 30 per hour | `POST /api/v1/bookings` with a session |
| Shop creation | user | 10 per day | `POST /api/v1/shops` |
| Member creation | shop | 30 per hour | `POST /api/v1/shops/{shop_id}/members` |
| Call starts (P2) | caller | 5 per 10 min | both call-start routes (spec 05) |

Each answers 429 `RATE_LIMITED` with `Retry-After`. Per-IP limits are generous ceilings because many visitors share Vercel's egress IPs; the per-account limiter carries the brute-force protection (spec 04). Counters live in memory in the single API replica (D14), except the call-start limit, which is counted from `call_logs` (spec 05 §11.3) and therefore survives restarts.

### 1.10 Size limits

- Request bodies are capped at **64 KiB**, except `POST /api/v1/internal/calls/{call_id}/summary` at **256 KiB** (its transcript may reach 200 KB, spec 05 §6.3). A larger body → 413 `PAYLOAD_TOO_LARGE`. A small pure-ASGI middleware enforces it from `Content-Length` and by counting streamed bytes; Starlette has no general body limit, only multipart parser limits (verified in the 1.7.0 source).
- Arrays are bounded by the schemas (at most 10 services per booking, 50 estimate lines, 50 PO items, …); beyond that → 422.

### 1.11 Paths, tags and operation IDs

- Path segments are lower-case kebab with no trailing slash. With `FastAPI(redirect_slashes=False)`, `/api/v1/me/` is a 404 instead of a 307 redirect that would send the browser to the Railway host without its cookie (both behaviours verified).
- Static segments are registered before parameter segments at the same level (`/bookings/status-counts` before `/bookings/{booking_id}`); otherwise the UUID route matches first and answers 422.
- **OpenAPI tag = the module whose router serves the path** (glossary §7): `identity` (`/auth/*`), `shops` (incl. `/me`), `scheduling`, `bookings`, `inventory`, `qc`, `notifications`, `reporting`, `calls`, plus `system` for `/health`. Normally that is the module that owns the path's resource: the `identity` router serves `/api/v1/auth/*` (`register-owner`, `login`, `logout`), whose bodies carry only the token fields and the `user` (D81). Two documented cases follow spec 01's rule that a route combining two modules lives in the higher module: `GET /api/v1/me` returns the user with their memberships and capabilities (`MeRead`), so the `shops` module serves and tags it (`shops_get_me`; D66, D81); booking-scoped estimate, parts and QC reads are served and tagged by `bookings`, which applies D21 (`estimates` has no router; `qc` serves only the checklist). Every route has exactly one tag.
- **`operationId = "<tag>_<endpoint function name>"`**, set once with `FastAPI(generate_unique_id_function=lambda route: f"{route.tags[0]}_{route.name}")` (FastAPI's documented pattern; verified output `bookings_create_booking`). Function names are verb-first and unique within a module. Booking action routes are named after the slug in snake case (`bookings_confirm`); the customer family adds `my_` (`bookings_my_cancel`). §4.1 lists every operation ID.
- Each router declares the problem responses its routes can return (`responses=` with `Problem` and `ValidationProblem`). Declaring 422 replaces FastAPI's default `HTTPValidationError` schema (verified). FastAPI places a response `model` under `application/json`, so a `custom_openapi()` hook moves every 4xx/5xx schema to `application/problem+json` (verified).
- Request and response models are always separate classes (`…Create`/`…Update`/`…Request` in, `…Read` out), so FastAPI never emits `-Input`/`-Output` schema variants.

---

## 2. Error model

### 2.1 Problem body (RFC 9457)

| Member | Type | Rule |
|---|---|---|
| `type` | string | Always `"about:blank"`: the problem has no meaning beyond its status code (RFC 9457 §3.1.1); `code` carries the machine-readable kind |
| `title` | string | The HTTP reason phrase, as RFC 9457 §4.2.1 recommends with `about:blank` (`"Conflict"`, `"Unprocessable Content"`) |
| `status` | integer | Equal to the HTTP status code (RFC 9457 §3.1.2) |
| `detail` | string | A safe human sentence about this occurrence. Never a stack trace, SQL, exception name or internal identifier. Every 404 uses the same text |
| `instance` | string | The request path without its query string |
| `code` | `ErrorCode` | Extension member: a glossary §10 code |
| `errors` | `FieldError[]` | Only on 422: the offending fields (§2.3) |

Clients must ignore members they don't know (RFC 9457 §3.2).

### 2.2 Code → HTTP status

Every glossary §10 code, with its status and where this contract raises it.

| Code | HTTP | Raised by |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Any request schema failure (body, query, path), malformed JSON or wrong content type; service-level field rules (inactive service, part of another shop, unchecked QC item, quantity below a shortage or above what is outstanding, …) |
| `INVALID_SLOT` | 422 | `POST /api/v1/bookings`: slot off the grid, in the past, outside working hours, ending after closing, on a closed day or beyond 30 days (D37); the one field error on `slot_start` names the reason (§2.3) |
| `ESTIMATE_EMPTY` | 422 | `submit-estimate`, `send-estimate` with no lines |
| `MEMBER_NOT_ELIGIBLE` | 422 | `assign-technician`, `assign-parts-person`, `reassign-*`: not an active member with the required role in this shop |
| `UNAUTHENTICATED` | 401 | Missing, invalid or expired token; inactive user; wrong token type; bad agent service token; bad webhook signature |
| `INVALID_CREDENTIALS` | 401 | `POST /api/v1/auth/login`: unknown e-mail, wrong password or inactive user (identical bodies) |
| `FORBIDDEN` | 403 | The caller can see the resource but the role may not do this (incl. any change to the `OWNER` membership, D19); the QC picker would be the booking's technician (D47); `/api/v1/admin/*` for anyone but a platform admin, for an admin deactivating or revoking themselves, and for any request whose `Sec-Fetch-Site` is not `same-origin` or `none` (D94, D98, spec 19 §4) |
| `NOT_ASSIGNED` | 403 | Visible booking, right role, not the assignee: in practice a QC inspector passing or failing a job someone else picked |
| `IDENTITY_NOT_VERIFIED` *(P2)* | 403 | Agent data routes before `verify-caller` succeeded |
| `NOT_FOUND` | 404 | Unknown or invisible resource (other tenant, not assigned, not own booking, inactive membership); unknown path or action slug |
| `METHOD_NOT_ALLOWED` | 405 | Known path, unsupported method |
| `EMAIL_ALREADY_REGISTERED` | 409 | Owner sign-up with an existing e-mail; wizard with an existing e-mail and a wrong password or an inactive account |
| `INVALID_TRANSITION` | 409 | Booking action not allowed from the current status (incl. any action on a terminal booking) |
| `CONCURRENT_UPDATE` | 409 | `expected_version` or `expected_received_qty` no longer matches; deadlock or lock timeout (should not happen with the lock order) |
| `SLOT_FULL` | 409 | Slot capacity reached at booking time |
| `ALREADY_PICKED` | 409 | `pick-qc` on a booking already `QC_IN_PROGRESS` |
| `STALE_ESTIMATE` | 409 | `approve-estimate`/`reject-estimate` with an `estimate_id` that is not the current `SENT` version (superseded, another booking's or unknown) |
| `ESTIMATE_LOCKED` | 409 | `PUT …/estimate` when the caller may not edit in the current status |
| `INSUFFICIENT_STOCK` | 409 | `mark-parts-ready` or `allocate-parts` without enough stock or reservations; a stock adjustment that would leave `on_hand` below `reserved` or below 0 |
| `CALL_BUSY` *(P2)* | 409 | The booking already has an active call, or the caller or the called customer is already in another call |
| `CALL_ALREADY_ANSWERED` *(P2)* | 409 | Another callee accepted first |
| `CALL_NOT_ACTIVE` *(P2)* | 409 | Accept or decline on a call that is no longer ringing; agent routes after the AI leg's window (ending an ended call is 200, not an error) |
| `CONFLICT` | 409 | Duplicate SKU, membership or active service name; grid change blocked by future bookings (D37); `order-parts` when nothing is short; receiving a `RECEIVED` PO; the platform levers' wrong states and the last active platform admin (spec 19 §4) |
| `PAYLOAD_TOO_LARGE` | 413 | Body over the §1.10 limit |
| `SHOP_SUSPENDED` | 403 | Staff routes of a suspended shop and customer actions on its bookings except `cancel` (D96, spec 19 §2) |
| `RATE_LIMITED` | 429 | §1.9 limiters |
| `INTERNAL_ERROR` | 500 | Unexpected errors (traceback logged with the request ID, never returned) |
| `CALLING_DISABLED` *(P2)* | 503 | Calling not configured (`CALL_PROVIDER_*` blank), LiveKit unreachable or out of quota, or the monthly calling cap `CALL_MONTHLY_MINUTES_CAP` reached (glossary §10, spec 05 §8.7). A blank `LLM_API_KEY` or a reached `AI_DAILY_CALL_CAP` never fails a call; the call just gets no AI leg |

### 2.3 Field errors (422)

`errors[]` items are `{field, message, code}`:

- `field` — a dot path into the request body (`customer.email`, `lines.2.unit_price`). Query and path parameters keep their location prefix (`query.limit`, `path.booking_id`); `""` means the body as a whole (missing or not JSON). The web maps body paths straight onto form fields (spec 09 §2.9).
- `message` — a human sentence (Pydantic's `msg` or the service's text). Pydantic's `input` and `ctx` are never returned, because they can echo a password (spec 04).
- `code` — machine-readable: Pydantic's error `type` for schema errors (`missing`, `string_too_short`, `string_too_long`, `extra_forbidden`, `enum`, `uuid_parsing`, `json_invalid`, `greater_than_equal`, `less_than_equal`, `too_short`, `too_long`, `value_error`, …), or one of these service codes: `invalid_reference` (an id that is unknown, inactive or from another shop), `not_whole_rupees`, `not_on_grid` (a working-hours time off the slot grid), `invalid_range`, `hours_not_on_grid`, `duplicate`, `not_allowed` (a field not permitted in this state, e.g. `inspection_notes` from an SA), `missing_shortage`, `below_shortage`, `not_short`, `exceeds_outstanding`, `nothing_to_receive`, `checklist_incomplete` (a QC checklist key missing or repeated; an **unknown** key never gets this far: `key` is typed `QcChecklistKey`, §3.6, so Pydantic answers `enum` at `checklist.N.key`), `checklist_item_failed`, `unchanged`.
- 422 codes other than `VALIDATION_ERROR` carry the one field they concern: `INVALID_SLOT` → `slot_start`, `ESTIMATE_EMPTY` → `lines` (field code `too_short`, as built), `MEMBER_NOT_ELIGIBLE` → `technician_user_id` or `parts_person_user_id`.
- **`INVALID_SLOT` reason codes** (glossary §10; checked in this order by `scheduling.validate_slot`, the first failure answers): `off_grid` (the local wall time is not midnight + k × `slot_duration_minutes` with zero seconds, or it is not one of that day's grid instants, e.g. inside a DST gap), `in_past` (the slot does not start after now, D63), `beyond_horizon` (its local date is later than today + 30 days), `closed_day` (the shop is closed that weekday), `outside_hours` (it starts before opening or ends after closing). The field error is `{field: "slot_start", code: <reason>, message}`.

Verified sample: a body with an invalid `shop_id`, a short nested password, an empty `service_ids` and an extra `status` produced four Pydantic errors whose `loc` values `["body","shop_id"]` (`uuid_parsing`), `["body","customer","password"]` (`string_too_short`), `["body","service_ids"]` (`too_short`) and `["body","status"]` (`extra_forbidden`) the handler turns into the fields `shop_id`, `customer.password`, `service_ids` and `status`, all in one response. `loc` and `msg` are Pydantic's internal names; the wire shape is always `{field, message, code}`.

### 2.4 Framework and database errors

- `RequestValidationError` → 422 `VALIDATION_ERROR`, through a handler registered as FastAPI documents ("Override request validation exceptions").
- Starlette's `HTTPException` — the handler is registered for Starlette's class, not FastAPI's subclass, so Starlette's own errors are caught too (FastAPI docs): 404 → `NOT_FOUND` (unknown path, trailing slash), 405 → `METHOD_NOT_ALLOWED` with `Allow` (verified), 401 → `UNAUTHENTICATED`, 403 → `FORBIDDEN`, 413 → `PAYLOAD_TOO_LARGE`, 429 → `RATE_LIMITED`; any other 4xx → 422 `VALIDATION_ERROR`; any 5xx → 500 `INTERNAL_ERROR`.
- `AppError` (pure Python, `app.core.errors`) → the status of its code.
- Anything unhandled → 500 `INTERNAL_ERROR` with a generic `detail` (`FastAPI(debug=False)`).
- Text PostgreSQL cannot store → 422 `VALIDATION_ERROR` with `errors: []` and `detail` "Text must not contain NUL (\\u0000) characters or unpaired surrogates." (as built, `app.core.db_errors`). It covers a NUL character in a text value or a query parameter (SQLSTATE `22021`) or inside JSONB (`22P05`), and a lone UTF-16 surrogate, which asyncpg rejects before sending (a `22000` data error caused by `UnicodeEncodeError`; other `22000` errors stay 500). All of these pass Pydantic's `str`, so this one mapping protects every module's text fields and search parameters. A module may still reject them earlier with a field error, as estimates does.
- Database integrity errors are mapped by constraint name (spec 02 §7.5–7.6): `uq_users_email` → 409 `EMAIL_ALREADY_REGISTERED`; `uq_parts_shop_id_sku`, `uq_shop_memberships_shop_id_user_id`, `uq_services_active_name`, `ck_purchase_order_items_quantities` → 409 `CONFLICT`; `uq_qc_inspections_one_open_per_booking` → 409 `ALREADY_PICKED`; `uq_estimates_*` → 409 `CONCURRENT_UPDATE`; `ck_parts_*` and `ck_booking_parts_quantities` → 409 `INSUFFICIENT_STOCK`; SQLSTATE `40P01` / `55P03` → 409 `CONCURRENT_UPDATE`; anything else, including the append-only trigger's `P0001`, → 500.

### 2.5 Examples

```json
{ "type": "about:blank", "title": "Unauthorized", "status": 401, "code": "UNAUTHENTICATED",
  "detail": "Authentication required.", "instance": "/api/v1/me" }
```
(401 also sends `WWW-Authenticate: Bearer`, and clears `bf_session` when the cookie was the invalid credential.)

```json
{ "type": "about:blank", "title": "Forbidden", "status": 403, "code": "FORBIDDEN",
  "detail": "Your role in this shop cannot perform 'confirm'.",
  "instance": "/api/v1/shops/3f2c9a1e-6b4d-4c8e-9a7f-1d2e3f4a5b6c/bookings/8d1e4b6a-2c3f-4e5a-b7c8-9d0e1f2a3b4c/actions/confirm" }
```

```json
{ "type": "about:blank", "title": "Forbidden", "status": 403, "code": "NOT_ASSIGNED",
  "detail": "This QC inspection was picked by another inspector.",
  "instance": "/api/v1/shops/3f2c9a1e-6b4d-4c8e-9a7f-1d2e3f4a5b6c/bookings/8d1e4b6a-2c3f-4e5a-b7c8-9d0e1f2a3b4c/actions/pass-qc" }
```

```json
{ "type": "about:blank", "title": "Not Found", "status": 404, "code": "NOT_FOUND",
  "detail": "The requested resource was not found.",
  "instance": "/api/v1/shops/7b8c9d0e-1f2a-4b3c-8d4e-5f6a7b8c9d0e/bookings/6c7d8e9f-0a1b-4c2d-8e3f-4a5b6c7d8e9f" }
```

```json
{ "type": "about:blank", "title": "Conflict", "status": 409, "code": "INVALID_TRANSITION",
  "detail": "'confirm' is not allowed while the booking is CONFIRMED.",
  "instance": "/api/v1/shops/3f2c9a1e-6b4d-4c8e-9a7f-1d2e3f4a5b6c/bookings/8d1e4b6a-2c3f-4e5a-b7c8-9d0e1f2a3b4c/actions/confirm" }
```

```json
{ "type": "about:blank", "title": "Conflict", "status": 409, "code": "SLOT_FULL",
  "detail": "This time slot is fully booked. Please choose another slot.", "instance": "/api/v1/bookings" }
```

```json
{ "type": "about:blank", "title": "Unprocessable Content", "status": 422, "code": "VALIDATION_ERROR",
  "detail": "The request contains invalid fields.", "instance": "/api/v1/bookings",
  "errors": [
    { "field": "vehicle.year", "message": "Year must be between 1900 and 2027.", "code": "value_error" },
    { "field": "customer.password", "message": "String should have at least 12 characters", "code": "string_too_short" }
  ] }
```

```json
{ "type": "about:blank", "title": "Too Many Requests", "status": 429, "code": "RATE_LIMITED",
  "detail": "Too many attempts. Try again in 412 seconds.", "instance": "/api/v1/auth/login" }
```
(with `Retry-After: 412`)

```json
{ "type": "about:blank", "title": "Internal Server Error", "status": 500, "code": "INTERNAL_ERROR",
  "detail": "An unexpected error occurred. Please try again.", "instance": "/api/v1/shops/3f2c9a1e-6b4d-4c8e-9a7f-1d2e3f4a5b6c/overview" }
```

---

## 3. Shared schemas

Notation: `name` type, separated by `·`. `T?` = may be `null` (the field is always present in responses). `T[]` = array. "timestamp", "date", "Money" and "Quantity" follow §1.5. Request-only schemas are marked "(request)"; the per-endpoint request bodies are in §4 and §5. Every enum is emitted as an OpenAPI enum component, so the generated TypeScript gets string unions (§3.9).

### 3.1 Envelopes and references

| Schema | Fields | Notes |
|---|---|---|
| `Problem` | `type` string · `title` string · `status` int · `detail` string · `instance` string · `code` ErrorCode | §2.1; media type `application/problem+json` |
| `ValidationProblem` | `Problem` + `errors` FieldError[] | 422 only |
| `FieldError` | `field` string · `message` string · `code` string | §2.3 |
| `Page[T]` | `items` T[] · `total` int · `limit` int · `offset` int | Paginated collections (§1.6) |
| `ItemList[T]` | `items` T[] | Bounded lists (§1.6) |
| `UserRef` | `user_id` uuid · `full_name` string | Actors and authors |
| `MemberRef` | `user_id` uuid · `full_name` string · `is_active` bool | Assignees; `is_active` is the membership in this shop, so a deactivated assignee shows a warning (D19) |
| `BookingRef` | `id` uuid · `reference` string · `status` BookingStatus · `version` int | |
| `PartRef` | `id` uuid · `sku` string · `name` string | |
| `PurchaseOrderRef` | `id` uuid · `po_number` string · `status` PurchaseOrderStatus · `ordered_qty_total` int · `received_qty_total` int | |

### 3.2 Identity, shops and team

| Schema | Fields | Notes |
|---|---|---|
| `UserRead` | `id` uuid · `email` string · `full_name` string · `phone` string? | The account itself, without memberships (D81). Never `password_hash` |
| `MeRead` | every `UserRead` field + `is_platform_admin` bool + `memberships` MembershipRead[] | Flat, as spec 04 fixes it. `is_platform_admin` opens the admin console (D94, spec 19 §4). **Active** memberships only, sorted by shop name; `[]` for a pure customer. Never `password_hash`, inactive memberships or another user's data |
| `MembershipRead` | `membership_id` uuid · `shop_id` uuid · `shop_name` string · `shop_slug` string · `shop_suspended` bool · `role` MembershipRole · `capabilities` Capability[] | Flat item (spec 04, D66); drives the shop switcher, role routing and non-booking buttons. `shop_suspended` (D96) lets the POS show a suspended shop without calling its blocked routes |
| `SessionRead` | `access_token` string · `token_type` `"bearer"` · `expires_in` int · `user` UserRead | Login and owner registration (D8, D81); the matching cookie is set too. No memberships: the web calls `GET /api/v1/me` next (D81) |
| `WorkingHoursRead` | `weekday` int 0–6 · `is_closed` bool · `opens_at` string? (`HH:MM`) · `closes_at` string? | Always 7 entries, Monday (0) first; times `null` on closed days |
| `WorkingHoursWrite` (request) | `weekday` int 0–6 · `is_closed` bool · `opens_at` string? · `closes_at` string? | Open day: both times required, on the slot grid (minutes since local midnight divisible by `slot_duration_minutes`, D37) → else `not_on_grid`; `closes_at` > `opens_at` → else `invalid_range`. Closed day: times ignored and stored as `null`. A list must hold exactly 7 entries with distinct weekdays (`duplicate`) |
| `ServiceRead` | `id` uuid · `name` string · `description` string? · `estimated_duration_minutes` int · `base_price` Money? · `is_active` bool · `created_at` · `updated_at` | `base_price` `null` = "Price after inspection" |
| `ShopPublicSummary` | `id` uuid · `slug` string · `name` string · `city` string · `logo_url` string? · `rating` number? · `services` {`id` uuid, `name` string}[] · `services_count` int | Active services, by name |
| `ShopPublicDetail` | `id` · `slug` · `name` · `address` · `city` · `phone` · `logo_url`? · `rating`? · `timezone` · `slot_duration_minutes` int · `working_hours` WorkingHoursRead[] · `services` ServiceRead[] · `is_bookable` bool | Active services only; `is_bookable` = at least one active service (D64) |
| `SlotRead` | `slot_start` timestamp · `slot_end` timestamp · `remaining` int | `remaining` = `slot_capacity − booked_count` ≥ 1 (D68) |
| `AvailabilityRead` | `shop_id` uuid · `date` date · `timezone` string · `slot_duration_minutes` int · `slots` SlotRead[] | Slots ordered by `slot_start` |
| `ShopRead` | `id` · `slug` · `name` · `address` · `city` · `phone` · `timezone` · `slot_duration_minutes` int · `slot_capacity` int · `logo_url`? · `rating`? · `is_listed` bool · `has_future_bookings` bool · `working_hours` WorkingHoursRead[] · `created_at` · `updated_at` | Staff view. `has_future_bookings` tells the settings form that duration and timezone are locked (D37) |
| `MemberRead` | `membership_id` uuid · `user` {`id` uuid, `full_name` string, `email` string, `phone` string?} · `role` MembershipRole · `is_active` bool · `open_jobs` int · `created_at` · `updated_at` | `open_jobs` = bookings not in `READY_FOR_PICKUP`, `COMPLETED` or `CANCELLED` where the member is the technician, the parts person or the current QC picker |
| `MemberCreatedRead` | every `MemberRead` field + `account_created` bool | `false` = an existing account was attached and only the membership was created (D18) |
| `RealtimeTicketRead` | `ticket` string · `expires_in` int | `expires_in` is 60 (D70) |
| `HealthRead` | `status` `"ok"` or `"degraded"` · `database` `"ok"` or `"error"` | `/health` only (as built, D84) |

Capabilities per role (D66, glossary §2.4), computed by the shops module and sorted alphabetically:

| Role | `capabilities` |
|---|---|
| `OWNER` | `parts.manage`, `services.manage`, `shop.manage`, `team.manage` (+ `tasks.manage`) |
| `SERVICE_ADVISOR` | none (+ `tasks.manage`) |
| `PARTS_PERSON` | `parts.manage`, `stock.manage` |
| `TECHNICIAN`, `QC_INSPECTOR` | none |

`tasks.manage` appears only when the bonus `calls` module is enabled (glossary §2.4, spec 04), so a P0-only deployment never shows task buttons.

### 3.3 Bookings

| Schema | Fields | Notes |
|---|---|---|
| `VehicleRead` | `id` uuid · `registration_number` string · `make` string · `model` string · `year` int · `color` string? · `mileage_km` int? · `created_at` · `updated_at` | The vehicle as stored now (D35) |
| `VehicleBrief` | `registration_number` · `make` · `model` · `year` | Lists |
| `VehicleWrite` (request) | `registration_number` string 2–20 · `make` string 1–60 · `model` string 1–60 · `year` int 1900 … current year + 1 · `color` string? ≤ 30 · `mileage_km` int? 0–2 000 000 | The registration key (upper case, spaces and hyphens removed) must match `^[A-Z0-9]{2,20}$` |
| `BookingServiceRead` | `service_id` uuid · `name` string · `base_price` Money? | Snapshots taken at booking time (D34) |
| `EstimateSummary` | `estimate_id` uuid · `version` int · `status` EstimateStatus · `grand_total` Money · `line_count` int | Staff: the latest version. Customer: the latest `SENT`, `APPROVED` or `REJECTED` version (D39) |
| `PartsSummary` | `required_count` int · `available_count` int · `shortage_count` int · `all_available` bool | `null` until `assign-parts-person` has run. Counts booking-parts rows: "available" = fully reserved, consumed, or coverable from stock now; `all_available` is `true` for zero rows (labour-only, D31). `null` for QC callers (stock data, spec 04 §B) |
| `BookingSummary` | `id` · `shop_id` · `reference` · `status` · `version` · `slot_start` · `slot_end` · `status_changed_at` · `customer` UserRef · `vehicle` VehicleBrief · `service_names` string[] · `technician` MemberRef? · `parts_person` MemberRef? · `qc_inspector` MemberRef? · `estimate_summary` EstimateSummary? · `parts_summary` PartsSummary? · `open_qc_issues_count` int · `qc_round` int · `repair_started_at` timestamp? · `allowed_actions` BookingActionSlug[] · `created_at` · `updated_at` | Staff list item |
| `BookingDetail` | `id` · `shop_id` · `reference` · `status` · `version` · `slot_start` · `slot_end` · `status_changed_at` · `customer` {`user_id`, `full_name`, `email`?, `phone`?} · `vehicle` VehicleRead · `mileage_km` int? · `services` BookingServiceRead[] · `customer_notes`? · `inspection_notes`? · `technician`? · `parts_person`? · `qc_inspector`? · `estimate_summary`? · `parts_summary`? · `open_qc_issues_count` · `qc_round` · `repair_started_at`? · `ready_notified_at`? · `completed_at`? · `cancelled_at`? · `cancelled_by` UserRef? · `cancel_reason`? · `last_event` BookingEventRead? · `allowed_actions` · `created_at` · `updated_at` | Staff detail and every staff action response. `customer.email` and `customer.phone` are `null` unless the caller is `OWNER` or `SERVICE_ADVISOR`. `mileage_km` is the snapshot given at booking time (D65) |
| `CustomerBookingSummary` | `id` · `reference` · `status` · `version` · `slot_start` · `slot_end` · `status_changed_at` · `shop` {`id`, `slug`, `name`, `city`, `phone`, `timezone`} · `vehicle` VehicleBrief · `service_names` string[] · `estimate_summary`? · `allowed_actions` · `created_at` · `updated_at` | Customer list item |
| `CustomerBookingDetail` | `id` · `reference` · `status` · `version` · `slot_start` · `slot_end` · `status_changed_at` · `shop` {`id`, `slug`, `name`, `address`, `city`, `phone`, `timezone`} · `vehicle` VehicleRead · `mileage_km`? · `services` BookingServiceRead[] · `customer_notes`? · `estimate` CustomerEstimateRead? · `estimate_revision_in_progress` bool · `allowed_actions` · `ready_notified_at`? · `completed_at`? · `cancelled_at`? · `cancelled_by_customer` bool? · `cancel_reason`? · `created_at` · `updated_at` | Customer detail and every customer action response. No staff names, internal notes, stock or event metadata (spec 04 §C) |
| `BookingCreatedRead` | `access_token` · `token_type` · `expires_in` · `account_created` bool · `booking` CustomerBookingDetail | D32 |
| `BookingEventRead` | `id` · `action` BookingAction · `from_status` BookingStatus? · `to_status` BookingStatus · `actor` UserRef? · `actor_role` ActorRole · `note` string? · `metadata` object · `created_at` | Staff timeline; `metadata` shapes in spec 08 |
| `CustomerBookingEventRead` | `id` · `action` BookingAction · `from_status`? · `to_status` · `by_customer` bool · `note` string? · `created_at` | Customer timeline (projection below) |
| `StatusCountsRead` | `items` {`status` BookingStatus, `count` int}[] · `total` int | All 17 statuses in glossary §3 order, zeros included |

Derived fields, computed on read (never trusted from a client):

- `status_changed_at` — `created_at` of the latest event whose `to_status` differs from its `from_status` (or the `CREATE` event).
- `qc_round` — the number of `qc_inspections` rows of the booking, plus 1 while it is `QC_PENDING`; 0 if it never reached QC.
- `open_qc_issues_count` — its `OPEN` QC issues.
- `estimate_revision_in_progress` — a version newer than the one shown in `estimate` exists but isn't visible to the customer yet (e.g. a draft after a rejection).
- `allowed_actions` — spec 08's pure function for this caller and endpoint family: data guards are not pre-evaluated; `CREATE` and `RECEIVE_PARTS` never appear; the customer family lists only `approve-estimate`, `reject-estimate`, `cancel`, `complete`; the Owner gets SA slugs only; the P1 `reassign-*` slugs appear only once their routes exist.
- `last_event` — the booking's latest event; after an action it is that action's event (e.g. `metadata.po_number` after `order-parts`).

Event lists are ordered by `(created_at, seq)` (D79). `seq` is not exposed: it is a global counter and would let any user estimate the platform's activity across tenants.

**Customer event projection:** `EDIT_ESTIMATE`, `REASSIGN_TECHNICIAN` and `REASSIGN_PARTS_PERSON` are omitted; `note` is filled only for `DECLINE`, `CANCEL` and `REJECT_ESTIMATE` (customer-facing reasons, spec 04 §C); actor names, roles and `metadata` never appear. A `FAIL_QC` event appears as `QC_IN_PROGRESS → IN_REPAIR` without issue details (spec 09 §4.4).

### 3.4 Estimates

| Schema | Fields | Notes |
|---|---|---|
| `PartStockRef` | `id` · `sku` · `name` · `unit_cost` Money · `is_active` bool · `on_hand` int? · `reserved` int? · `available` int? · `reorder_level` int? · `stock_state` StockState? | Stock fields are `null` when the caller is a QC inspector (spec 04 §B); live values (D40) |
| `EstimateLineRead` | `id` · `position` int · `line_type` EstimateLineType · `part` PartStockRef? · `description` string · `quantity` Quantity · `unit_price` Money · `line_total` Money | `part` is `null` on `LABOUR` lines; on `PART` lines `description` is the catalogue name copied when the line was saved |
| `EstimateRead` | `id` · `booking_id` · `version` int · `status` EstimateStatus · `lines` EstimateLineRead[] · `parts_total` Money · `labour_total` Money · `grand_total` Money · `created_by` UserRef · `created_at` · `submitted_at`? · `sent_at`? · `sent_by` UserRef? · `decided_at`? · `decided_by` UserRef? · `customer_note`? | Staff view of one version |
| `EstimateEditRead` | `EstimateRead` + `booking_version` int · `created_new_version` bool | `PUT …/estimate` response |
| `CustomerEstimateLineRead` | `id` · `position` · `line_type` · `description` · `quantity` · `unit_price` · `line_total` | No SKU, no stock |
| `CustomerEstimateRead` | `id` · `version` · `status` (`SENT`, `APPROVED` or `REJECTED` only) · `lines` CustomerEstimateLineRead[] · `parts_total` · `labour_total` · `grand_total` · `sent_at` · `decided_at`? · `customer_note`? | D39 |

### 3.5 Inventory

| Schema | Fields | Notes |
|---|---|---|
| `PartRead` | `id` · `sku` · `name` · `unit_cost` Money · `is_active` bool · `on_hand` int · `reserved` int · `available` int · `reorder_level` int · `stock_state` StockState · `on_order` int · `created_at` · `updated_at` | `available = on_hand − reserved`; `stock_state` = `OUT` when available is 0, else `LOW` when available ≤ `reorder_level`, else `OK` (D45); `on_order` = outstanding quantity on open POs |
| `StockMovementRead` | `id` · `part_id` · `movement_type` StockMovementType · `quantity` int · `on_hand_delta` int · `reserved_delta` int · `booking` {`id`, `reference`}? · `purchase_order` {`id`, `po_number`}? · `actor` UserRef · `note`? · `created_at` | The ledger (D42) |
| `StockAdjustmentRead` | `part` PartRead · `movement` StockMovementRead | |
| `BookingPartRead` | `part` PartStockRef · `required_qty` int · `reserved_qty` int · `consumed_qty` int · `outstanding_qty` int · `shortage_qty` int | `outstanding = required − reserved − consumed`; `shortage = max(0, outstanding − available)` (brief §7.6) |
| `BookingPartsRead` | `booking_id` uuid · `all_available` bool · `required_count` int · `available_count` int · `items` BookingPartRead[] · `purchase_orders` PurchaseOrderRef[] | `purchase_orders` = POs linked to this booking (D43) |
| `PurchaseOrderItemRead` | `id` · `part` PartRef · `ordered_qty` int · `received_qty` int · `outstanding_qty` int · `unit_cost` Money · `line_cost` Money | `line_cost = ordered_qty × unit_cost` |
| `PurchaseOrderSummary` | `id` · `po_number` · `status` PurchaseOrderStatus · `supplier_name`? · `booking` BookingRef? · `item_count` int · `ordered_qty_total` int · `received_qty_total` int · `total_cost` Money · `created_by` UserRef · `created_at` · `received_at`? | `booking` `null` = general restock |
| `PurchaseOrderRead` | all `PurchaseOrderSummary` fields + `items` PurchaseOrderItemRead[] · `updated_at` | |
| `PurchaseOrderReceiveRead` | `purchase_order` PurchaseOrderRead · `receive_parts_applied` bool | `true` when this receipt moved the linked booking to `PARTS_READY` (T15); its new status is `purchase_order.booking.status` |

### 3.6 QC

| Schema | Fields | Notes |
|---|---|---|
| `QcChecklistTemplateItem` | `key` QcChecklistKey · `label` string | D46 order: `road_test` "Road test", `no_warning_lights` "No warning lights", `no_leaks` "No leaks", `fluid_levels` "Fluid levels OK", `complaint_resolved` "Customer complaint resolved" |
| `QcChecklistItemWrite` (request) | `key` QcChecklistKey · `passed` bool · `note` string? ≤ 500 | A checklist is exactly the 5 keys, each once: a missing or repeated key → `checklist_incomplete` (field `checklist`); an unknown key fails the enum → `enum` (field `checklist.N.key`) |
| `QcChecklistItemRead` | `key` · `label` · `passed` bool · `note`? | Stored on the inspection for pass and fail (D46) |
| `QcIssueRead` | `id` · `qc_inspection_id` · `title` · `description` · `status` QcIssueStatus · `created_by` UserRef · `created_at` · `resolved_at`? · `resolved_by` UserRef? | |
| `QcInspectionRead` | `id` · `round` int · `inspector` UserRef · `picked_at` · `completed_at`? · `result` QcResult? · `checklist` QcChecklistItemRead[]? · `notes`? · `issues` QcIssueRead[] | One row per QC round, in order; `result` `null` while in progress |

### 3.7 Notifications and reporting

| Schema | Fields | Notes |
|---|---|---|
| `NotificationRead` | `id` · `type` NotificationType · `title` string · `body` string · `recipient_role` ActorRole · `link` string · `shop_id`? · `shop_name`? · `booking_id`? · `booking_reference`? · `read_at`? · `created_at` | D67; title and body are composed by the server in English |
| `UnreadCountRead` | `count` int | |
| `OverviewRead` | `shop` {`id`, `slug`, `name`, `city`, `is_listed`} · `status_counts` {`status`, `count`}[] · `today` {`date`, `bookings`, `ready_for_pickup`, `completed`} · `team` {`membership_id`, `user_id`, `full_name`, `role`, `is_active`, `open_jobs`}[] · `inventory` {`parts_count`, `low_stock_count`, `out_of_stock_count`, `stock_value` Money, `open_purchase_orders`} · `low_stock` PartRead[] · `setup` {`has_services`, `has_team`, `has_parts`, `is_listed`} | Brief §7.4 Owner |
| `OwnerShopSummary` | `shop` {`id`, `slug`, `name`, `city`} · `today_bookings` int · `needs_sa_action` int · `in_progress` int · `ready_for_pickup` int · `low_stock_count` int | P1 |
| `OwnerSummaryRead` | `items` OwnerShopSummary[] | Shops where the caller is `OWNER` and that are not suspended (D99), by name |

Reporting definitions (shop timezone): `today.bookings` = non-cancelled bookings whose slot starts today; `today.ready_for_pickup` = bookings currently `READY_FOR_PICKUP`; `today.completed` = `completed_at` today; `needs_sa_action` = statuses whose step owner is the SA (`PENDING`, `CONFIRMED`, `ESTIMATE_REVIEW`, `ESTIMATE_APPROVED`, `ESTIMATE_REJECTED`, `READY_FOR_PICKUP`); `in_progress` = every other non-terminal status; `stock_value` = Σ `on_hand × unit_cost` over active parts; `low_stock` = up to 5 active parts, `OUT` first, then by `available`; `low_stock_count` counts `LOW` and `OUT`; `has_team` = at least one active non-owner member; `has_parts` / `has_services` = at least one active part / service.

Notification `link` (D67), chosen by `recipient_role`:

| `recipient_role` | `link` |
|---|---|
| `CUSTOMER` | `/bookings/{booking_id}` |
| `SERVICE_ADVISOR`, `OWNER` | `/pos/shops/{shop_id}/bookings/{booking_id}` |
| `TECHNICIAN` | `/pos/shops/{shop_id}/jobs/{booking_id}` |
| `PARTS_PERSON` | `/pos/shops/{shop_id}/parts/{booking_id}` |
| `QC_INSPECTOR` | `/pos/shops/{shop_id}/qc/{booking_id}` |
| any, type `AI_TASK_CREATED` (P2) | `/pos/shops/{shop_id}/calls` |

When "SAs of the shop" fall back to the Owner (D26), the row's `recipient_role` is `OWNER`. The `link` is computed once, when the row is written, and is the only deep link: clients navigate to it and never derive a route from `recipient_role`, `type` or ids (D67).

### 3.8 Bonus schemas (P2 — copied from spec 05 §8.3, which is authoritative)

| Schema | Fields |
|---|---|
| `CallRead` | `id` · `shop_id` · `shop_name` · `booking_id` · `booking_reference` · `vehicle_label` · `direction` CallDirection · `status` CallStatus · `missed_reason` MissedReason? · `caller` {`user_id`, `display_name`} · `callee_label` · `answered_by` {`user_id`, `display_name`}? · `rung_count` int · `started_at` · `ring_deadline` · `answered_at`? · `ended_at`? · `duration_seconds`? · `ai` {`status` AiLegStatus, `answered_at`?, `ended_at`?, `duration_seconds`?}? · staff views add `has_summary` bool · `open_task_count` int. **Never a phone number or e-mail** (brief §8.1) |
| `CallConnection` | `url` (LiveKit WebSocket URL) · `room` · `token` · `identity` · `expires_at` |
| `CallStartRead` | `call` CallRead · `connection` CallConnection (start and accept) |
| `CallDetailRead` | `CallRead` + `identity_method` IdentityMethod? · `summary` {`intent`, `intent_category` CallIntent, `details`, `sentiment` Sentiment, `is_urgent`, `language`, `is_fallback`, `transcript`, `created_at`}? · `tasks` TaskRead[] |
| `TaskRead` | `id` · `shop_id` · `booking_id`? · `booking_reference`? · `call_id`? · `customer` {`user_id`, `display_name`}? · `kind` TaskKind · `title` · `description`? · `is_urgent` bool · `status` TaskStatus · `metadata` object · `created_at` · `done_at`? · `done_by` {`user_id`, `display_name`}? · `done_note`? · `summary` {`intent`, `intent_category`, `sentiment`, `is_fallback`}? |

### 3.9 Enums on the wire

All values exactly as glossary §2–§6 and §10: `BookingStatus` (17), `BookingAction` (27, incl. `CREATE` and `RECEIVE_PARTS`; used in events), `ActorRole`, `MembershipRole`, `StaffRole`, `Capability` (the 6 dotted names), `EstimateStatus`, `EstimateLineType`, `StockMovementType`, `PurchaseOrderStatus`, `QcResult`, `QcIssueStatus`, `QcChecklistKey`, `NotificationType`, `ErrorCode`; bonus `CallStatus`, `CallDirection`, `MissedReason`, `AiLegStatus`, `IdentityMethod`, `CallIntent`, `Sentiment`, `TaskKind`, `TaskStatus`. Two wire-only enums are proposed for the glossary: **`BookingActionSlug`** (the 25 lower-kebab slugs of glossary §4, `edit-estimate` included; the item type of `allowed_actions`) and **`StockState`** (`OK`, `LOW`, `OUT`; computed, never stored).

---

## 4. Endpoint catalogue

### 4.1 Summary

Auth: **public** = no credentials read · **optional** = session if present · **session** = any logged-in user, own data only · **member** = active member of `{shop_id}` (else 404). Roles: O = `OWNER`, SA = `SERVICE_ADVISOR`, T = `TECHNICIAN`, PP = `PARTS_PERSON`, QC = `QC_INSPECTOR`; a member with another role gets 403 `FORBIDDEN`. "D21" = only bookings the caller can see. Paths below `/api/v1/shops/{shop_id}` are shortened to `…`.

| Method and path | `operationId` | Auth · roles | Success | Pri | Serves |
|---|---|---|---|---|---|
| `GET /health` | `system_health` | public | 200 `HealthRead` | P0 | Railway, DEP-01 |
| `POST /api/v1/auth/register-owner` | `identity_register_owner` | public | 201 `SessionRead` + cookie | P0 | P-05 · E-03 |
| `POST /api/v1/auth/login` | `identity_login` | public | 200 `SessionRead` + cookie | P0 | P-04, P-03 · E-01 |
| `POST /api/v1/auth/logout` | `identity_logout` | public | 204, cookie cleared | P0 | S-01, X-04 · E-02 |
| `GET /api/v1/me` | `shops_get_me` | session | 200 `MeRead` | P0 | all screens · E-04 |
| `GET /api/v1/public/shops` | `shops_list_public_shops` | public | 200 `Page[ShopPublicSummary]` | P0 | P-01, P-03 · E-06 |
| `GET /api/v1/public/cities` | `shops_list_public_cities` | public | 200 `ItemList[string]` | P0 | P-01 · E-07 |
| `GET /api/v1/public/shops/{shop_slug}` | `shops_get_public_shop` | public | 200 `ShopPublicDetail` | P0 | P-02, P-03 · E-08 |
| `GET /api/v1/public/shops/{shop_slug}/availability` | `scheduling_get_availability` | public | 200 `AvailabilityRead` | P0 | P-03 W3 · E-09 |
| `POST /api/v1/bookings` | `bookings_create_booking` | optional | 201 `BookingCreatedRead` + cookie | P0 | P-03 W5 · E-10 |
| `GET /api/v1/me/bookings` | `bookings_list_my_bookings` | session | 200 `Page[CustomerBookingSummary]` | P0 | C-01 · E-11 |
| `GET /api/v1/me/bookings/{booking_id}` | `bookings_get_my_booking` | session (own) | 200 `CustomerBookingDetail` | P0 | C-02, C-03 · E-12 |
| `GET /api/v1/me/bookings/{booking_id}/events` | `bookings_list_my_booking_events` | session (own) | 200 `ItemList[CustomerBookingEventRead]` | P0 | C-02 · E-13 |
| `GET /api/v1/me/bookings/{booking_id}/estimates` | `bookings_list_my_booking_estimates` | session (own) | 200 `ItemList[CustomerEstimateRead]` | P1 | C-02 · E-14 |
| `POST /api/v1/me/bookings/{booking_id}/actions/{slug}` (4 slugs) | `bookings_my_<slug>` | session (own) | 200 `CustomerBookingDetail` | P0 | C-02 · E-15 (§5) |
| `GET /api/v1/me/vehicles` | `bookings_list_my_vehicles` | session | 200 `ItemList[VehicleRead]` | P1 | P-03 W4 · E-16 |
| `GET …/bookings` | `bookings_list_shop_bookings` | member, D21 | 200 `Page[BookingSummary]` | P0 | SA-01, T-01, PP-01, QI-01, O-01 · E-33 |
| `GET …/bookings/status-counts` | `bookings_get_status_counts` | member, D21 | 200 `StatusCountsRead` | P0 | SA-01 · E-34 |
| `GET …/bookings/{booking_id}` | `bookings_get_shop_booking` | member, D21 | 200 `BookingDetail` | P0 | SA-02, T-02, PP-02, QI-02 · E-35 |
| `GET …/bookings/{booking_id}/events` | `bookings_list_booking_events` | member, D21 | 200 `ItemList[BookingEventRead]` | P0 | SA-02, T-02, QI-02 · E-36 |
| `GET …/bookings/{booking_id}/estimates` | `bookings_list_booking_estimates` | member, D21 | 200 `ItemList[EstimateRead]` | P0 | SA-02, T-02, PP-02, QI-02 · E-38 |
| `PUT …/bookings/{booking_id}/estimate` | `bookings_edit_estimate` | T (assigned), SA, O | 200 `EstimateEditRead` | P0 | T-02, SA-02 · E-39 (§5.3) |
| `GET …/bookings/{booking_id}/parts` | `bookings_get_booking_parts` | O, SA, T, PP; D21 | 200 `BookingPartsRead` | P0 | PP-02, SA-02, T-02 · E-40 |
| `GET …/bookings/{booking_id}/qc-inspections` | `bookings_list_booking_qc_inspections` | member, D21 | 200 `ItemList[QcInspectionRead]` | P0 | QI-02, T-02, SA-02 · E-41 |
| `POST …/bookings/{booking_id}/actions/{slug}` (22 slugs) | `bookings_<slug>` | per §5.1 | 200 `BookingDetail` | P0 (2 × P1) | SA-02, T-01/02, PP-02, QI-01/02 · E-37 (§5) |
| `POST /api/v1/shops` | `shops_create_shop` | session | 201 `ShopRead` | P0 | S-03, O-05 · E-21 |
| `GET …` (the shop) | `shops_get_shop` | member | 200 `ShopRead` | P0 | O-04 · E-22 |
| `PATCH …` (the shop) | `shops_update_shop` | O | 200 `ShopRead` | P0 | O-04 · E-23 |
| `PUT …/working-hours` | `shops_replace_working_hours` | O | 200 `ShopRead` | P0 | O-04 · E-24 |
| `GET …/members` | `shops_list_members` | O; SA (active T and PP only) | 200 `Page[MemberRead]` | P0 | O-02, SA-02, O-01, T-01 · E-25 |
| `POST …/members` | `shops_add_member` | O | 201 `MemberCreatedRead` | P0 | O-02 · E-26 |
| `PATCH …/members/{membership_id}` | `shops_update_member` | O | 200 `MemberRead` | P0 | O-02 · E-27 |
| `GET …/services` | `shops_list_services` | member | 200 `Page[ServiceRead]` | P0 | O-03 · E-28 |
| `POST …/services` | `shops_create_service` | O | 201 `ServiceRead` | P0 | O-03 · E-29 |
| `PATCH …/services/{service_id}` | `shops_update_service` | O | 200 `ServiceRead` | P0 | O-03 · E-30 |
| `GET …/parts` | `inventory_list_parts` | O, SA, T, PP | 200 `Page[PartRead]` | P0 | PP-03, T-02, SA-02, PP-04 · E-43 |
| `POST …/parts` | `inventory_create_part` | O, PP | 201 `PartRead` | P0 | PP-03 · E-44 |
| `PATCH …/parts/{part_id}` | `inventory_update_part` | O, PP | 200 `PartRead` | P0 | PP-03 · E-45 |
| `POST …/parts/{part_id}/adjustments` | `inventory_adjust_stock` | PP | 201 `StockAdjustmentRead` | P0 | PP-03 · E-46 |
| `GET …/parts/{part_id}/movements` | `inventory_list_part_movements` | O, PP | 200 `Page[StockMovementRead]` | P1 | PP-03 · E-47 |
| `GET …/purchase-orders` | `inventory_list_purchase_orders` | O, PP | 200 `Page[PurchaseOrderSummary]` | P0 | PP-04, PP-02 · E-48 |
| `POST …/purchase-orders` | `inventory_create_purchase_order` | PP | 201 `PurchaseOrderRead` | P0 | PP-04 · E-49 |
| `GET …/purchase-orders/{po_id}` | `inventory_get_purchase_order` | O, PP | 200 `PurchaseOrderRead` | P0 | PP-05 · E-50 |
| `POST …/purchase-orders/{po_id}/receive` | `inventory_receive_purchase_order` | PP | 200 `PurchaseOrderReceiveRead` | P0 | PP-05 · E-51 (§5.3) |
| `GET …/qc/checklist` | `qc_get_checklist` | member | 200 `ItemList[QcChecklistTemplateItem]` | P0 | QI-02 · E-42 |
| `GET /api/v1/me/notifications` | `notifications_list_my_notifications` | session | 200 `Page[NotificationRead]` | P0 | X-01 · E-17 |
| `GET /api/v1/me/notifications/unread-count` | `notifications_get_unread_count` | session | 200 `UnreadCountRead` | P0 | S-01 bell · E-18 |
| `POST /api/v1/me/notifications/{notification_id}/read` | `notifications_mark_notification_read` | session (own) | 204 | P0 | X-01 · E-19 |
| `POST /api/v1/me/notifications/read-all` | `notifications_mark_all_notifications_read` | session | 204 | P0 | X-01 · E-20 |
| `GET /api/v1/realtime/ticket` | `notifications_get_realtime_ticket` | session | 200 `RealtimeTicketRead` | P1 (D88) | RealtimeProvider · E-05 |
| `WS /api/v1/ws?ticket=…` | — (not in OpenAPI) | ticket | 101 | P1 (D88) | §6 |
| `GET …/overview` | `reporting_get_overview` | O | 200 `OverviewRead` | P0 | O-01 · E-31 |
| `GET /api/v1/me/owner-summary` | `reporting_get_owner_summary` | session | 200 `OwnerSummaryRead` | P1 | O-07 · E-32 |
| P2 call, task, webhook and agent routes (25) | `calls_*` | §4.14 | §4.14 | P2 | B-01…B-04 · E-52…E-60 |

OpenAPI therefore holds 76 core operations (26 of them booking-action routes) and 14 bonus operations; the webhook, the 10 agent routes and the WebSocket are excluded.

**Realtime priority (D88).** The P0 freshness path is the bell and the current view kept fresh by polling every 15 s (D14, §6.6). The WebSocket hub, `GET /api/v1/realtime/ticket` and `/api/v1/ws` are **P1** (brief §8.3 lists real-time updates as optional); the P2 calling routes need them, so they ship before any bonus work. Every other route marked P0 above works without them.

### 4.2 System

#### `GET /health` — `system_health` · public · P0
- Runs `SELECT 1` with a 2 s timeout. **200** `{"status": "ok", "database": "ok"}`; **503** `{"status": "degraded", "database": "error"}` (as built, D84). Railway's deploy-time check (D13) and DEP-01. Never reads credentials. This infrastructure route is the one exception to problem+json (§2): its 503 is `HealthRead`. Sends `Cache-Control: no-store` and `X-Request-ID` like everything else.

### 4.3 Identity (authentication)

The three `/api/v1/auth/*` routes are served by the `identity` module's router (D81). Login and owner registration return `SessionRead` — the token fields and the `user`, **never memberships** — and set the cookie; the web then calls `GET /api/v1/me` (§4.4) for memberships and capabilities.

#### `POST /api/v1/auth/register-owner` — `identity_register_owner` · public · P0 · P-05 · E-03
- **Body `OwnerRegistrationCreate`:** `full_name` 1–120 · `email` Email · `password` 12–128 (D10; never trimmed) · `phone`? Phone.
- **201 `SessionRead`** (the new `user`; no memberships, D81) + `Set-Cookie: bf_session`. Creates a user only, with no membership (D17, brief §4: staff never self-sign-up); the web then calls `GET /api/v1/me` (`memberships: []`) and `POST /api/v1/shops`.
- **Errors:** 409 `EMAIL_ALREADY_REGISTERED` (detail: "This e-mail already has a BayFlow account. Log in, then create your shop."); 422; 429 (20 per hour per IP).

#### `POST /api/v1/auth/login` — `identity_login` · public · P0 · P-04, P-03 inline login · E-01
- **Body `SessionCreate`:** `email` Email · `password` 1–128 (the D10 policy applies to new passwords, not to logins).
- **200 `SessionRead`** + `Set-Cookie`. The body carries no memberships (D81): the web calls `GET /api/v1/me` right after and routes from its answer (spec 09 §2.8). Side effects: `users.last_login_at`; transparent Argon2 rehash when pwdlib asks; the account's failure counter is cleared.
- **Errors:** 401 `INVALID_CREDENTIALS` for an unknown e-mail (a dummy hash keeps the timing equal), a wrong password or an inactive user, with identical bodies (spec 04 SEC-22); 422; 429 (5 failed checks per e-mail per 15 min; 30 per minute per IP).
- A user whose memberships are all inactive still logs in; they may be a customer, and `GET /api/v1/me` lists no memberships.

#### `POST /api/v1/auth/logout` — `identity_logout` · public · P0 · S-01 user menu, X-04 · E-02
- No body, no authentication needed. **204** + `Set-Cookie: bf_session=""; HttpOnly; Max-Age=0; Path=/; SameSite=lax` (+ `Secure`). Idempotent. A copied Bearer token stays valid until `exp` (stateless JWT, spec 04).
- When the Bearer token or else the cookie names an active user, `auth.logged_out` is recorded (spec 19 §3.3). Recording is best effort: any failure there (database, audit write) is logged without the token, rolled back, and the answer is still 204 with the cookie expired.
- **Errors:** 429 `RATE_LIMITED`, 30 per minute per IP (§1.9).

### 4.4 Current user

#### `GET /api/v1/me` — `shops_get_me` · session · P0 · every screen · E-04
- **200 `MeRead`**: the user, `is_platform_admin` (D94) and their active memberships, each with server-computed `capabilities` (D66) and `shop_suspended` (D96). Built by `shops.service.get_me`; the shops module serves and tags this route because it combines identity and memberships (spec 01, D81; §1.11), while the identity module serves `/api/v1/auth/*`, whose bodies carry only the token fields and the `user` (§4.3). The web calls it on app load and right after login, owner registration and the booking wizard (D81, spec 09 §2.8).
- **Errors:** 401 (the web treats a 401 here as "anonymous", spec 09).

### 4.5 Public directory and availability

#### `GET /api/v1/public/shops` — `shops_list_public_shops` · public · P0 · P-01, P-03 W1 · E-06
- **Query:** `q`? ≤ 100 (shop name, city or active service name) · `city`? (exact, case-insensitive) · `limit` · `offset`.
- **200 `Page[ShopPublicSummary]`**: shops with `is_listed = true` **and** at least one active service (D64), ordered by `name`, `id`.

#### `GET /api/v1/public/cities` — `shops_list_public_cities` · public · P0 · P-01 · E-07
- **200 `ItemList[string]`**: the distinct cities of directory shops (D64), alphabetical.

#### `GET /api/v1/public/shops/{shop_slug}` — `shops_get_public_shop` · public · P0 · P-02, P-03 · E-08
- **200 `ShopPublicDetail`**. A listed shop without active services is returned with `services: []` and `is_bookable: false`, so the page can say "not taking online bookings yet" (D64; it is absent from the directory and booking creation answers 404).
- **Errors:** 404 for an unknown slug or `is_listed = false` (D64).

#### `GET /api/v1/public/shops/{shop_slug}/availability` — `scheduling_get_availability` · public · P0 · P-03 W3 · E-09
- **Query:** `date` (required, `YYYY-MM-DD` in the shop's timezone).
- **200 `AvailabilityRead`** with the grid slots of that day (D37: anchored at local midnight, stepping by `slot_duration_minutes`, inside working hours, ending by closing time) that start after now (the injected clock, D63), lie within 30 days, and still have `remaining > 0`. Full slots are omitted (brief §7.3 "shows only available slots"; spec 12 BK-11). Past dates, dates beyond the horizon and closed days return `slots: []`.
- **Errors:** 404 (unknown or unlisted shop; a listed shop without an active service still answers 200, D64); 422 (malformed date). The wizard polls it every 15 s while on the time step (§6.6).

### 4.6 Booking creation (`CREATE`, spec 08 T01)

#### `POST /api/v1/bookings` — `bookings_create_booking` · optional session · P0 · P-03 W5, C-03 · E-10
- **Body `BookingCreate`:**
  - `shop_id` uuid · `service_ids` uuid[] 1–10, distinct · `slot_start` timestamp (must equal a slot start of the shop's grid) · `customer_notes`? ≤ 2000;
  - `customer`? `CustomerWrite`, every field optional in the schema: `full_name` 1–120 · `email` Email · `password` 12–128 · `phone` Phone. When anonymous, `full_name`, `email` and `password` are required → else 422 (`customer.full_name` …, `missing`). With a session only `customer.phone` is used, to fill an empty `users.phone` (D33); the other fields are ignored (spec 04 case A, SEC-20);
  - `vehicle` `VehicleWrite` (§3.3).
- **201 `BookingCreatedRead`** + `Set-Cookie: bf_session` in every successful case (D32: a booking always logs the customer in; with a session the token is re-issued).
- **Account rule (D32, spec 04):** A, a valid session → booked for that user (`account_created: false`). B, new e-mail → user created (`account_created: true`). C, existing active account + correct password → reused (`false`; Argon2 rehash if needed). D, wrong password or inactive account → 409 `EMAIL_ALREADY_REGISTERED`, **nothing is created**, and it counts as a failed password check.
- **Audit (D100, spec 19 §3.2):** a case C sign-in records `auth.login_succeeded` in the booking's transaction (lost if the booking fails later); case D records `auth.login_failed`, and a blocked account `auth.login_rate_limited`, in a short transaction of their own committed before the 409 / 429, which holds nothing else.
- **Order of checks:** 422 schema → 404 shop unknown, unlisted, suspended (D96) or without an active service (D64; spec 12 BK-15) → 422 `VALIDATION_ERROR` when a service is unknown, inactive or of another shop (`service_ids.N`, `invalid_reference`) → 422 `INVALID_SLOT` (`slot_start`, reason `off_grid`, `in_past`, `beyond_horizon`, `closed_day` or `outside_hours`, §2.3) when the slot is off the grid, not after now, beyond 30 days, on a closed day, or starts before opening or ends after closing → account rule (409, or 429 for the account; Argon2 never holds a row lock) → one transaction: read the shop row `FOR SHARE`, check again that the shop is bookable (404 when it was unlisted or suspended while the request waited for that lock: both write the shop row, so the re-read under the lock is final; spec 19 §7) and re-check the slot rules against it (D37: a concurrent change of `slot_duration_minutes` or `timezone` holds that row `FOR UPDATE`, so the two never interleave; a slot that is off the new grid → 422 `INVALID_SLOT` with reason `off_grid`; spec 02 §7.2), create the user (case B), upsert the vehicle on its normalised registration key (D35), lock the slot counter (409 `SLOT_FULL` when `booked_count ≥ slot_capacity`) and increment it, insert the booking (`reference` `BF-XXXXXX`, `version` 1, `mileage_km` snapshot, D65), snapshot the services (D34), write the `CREATE` event → commit → set the cookie. Any failure rolls back everything, so case B never leaves an orphan account.
- **Errors:** 401 (credentials sent but invalid); 404; 409 `EMAIL_ALREADY_REGISTERED`; 409 `SLOT_FULL`; 422 `INVALID_SLOT`; 422; 429 (per IP when anonymous, per user with a session, per account for cases C and D).
- **Notifications:** `BOOKING_CREATED` → the SAs of the shop (D26). After commit: `notification.created` to them and `booking.updated` to the customer and the booking's viewers.

### 4.7 Customer bookings (`CUSTOMER` actor)

#### `GET /api/v1/me/bookings` — `bookings_list_my_bookings` · session · P0 · C-01 · E-11
- **Query:** `active`? (`true` = non-terminal, `false` = `COMPLETED` or `CANCELLED`, omitted = all) · `sort` ∈ `slot_start`, `-slot_start`, `-updated_at` (default `slot_start` when `active=true`, else `-slot_start`) · `limit` · `offset`.
- **200 `Page[CustomerBookingSummary]`**: the caller's own bookings at every shop. A booking that needs the customer is recognisable from `allowed_actions` (`approve-estimate`, `complete`; spec 12 BK-17).

#### `GET /api/v1/me/bookings/{booking_id}` — `bookings_get_my_booking` · session · P0 · C-02, C-03 · E-12
- **200 `CustomerBookingDetail`**. **404** unless it is the caller's own booking (SM-17), even for staff of that shop.

#### `GET /api/v1/me/bookings/{booking_id}/events` — `bookings_list_my_booking_events` · session · P0 · C-02 · E-13
- **200 `ItemList[CustomerBookingEventRead]`**, oldest first `(created_at, seq)` (D79), with the §3.3 customer projection.

#### `GET /api/v1/me/bookings/{booking_id}/estimates` — `bookings_list_my_booking_estimates` · session · P1 · C-02 "Previous versions" · E-14
- **200 `ItemList[CustomerEstimateRead]`**: only `SENT`, `APPROVED` and `REJECTED` versions (D39), ascending by `version`.

#### `POST /api/v1/me/bookings/{booking_id}/actions/{slug}` — 4 routes · P0 · C-02 · E-15
- `approve-estimate`, `reject-estimate`, `cancel`, `complete`; specified in §5.
- At a suspended shop (D96) every action but `cancel` is 403 `SHOP_SUSPENDED` (the three routes declare 403), and the customer's `allowed_actions` hold `cancel` only.

#### `GET /api/v1/me/vehicles` — `bookings_list_my_vehicles` · session · P1 · P-03 W4 · E-16
- **200 `ItemList[VehicleRead]`**: the caller's vehicles, most recently updated first. Re-booking a listed vehicle sends its fields again in `vehicle`; the upsert matches on the registration key (D35).

### 4.8 Staff bookings (reads and the estimate editor)

#### `GET /api/v1/shops/{shop_id}/bookings` — `bookings_list_shop_bookings` · member, D21 · P0 · SA-01, T-01, PP-01, QI-01, O-01, O-06 · E-33
- **Query:** `status` (repeatable BookingStatus) · `q` ≤ 100 (reference with or without `BF-`, customer name, plate) · `date_from`, `date_to` (on `slot_start`, shop-local) · `technician_user_id` · `parts_person_user_id` · `sort` ∈ `slot_start`, `updated_at`, `status_changed_at`, `created_at`, each with optional `-` (default `-updated_at`) · `limit` · `offset`.
- **200 `Page[BookingSummary]`**. Filters narrow the D21 set and never widen it: a technician filtering by another technician gets an empty page.
- The **QC queue** (brief §7.4, QI-01) is this endpoint with `status=QC_PENDING&status=QC_IN_PROGRESS&sort=status_changed_at`; no separate route is needed because D21 already scopes it.

#### `GET /api/v1/shops/{shop_id}/bookings/status-counts` — `bookings_get_status_counts` · member, D21 · P0 · SA-01 · E-34
- **200 `StatusCountsRead`** over the caller's visible bookings. Registered before `/bookings/{booking_id}` (§1.11).

#### `GET /api/v1/shops/{shop_id}/bookings/{booking_id}` — `bookings_get_shop_booking` · member, D21 · P0 · SA-02, T-02, PP-02, QI-02 · E-35
- **200 `BookingDetail`**. **404** when not visible (spec 04 SEC-01, SEC-08…SEC-10).

#### `GET /api/v1/shops/{shop_id}/bookings/{booking_id}/events` — `bookings_list_booking_events` · member, D21 · P0 · SA-02, T-02, QI-02 · E-36
- **200 `ItemList[BookingEventRead]`**, oldest first `(created_at, seq)`, with notes, actor and `metadata` (brief §7.5 audit log).

#### `GET /api/v1/shops/{shop_id}/bookings/{booking_id}/estimates` — `bookings_list_booking_estimates` · member, D21 · P0 · SA-02, T-02, PP-02, QI-02 · E-38
- **200 `ItemList[EstimateRead]`**: every version, ascending. Part lines carry live stock (D40), except for QC callers (§3.4).

#### `PUT /api/v1/shops/{shop_id}/bookings/{booking_id}/estimate` — `bookings_edit_estimate` · P0 · T-02, SA-02 · E-39
- The `edit-estimate` operation (O1); specified in §5.3.

#### `GET /api/v1/shops/{shop_id}/bookings/{booking_id}/parts` — `bookings_get_booking_parts` · O, SA, T, PP; D21 · P0 · PP-02, SA-02, T-02 · E-40
- **200 `BookingPartsRead`**: required vs reserved vs available per part, shortages and linked POs (brief §7.6 "required parts compared to stock automatically"). `items` is empty before `assign-parts-person` and for labour-only jobs.
- **Errors:** 403 for `QC_INSPECTOR` (stock data, spec 04 §B); 404 when not visible.

#### `GET /api/v1/shops/{shop_id}/bookings/{booking_id}/qc-inspections` — `bookings_list_booking_qc_inspections` · member, D21 · P0 · QI-02, T-02, SA-02 · E-41
- **200 `ItemList[QcInspectionRead]`**: every round with its checklist and issues, so the technician sees what QC sent back (brief §7.4).

### 4.9 Shops, team, services, working hours

#### `POST /api/v1/shops` — `shops_create_shop` · session (any user, D17) · P0 · S-03, O-05 · E-21
- **Body `ShopCreate`:** `name` 1–120 · `address` 1–255 · `city` 1–80 · `phone` Phone · `logo_url`? `https://…` ≤ 2048 · `timezone`? IANA name (default `Asia/Karachi`, D38) · `slot_duration_minutes` 15–240, multiple of 15 · `slot_capacity` 1–50 · `is_listed`? (default `true`) · `working_hours` WorkingHoursWrite[7].
- **201 `ShopRead`**. One transaction creates the shop, its 7 working-hours rows and the caller's `OWNER` membership. The slug comes from the name (`-2`, `-3` … on collision, never a 409) and never changes afterwards. `rating` can't be set over HTTP (seed-only, D56).
- **Errors:** 422 (incl. `working_hours.N.opens_at` `not_on_grid`); 429 (10 per day per user).

#### `GET /api/v1/shops/{shop_id}` — `shops_get_shop` · member · P0 · O-04, S-01 · E-22
- **200 `ShopRead`**.

#### `PATCH /api/v1/shops/{shop_id}` — `shops_update_shop` · O · P0 · O-04 · E-23
- **Body `ShopUpdate`** (at least one field): `name` · `address` · `city` · `phone` · `logo_url` (nullable) · `is_listed` · `slot_duration_minutes` · `slot_capacity` · `timezone`. `slug` and `rating` are not accepted (422).
- **200 `ShopRead`**.
- **Errors:** 409 `CONFLICT` when `slot_duration_minutes` or `timezone` changes while the shop has future non-cancelled bookings (D37); 422 `hours_not_on_grid` (field `slot_duration_minutes`) when the current working hours don't lie on the new grid; 403, 422. Capacity changes are always allowed; existing bookings are kept.

#### `PUT /api/v1/shops/{shop_id}/working-hours` — `shops_replace_working_hours` · O · P0 · O-04 · E-24
- **Body `WorkingHoursUpdate`:** `working_hours` WorkingHoursWrite[7].
- **200 `ShopRead`**. Always allowed; existing bookings outside the new hours are kept (D37).

#### `GET /api/v1/shops/{shop_id}/members` — `shops_list_members` · O, SA · P0 · O-02, SA-02 assign dialogs, O-01, T-01 Owner filter · E-25
- **Query:** `role` (repeatable MembershipRole) · `is_active`? · `limit` · `offset`. Order: role in glossary order, then name.
- **200 `Page[MemberRead]`**. The Owner sees every member, including inactive ones and the `OWNER` row. A Service Advisor sees only active `TECHNICIAN` and `PARTS_PERSON` members (the assign pickers, spec 04 §A); their filters intersect with that set.
- **Errors:** 403 for T, PP and QC.

#### `POST /api/v1/shops/{shop_id}/members` — `shops_add_member` · O · P0 · O-02 · E-26
- **Body `MemberCreate`:** `email` Email · `full_name` 1–120 · `role` StaffRole (`OWNER` → 422) · `password`? 12–128 · `phone`? Phone (spec 04).
- **201 `MemberCreatedRead`** (the member plus `account_created`). New e-mail: user and membership in one transaction, `account_created: true`; `password` is required (else 422 `password` `missing`) and the Owner hands it over privately. Existing e-mail: **only the membership** is created, `account_created: false`; the user's password, name and phone are never modified and a supplied password is ignored (D18, spec 04 SEC-21).
- **Errors:** 409 `CONFLICT` when the user already has a membership here, active or inactive (use PATCH); 422; 429 (30 per hour per shop).

#### `PATCH /api/v1/shops/{shop_id}/members/{membership_id}` — `shops_update_member` · O · P0 · O-02 · E-27
- **Body `MemberUpdate`** (at least one): `role`? StaffRole · `is_active`? bool.
- **200 `MemberRead`**. Takes effect on the member's next request (D9). Bookings assigned to the member stay assigned; the SA moves them with `reassign-*` (D19).
- **Errors:** 403 `FORBIDDEN` on the `OWNER` membership, whoever asks (D19, SEC-15); 404 for a membership of another shop; 422.

#### `GET /api/v1/shops/{shop_id}/services` — `shops_list_services` · member · P0 · O-03 · E-28
- **Query:** `include_inactive` (default `false`) · `limit` · `offset`. **200 `Page[ServiceRead]`**, by name.

#### `POST /api/v1/shops/{shop_id}/services` — `shops_create_service` · O · P0 · O-03 · E-29
- **Body `ServiceCreate`:** `name` 1–120 · `description`? ≤ 1000 · `estimated_duration_minutes` 5–10 080 · `base_price`? Money · `is_active`? (default `true`).
- **201 `ServiceRead`**. **Errors:** 409 `CONFLICT` for a duplicate active name (case-insensitive) in the shop; 422.

#### `PATCH /api/v1/shops/{shop_id}/services/{service_id}` — `shops_update_service` · O · P0 · O-03 · E-30
- **Body `ServiceUpdate`** (at least one; `description` and `base_price` nullable). **200 `ServiceRead`**. Deactivating hides the service from the directory and the wizard; existing bookings keep their snapshot (D34). **Errors:** 409 duplicate active name; 404; 422.

### 4.10 Inventory and purchase orders (D42–D45)

#### `GET /api/v1/shops/{shop_id}/parts` — `inventory_list_parts` · O, SA, T, PP · P0 · PP-03, estimate editor (T-02, SA-02), PP-04 dialog · E-43
- **Query:** `q` ≤ 100 (SKU, name) · `stock_state` (repeatable `OK`, `LOW`, `OUT`) · `include_inactive` (default `false`) · `sort` ∈ `sku`, `name`, `available`, each with optional `-` (default `sku`) · `limit` · `offset`.
- **200 `Page[PartRead]`** with computed `available`, `stock_state` and `on_order` (brief §7.4 inventory table: SKU, name, quantity, reorder level, cost).
- **Errors:** 403 for QC (spec 04 §B).

#### `POST /api/v1/shops/{shop_id}/parts` — `inventory_create_part` · O, PP (`parts.manage`) · P0 · PP-03 · E-44
- **Body `PartCreate`:** `sku` 1–40, upper-cased, `^[A-Z0-9][A-Z0-9._/-]{0,39}$` · `name` 1–120 · `unit_cost` Money · `reorder_level`? 0–100 000 (default 0) · `is_active`? (default `true`). There is **no stock field**: `on_hand` or `reserved` in the body → 422 `extra_forbidden`.
- **201 `PartRead`** with `on_hand = 0` (D44); opening stock is an adjustment or a PO receipt by a Parts Person.
- **Errors:** 409 `CONFLICT` for a duplicate SKU in the shop (another shop may reuse it); 422.

#### `PATCH /api/v1/shops/{shop_id}/parts/{part_id}` — `inventory_update_part` · O, PP · P0 · PP-03 · E-45
- **Body `PartUpdate`** (at least one): `sku` · `name` · `unit_cost` · `reorder_level` · `is_active` — never stock quantities. **200 `PartRead`**. Existing estimate lines keep their prices and names; an inactive part can't be added to new lines (D40). **Errors:** 409 duplicate SKU; 404; 422.

#### `POST /api/v1/shops/{shop_id}/parts/{part_id}/adjustments` — `inventory_adjust_stock` · PP only (D44) · P0 (D82) · PP-03 · E-46
- **Body `StockAdjustmentCreate`:** `quantity_delta` int, non-zero, −100 000 … 100 000 · `reason` 1–500.
- **201 `StockAdjustmentRead`**: one `ADJUST` movement under a lock on the part row (opening stock, count corrections).
- **Errors:** **409 `INSUFFICIENT_STOCK`** when the result would leave `on_hand` below `reserved` or below 0 — nothing changes (D82; this replaces the 422 in spec 06); 403 for the Owner and other roles; 404; 422.
- **P0 (D82):** it is the only way to enter opening stock for a new part (parts start at 0, D44) and to correct drift (D71: "Usman can adjust stock"), so it ships with the core inventory work.

#### `GET /api/v1/shops/{shop_id}/parts/{part_id}/movements` — `inventory_list_part_movements` · O, PP · P1 · PP-03 · E-47
- **200 `Page[StockMovementRead]`**, newest first: `(created_at, seq)` descending (D79). **Errors:** 403 for SA, T, QC.

#### `GET /api/v1/shops/{shop_id}/purchase-orders` — `inventory_list_purchase_orders` · O (read), PP · P0 · PP-04, PP-02 · E-48
- **Query:** `status` (repeatable) · `booking_id` · `limit` · `offset`. Order: open POs (`ORDERED`, `PARTIALLY_RECEIVED`) first, then newest.
- **200 `Page[PurchaseOrderSummary]`**. **Errors:** 403 for SA, T, QC (they see linked POs through `…/bookings/{id}/parts`).

#### `POST /api/v1/shops/{shop_id}/purchase-orders` — `inventory_create_purchase_order` · PP · P0 · PP-04 · E-49
- **Body `PurchaseOrderCreate`:** `supplier_name`? 1–120 · `items` 1–50 of {`part_id` (an active part of this shop), `quantity` 1–10 000, `unit_cost`? Money (default `parts.unit_cost`)}, with distinct `part_id`.
- **201 `PurchaseOrderRead`** (`ORDERED`, new `PO-XXXXXX`, no booking). Booking-linked POs are created only by `order-parts` (D43); a `booking_id` in this body → 422.
- **Errors:** 403 (incl. the Owner, D44); 422 (`items.N.part_id` `invalid_reference`, `duplicate`).

#### `GET /api/v1/shops/{shop_id}/purchase-orders/{po_id}` — `inventory_get_purchase_order` · O, PP · P0 · PP-05 · E-50
- **200 `PurchaseOrderRead`**. **Errors:** 403; 404.

#### `POST /api/v1/shops/{shop_id}/purchase-orders/{po_id}/receive` — `inventory_receive_purchase_order` · PP · P0 · PP-05 · E-51
- The receipt that may fire `RECEIVE_PARTS`; specified in §5.3.

### 4.11 QC

#### `GET /api/v1/shops/{shop_id}/qc/checklist` — `qc_get_checklist` · member · P0 · QI-02 · E-42
- **200 `ItemList[QcChecklistTemplateItem]`**: the D46 default checklist in fixed order. The QC queue and inspection reads are under §4.8.

### 4.12 Notifications and the realtime ticket

#### `GET /api/v1/me/notifications` — `notifications_list_my_notifications` · session · P0 · X-01 · E-17
- **Query:** `unread_only` (default `false`) · `limit` · `offset`. **200 `Page[NotificationRead]`**: only the caller's rows, across all shops and roles, newest first.

#### `GET /api/v1/me/notifications/unread-count` — `notifications_get_unread_count` · session · P0 · bell · E-18
- **200 `UnreadCountRead`**. Polled every 15 s on every logged-in page (D14).

#### `POST /api/v1/me/notifications/{notification_id}/read` — `notifications_mark_notification_read` · session · P0 · X-01 · E-19
- **204**, idempotent. **404** for another user's notification (spec 04 SEC-34).

#### `POST /api/v1/me/notifications/read-all` — `notifications_mark_all_notifications_read` · session · P0 · X-01 · E-20
- **204**; marks every unread notification of the caller.

#### `GET /api/v1/realtime/ticket` — `notifications_get_realtime_ticket` · session · P1 (D88) · RealtimeProvider · E-05
- Served by the notifications module, which owns the WebSocket hub (D70, spec 01). P1 like the hub and `/api/v1/ws` (D88): the P0 bell needs only the polled routes above. **200 `RealtimeTicketRead`**: a JWT with exactly `sub`, `iat`, `exp = iat + 60`, `typ = "ws"` (D70). It creates no server state; a new ticket is fetched for every connect attempt. **401** means the session has expired (spec 09 session-expired flow). Protocol in §6.

### 4.13 Reporting

#### `GET /api/v1/shops/{shop_id}/overview` — `reporting_get_overview` · O · P0 · O-01 · E-31
- **200 `OverviewRead`**: bookings by status, team, inventory summary (brief §7.4 Owner), plus the setup checklist. The five most recent bookings come from `GET …/bookings?sort=-updated_at&limit=5`.
- **Errors:** 403 for every other role (spec 12 RPT-03).

#### `GET /api/v1/me/owner-summary` — `reporting_get_owner_summary` · session · P1 · O-07 · E-32
- **200 `OwnerSummaryRead`**: one row per shop where the caller is `OWNER` (brief §2 "no visibility across locations"); `items: []` for everyone else (spec 12 RPT-02). A suspended shop is left out (D99): its staff routes are 403 `SHOP_SUSPENDED`, and `GET /api/v1/me` still lists the membership with `shop_suspended: true`.

### 4.14 Calls, tasks, webhook and agent routes (P2 — copied from spec 05 §5.3 and §8, which are authoritative)

Built only after P0 works end to end on the live URL (D36). With `CALL_PROVIDER_*` blank, or once `CALL_MONTHLY_MINUTES_CAP` is reached, the call-start routes answer 503 `CALLING_DISABLED`. A blank `LLM_API_KEY` or a reached `AI_DAILY_CALL_CAP` never fails a call; it only means no AI leg (glossary §10). Calls ring for the full `AI_RING_TIMEOUT_SECONDS` before the AI is dispatched, unless every rung SA declines first (D77). Calls and tasks are SA/Owner work: T, PP and QC get 403 on the collections and 404 on single items (D21, spec 05 §8.2).

| Method and path | `operationId` | Who | Body | Success | Errors |
|---|---|---|---|---|---|
| `POST /api/v1/me/bookings/{booking_id}/calls` | `calls_start_my_call` | the booking's customer | none | 201 `CallStartRead` | 404, 503 `CALLING_DISABLED`, 429 (5 per 10 min), 409 `CALL_BUSY` |
| `GET /api/v1/me/bookings/{booking_id}/calls` | `calls_list_my_booking_calls` | the booking's customer | — | 200 `Page[CallRead]` | 404 |
| `POST /api/v1/me/calls/{call_id}/accept` | `calls_accept_my_call` | the called customer | none | 200 `CallStartRead` | 404, 403, 409 `CALL_NOT_ACTIVE` |
| `POST /api/v1/me/calls/{call_id}/decline` | `calls_decline_my_call` | the called customer | none | 200 `CallRead` | 404, 403, 409 `CALL_NOT_ACTIVE` |
| `POST /api/v1/me/calls/{call_id}/end` | `calls_end_my_call` | a participant | none | 200 `CallRead` (idempotent) | 404, 403 |
| `POST …/bookings/{booking_id}/calls` | `calls_start_call` | SA, O | none | 201 `CallStartRead` | 404, 403, 503, 429, 409 `CALL_BUSY` |
| `GET …/bookings/{booking_id}/calls` | `calls_list_booking_calls` | SA, O | — | 200 `Page[CallRead]` | 403, 404 |
| `GET …/calls` | `calls_list_shop_calls` | SA, O | query `status`, `direction`, `ai_handled`, `booking_id`, paging | 200 `Page[CallRead]` | 403 |
| `GET …/calls/{call_id}` | `calls_get_call` | SA, O | — | 200 `CallDetailRead` | 404 |
| `POST …/calls/{call_id}/accept` | `calls_accept_call` | an eligible callee of the customer → shop call: an active SA of the shop, or the Owner only when the shop has no active SA (spec 05 §3.3, C2); being rung is not required | none | 200 `CallStartRead` | 404, 403, 409 `CALL_ALREADY_ANSWERED` / `CALL_NOT_ACTIVE` |
| `POST …/calls/{call_id}/decline` | `calls_decline_call` | an eligible callee of the customer → shop call: an active SA of the shop, or the Owner only when the shop has no active SA (spec 05 §3.3, C3); being rung is not required (spec 05 CALL-15) | none | 200 `CallRead` | 404, 403, 409 `CALL_NOT_ACTIVE` |
| `POST …/calls/{call_id}/end` | `calls_end_call` | a participant | none | 200 `CallRead` (idempotent) | 404, 403 |
| `GET …/tasks` | `calls_list_tasks` | SA, O (`tasks.manage`) | query `status` (`OPEN` default, `DONE`), `kind` (repeatable), paging | 200 `Page[TaskRead]`, urgent first, then newest | 403 |
| `POST …/tasks/{task_id}/mark-done` | `calls_mark_task_done` | SA, O | `{note?: ≤ 500}` | 200 `TaskRead` (idempotent) | 404, 422 |

Start-call check order (spec 05 C1): booking visible (404) → SA or Owner on the staff route (403) → calling enabled and monthly cap not reached (503) → 5 starts per caller per 10 min (429) → no active call for the booking, the caller or the called customer (409 `CALL_BUSY`) → LiveKit room created (else 503, nothing stored). Effects, ring timer, sweeper and AI leg: spec 05 §3. Notifications: `CALL_MISSED` (customer → shop: SAs of the shop; shop → customer: the customer), `AI_TASK_CREATED` → SAs of the shop. Realtime: `call.incoming`, `call.updated`, `task.created` (§6.3).

**Webhook (excluded from OpenAPI):** `POST /api/v1/webhooks/livekit` — no cookie; LiveKit calls the API host directly. The raw body and the `Authorization` JWT are checked with `WebhookReceiver(TokenVerifier(CALL_PROVIDER_API_KEY, CALL_PROVIDER_API_SECRET)).receive(…)` (signature and body SHA-256): failure → 401 `UNAUTHENTICATED`, nothing processed; success → 200 with an empty body. Handles `participant_left`, `participant_connection_aborted` and `room_finished` idempotently.

**Agent routes (excluded from OpenAPI, never through the web rewrite):** prefix `/api/v1/internal/calls/{call_id}`; mounted only when `AGENT_SERVICE_TOKEN` is set. Every request needs `Authorization: Bearer <AGENT_SERVICE_TOKEN>` (constant-time compare, else 401) and `X-Agent-Call-Token` (SHA-256 compared with `call_logs.ai_call_token_hash`, else 404); the call must be an AI call (else 404); the scope (`shop_id`, `customer_user_id`) is read from the call row, never from the request (out of scope → 404); data and task routes work only while the AI leg is open, `summary` until 10 min after it ended (else 409 `CALL_NOT_ACTIVE`); the booking, estimate and reschedule routes require a verified caller (403 `IDENTITY_NOT_VERIFIED`).

| Method and path | Body or query | Success |
|---|---|---|
| `POST /session` | — | 200 `{shop: {name, city, timezone}, max_ai_seconds: 300}` |
| `POST /verify-caller` | `{name?, phone?, email?, booking_reference?}` (at least one) | 200 `{verified, method, attempts_left, locked, first_name?, call_booking_reference?}` |
| `GET /shop` | — | 200 `{name, city, address, phone, working_hours: [{weekday, open, close}], services: [...]}` |
| `GET /bookings` | — | 200 `{items: [...], total}` (≤ 10, newest first) |
| `GET /bookings/{reference}` | — | 200 booking view (spec 05 §5.3), or 404 |
| `GET /bookings/{reference}/estimate` | — | 200 estimate view (only `SENT`, `APPROVED`, `REJECTED`), or 404 |
| `GET /available-slots` | `?date=YYYY-MM-DD&days=1…7` | 200 `{timezone, slots: [{start, start_local}]}` (≤ 12; D37 rules) |
| `POST /tasks` | `{kind: CALLBACK or RESCHEDULE_REQUEST or ESCALATION, booking_reference?, topic?, description?, preferred_starts?, safety_concern?}` | 201 `{task_id, created: true}`, or 200 `{task_id, created: false}` when that call already had a task of that kind |
| `POST /end` | `{error?: string}` | 200, idempotent |
| `POST /summary` | spec 05 §6.3 (transcript ≤ 300 entries, ≤ 200 KB; body ≤ 256 KiB) | 201, or 200 when a summary already exists |

---

## 5. Booking actions

### 5.1 Rules common to every action

- **Routes (D48: one endpoint per slug).** Staff: `POST /api/v1/shops/{shop_id}/bookings/{booking_id}/actions/{slug}` → **200 `BookingDetail`**. Customer: `POST /api/v1/me/bookings/{booking_id}/actions/{slug}` → **200 `CustomerBookingDetail`**. Both responses carry the new `version` and the caller's fresh `allowed_actions`; the staff one also carries `last_event`.
- **Which slugs exist where.** Routes are generated from the spec 08 rule table: a family gets a route for a slug only when one of its actors can perform it. The **staff family has 22 slugs** (every slug except `approve-estimate`, `reject-estimate` and `edit-estimate`, which is the `PUT …/estimate` route). The **customer family has 4**: `approve-estimate`, `reject-estimate`, `cancel`, `complete`. A slug outside the family is an unknown route → 404 (spec 12 API-10). Inside a family the rule table answers wrong roles with 403 `FORBIDDEN` (a technician calling `confirm`, the Owner calling `pick-qc`).
- **Bodies.** A JSON object with `extra="forbid"` and an optional `expected_version` (int ≥ 1). When an action has no required field the body may be omitted or `{}`.
- **Common errors** (not repeated below): 401; 404 (membership, visibility or own-booking scope); 422 `VALIDATION_ERROR` (schema); 403 `FORBIDDEN` on staff routes (the caller's role is not in the rule); 409 `INVALID_TRANSITION` (status not in `from`, incl. any terminal booking); 409 `CONCURRENT_UPDATE` (stale `expected_version`). 403 `NOT_ASSIGNED` applies where a guard is named; with D21 it can only surface for QC picker actions, because an unassigned technician or parts person can't see the booking (404).
- **Effects of every success:** one transaction that locks the booking first, writes exactly one `booking_events` row (`action`, `from_status`, `to_status`, actor, `actor_role`, `note`, `metadata`), increments `version`, publishes `BookingActionApplied` and inserts the notification rows; after commit, `booking.updated` goes to the booking's viewers and `notification.created` to each recipient (§6). Timestamps come from the injected clock (D63).

| Slug | Family | Actors · guard | From → To | Request schema | Extra errors | Notification | Pri |
|---|---|---|---|---|---|---|---|
| `confirm` | staff | SA, O | `PENDING` → `CONFIRMED` | `ConfirmRequest` | — | `BOOKING_CONFIRMED` → customer | P0 |
| `decline` | staff | SA, O | `PENDING` → `CANCELLED` | `DeclineRequest` | — | `BOOKING_CANCELLED` → customer | P0 |
| `assign-technician` | staff | SA, O | `CONFIRMED` → `ASSIGNED` | `AssignTechnicianRequest` | 422 `MEMBER_NOT_ELIGIBLE` | `TECHNICIAN_ASSIGNED` → technician | P0 |
| `start-inspection` | staff | T · `ASSIGNED_TECHNICIAN` | `ASSIGNED` → `INSPECTING` | `StartInspectionRequest` | — | — | P0 |
| `edit-estimate` | `PUT …/estimate` | T in `INSPECTING`; SA, O in `ESTIMATE_REVIEW` | same | `EstimateUpdate` | 409 `ESTIMATE_LOCKED`, 422 | — | P0 |
| `submit-estimate` | staff | T · `ASSIGNED_TECHNICIAN` | `INSPECTING` → `ESTIMATE_REVIEW` | `SubmitEstimateRequest` | 422 `ESTIMATE_EMPTY`, 422 | `ESTIMATE_SUBMITTED` → SAs | P0 |
| `send-estimate` | staff | SA, O | `ESTIMATE_REVIEW` → `AWAITING_CUSTOMER` | `SendEstimateRequest` | 422 `ESTIMATE_EMPTY` | `ESTIMATE_SENT` → customer (+ e-mail) | P0 |
| `approve-estimate` | customer | booking's customer | `AWAITING_CUSTOMER` → `ESTIMATE_APPROVED` | `ApproveEstimateRequest` | 409 `STALE_ESTIMATE` | `ESTIMATE_APPROVED` → SAs | P0 |
| `reject-estimate` | customer | booking's customer | `AWAITING_CUSTOMER` → `ESTIMATE_REJECTED` | `RejectEstimateRequest` | 409 `STALE_ESTIMATE` | `ESTIMATE_REJECTED` → SAs | P0 |
| `revise-estimate` | staff | SA, O | `ESTIMATE_REJECTED` → `ESTIMATE_REVIEW` | `ReviseEstimateRequest` | — | — | P0 |
| `return-to-technician` | staff | SA, O | `ESTIMATE_REJECTED` → `INSPECTING` | `ReturnToTechnicianRequest` | — | `ESTIMATE_RETURNED` → technician | P0 |
| `assign-parts-person` | staff | SA, O | `ESTIMATE_APPROVED` → `PARTS_PENDING` | `AssignPartsPersonRequest` | 422 `MEMBER_NOT_ELIGIBLE` | `PARTS_NEEDED` → parts person | P0 |
| `order-parts` | staff | PP · `ASSIGNED_PARTS_PERSON` | `PARTS_PENDING` → `PARTS_ORDERED` | `OrderPartsRequest` | 409 `CONFLICT`, 422 | — | P0 |
| `mark-parts-ready` | staff | PP · `ASSIGNED_PARTS_PERSON` | `PARTS_PENDING`, `PARTS_ORDERED` → `PARTS_READY` | `MarkPartsReadyRequest` | 409 `INSUFFICIENT_STOCK` | — | P0 |
| *(`RECEIVE_PARTS`)* | PO receive | any PP of the shop | `PARTS_ORDERED` → `PARTS_READY` | `PurchaseOrderReceive` | 409 `CONFLICT`, 409 `CONCURRENT_UPDATE`, 422 | — | P0 |
| `allocate-parts` | staff | PP · `ASSIGNED_PARTS_PERSON` | `PARTS_READY` → `IN_REPAIR` | `AllocatePartsRequest` | 409 `INSUFFICIENT_STOCK` | `PARTS_READY` → technician | P0 |
| `start-repair` | staff | T · `ASSIGNED_TECHNICIAN` | `IN_REPAIR` (operation) | `StartRepairRequest` | — | — | P0 |
| `send-to-qc` | staff | T · `ASSIGNED_TECHNICIAN` | `IN_REPAIR` → `QC_PENDING` | `SendToQcRequest` | — | `QC_REQUESTED` → all QC inspectors | P0 |
| `pick-qc` | staff | QC (any active) | `QC_PENDING` → `QC_IN_PROGRESS` | `PickQcRequest` | 409 `ALREADY_PICKED`, 403 (D47) | — | P0 |
| `pass-qc` | staff | QC · `QC_PICKER` | `QC_IN_PROGRESS` → `READY_FOR_PICKUP` | `PassQcRequest` | 403 `NOT_ASSIGNED`, 422 | `QC_PASSED` → SAs | P0 |
| `fail-qc` | staff | QC · `QC_PICKER` | `QC_IN_PROGRESS` → `IN_REPAIR` | `FailQcRequest` | 403 `NOT_ASSIGNED`, 422 | `QC_FAILED` → technician | P0 |
| `notify-ready` | staff | SA, O | `READY_FOR_PICKUP` (operation) | `NotifyReadyRequest` | — | `VEHICLE_READY` → customer (+ e-mail) | P0 |
| `complete` | staff + customer | SA, O; booking's customer | `READY_FOR_PICKUP` → `COMPLETED` | `CompleteRequest` | — | — | P0 |
| `cancel` | staff + customer | SA, O; booking's customer | 11 cancellable statuses → `CANCELLED` | `CancelRequest` (staff) / `CustomerCancelRequest` | — | `BOOKING_CANCELLED` (see §5.2) | P0 |
| `reassign-technician` | staff | SA, O | `ASSIGNED`, `INSPECTING`, `IN_REPAIR` (operation) | `ReassignTechnicianRequest` | 422 `MEMBER_NOT_ELIGIBLE`, 422 | `TECHNICIAN_ASSIGNED` → new technician | P1 |
| `reassign-parts-person` | staff | SA, O | `PARTS_PENDING`, `PARTS_ORDERED`, `PARTS_READY` (operation) | `ReassignPartsPersonRequest` | 422 `MEMBER_NOT_ELIGIBLE`, 422 | `PARTS_NEEDED` → new parts person | P1 |

Operation IDs: `bookings_<slug in snake case>` for staff routes (`bookings_assign_technician`), `bookings_my_<slug>` for customer routes (`bookings_my_approve_estimate`), `bookings_edit_estimate`, `inventory_receive_purchase_order`. `CREATE` is §4.6.

Eligibility (used by `assign-*` and `reassign-*`): the user has an **active** membership with the required role (`TECHNICIAN` or `PARTS_PERSON`) in this shop and an active account; otherwise 422 `MEMBER_NOT_ELIGIBLE` on that field, whether the user has the wrong role, is inactive, belongs to another shop or doesn't exist (spec 12 BK-21).

### 5.2 Per action (spec 08 rows in brackets)

#### `confirm` [T02] — SA-02
- **`ConfirmRequest`:** `expected_version`? · `note`? ≤ 500 (staff-only event note).
- Effects: status only. Notification `BOOKING_CONFIRMED` → the customer (extra).

#### `decline` [T03] — SA-02
- **`DeclineRequest`:** `reason` 1–500 (**required**) · `expected_version`?.
- Effects: `cancelled_at`, `cancelled_by_user_id`, `cancel_reason`; slot counter −1 (locks booking → slot counter). The reason is customer-visible (`cancel_reason`, customer timeline). Notification `BOOKING_CANCELLED` → the customer.

#### `assign-technician` [T04] — SA-02
- **`AssignTechnicianRequest`:** `technician_user_id` uuid · `expected_version`?.
- Errors: 422 `MEMBER_NOT_ELIGIBLE` (`technician_user_id`). Effects: sets `technician_user_id`. Notification `TECHNICIAN_ASSIGNED` → that technician; the booking appears in their My jobs.

#### `start-inspection` [T05] — T-01 inline, T-02
- **`StartInspectionRequest`:** `expected_version`?.
- Effects: ensures a `DRAFT` estimate (creates v1 when the booking has none). No notification.

#### `submit-estimate` [T06] — T-02
- **`SubmitEstimateRequest`:** `inspection_notes`? ≤ 4000 (saved on the booking when present; otherwise the notes saved with the draft stay) · `expected_version`?.
- Errors: 422 `ESTIMATE_EMPTY` (`lines`) when the draft has no line; 422 `VALIDATION_ERROR` (`lines.N.part_id`, `invalid_reference`) when a part line references a part deactivated since it was added.
- Effects: draft → `SUBMITTED` (`submitted_at`), totals recomputed; event metadata `{estimate_id, version, grand_total}`. Notification `ESTIMATE_SUBMITTED` → SAs of the shop.

#### `send-estimate` [T07] — SA-02
- **`SendEstimateRequest`:** `expected_version`?.
- Errors: 422 `ESTIMATE_EMPTY`. Effects: the open version (the technician's `SUBMITTED` one, or the SA's `DRAFT`) → `SENT` (`sent_at`, `sent_by_user_id`). Notification `ESTIMATE_SENT` → the customer, plus e-mail when configured (D26).

#### `approve-estimate` [T08] — C-02 (customer route only)
- **`ApproveEstimateRequest`:** `estimate_id` uuid · `expected_version`?.
- Errors: 409 `STALE_ESTIMATE` when `estimate_id` is not the current `SENT` version — superseded, another booking's or unknown (spec 12 EST-14, SM-14).
- Effects: the version → `APPROVED` with `decided_at` and `decided_by_user_id`: the timestamped acceptance of brief §3, locked from now on (D39). Notification `ESTIMATE_APPROVED` → SAs. Customer `allowed_actions` afterwards: `["cancel"]`.

#### `reject-estimate` [T09] — C-02 (customer route only)
- **`RejectEstimateRequest`:** `estimate_id` uuid · `reason`? ≤ 500 · `expected_version`?.
- Errors: 409 `STALE_ESTIMATE`. Effects: the version → `REJECTED`, `decided_at`, `decided_by_user_id`, `customer_note` = reason. Notification `ESTIMATE_REJECTED` → SAs (the body quotes the reason).

#### `revise-estimate` [T10] — SA-02
- **`ReviseEstimateRequest`:** `expected_version`?.
- Effects: a new `DRAFT` version (`version + 1`, author = actor) copying the rejected version's lines; the SA then edits it with `PUT …/estimate` and sends it. No notification.

#### `return-to-technician` [T11] — SA-02
- **`ReturnToTechnicianRequest`:** `note`? ≤ 500 (stored as the event note and shown to the technician) · `expected_version`?.
- Effects: a new `DRAFT` copying the rejected version's lines, for the technician to edit in `INSPECTING`. Notification `ESTIMATE_RETURNED` → the technician (extra).

#### `assign-parts-person` [T12] — SA-02
- **`AssignPartsPersonRequest`:** `parts_person_user_id` uuid · `expected_version`?.
- Errors: 422 `MEMBER_NOT_ELIGIBLE` (`parts_person_user_id`).
- Effects: sets `parts_person_user_id`; creates the `booking_parts` rows from the **approved** version's `PART` lines, quantities summed per part (zero rows for a labour-only job, D31). Notification `PARTS_NEEDED` → that parts person.

#### `order-parts` [T13] — PP-02
- **`OrderPartsRequest`:** `supplier_name`? 1–120 · `items`? 1–50 of {`part_id` uuid, `quantity` int 1–10 000} with distinct parts · `expected_version`?.
- Under the part locks, each booking part first reserves `min(available, outstanding)`; what is still outstanding is its shortage. With **no shortage** → 409 `CONFLICT` ("All parts are available — use mark-parts-ready.") and nothing is reserved or ordered (spec 12 INV-03).
- `items` omitted → the PO orders exactly the shortages. `items` given → it must cover every short part (`items`, `missing_shortage`) with `quantity ≥ shortage` (`items.N.quantity`, `below_shortage`; spec 12 INV-04) and may list only short parts (`items.N.part_id`, `not_short`); each a 422 `VALIDATION_ERROR`.
- Effects: `RESERVE` movements; a `purchase_orders` row (`ORDERED`, `booking_id` set, new `PO-XXXXXX`, `supplier_name`) whose item costs default to `parts.unit_cost`. Event metadata `{purchase_order_id, po_number, reserved: [{part_id, qty}]}`, so `last_event.metadata.po_number` names the new PO. No notification (glossary §6).

#### `mark-parts-ready` [T14] — PP-02
- **`MarkPartsReadyRequest`:** `expected_version`?.
- Errors: 409 `INSUFFICIENT_STOCK` when any booking part's outstanding quantity exceeds available stock; nothing is reserved (atomic, spec 12 INV-10). Effects: reserves everything outstanding (`RESERVE`). Zero parts pass trivially (D31). Works from `PARTS_ORDERED` too, when stock arrived another way (D43).

#### `allocate-parts` [T16] — PP-02
- **`AllocatePartsRequest`:** `expected_version`?.
- Errors: 409 `INSUFFICIENT_STOCK` when any `reserved_qty < required_qty`. Effects: `CONSUME` movements (`on_hand` and `reserved` both drop); `consumed_qty = required_qty`, `reserved_qty = 0`; metadata `{consumed: [{part_id, qty}]}`. Notification `PARTS_READY` → the technician (brief §5.4 "parts ready → Technician").

#### `start-repair` [O2] — T-01 inline, T-02
- **`StartRepairRequest`:** `expected_version`?.
- Effects: `repair_started_at` = now; repeatable, each repair round overwrites it while the events keep every round (D25). No status change, no notification.

#### `send-to-qc` [T17] — T-02
- **`SendToQcRequest`:** `repair_notes`? ≤ 2000 (stored as the event note) · `expected_version`?.
- Effects: every `OPEN` QC issue of the booking → `RESOLVED` (`resolved_at`, `resolved_by_user_id`); `qc_inspector_user_id` cleared (D47). Notification `QC_REQUESTED` → every active QC inspector of the shop.

#### `pick-qc` [T18] — QI-01, QI-02
- **`PickQcRequest`:** `expected_version`?.
- Errors: 409 `ALREADY_PICKED` when the locked row is already `QC_IN_PROGRESS` — the loser of a concurrent pick (FAQ "first to pick locks it", SM-06); the detail says who is inspecting, and if that is the caller (a double click), the UI simply opens the inspection. 403 `FORBIDDEN` when the caller is the booking's technician (D47; unreachable with one role per shop).
- Effects: `qc_inspector_user_id` = caller; a `qc_inspections` row (`picked_at`); metadata `{qc_inspection_id}`. No notification.

#### `pass-qc` [T19] — QI-02
- **`PassQcRequest`:** `checklist` QcChecklistItemWrite[] (**required**: the five D46 keys, each once) · `notes`? ≤ 2000 · `expected_version`?.
- Errors: 403 `NOT_ASSIGNED` for a QC inspector who isn't the picker (SEC-10); 422 `VALIDATION_ERROR` with `checklist`/`checklist_incomplete` when a key is missing or repeated, with `checklist.N.key`/`enum` when a key is unknown (the schema types `key` as `QcChecklistKey`, §3.6, so Pydantic rejects it before the service runs), and with `checklist.N.passed`/`checklist_item_failed` for every item that is not passed ("use fail-qc"; spec 12 QC-01).
- Effects: inspection `result = PASS`, `completed_at`, checklist and notes stored; `qc_inspector_user_id` kept (D47). Notification `QC_PASSED` → SAs (extra). The customer sees "Ready for pick-up" at once (D27).

#### `fail-qc` [T20] — QI-02
- **`FailQcRequest`:** `issue_title` 1–120 · `issue_description` 1–2000 · `checklist`? (if present: the five keys, each once; any values) · `notes`? ≤ 2000 · `expected_version`?.
- Errors: 403 `NOT_ASSIGNED`; 422 (a checklist, when sent, follows the same key rules as `pass-qc`: `checklist_incomplete` for a missing or repeated key, `enum` for an unknown one).
- Effects: inspection `result = FAIL` with checklist and notes; a `qc_issues` row (`OPEN`); `qc_inspector_user_id` cleared; back to the **same** technician (D47); metadata `{qc_inspection_id, qc_issue_id}`. Notification `QC_FAILED` → the technician.

#### `notify-ready` [O3] — SA-02
- **`NotifyReadyRequest`:** `expected_version`?.
- Effects: `ready_notified_at` = now; repeatable (D27; send `expected_version` to avoid duplicates). Notification `VEHICLE_READY` → the customer, plus e-mail when configured (D26).

#### `complete` [T21] — SA-02 (staff route), C-02 (customer route, "mark pick-up", D28)
- **`CompleteRequest`:** `expected_version`?.
- Effects: `completed_at`. No notification. If the customer and the SA both press it, the second gets 409 `INVALID_TRANSITION`.

#### `cancel` [T22] — SA-02 (staff), C-02 (customer)
- **`CancelRequest` (staff):** `reason` 1–500 (**required**) · `expected_version`?. **`CustomerCancelRequest`:** `reason`? ≤ 500 · `expected_version`?.
- From the 11 cancellable statuses only; `IN_REPAIR` and later → 409 `INVALID_TRANSITION` (brief §5.3 "before IN_REPAIR").
- Effects (locks booking → reserved parts by ascending `id` → slot counter): every reservation released (`RELEASE`; metadata `{released: [{part_id, qty}]}`); slot counter −1; `cancelled_at`, `cancelled_by_user_id`, `cancel_reason`; open estimate versions (`DRAFT`, `SUBMITTED`, `SENT`) → `SUPERSEDED`; linked POs untouched and their later receipts become general stock (D24, D43).
- Notification `BOOKING_CANCELLED`: staff cancelled → the customer; the customer cancelled → SAs of the shop + the assigned technician + the assigned parts person.

#### `reassign-technician` [O4, P1] — SA-02 "More"
- **`ReassignTechnicianRequest`:** `technician_user_id` uuid · `expected_version`?.
- Errors: 422 `MEMBER_NOT_ELIGIBLE`; 422 `VALIDATION_ERROR` (`technician_user_id`, `unchanged`) when it is the current technician. Effects: new `technician_user_id`; the draft estimate stays; the previous technician loses visibility (404 from now on). Notification `TECHNICIAN_ASSIGNED` → the new technician.

#### `reassign-parts-person` [O5, P1] — SA-02 "More"
- **`ReassignPartsPersonRequest`:** `parts_person_user_id` uuid · `expected_version`?.
- Same rules as above; reservations and linked POs are unchanged. Notification `PARTS_NEEDED` → the new parts person.

### 5.3 `edit-estimate` and the `RECEIVE_PARTS` trigger

#### `edit-estimate` [O1] — `PUT /api/v1/shops/{shop_id}/bookings/{booking_id}/estimate` · `bookings_edit_estimate` · T-02, SA-02 · E-39
- **Who and when:** the assigned `TECHNICIAN` while `INSPECTING`; `SERVICE_ADVISOR` or `OWNER` while `ESTIMATE_REVIEW`. `PARTS_PERSON` and `QC_INSPECTOR` → 403 `FORBIDDEN`. An allowed role in any other status → 409 `ESTIMATE_LOCKED` (e.g. the SA during `INSPECTING`, anyone after sending or approval; SEC-35, EST-11).
- **`EstimateUpdate`:** `lines` EstimateLineWrite[] 1–50 (the full new list, in display order) · `inspection_notes`? ≤ 4000 (technician while `INSPECTING` only; from an SA or the Owner → 422 `not_allowed`) · `expected_version`?.
- **`EstimateLineWrite`:** `line_type` `PART` or `LABOUR` ·
  - `PART`: `part_id` uuid (an active part of this shop, else `invalid_reference`; spec 12 EST-07) · `quantity` whole number 1–9 999 · `unit_price`? Money (default `parts.unit_cost`, editable, D40) · no `description` (`not_allowed`: the server stores the catalogue name);
  - `LABOUR`: `description` 1–255 · `quantity` 0.01–999.99, at most two decimals (hours, or 1 for a flat fee) · `unit_price` Money (required) · no `part_id`.
  Totals are always recomputed on the server: `line_total = quantity × unit_price` rounded half-up to whole rupees (D41), then summed per type. Client totals are not accepted (`extra_forbidden`).
- **Semantics (D39):** in `INSPECTING`, the technician's `DRAFT` is replaced in place (no event, no version bump). In `ESTIMATE_REVIEW`, when the latest version is `SUBMITTED`, a new `DRAFT` version (author = caller) is created and the old one becomes `SUPERSEDED`, with one `EDIT_ESTIMATE` event (version bump, metadata `{estimate_id, version, grand_total}`); when the latest is already the SA's `DRAFT`, it is updated in place. Plain draft saves are last-write-wins (D30).
- **200 `EstimateEditRead`**: the editable version with live part stock, plus `booking_version` and `created_new_version`, so the client can send the right `expected_version` with `send-estimate` without refetching.
- **Errors:** common (§5.1) + 403 `FORBIDDEN`, 409 `ESTIMATE_LOCKED`, 422.

#### `RECEIVE_PARTS` [T15] — `POST /api/v1/shops/{shop_id}/purchase-orders/{po_id}/receive` · `inventory_receive_purchase_order` · PP-05 · E-51
- **Who:** any active `PARTS_PERSON` of the shop, not only the booking's parts person (receiving is a stock operation, D44). The Owner and every other role → 403.
- **`PurchaseOrderReceive`:** `items` 1–50 of {`item_id` uuid, `quantity` int 0–10 000, `expected_received_qty`? int}, distinct items.
- **Validation:** the PO is already `RECEIVED` → 409 `CONFLICT`; an item of another PO → 422 `invalid_reference`; `quantity` above the item's outstanding → 422 `exceeds_outstanding`; every quantity 0 → 422 `nothing_to_receive`; `expected_received_qty` given and different from the stored `received_qty` → 409 `CONCURRENT_UPDATE` (a duplicated or concurrent receipt; spec 12 INV-07).
- **Effects, one transaction (D43):** for a PO linked to a booking, `PurchaseOrderReceiving` lets the bookings module lock the booking first; then the PO and the received parts are locked (lock order booking → PO → parts). `RECEIVE` movements (`on_hand` up); `received_qty` per item; PO status `PARTIALLY_RECEIVED` or `RECEIVED` (+ `received_at`). If the linked booking is `PARTS_ORDERED`, the received quantities are reserved for its outstanding booking parts first (`RESERVE`, with the PO id), and the excess stays general stock; when every booking part is then fully reserved, the **`RECEIVE_PARTS`** transition moves the booking to `PARTS_READY` in the same transaction (event by the receiving Parts Person, `actor_role` `PARTS_PERSON`, metadata `{purchase_order_id}`). A partial delivery keeps the booking `PARTS_ORDERED` (brief §5.3, SM-12) and writes no booking event; when it reserved stock for the booking, the bookings module publishes `BookingPartsChanged` and the notifications module pushes `booking.updated` after commit, with the booking's unchanged `version` (D83, spec 01 event catalogue). A booking in any other status (e.g. `CANCELLED`) gets nothing reserved, and a general-restock PO only raises `on_hand` (D24, INV-08, INV-09).
- **200 `PurchaseOrderReceiveRead`**: the updated PO; `receive_parts_applied` says whether the booking moved, and `purchase_order.booking.status` gives its status. No notification type exists for `RECEIVE_PARTS` or for a partial reservation; in both cases the booking's viewers get `booking.updated` (§6.4).

---

## 6. Realtime protocol (glossary §11, D14, D70)

**Priority (D88):** everything in §6.1–§6.5 — the ticket, the socket and the hub — is **P1**; the bonus calling (P2) depends on it. The P0 product stays current through the §6.6 polling alone, so no P0 screen may depend on a push arriving.

### 6.1 Ticket

`GET /api/v1/realtime/ticket` (session, through the web rewrite) → `{"ticket": "<jwt>", "expires_in": 60}`. The ticket is an HS256 JWT with exactly `sub`, `iat`, `exp = iat + 60` and `typ = "ws"`; it is only good for the handshake and is useless as a session token (401). The client fetches a new one for **every** connect attempt. A **401 from this endpoint means the session has expired**: the client stops reconnecting and runs the session-expired flow (spec 09). Tickets may be reused within their 60 s in Tier 1; single use is Tier 2 (D70). Server logs redact the query string value (`ticket=[redacted]`, spec 04).

### 6.2 Handshake

- URL: `wss://<api-host>/api/v1/ws?ticket=<url-encoded ticket>`, i.e. `NEXT_PUBLIC_WS_URL` + `?ticket=` (locally `ws://localhost:4000/api/v1/ws`). It never goes through Vercel (D7).
- Before `accept()` the server checks, in order: an `Origin` header, when present, must equal `CLIENT_URL` (cross-site WebSocket hijacking defence; clients without `Origin`, such as tests, still need a ticket); the ticket's signature, `exp` and `typ == "ws"`; the user exists and is active. **Any failure → `close(code=1008)` before accept** (D70, spec 04).
- What clients observe (verified on uvicorn 0.54 + Starlette 1.7): a close before accept makes uvicorn refuse the upgrade with HTTP 403, so **browsers report the `close` event with code 1006**, never 1008; Starlette's `TestClient` raises `WebSocketDisconnect(code=1008)`, which is what SEC-33 asserts. A 1008 sent after accept does arrive as 1008.
- Therefore **clients never branch on close codes: any close → fetch a new ticket → reconnect with backoff** (§6.5).
- After accept, the socket is registered under the user's id; a user may hold several sockets (tabs).

### 6.3 Messages

Every frame is JSON. Server → client: `{"type": "<type>", "data": {…}}`.

| `type` | Sent to | `data` |
|---|---|---|
| `notification.created` | the notification's recipient | `NotificationRead` |
| `booking.updated` | the booking's customer + every active member of its shop who can see it under D21 (SAs and the Owner; its technician; its parts person; QC inspectors while `QC_PENDING`/`QC_IN_PROGRESS` or who inspected it) | `{"booking_id", "shop_id", "status", "version"}` |
| `pong` | the socket that sent `ping` | `{}` |
| `call.incoming` *(P2)* | the rung users | `CallRead` |
| `call.updated` *(P2)* | the caller, the answerer and everyone who was rung (so their pop-ups close) | `CallRead` |
| `task.created` *(P2)* | the SAs of the shop | `TaskRead` |

Client → server: `{"type": "ping"}` only; the server answers `pong`. Any other frame is ignored (no reply, the connection stays open).

### 6.4 Fan-out rules

- Pushes run only from after-commit hooks (spec 01): nothing is ever pushed for a rolled-back action, and push failures never change the HTTP response.
- `booking.updated` follows every booking event: every action and operation, `CREATE`, `RECEIVE_PARTS`, and an `EDIT_ESTIMATE` that created a version. It is also pushed when a booking's parts state changes without a booking event (D83): today, a PO receipt that reserves stock for a `PARTS_ORDERED` booking without completing it (§5.3). The bookings module publishes `BookingPartsChanged` and the notifications module pushes after commit (spec 01); that push carries the booking's unchanged `version`, because D30 bumps it only with an event. Recipients are computed at push time from live database state, so a deactivated member, a former assignee after `reassign-*`, or a QC inspector who never touched the booking receive nothing. An in-place draft save writes no event and pushes nothing; polling and focus refetches cover it.
- `notification.created`: one per notification row, to that row's recipient only.
- Clients compare the pushed `version` with their cached booking (spec 09 §2.7). **Newer**, or nothing cached → refetch the booking and the lists that show it. **Equal** → the booking row did not change: it is the echo of their own action or a D83 parts change, so only the parts views refetch (the booking's parts, the parts list, purchase orders). **Older** → ignore.
- P2: when a socket connects, the hub re-sends `call.incoming` for calls still `RINGING` that target the user.

### 6.5 Liveness, close codes, reconnect

- The client sends `ping` every 25 s and reconnects when nothing arrives within 10 s (spec 09). Server-side, uvicorn's protocol-level pings drop dead connections (`ws_ping_interval` 20 s, `ws_ping_timeout` 20 s by default — verified in uvicorn 0.54's `Config`).
- Codes a browser may see: 1000 (normal, e.g. logout), 1001 (server going away, e.g. redeploy), 1006 (network loss **or a rejected handshake**), 1008 (only after accept: the Tier 2 single-use ticket or deactivated-member close). All are handled the same way.
- Reconnect: new ticket per attempt; backoff `min(30 s, 1 s × 2^attempt) × random(0.8–1.2)`, reset on open, immediate on the `online` event or when the tab becomes visible; after a reconnect (not the first connect) the client invalidates `['me']` and `['shops']` to catch up. Messages are not replayed.

### 6.6 Polling fallback (D14)

While the tab is visible the web polls every 15 s, even with the socket open. This polling is the **P0** freshness path (D88); the socket only makes updates faster:

| Endpoint | Where |
|---|---|
| `GET /api/v1/me/notifications/unread-count` | every logged-in page (bell) |
| `GET …/bookings`, `GET …/bookings/status-counts` | staff lists and queues (SA-01, T-01, PP-01, QI-01) |
| `GET …/bookings/{booking_id}` | staff booking pages (SA-02, T-02, PP-02, QI-02) |
| `GET /api/v1/me/bookings`, `GET /api/v1/me/bookings/{booking_id}` | customer area (C-01, C-02) |
| `GET …/overview` | O-01 |
| `GET …/parts`, `GET …/purchase-orders` | PP-03, PP-04, open estimate editors (live stock, D40) |
| `GET /api/v1/public/shops/{shop_slug}/availability` | wizard time step (P-03 W3) |
| `GET …/tasks` *(P2)* | B-04 |

Child panels (events, estimates, booking parts, QC rounds) refetch when the booking's `version` changes; the booking-parts panel also refetches on a `booking.updated` with an unchanged `version` (D83, §6.4). Every polled route is an indexed GET with `Cache-Control: no-store`.

---

## 7. Examples

Worked example (brief §6) on Lahore Auto Care. Friday 16 Oct 2026, 10:00 PKT = `2026-10-16T05:00:00Z`. IDs: shop `3f2c9a1e-6b4d-4c8e-9a7f-1d2e3f4a5b6c`, booking `8d1e4b6a-2c3f-4e5a-b7c8-9d0e1f2a3b4c` (`BF-7K2M9Q`), Ahmed `c5a1f2e3-4b6d-4e8f-a1b2-c3d4e5f60718`, Imran `1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5e`, Usman `2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6f`. Tokens and passwords are shown as placeholders so that no credential-like strings live in the repository.

### 7.1 Create a booking with a new account (step 3)

```http
POST /api/v1/bookings HTTP/1.1
Host: <web-host>
Content-Type: application/json

{
  "shop_id": "3f2c9a1e-6b4d-4c8e-9a7f-1d2e3f4a5b6c",
  "service_ids": ["a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d", "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e"],
  "slot_start": "2026-10-16T05:00:00Z",
  "customer_notes": "Light came on yesterday, car vibrates at idle.",
  "customer": {
    "full_name": "Ahmed",
    "email": "ahmed.demo@bayflow.test",
    "password": "<12 to 128 characters>",
    "phone": "+92 300 1234567"
  },
  "vehicle": { "registration_number": "LEA-1234", "make": "Honda", "model": "Civic", "year": 2016 }
}
```

```http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-store
X-Request-ID: 4f6c2d1a-7b8e-4c3d-9a1b-2c3d4e5f6a7b
Set-Cookie: bf_session=<jwt>; HttpOnly; Max-Age=604800; Path=/; SameSite=lax; Secure

{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 604800,
  "account_created": true,
  "booking": {
    "id": "8d1e4b6a-2c3f-4e5a-b7c8-9d0e1f2a3b4c",
    "reference": "BF-7K2M9Q",
    "status": "PENDING",
    "version": 1,
    "slot_start": "2026-10-16T05:00:00Z",
    "slot_end": "2026-10-16T06:00:00Z",
    "status_changed_at": "2026-10-09T10:15:04Z",
    "shop": {
      "id": "3f2c9a1e-6b4d-4c8e-9a7f-1d2e3f4a5b6c", "slug": "lahore-auto-care", "name": "Lahore Auto Care",
      "address": "Plot 12, Main Boulevard, Gulberg III", "city": "Lahore", "phone": "+924200000101", "timezone": "Asia/Karachi"
    },
    "vehicle": {
      "id": "d4e5f6a7-b8c9-4d0e-8f1a-2b3c4d5e6f70", "registration_number": "LEA-1234", "make": "Honda", "model": "Civic",
      "year": 2016, "color": null, "mileage_km": null, "created_at": "2026-10-09T10:15:04Z", "updated_at": "2026-10-09T10:15:04Z"
    },
    "mileage_km": null,
    "services": [
      { "service_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d", "name": "Check engine light", "base_price": "2000.00" },
      { "service_id": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e", "name": "Oil change", "base_price": "1000.00" }
    ],
    "customer_notes": "Light came on yesterday, car vibrates at idle.",
    "estimate": null,
    "estimate_revision_in_progress": false,
    "allowed_actions": ["cancel"],
    "ready_notified_at": null,
    "completed_at": null,
    "cancelled_at": null,
    "cancelled_by_customer": null,
    "cancel_reason": null,
    "created_at": "2026-10-09T10:15:04Z",
    "updated_at": "2026-10-09T10:15:04Z"
  }
}
```

In the same transaction: user created (phone stored as `+923001234567`), vehicle created, slot counter for 05:00 Z incremented, `CREATE` event, `BOOKING_CREATED` → Bilal. After commit: the cookie logs Ahmed in, and Bilal gets `notification.created` and `booking.updated`.

### 7.2 Approve the estimate (step 7, customer route)

```http
POST /api/v1/me/bookings/8d1e4b6a-2c3f-4e5a-b7c8-9d0e1f2a3b4c/actions/approve-estimate HTTP/1.1
Host: <web-host>
Cookie: bf_session=<jwt>
Content-Type: application/json

{ "estimate_id": "e7f8a9b0-c1d2-4e3f-a4b5-c6d7e8f9a0b1", "expected_version": 7 }
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id": "8d1e4b6a-2c3f-4e5a-b7c8-9d0e1f2a3b4c",
  "reference": "BF-7K2M9Q",
  "status": "ESTIMATE_APPROVED",
  "version": 8,
  "slot_start": "2026-10-16T05:00:00Z",
  "slot_end": "2026-10-16T06:00:00Z",
  "status_changed_at": "2026-10-16T10:05:12Z",
  "shop": {
    "id": "3f2c9a1e-6b4d-4c8e-9a7f-1d2e3f4a5b6c", "slug": "lahore-auto-care", "name": "Lahore Auto Care",
    "address": "Plot 12, Main Boulevard, Gulberg III", "city": "Lahore", "phone": "+924200000101", "timezone": "Asia/Karachi"
  },
  "vehicle": {
    "id": "d4e5f6a7-b8c9-4d0e-8f1a-2b3c4d5e6f70", "registration_number": "LEA-1234", "make": "Honda", "model": "Civic",
    "year": 2016, "color": null, "mileage_km": null, "created_at": "2026-10-09T10:15:04Z", "updated_at": "2026-10-09T10:15:04Z"
  },
  "mileage_km": null,
  "services": [
    { "service_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d", "name": "Check engine light", "base_price": "2000.00" },
    { "service_id": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e", "name": "Oil change", "base_price": "1000.00" }
  ],
  "customer_notes": "Light came on yesterday, car vibrates at idle.",
  "estimate": {
    "id": "e7f8a9b0-c1d2-4e3f-a4b5-c6d7e8f9a0b1",
    "version": 2,
    "status": "APPROVED",
    "lines": [
      { "id": "f1a2b3c4-d5e6-4f7a-8b9c-0d1e2f3a4b51", "position": 1, "line_type": "PART", "description": "Ignition coil",
        "quantity": "1.00", "unit_price": "6500.00", "line_total": "6500.00" },
      { "id": "f1a2b3c4-d5e6-4f7a-8b9c-0d1e2f3a4b52", "position": 2, "line_type": "PART", "description": "Oil filter",
        "quantity": "1.00", "unit_price": "900.00", "line_total": "900.00" },
      { "id": "f1a2b3c4-d5e6-4f7a-8b9c-0d1e2f3a4b53", "position": 3, "line_type": "PART", "description": "Engine oil 4 L",
        "quantity": "1.00", "unit_price": "5200.00", "line_total": "5200.00" },
      { "id": "f1a2b3c4-d5e6-4f7a-8b9c-0d1e2f3a4b54", "position": 4, "line_type": "LABOUR", "description": "Diagnosis and repair labour",
        "quantity": "1.00", "unit_price": "3500.00", "line_total": "3500.00" }
    ],
    "parts_total": "12600.00",
    "labour_total": "3500.00",
    "grand_total": "16100.00",
    "sent_at": "2026-10-16T09:40:00Z",
    "decided_at": "2026-10-16T10:05:12Z",
    "customer_note": null
  },
  "estimate_revision_in_progress": false,
  "allowed_actions": ["cancel"],
  "ready_notified_at": null,
  "completed_at": null,
  "cancelled_at": null,
  "cancelled_by_customer": null,
  "cancel_reason": null,
  "created_at": "2026-10-09T10:15:04Z",
  "updated_at": "2026-10-16T10:05:12Z"
}
```

Effects: v2 `APPROVED` with `decided_at` and `decided_by_user_id` = Ahmed (locked from now on); `APPROVE_ESTIMATE` event (metadata `{estimate_id, version: 2, grand_total: "16100.00"}`); `ESTIMATE_APPROVED` → Bilal. With an old tab still holding v1, the same call with v1's id returns 409 `STALE_ESTIMATE`.

### 7.3 Order the missing part (step 9, assigned Parts Person)

```http
POST /api/v1/shops/3f2c9a1e-6b4d-4c8e-9a7f-1d2e3f4a5b6c/bookings/8d1e4b6a-2c3f-4e5a-b7c8-9d0e1f2a3b4c/actions/order-parts HTTP/1.1
Host: <web-host>
Cookie: bf_session=<jwt>
Content-Type: application/json

{
  "supplier_name": "City Auto Parts",
  "items": [{ "part_id": "0a1b2c3d-4e5f-4a6b-9c7d-8e9f0a1b2c31", "quantity": 1 }],
  "expected_version": 9
}
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id": "8d1e4b6a-2c3f-4e5a-b7c8-9d0e1f2a3b4c",
  "shop_id": "3f2c9a1e-6b4d-4c8e-9a7f-1d2e3f4a5b6c",
  "reference": "BF-7K2M9Q",
  "status": "PARTS_ORDERED",
  "version": 10,
  "slot_start": "2026-10-16T05:00:00Z",
  "slot_end": "2026-10-16T06:00:00Z",
  "status_changed_at": "2026-10-16T10:20:31Z",
  "customer": { "user_id": "c5a1f2e3-4b6d-4e8f-a1b2-c3d4e5f60718", "full_name": "Ahmed", "email": null, "phone": null },
  "vehicle": {
    "id": "d4e5f6a7-b8c9-4d0e-8f1a-2b3c4d5e6f70", "registration_number": "LEA-1234", "make": "Honda", "model": "Civic",
    "year": 2016, "color": null, "mileage_km": null, "created_at": "2026-10-09T10:15:04Z", "updated_at": "2026-10-09T10:15:04Z"
  },
  "mileage_km": null,
  "services": [
    { "service_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d", "name": "Check engine light", "base_price": "2000.00" },
    { "service_id": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e", "name": "Oil change", "base_price": "1000.00" }
  ],
  "customer_notes": "Light came on yesterday, car vibrates at idle.",
  "inspection_notes": "Faulty ignition coil; oil and filter due.",
  "technician": { "user_id": "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5e", "full_name": "Imran", "is_active": true },
  "parts_person": { "user_id": "2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6f", "full_name": "Usman", "is_active": true },
  "qc_inspector": null,
  "estimate_summary": { "estimate_id": "e7f8a9b0-c1d2-4e3f-a4b5-c6d7e8f9a0b1", "version": 2, "status": "APPROVED",
                        "grand_total": "16100.00", "line_count": 4 },
  "parts_summary": { "required_count": 3, "available_count": 2, "shortage_count": 1, "all_available": false },
  "open_qc_issues_count": 0,
  "qc_round": 0,
  "repair_started_at": null,
  "ready_notified_at": null,
  "completed_at": null,
  "cancelled_at": null,
  "cancelled_by": null,
  "cancel_reason": null,
  "last_event": {
    "id": "5e6f7a8b-9c0d-4e1f-a2b3-c4d5e6f7a8b9",
    "action": "ORDER_PARTS",
    "from_status": "PARTS_PENDING",
    "to_status": "PARTS_ORDERED",
    "actor": { "user_id": "2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6f", "full_name": "Usman" },
    "actor_role": "PARTS_PERSON",
    "note": null,
    "metadata": {
      "purchase_order_id": "9e8d7c6b-5a4f-4e3d-a2c1-b0a9f8e7d6c5",
      "po_number": "PO-4H8K2M",
      "reserved": [
        { "part_id": "0a1b2c3d-4e5f-4a6b-9c7d-8e9f0a1b2c32", "qty": 1 },
        { "part_id": "0a1b2c3d-4e5f-4a6b-9c7d-8e9f0a1b2c33", "qty": 1 }
      ]
    },
    "created_at": "2026-10-16T10:20:31Z"
  },
  "allowed_actions": ["mark-parts-ready"],
  "created_at": "2026-10-09T10:15:04Z",
  "updated_at": "2026-10-16T10:20:31Z"
}
```

Stock afterwards (on hand / reserved): oil filter 10/1, engine oil 8/1, ignition coil 0/0; `PO-4H8K2M` is `ORDERED` for one coil and linked to the booking. The customer's e-mail and phone are `null` because the caller is a Parts Person. No notification.

### 7.4 Receive the purchase order, which fires `RECEIVE_PARTS` (step 10)

```http
POST /api/v1/shops/3f2c9a1e-6b4d-4c8e-9a7f-1d2e3f4a5b6c/purchase-orders/9e8d7c6b-5a4f-4e3d-a2c1-b0a9f8e7d6c5/receive HTTP/1.1
Host: <web-host>
Cookie: bf_session=<jwt>
Content-Type: application/json

{ "items": [{ "item_id": "9e8d7c6b-5a4f-4e3d-a2c1-b0a9f8e7d6d1", "quantity": 1, "expected_received_qty": 0 }] }
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "purchase_order": {
    "id": "9e8d7c6b-5a4f-4e3d-a2c1-b0a9f8e7d6c5",
    "po_number": "PO-4H8K2M",
    "status": "RECEIVED",
    "supplier_name": "City Auto Parts",
    "booking": { "id": "8d1e4b6a-2c3f-4e5a-b7c8-9d0e1f2a3b4c", "reference": "BF-7K2M9Q", "status": "PARTS_READY", "version": 11 },
    "item_count": 1,
    "ordered_qty_total": 1,
    "received_qty_total": 1,
    "total_cost": "6500.00",
    "created_by": { "user_id": "2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6f", "full_name": "Usman" },
    "created_at": "2026-10-16T10:20:31Z",
    "received_at": "2026-10-17T05:30:08Z",
    "items": [
      { "id": "9e8d7c6b-5a4f-4e3d-a2c1-b0a9f8e7d6d1",
        "part": { "id": "0a1b2c3d-4e5f-4a6b-9c7d-8e9f0a1b2c31", "sku": "IGN-COIL-01", "name": "Ignition coil" },
        "ordered_qty": 1, "received_qty": 1, "outstanding_qty": 0, "unit_cost": "6500.00", "line_cost": "6500.00" }
    ],
    "updated_at": "2026-10-17T05:30:08Z"
  },
  "receive_parts_applied": true
}
```

One transaction: booking locked first, then the PO and the coil; `RECEIVE` (+1 on hand) and `RESERVE` (+1 reserved for BF-7K2M9Q) movements, so the coil is 1/1; every booking part is now fully reserved, so `RECEIVE_PARTS` moves the booking to `PARTS_READY` (event by Usman, `actor_role` `PARTS_PERSON`, version 10 → 11); `booking.updated` is pushed and no notification is created. Usman's next call is `allocate-parts` with `expected_version: 11` (→ `IN_REPAIR`, `PARTS_READY` → Imran). Had only part of the order arrived, the PO would be `PARTIALLY_RECEIVED`, the booking would stay `PARTS_ORDERED` at version 10 and `receive_parts_applied` would be `false`; the stock reserved for it would still push `booking.updated` (with version 10) to its viewers (D83).

### 7.5 `INVALID_TRANSITION`: a double-clicked `confirm` (step 4)

The first request returned 200 (`CONFIRMED`, version 2). The second, sent from the same render:

```http
POST /api/v1/shops/3f2c9a1e-6b4d-4c8e-9a7f-1d2e3f4a5b6c/bookings/8d1e4b6a-2c3f-4e5a-b7c8-9d0e1f2a3b4c/actions/confirm HTTP/1.1
Host: <web-host>
Cookie: bf_session=<jwt>
Content-Type: application/json

{ "expected_version": 1 }
```

```http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-ID: 7c1d9e2f-3a4b-4c5d-8e6f-7a8b9c0d1e2f

{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "code": "INVALID_TRANSITION",
  "detail": "'confirm' is not allowed while the booking is CONFIRMED.",
  "instance": "/api/v1/shops/3f2c9a1e-6b4d-4c8e-9a7f-1d2e3f4a5b6c/bookings/8d1e4b6a-2c3f-4e5a-b7c8-9d0e1f2a3b4c/actions/confirm"
}
```

The status is checked before `expected_version` (§1.4), so the code is `INVALID_TRANSITION` rather than `CONCURRENT_UPDATE`. No event is written; the web refetches the booking (spec 09 §2.9).

### 7.6 Cross-tenant access: 404 (brief §7.1 acceptance, spec 04 SEC-01)

Bilal, a Service Advisor of Lahore Auto Care only, asks for a Clifton Car Clinic booking:

```http
GET /api/v1/shops/7b8c9d0e-1f2a-4b3c-8d4e-5f6a7b8c9d0e/bookings/6c7d8e9f-0a1b-4c2d-8e3f-4a5b6c7d8e9f HTTP/1.1
Host: <api-host>
Authorization: Bearer <jwt>
```

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "code": "NOT_FOUND",
  "detail": "The requested resource was not found.",
  "instance": "/api/v1/shops/7b8c9d0e-1f2a-4b3c-8d4e-5f6a7b8c9d0e/bookings/6c7d8e9f-0a1b-4c2d-8e3f-4a5b6c7d8e9f"
}
```

The membership dependency answers 404 before the booking is read. Putting the same booking id under his own shop (`GET /api/v1/shops/3f2c9a1e-6b4d-4c8e-9a7f-1d2e3f4a5b6c/bookings/6c7d8e9f-0a1b-4c2d-8e3f-4a5b6c7d8e9f`) returns the identical body apart from `instance`, because the booking query is scoped by `shop_id` (composite foreign keys back it up, spec 02 §4). The response never reveals whether the id exists elsewhere.

---

## 8. Traceability

### 8.1 Spec 10 assumed endpoints → this contract

"Same" = path, method and the fields the screen relies on are unchanged. Otherwise the change is given as old → new.

| E-nn | Endpoint (`operationId`) | Status |
|---|---|---|
| E-01 | `POST /api/v1/auth/login` (`identity_login`) | Same path, served by the identity router (D81); body `SessionRead` = token fields + `user` (`UserRead`), no memberships; memberships come from E-04, called right after |
| E-02 | `POST /api/v1/auth/logout` (`identity_logout`) | Same |
| E-03 | `POST /api/v1/auth/register-owner` (`identity_register_owner`) | Same, + optional `phone` (spec 04); body `SessionRead` like E-01 (D81) |
| E-04 | `GET /api/v1/me` (`shops_get_me`, served and tagged by `shops`, D81) | `user {…}` → user fields at the top level; membership `shop {id, name, slug, city, timezone, logo_url}` → flat `shop_id`, `shop_name`, `shop_slug`; `is_active` dropped (active only) — spec 04's shape |
| E-05 | `GET /api/v1/realtime/ticket` (`notifications_get_realtime_ticket`) | Same |
| WS | `wss://<api-host>/api/v1/ws?ticket=…` | Same; `pong` frame is `{"type": "pong", "data": {}}` (§6.3) |
| E-06 | `GET /api/v1/public/shops` (`shops_list_public_shops`) | Same |
| E-07 | `GET /api/v1/public/cities` (`shops_list_public_cities`) | bare `string[]` → `{items: string[]}` |
| E-08 | `GET /api/v1/public/shops/{shop_slug}` (`shops_get_public_shop`) | Same, + `is_bookable` |
| E-09 | `GET /api/v1/public/shops/{shop_slug}/availability` (`scheduling_get_availability`) | slot `{start, end, remaining}` → `{slot_start, slot_end, remaining}`; + `shop_id`, `slot_duration_minutes`; full slots are omitted |
| E-10 | `POST /api/v1/bookings` (`bookings_create_booking`) | `vehicle.colour` → `color`; booking fields at the top level → nested under `booking`, next to `access_token`, `token_type`, `expires_in`, `account_created` |
| E-11 | `GET /api/v1/me/bookings` (`bookings_list_my_bookings`) | `services[]` (names) → `service_names`; + `sort` |
| E-12 | `GET /api/v1/me/bookings/{booking_id}` (`bookings_get_my_booking`) | Same, + `estimate_revision_in_progress`, `cancelled_by_customer` |
| E-13 | `GET /api/v1/me/bookings/{booking_id}/events` (`bookings_list_my_booking_events`) | bare array → `{items}`; + `id` and `note` (customer-facing reasons only) |
| E-14 | `GET /api/v1/me/bookings/{booking_id}/estimates` (`bookings_list_my_booking_estimates`) | Same (P1), wrapped in `{items}` |
| E-15 | `POST /api/v1/me/bookings/{booking_id}/actions/{slug}` (`bookings_my_*`) | Same four slugs and bodies; any other slug on this family is 404 |
| E-16 | `GET /api/v1/me/vehicles` (`bookings_list_my_vehicles`) | `colour` → `color`; `{items}` |
| E-17 | `GET /api/v1/me/notifications` (`notifications_list_my_notifications`) | Same |
| E-18 | `GET /api/v1/me/notifications/unread-count` (`notifications_get_unread_count`) | Same |
| E-19 | `POST /api/v1/me/notifications/{notification_id}/read` (`notifications_mark_notification_read`) | Same |
| E-20 | `POST /api/v1/me/notifications/read-all` (`notifications_mark_all_notifications_read`) | Same |
| E-21 | `POST /api/v1/shops` (`shops_create_shop`) | Same; `working_hours` (7 rows) required, `timezone` optional |
| E-22 | `GET /api/v1/shops/{shop_id}` (`shops_get_shop`) | Same, + `has_future_bookings` |
| E-23 | `PATCH /api/v1/shops/{shop_id}` (`shops_update_shop`) | Same, + 422 `hours_not_on_grid` |
| E-24 | `PUT /api/v1/shops/{shop_id}/working-hours` (`shops_replace_working_hours`) | bare array → `{working_hours: [...]}`; returns `ShopRead` |
| E-25 | `GET /api/v1/shops/{shop_id}/members` (`shops_list_members`) | Same, paginated |
| E-26 | `POST /api/v1/shops/{shop_id}/members` (`shops_add_member`) | Same (`password?`, `phone?`; the member + `account_created`) |
| E-27 | `PATCH /api/v1/shops/{shop_id}/members/{membership_id}` (`shops_update_member`) | Same |
| E-28 | `GET /api/v1/shops/{shop_id}/services` (`shops_list_services`) | Same |
| E-29 | `POST /api/v1/shops/{shop_id}/services` (`shops_create_service`) | Same |
| E-30 | `PATCH /api/v1/shops/{shop_id}/services/{service_id}` (`shops_update_service`) | Same |
| E-31 | `GET /api/v1/shops/{shop_id}/overview` (`reporting_get_overview`) | `status_counts` map → `[{status, count}]`; + `shop`, `inventory.open_purchase_orders` |
| E-32 | `GET /api/v1/me/owner-summary` (`reporting_get_owner_summary`) | bare array → `{items}` |
| E-33 | `GET /api/v1/shops/{shop_id}/bookings` (`bookings_list_shop_bookings`) | `services[]` → `service_names`; + `parts_person_user_id` filter and the `sort` allowlist |
| E-34 | `GET /api/v1/shops/{shop_id}/bookings/status-counts` (`bookings_get_status_counts`) | map → `{items: [{status, count}], total}` |
| E-35 | `GET /api/v1/shops/{shop_id}/bookings/{booking_id}` (`bookings_get_shop_booking`) | Same, + `last_event`; customer e-mail/phone only for SA and Owner |
| E-36 | `GET …/bookings/{booking_id}/events` (`bookings_list_booking_events`) | bare array → `{items}` |
| E-37 | `POST …/bookings/{booking_id}/actions/{slug}` (`bookings_<slug>`, 22 routes) | Same; bodies in §5 |
| E-38 | `GET …/bookings/{booking_id}/estimates` (`bookings_list_booking_estimates`) | bare array → `{items}`; `part` = `PartStockRef` (+ `stock_state`) |
| E-39 | `PUT …/bookings/{booking_id}/estimate` (`bookings_edit_estimate`) | Same body; response `EstimateEditRead` (+ `booking_version`, `created_new_version`) |
| E-40 | `GET …/bookings/{booking_id}/parts` (`bookings_get_booking_parts`) | Same, + `required_count`, `available_count`, `outstanding_qty`, `shortage_qty`, `purchase_orders` |
| E-41 | `GET …/bookings/{booking_id}/qc-inspections` (`bookings_list_booking_qc_inspections`) | `picked_by` → `inspector`; + `round`; `{items}` |
| E-42 | `GET /api/v1/shops/{shop_id}/qc/checklist` (`qc_get_checklist`) | bare array → `{items}` |
| E-43 | `GET /api/v1/shops/{shop_id}/parts` (`inventory_list_parts`) | filter `stock` (low, out) → repeatable `stock_state` (`OK`, `LOW`, `OUT`); + `stock_state`, `on_order`, `sort` |
| E-44 | `POST …/parts` (`inventory_create_part`) | Same (no stock field, D44) |
| E-45 | `PATCH …/parts/{part_id}` (`inventory_update_part`) | Same |
| E-46 | `POST …/parts/{part_id}/adjustments` (`inventory_adjust_stock`) | Same body; response `{part, movement}`; below reserved → 409 `INSUFFICIENT_STOCK`; P1 → **P0** (D82) |
| E-47 | `GET …/parts/{part_id}/movements` (`inventory_list_part_movements`) | `booking_reference?`, `po_number?` → `booking {id, reference}`, `purchase_order {id, po_number}`; + deltas |
| E-48 | `GET …/purchase-orders` (`inventory_list_purchase_orders`) | Same |
| E-49 | `POST …/purchase-orders` (`inventory_create_purchase_order`) | Same, + optional `unit_cost` per item |
| E-50 | `GET …/purchase-orders/{po_id}` (`inventory_get_purchase_order`) | Same, + `outstanding_qty`, `unit_cost`, `line_cost`, `total_cost` |
| E-51 | `POST …/purchase-orders/{po_id}/receive` (`inventory_receive_purchase_order`) | `booking_status` → `receive_parts_applied` + `purchase_order.booking.status`; + optional `expected_received_qty` |
| E-52 | `POST /api/v1/me/bookings/{booking_id}/calls` (`calls_start_my_call`) | `{call, room, token}` → `CallStartRead {call, connection}` (spec 05) |
| E-53 | `POST …/bookings/{booking_id}/calls` (`calls_start_call`) | as E-52 |
| E-54 | `POST /api/v1/me/calls/{call_id}/accept`, `/decline`, `/end` (`calls_*_my_call`) | `accept` → `CallStartRead` |
| E-55 | `POST …/calls/{call_id}/accept`, `/decline`, `/end` (`calls_accept_call`, …) | `accept` → `CallStartRead` |
| E-56 | `GET /api/v1/me/bookings/{booking_id}/calls` (`calls_list_my_booking_calls`) | `Page[CallRead]` |
| E-57 | `GET …/bookings/{booking_id}/calls` (`calls_list_booking_calls`) | `ai_call_summary_id` → `has_summary`, `open_task_count` |
| E-58 | `GET …/calls`, `GET …/calls/{call_id}` (`calls_list_shop_calls`, `calls_get_call`) | Same (spec 05) |
| E-59 | `GET …/tasks` (`calls_list_tasks`) | `Page[TaskRead]` |
| E-60 | `POST …/tasks/{task_id}/mark-done` (`calls_mark_task_done`) | Same, body `{note?}` |

### 8.2 Brief capabilities → endpoints

| Brief | Capability | Endpoints |
|---|---|---|
| §7.1 | Owner sign-up and login; staff login with Owner-created credentials; customer login with wizard credentials | `identity_register_owner`, `identity_login`, `shops_add_member`, `bookings_create_booking` |
| §7.1 | Secure hashing, token/session auth, role checks on every protected endpoint | §1.2–§1.4 (cookie or Bearer, D9 re-checks, `require_shop_member`, `require_roles`, spec 08 rules) |
| §7.1 | Tenant isolation; Shop A staff on Shop B bookings → 403/404 | every `/api/v1/shops/{shop_id}/…` route → 404 (§7.6) |
| §7.2 | Create a shop (name, address, city, phone, working hours, slot duration/capacity, logo) | `shops_create_shop`, `shops_update_shop`, `shops_replace_working_hours` |
| §7.2 | Add team members with a role; edit or deactivate them | `shops_list_members`, `shops_add_member`, `shops_update_member` |
| §7.2 | Additional shops; shop switcher | `shops_create_shop`; `shops_get_me` memberships |
| §7.2 | Service catalogue | `shops_list_services`, `shops_create_service`, `shops_update_service` |
| §7.3 | Landing: all shops (name, city, rating, services), search or city filter | `shops_list_public_shops`, `shops_list_public_cities`, `shops_get_public_shop` |
| §7.3 | Wizard; slot picker shows only available slots | `scheduling_get_availability`, `bookings_create_booking`, `bookings_list_my_vehicles` (P1) |
| §7.3 | Customer dashboard: list, live timeline, pending actions, itemised estimate, accept/reject, ready-for-pick-up | `bookings_list_my_bookings`, `bookings_get_my_booking`, `bookings_list_my_booking_events`, `bookings_my_approve_estimate`, `bookings_my_reject_estimate`, `bookings_my_complete`, `bookings_my_cancel`; §6 |
| §7.4 SA | Bookings list with status filters; confirm/decline; assign technician; review/edit estimate; send; assign parts person; notify ready; complete; bell | `bookings_list_shop_bookings`, `bookings_get_status_counts`, `bookings_confirm`, `bookings_decline`, `bookings_assign_technician`, `bookings_edit_estimate`, `bookings_send_estimate`, `bookings_assign_parts_person`, `bookings_notify_ready`, `bookings_complete`, notifications routes |
| §7.4 Technician | My jobs; booking and vehicle detail; estimate lines (part, quantity, unit cost, labour); submit; start repair; send to QC; QC issues sent back | `bookings_list_shop_bookings` (D21), `bookings_get_shop_booking`, `bookings_start_inspection`, `bookings_edit_estimate`, `inventory_list_parts`, `bookings_submit_estimate`, `bookings_start_repair`, `bookings_send_to_qc`, `bookings_list_booking_qc_inspections` |
| §7.4 Parts | Inventory table; jobs awaiting parts with required vs available; create POs; receive (stock up); allocate | `inventory_list_parts`, `bookings_list_shop_bookings`, `bookings_get_booking_parts`, `bookings_order_parts`, `inventory_create_purchase_order`, `inventory_receive_purchase_order`, `bookings_mark_parts_ready`, `bookings_allocate_parts` |
| §7.4 QC | Shared queue; pick; checklist/notes; pass or raise an issue | `bookings_list_shop_bookings` (QC statuses), `qc_get_checklist`, `bookings_pick_qc`, `bookings_pass_qc`, `bookings_fail_qc` |
| §7.4 Owner | Overview: bookings by status, team, inventory summary; any role view | `reporting_get_overview`, every staff read route (D16), `reporting_get_owner_summary` (P1) |
| §7.5 | One source of truth; audit log; role guard per transition; estimate versioning | §5 (rule-table routes, `allowed_actions`), `bookings_list_booking_events`, `bookings_list_booking_estimates` |
| §7.6 | Per-shop catalogue and quantities; shortages computed; POs `ORDERED`/`PARTIALLY_RECEIVED`/`RECEIVED`; receiving raises stock; allocation lowers it; cancellation returns reservations | parts routes, `bookings_get_booking_parts`, PO routes, `inventory_receive_purchase_order`, `bookings_allocate_parts`, `bookings_cancel`, `bookings_my_cancel` |
| §7.7 | Seed data and demo credentials | no endpoint: the seed calls the same services (D51); demo users log in through `identity_login` |
| §7.8 | Full flow to `COMPLETED`, QC fail loop, estimate-rejected path, no role performs another's action | §5 routes and check order (§1.4); examples §7 |
| §5.3 | Edge cases | `bookings_revise_estimate`, `bookings_return_to_technician`, `bookings_mark_parts_ready`, partial `inventory_receive_purchase_order`, `bookings_fail_qc`, 409 `SLOT_FULL`, `bookings_cancel` |
| §5.4 | In-app notifications with unread count | `notifications_*`, `notification.created` (§6) |
| §8.1 | In-app calling (button, popup, states, call log, missed calls) | §4.14 call routes, `call.incoming`/`call.updated` |
| §8.2 | AI Front Desk; SA dashboard with AI summaries and tasks | §4.14 agent routes, `calls_list_shop_calls`, `calls_get_call`, `calls_list_tasks`, `calls_mark_task_done`, `task.created` |
| §9.1 | API documentation (optional) | `/docs`, `/openapi.json` |

### 8.3 Changes to what other specs assumed

| Spec | Assumed | This contract |
|---|---|---|
| 04 | `Cache-Control: no-store` on every response except `/api/v1/public/*` and `/health` (headers table, SEC-32) | Every `/api/*` response and `/health` (D61) — ✅ aligned in spec 04 |
| 04 | Password policy "8–128 characters" (§Password policy) | 12–128 (D10) — ✅ spec 04 says 12–128 everywhere |
| 04 | A customer calling a non-customer slug on their own booking → 403; staff calling `approve-estimate` → 403 | 404: those routes don't exist in that family (§5.1); 403 stays for wrong roles inside a family — ✅ aligned in spec 04 |
| 04 | Login and registration bodies `{access_token, token_type, expires_in, me}` | `{access_token, token_type, expires_in, user}` without memberships; the web calls `GET /api/v1/me` next (D81) — ✅ aligned in spec 04 |
| 04 | WebSocket ticket served by the identity module (Tier 1 table) | The notifications module, which runs the hub (D70) — ✅ aligned in spec 04 |
| 04 | Request-body size cap as a Tier 2 item ("e.g. 1 MiB") | Part of the contract: 64 KiB, 256 KiB for the agent summary route (§1.10) — ✅ aligned in spec 04 (Tier 1) |
| 06 | B4 `GET /api/v1/shops/{shop_id}/ai-call-summaries`; `PATCH …/tasks/{task_id}` `{status: "DONE"}` | `GET …/calls` (+ `GET …/calls/{call_id}` for summary and transcript); `POST …/tasks/{task_id}/mark-done` `{note?}` (spec 05) — ✅ aligned in spec 06 |
| 06 | P7: adjusting below reserved → 422 | 409 `INSUFFICIENT_STOCK` — ✅ aligned in spec 06 |
| 06, 09, 10 | Vehicle field `colour` | `color` (spec 02 column) — ✅ aligned in specs 06, 09 and 10 |
| 07 | Smoke test: `GET /api/v1/public/shops/$SHOP_B` by UUID; `slots[].available`, `.start`; booking `.id`, `.status` | `/api/v1/public/shops/{shop_slug}` (D68); `slots[].remaining`, `.slot_start`; `.booking.id`, `.booking.status` — ✅ aligned in spec 07 (its open question 7) |
| 09, 10 | `GET /api/v1/me` with nested `user {…}` and `shop {…}`, `is_active` per membership | Flat (spec 04): `{id, email, full_name, phone, memberships: [{membership_id, shop_id, shop_name, shop_slug, role, capabilities}]}` — ✅ aligned in specs 09 §2.8 and 10 (E-04) |
| 09 | Field errors `{field or loc, message or msg}` | Always `{field, message, code}` (§2.3) — ✅ aligned in spec 09 §2.9 |
| 09, 10 | UI limits: full name 2–100; notes ≤ 1000; year ≥ 1950; make/model ≤ 50; service name 2–100, description ≤ 500, duration 15–480; capacity ≤ 20; password ≥ 8 | API limits: 1–120; ≤ 2000; ≥ 1900; ≤ 60; 1–120, ≤ 1000, 5–10 080; ≤ 50; ≥ 12. The UI may stay stricter, never looser (password must be ≥ 12) — ✅ spec 09 §2.10 now uses spec 03's limits exactly, and spec 10 follows it |
| 10 | Spec 10 §8.1 renames above (availability slot fields, bare arrays, status-count maps, `stock`, `booking_status`, `picked_by`, call responses) | As listed in §8.1 — ✅ aligned in spec 10 |
| 10 | E-46 stock adjustment (PP-03 dialog, endpoint table) is P1 | P0 (D82) — ✅ aligned in spec 10 |
| 10 | E-05 realtime ticket and the WebSocket are P0 | P1 (D88) — ✅ aligned in spec 10 |
| 11 | Service argument `initial_password` for `add_member` | HTTP field `password` — ✅ spec 11's assumed-functions table now uses the module specs' signatures |
| 12 | API-05 "every list uses the pagination envelope" | Collections use `Page`; bounded lists return `{items}` (§1.6) — ✅ aligned in spec 12 API-05 |
| 12 | † codes | Confirmed: BK-15 404; BK-20 year 1900 … current year + 1; EST-07 422; EST-14 409 `STALE_ESTIMATE`; INV-04 422; INV-07 422 (`exceeds_outstanding`) and 409 `CONFLICT` (already `RECEIVED`); QC-01 422; RPT-03 403; API-05 422 |
| 12 | SM-03 / SEC-07 at the API level | Cells for slugs outside the caller's family are 404 (no route); domain-level SM-03 stays 403 |
| 01 | `GET /api/v1/me` in the shops router | Unchanged; also tagged `shops` (`shops_get_me`, §1.11). The `/api/v1/auth/*` routes stay in the identity router (tag `identity`) and return the token fields + `user`, no memberships (D81) |

---

## 9. Verified facts and sources (checked 2026-10-09)

| Fact used in this spec | Source | How |
|---|---|---|
| A `RequestValidationError` handler customises 422; register the `HTTPException` handler for Starlette's class so internal 404/405 are caught | [FastAPI: Handling errors](https://fastapi.tiangolo.com/tutorial/handling-errors/) | Docs + scratch app: unknown path 404, wrong method 405 with `Allow: GET`, malformed JSON 422 `json_invalid`, `text/plain` and missing content type 422, nested `loc` paths, `extra_forbidden` |
| `redirect_slashes` defaults to `True` (307); `False` gives 404 | [FastAPI reference: FastAPI class](https://fastapi.tiangolo.com/reference/fastapi/) | Docs + executed both settings |
| `strict_content_type` defaults to `True` | same page | Docs + executed |
| `generate_unique_id_function` with `route.tags[0]` and `route.name`; uniqueness is the app's job | [FastAPI: Generate clients](https://fastapi.tiangolo.com/advanced/generate-clients/), [Path operation advanced configuration](https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/) | Docs + executed (`bookings_create_booking`) |
| `include_in_schema=False` | Path operation advanced configuration, "Exclude from OpenAPI" | Docs + executed |
| A response `model` lands under `application/json`; declaring 422 suppresses FastAPI's `HTTPValidationError` | [FastAPI: Additional responses](https://fastapi.tiangolo.com/advanced/additional-responses/) | Docs + executed |
| Overriding `app.openapi` with a cached `custom_openapi()` | [FastAPI: Extending OpenAPI](https://fastapi.tiangolo.com/how-to/extending-openapi/) | Docs + executed (4xx schemas moved to `application/problem+json`) |
| List query parameters need `Query()`; `?status=A&status=B` | [FastAPI: Query parameters and string validations](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/) | Docs + executed; `limit=101` and `offset=-1` → 422 |
| Router dependencies run before body validation (404/403 beat 422), malformed JSON fails first | FastAPI 0.143.0 | Executed |
| `WebSocketException(code=WS_1008_POLICY_VIOLATION)` in dependencies, before `accept()` | [FastAPI: WebSockets](https://fastapi.tiangolo.com/advanced/websockets/) | Docs; executed on uvicorn 0.54: close before accept → HTTP 403 handshake failure; TestClient → `WebSocketDisconnect(1008)`; accept then close → 1008 |
| Close code 1006 = abnormal closure without a close frame, e.g. a failed handshake; 1008 = policy violation | [MDN CloseEvent.code](https://developer.mozilla.org/en-US/docs/Web/API/CloseEvent/code) | Docs (spec 09 also verified 1006 with Node 24's WHATWG `WebSocket`) |
| uvicorn `ws_ping_interval` 20 s, `ws_ping_timeout` 20 s by default | uvicorn 0.54.0 `Config` signature | Executed |
| `ServerErrorMiddleware` is always the outermost layer | [Starlette: Middleware](https://www.starlette.dev/middleware/) | Docs + executed: a 500 left without `Cache-Control` and `X-Request-ID` when they were added by user middleware |
| No general request-body limit in Starlette (multipart only) | Starlette 1.7.0 source (`formparsers.py`, `requests.py`) | Read source |
| `Decimal`, `datetime`, `UUID` are strings in JSON mode; `Decimal` accepts int, float and str | [Pydantic: Standard library types](https://pydantic.dev/docs/validation/latest/api/pydantic/standard_library_types/) | Docs + executed: `Decimal("16100")` → `"16100"` (hence `Money`); UTC datetime → `"2026-10-16T05:00:00Z"`; `6500.5` accepted |
| Problem members, `about:blank`, extension members ignored by clients, `status` must match | [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html) §3.1–§3.2, §4.2.1 | Docs |
| 401 needs `WWW-Authenticate`; 405 needs `Allow`; reason phrases "Content Too Large" (413), "Unprocessable Content" (422); `Retry-After` | [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html) §15.5.2, §15.5.6, §15.5.14, §15.5.21, §10.2.3 | Docs |
| openapi-fetch parses every error body with `JSON.parse`, whatever its media type | openapi-fetch 0.17.0 `dist/index.mjs` | Read source. Whether the generated error *types* pick up `application/problem+json` content is checked by the WEB-07 contract test (unverified here) |

## Dependencies

- **Depends on:** the brief; [00-overview.md](00-overview.md); [18-glossary.md](18-glossary.md) (§3–§11); [17-decisions.md](17-decisions.md) (D7–D10, D14, D16–D21, D23–D47, D61–D71, D73, D76, D77, D79–D84, D86, D88); [08-booking-state-machine.md](08-booking-state-machine.md) (rules, guards, error order, `allowed_actions`, metadata); [01-architecture.md](01-architecture.md) (layers, routers, events incl. `BookingPartsChanged`, after-commit pushes, middleware); [02-data-model.md](02-data-model.md) (columns, lengths, constraint names, derived values); [04-auth-and-security.md](04-auth-and-security.md) (auth flows, RBAC, rate limits, WebSocket ticket); [05-calling-and-ai-front-desk.md](05-calling-and-ai-front-desk.md) (every bonus route and schema).
- **Used by:** every `modules/*.md`; [09-frontend-and-ux.md](09-frontend-and-ux.md) and [10-screens.md](10-screens.md) (generated types, field names); [06-workflows.md](06-workflows.md); [07-deployment-and-docs.md](07-deployment-and-docs.md) (smoke test, OpenAPI export); [11-seed-data.md](11-seed-data.md) (the seed calls the services behind these routes); [12-quality-and-testing.md](12-quality-and-testing.md) (API, SEC, BK, EST, INV, QC, NOT, RPT and the † codes); 14, 15.

## Open questions

1. ✅ **Resolved by D81: where the auth routes live.** `/api/v1/auth/*` belong to the `identity` module (tag `identity`); login and owner registration return `{access_token, token_type, expires_in, user}` (`SessionRead`) and set the cookie, with no memberships. The web calls `GET /api/v1/me` right after (spec 09 §2.8); that route is served and tagged by `shops` (`shops_get_me`, §1.11, §4.3, §4.4).
2. **Booking-creation idempotency.** Should `POST /api/v1/bookings` honour an `Idempotency-Key` header (in memory for 10 minutes, keyed with the e-mail or user), so a retry after a lost response can't create a second booking (spec 09 open question 8)? Cheap; P1 if wanted.
3. **Membership items carry no city, logo or timezone.** Spec 04's flat six fields leave the switcher's city (spec 10 S-01) and the POS time zone to `GET /api/v1/shops/{shop_id}`. Adding `shop_city` and `shop_timezone` would save a request per shop; it needs spec 04 to agree.
4. ✅ **Resolved in spec 12: bounded lists.** API-05 now says "collections" use the pagination envelope and bounded lists return `{items}` (§1.6, §8.3).
5. ✅ **Resolved in spec 12: `/health`.** API-01 exempts `/health`'s 503, whose body is `HealthRead`, not problem+json. The body itself is D84's `{"status": "degraded", "database": "error"}`, which specs 07 and 12 (API-01, API-08) now quote too.
6. ✅ **Resolved by D82: stock adjustments are P0** — the only way to enter opening stock (D44) and to correct drift (D71); below `reserved` or below 0 → 409 `INSUFFICIENT_STOCK` (§4.10). Spec 10 now agrees (§8.3).
7. ✅ **Resolved by D83: partial PO receipts push `booking.updated`.** A receipt that reserves stock for a `PARTS_ORDERED` booking without completing it writes no booking event, but the bookings module publishes `BookingPartsChanged` and the notifications module pushes `booking.updated` with the unchanged `version` (§5.3, §6.4; spec 01).

## Proposed glossary additions

| Kind | Proposal |
|---|---|
| Wire enums | `BookingActionSlug` (the 25 slugs of §4, incl. `edit-estimate`; item type of `allowed_actions`); `StockState` = `OK`, `LOW`, `OUT` (computed: `OUT` when available = 0, `LOW` when available ≤ `reorder_level`) |
| Response schemas | `Problem`, `ValidationProblem`, `FieldError`, `Page`, `ItemList`, `UserRef`, `MemberRef`, `BookingRef`, `PartRef`, `PartStockRef`, `PurchaseOrderRef`, `UserRead` (D81), `MeRead`, `MembershipRead`, `SessionRead`, `ShopPublicSummary`, `ShopPublicDetail`, `SlotRead`, `AvailabilityRead`, `ShopRead`, `WorkingHoursRead`, `ServiceRead`, `MemberRead`, `MemberCreatedRead`, `VehicleRead`, `VehicleBrief`, `BookingServiceRead`, `EstimateSummary`, `PartsSummary`, `BookingSummary`, `BookingDetail`, `CustomerBookingSummary`, `CustomerBookingDetail`, `BookingCreatedRead`, `BookingEventRead`, `CustomerBookingEventRead`, `StatusCountsRead`, `EstimateRead`, `EstimateLineRead`, `EstimateEditRead`, `CustomerEstimateRead`, `CustomerEstimateLineRead`, `PartRead`, `StockMovementRead`, `StockAdjustmentRead`, `BookingPartRead`, `BookingPartsRead`, `PurchaseOrderSummary`, `PurchaseOrderRead`, `PurchaseOrderItemRead`, `PurchaseOrderReceiveRead`, `QcChecklistTemplateItem`, `QcChecklistItemRead`, `QcInspectionRead`, `QcIssueRead`, `NotificationRead`, `UnreadCountRead`, `RealtimeTicketRead`, `OverviewRead`, `OwnerShopSummary`, `OwnerSummaryRead`, `HealthRead` |
| Request schemas | `SessionCreate`, `OwnerRegistrationCreate`, `BookingCreate`, `CustomerWrite`, `VehicleWrite`, `ShopCreate`, `ShopUpdate`, `WorkingHoursWrite`, `WorkingHoursUpdate`, `MemberCreate`, `MemberUpdate`, `ServiceCreate`, `ServiceUpdate`, `PartCreate`, `PartUpdate`, `StockAdjustmentCreate`, `PurchaseOrderCreate`, `PurchaseOrderReceive`, `EstimateUpdate`, `EstimateLineWrite`, `QcChecklistItemWrite`; booking-action bodies named `<PascalCaseSlug>Request` (`ConfirmRequest` … `ReassignPartsPersonRequest`) plus `CustomerCancelRequest` |
| Response fields | `account_created`, `is_bookable`, `has_future_bookings`, `open_jobs`, `service_names`, `status_changed_at`, `estimate_summary`, `parts_summary`, `line_count`, `open_qc_issues_count`, `qc_round`, `last_event`, `estimate_revision_in_progress`, `cancelled_by_customer`, `by_customer`, `booking_version`, `created_new_version`, `outstanding_qty`, `shortage_qty`, `on_order`, `stock_state`, `receive_parts_applied`, `round` (QC inspection), `stock_value`, `needs_sa_action`, `in_progress` |
| Request fields | `expected_received_qty` (PO receipt); `slot_start`/`slot_end` in availability slots |
| Query parameters | `q`, `city`, `date`, `date_from`, `date_to`, `status`, `sort`, `active`, `unread_only`, `include_inactive`, `stock_state`, `role`, `is_active`, `booking_id`, `technician_user_id`, `parts_person_user_id` |
| Field error codes (§2.3) | `invalid_reference`, `not_whole_rupees`, `not_on_grid` (working-hours times only), `invalid_range`, `hours_not_on_grid`, `duplicate`, `not_allowed`, `missing_shortage`, `below_shortage`, `not_short`, `exceeds_outstanding`, `nothing_to_receive`, `checklist_incomplete`, `checklist_item_failed`, `unchanged` |
| `INVALID_SLOT` reason codes (§2.3) | ✅ merged (glossary §10): `off_grid`, `in_past`, `beyond_horizon`, `closed_day`, `outside_hours` |
| OpenAPI conventions | Tag = the module whose router serves the route (`identity` for `/auth/*`, `shops` for `/me`, D81), plus `system` for `/health`; `operationId = <tag>_<function name>` (customer action routes `bookings_my_<slug>`); 4xx/5xx documented as `application/problem+json` |
| Problem members | `type` always `about:blank`; `title` = HTTP reason phrase; `instance` = request path |
| Headers | `WWW-Authenticate: Bearer` on 401, `Retry-After` on 429, `Allow` on 405 |
| Realtime | Server frame `{"type": "pong", "data": {}}` |
| Limits | Request body ≤ 64 KiB (≤ 256 KiB for the agent summary route) → 413 `PAYLOAD_TOO_LARGE` |
| Glossary §10 wording | ✅ merged (glossary change log 2026-10-09 "API contract"): `INSUFFICIENT_STOCK` (stock adjustment below `reserved` or 0), `CONFLICT` (`order-parts` with nothing short; receiving a `RECEIVED` PO), `CONCURRENT_UPDATE` (`expected_received_qty` mismatch), `NOT_FOUND` (unknown path or an action slug outside the caller's endpoint family) |
| Capabilities (glossary §2.4) | ✅ merged: `tasks.manage` is present only when the bonus calls module is enabled (§3.2) |
| Auth paths (glossary §9) | ✅ merged: `/api/v1/auth/*` is the identity module; login returns token + user, then the web calls `GET /api/v1/me` (D81) |
