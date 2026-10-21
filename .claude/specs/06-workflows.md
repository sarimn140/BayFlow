# 06 — Workflows

**Status:** Draft

## Purpose

End-to-end user journeys for every BayFlow role: the screens each person passes through, the booking action (slug) or endpoint each click calls, the status that results, the side effects and notifications it causes, and the errors the UI must handle. It also turns the brief's worked example (§6) into a click-by-click script, scripts every edge case of §5.3 and the security checks, and gives the judge demo path that proves the core Definition of Done (§7.8) plus the optional video storyboard (§9.1).

This spec is the reference for the frontend (specs 09, 10), the Playwright smoke test and the worked-example API test (spec 12), and demo day. Rules (who may do what, from which status, with which side effects) come from [08-booking-state-machine.md](08-booking-state-machine.md); names from [18-glossary.md](18-glossary.md); interpretations from [17-decisions.md](17-decisions.md). If this spec ever disagrees with them, they win and this spec is corrected.

## Shared conventions

### IDs used in this spec

- Journey IDs (C1–C8, O1–O8, S1–S9, T1–T7, P1–P8, Q1–Q5, E1–E7, SEC1–SEC3, B1–B4) are local to this spec.
- Spec 08 rules are cited as **T01–T22** (transitions, two digits) and **"spec 08 O1–O5"** (operations).
- Priorities are always written **"priority P0/P1/P2"** so they never clash with the Parts journeys P1–P8.
- `BF-SEEDnn` references are the seeded sample bookings from [11-seed-data.md](11-seed-data.md).

### Action buttons

1. A booking action button is rendered **only when its slug is in `allowed_actions`** of the booking payload the screen last fetched. The UI never re-derives rules from status or role (spec 08, `allowed_actions`).
2. Three actions are not called through `/actions/{slug}`: `edit-estimate` (listed in `allowed_actions`, saved with `PUT /api/v1/shops/{shop_id}/bookings/{booking_id}/estimate`), `CREATE` (the wizard, `POST /api/v1/bookings`) and `RECEIVE_PARTS` (fired by `POST /api/v1/shops/{shop_id}/purchase-orders/{po_id}/receive`).
3. Data guards (stock, QC checklist, empty estimate) are not pre-evaluated in `allowed_actions`. The UI uses helper fields such as `parts_summary.all_available` to highlight the right button and shows the server's message when a guard fails.
4. Non-booking controls are shown **only from the `capabilities`** of the caller's membership in that shop, returned by `GET /api/v1/me` (D66, glossary §2.4): shop settings `shop.manage`, team `team.manage`, services `services.manage`, parts catalogue `parts.manage`, stock (new PO, receive, adjust stock) `stock.manage`, bonus tasks `tasks.manage`. The UI never derives them from the role name; the server re-checks every call.
5. Every booking action request carries `expected_version` = the `version` the screen rendered. A mismatch returns 409 `CONCURRENT_UPDATE` (D30); the UI refetches and says "This booking was just updated — check and try again". This also makes double clicks harmless.
6. Actions that bind someone or cannot be undone (`decline`, `cancel`, `approve-estimate`, `reject-estimate`, `fail-qc`, `allocate-parts`, `complete`) open a confirm dialog. Reason/note fields follow the limits in spec 08.

### Audit trail

- Every transition and operation writes exactly one `booking_events` row (who, role, when, from, to, action, note, metadata) — T01–T22 and spec 08 O2–O5. `EDIT_ESTIMATE` writes a row only when it creates a new estimate version (spec 08 O1).
- Stock and purchase-order changes that do not move the booking (e.g. a partial PO receipt) are recorded in `stock_movements` and on the PO, not as booking events. They still push `booking.updated` to the booking's viewers when they change its parts state (D83).
- The staff booking detail shows the full event log (actor name + role chip, from → to, note, time). The customer sees a reduced timeline (C4).

### Notifications and live updates

- Notification types, triggers and recipients are exactly glossary §6. **In-app always**, under the bell with an unread count. E-mail is an **optional** extra (priority P1) for `ESTIMATE_SENT` and `VEHICLE_READY` only, sent when an e-mail provider is configured (D26: an HTTPS e-mail API in production, because Railway Hobby blocks outbound SMTP; Mailpit locally; `none` disables it) and never to reserved/test TLDs such as `.test`. No journey depends on an e-mail arriving: the bell and the booking page are the source of truth. "SAs of the shop" = all active Service Advisors; if none, the Owner.
- After commit the API pushes `notification.created` to the recipient and `booking.updated` to the booking's customer and the shop members who can see the booking under D21 (glossary §11) — after every booking event, and also after a parts change that writes no event, such as a partial PO receipt reserving stock for the booking (D83). Open lists and details refetch on `booking.updated`; the bell refetches on `notification.created`. Every client also polls the unread count and the current view every 15 s (D14). **"Appears for X"** in this spec means it arrives through these pushes within about a second, or at the next 15 s poll. The pushes need the WebSocket layer, which is priority P1 (D88); with the P0 build alone every journey here still works, and "appears" means "at the next 15 s poll".
- Clicking a notification opens its server-computed `link` — the deep link into the right surface for that recipient (D67), e.g. the Customer booking detail for a customer, the technician's job page for a technician — and marks it read.

### Areas, login and roles

- The **area** decides the actor: the customer area calls `/api/v1/me/...`, the POS calls `/api/v1/shops/{shop_id}/...` (spec 08 "Who is the actor?"). A staff member who books their own car acts as a customer on that booking.
- One login page for everyone. `POST /api/v1/auth/login` returns only the token and the user (`{access_token, token_type, expires_in, user}`) and sets the cookie; it carries no memberships (D81). The web app then calls `GET /api/v1/me` and routes from its memberships (spec 09 `resolveHome`): a user with at least one active membership lands in the POS (shop picker, or their only shop); everyone else lands on My bookings. Owner sign-up works the same way (D81). The account menu links both areas when both apply.
- **Fresh customers.** Wherever a journey or the demo script says "fresh e-mail", use an unused `.test` address such as `ahmed1@bayflow.test` (add a number or your initials if it is taken). The project `Email` type accepts `.test` (D62) and the e-mail sender never mails reserved TLDs (D26), so no real inbox is ever contacted — unlike the brief's `ahmed@mail.com`, which belongs to a real mail provider and is not seeded (D51). Passwords are 12–128 characters (D10).
- Times are shown in the shop's timezone (`Asia/Karachi`); money in **whole rupees** (PKR, no paisa; line totals rounded half-up; `Intl.NumberFormat('en-PK', { style: 'currency', currency: 'PKR' })`, D41). Staff see status chips with the staff labels and customers see the customer-facing labels (both in glossary §3). This spec writes statuses by their value (`PARTS_ORDERED`) for precision.

### Error handling (UI)

| Response | UI behaviour |
|---|---|
| 401 `UNAUTHENTICATED` | Go to Login with a return URL; wizard input survives in `sessionStorage` (never the password, spec 09 R9) |
| 401 `INVALID_CREDENTIALS` | Inline "E-mail or password is incorrect" |
| 403 `FORBIDDEN`, `NOT_ASSIGNED` | Toast "You can't do this on this booking"; refetch (the button disappears) |
| 404 `NOT_FOUND` | `NotFoundState` ("We couldn't find that. It may have been removed, or you may not have access.") with a link home — same page for "doesn't exist" and "other shop", so existence never leaks. On a POS shop route the UI also refetches `GET /api/v1/me`; once a deactivated membership drops out, ShopScope shows its not-found state and the shop disappears from the switcher (spec 09) |
| 409 `INVALID_TRANSITION`, `CONCURRENT_UPDATE` | Refetch; toast "This booking was just updated by someone else" |
| 409 `SLOT_FULL` | Wizard goes back to the Time step (C2) |
| 409 `EMAIL_ALREADY_REGISTERED` | Password-field error + "Log in" (C3, O1) |
| 409 `ALREADY_PICKED` | Toast "Another inspector already picked this job"; queue refreshes (Q2) |
| 409 `STALE_ESTIMATE` | Refetch; the current revision is shown (C5) |
| 409 `ESTIMATE_LOCKED` | Refetch; the editor becomes read-only |
| 409 `INSUFFICIENT_STOCK` | Show which part is short; suggest Order / Receive (P3, P6). From Adjust stock: the adjustment would take `on_hand` below `reserved` or below zero (P7) |
| 409 `CONFLICT` | Inline message from the problem `detail` (duplicate SKU, existing membership, "all parts available — use mark-parts-ready", slot duration or timezone change blocked by future bookings — D37) |
| 422 `VALIDATION_ERROR`, `INVALID_SLOT`, `ESTIMATE_EMPTY`, `MEMBER_NOT_ELIGIBLE` | Field-level errors or inline message |
| 429 `RATE_LIMITED` | "Too many attempts — try again in a minute"; inputs kept |
| 500 `INTERNAL_ERROR` | Generic error with Retry; no internals |

### Screens referenced

Routes follow the canonical route list in [09-frontend-and-ux.md](09-frontend-and-ux.md) (§2.3 and its glossary-additions table); [10-screens.md](10-screens.md) owns the full screen definitions. Public pages address a shop by its **slug** (web `/shops/[slug]`, `/book/[slug]`; API `/api/v1/public/shops/{shop_slug}`), staff pages by its UUID (D68). `/pos/shops/{shop_id}` redirects to the caller's role home.

| Screen (name used in this spec) | Route | Used by |
|---|---|---|
| Landing | `/` | public |
| Shop page | `/shops/{slug}` | public |
| Booking wizard (steps: Services → Time → Details → Review) | `/book/{slug}?step=…` (D68) | public, customer |
| Booking confirmation | `/book/confirmed/{booking_id}` | customer |
| Login (shows demo credentials as plain text, D52) | `/login` | everyone |
| Owner sign-up | `/register` | public |
| My bookings | `/bookings` | customer |
| Customer booking detail | `/bookings/{booking_id}` | customer |
| Shop picker (POS hub) | `/pos` | staff, owner |
| Create shop | `/pos/shops/new` | any logged-in user (D17) |
| Multi-shop summary *(priority P1)* | `/pos/summary` | owner |
| Overview | `/pos/shops/{shop_id}/overview` | owner |
| Bookings board | `/pos/shops/{shop_id}/bookings` | SA, owner |
| Staff booking detail — one booking, role-specific panels (estimate editor, parts panel, QC panel) | SA/Owner `/pos/shops/{shop_id}/bookings/{booking_id}`; technician `/pos/shops/{shop_id}/jobs/{booking_id}`; parts `/pos/shops/{shop_id}/parts/{booking_id}`; QC `/pos/shops/{shop_id}/qc/{booking_id}` | all staff |
| My jobs | `/pos/shops/{shop_id}/jobs` | technician (owner read-only) |
| Parts queue | `/pos/shops/{shop_id}/parts` | parts person (owner read-only) |
| Inventory | `/pos/shops/{shop_id}/inventory` | parts person, owner |
| Purchase orders / PO detail and receive | `/pos/shops/{shop_id}/purchase-orders`, `/pos/shops/{shop_id}/purchase-orders/{po_id}` (spec 10 PP-04, PP-05) | parts person (owner read-only) |
| QC queue | `/pos/shops/{shop_id}/qc` | QC inspector (owner read-only) |
| Team | `/pos/shops/{shop_id}/team` | owner |
| Services | `/pos/shops/{shop_id}/services` | owner |
| Shop settings (details, working hours, slots) | `/pos/shops/{shop_id}/settings` | owner |
| Notifications | bell dropdown | every logged-in user |
| Calls & tasks *(bonus)* | `/pos/shops/{shop_id}/calls` | SA, owner |

---

## 1. Customer journeys

### C1 · Browse and filter shops

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Landing | Open `/` → `GET /api/v1/public/shops` | — | Hero + grid of listed shops that have at least one active service (D64): logo or initials (D55), name, city, rating (★ 4.7, or "New" when NULL — D56), services offered (chips) | Empty directory → "No shops yet" |
| 2 | Landing | Choose a city (list from `GET /api/v1/public/cities`) and/or type a search → `GET /api/v1/public/shops?city=Lahore&q=brake` | — | Grid filters; filters live in the URL query (shareable, back-button safe) | No match → "No shops match — clear filters" |
| 3 | Shop page | Click a card → `/shops/{slug}` → `GET /api/v1/public/shops/{shop_slug}` | — | Address, phone, working hours, services (duration; "from PKR 1,000" or "Price after inspection" when the base price is NULL), "Book a service" | Unknown or unlisted shop → 404 page. Shop with no active service (absent from the directory, D64; reachable only by a direct link) → "Not taking online bookings yet", no Book button (T01 needs ≥ 1 service) |

### C2 · Book via the wizard (new account)

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Wizard · Services | Tick one or more services; optional free-text notes (§5.1) | — | Kept in the wizard state (`sessionStorage`, spec 09 R9) | Next disabled with 0 services; server 422 `VALIDATION_ERROR` |
| 2 | Wizard · Time | Pick a date (today … +30 days, closed weekdays disabled) → `GET /api/v1/public/shops/{shop_slug}/availability?date=YYYY-MM-DD` → pick a slot | — | Only slots with free places are offered (§7.3): the API returns `slots: [{slot_start, slot_end, remaining}]` and omits full slots; `remaining` (D68) is shown as "n places left" (D37) | No slot that day (`slots: []`) → "Fully booked — try another day" |
| 3 | Wizard · Details | Full name, e-mail (in demos a fresh `.test` address, e.g. `ahmed1@bayflow.test`, D62), password (12–128 characters, D10), optional phone (D33); vehicle: registration number, make, model, year, optional color (`color`) and mileage (`mileage_km`) | — | Client validation mirrors the API (the UI may be stricter, never looser; spec 03 §8.3) | — |
| 4 | Wizard · Review | Check the summary → **Confirm booking** → `POST /api/v1/bookings` (spec 04 wizard **case B**: no session, new e-mail) | `PENDING` | One transaction (T01): account created; vehicle upserted (D35) and the mileage snapshotted on the booking (`mileage_km`, D65); slot counter +1; booking with reference `BF-XXXXXX`; services snapshotted (D34); `CREATE` event. **The customer is now logged in**: the 201 response sets the session cookie **and** returns `{access_token, token_type, expires_in, account_created, booking}` — the booking (`CustomerBookingDetail`) is nested under `booking` (D32, spec 03 §4.6; the web app relies on the cookie, the token is the Bearer fallback of D7). **`BOOKING_CREATED` → SAs of the shop** | See below |
| 5 | Booking confirmation | The web refetches `GET /api/v1/me` (now logged in) and redirects to `/book/confirmed/{booking_id}` (`booking.id` from the response) → link to the Customer booking detail | `PENDING` ("Booking received") | Reference, shop, slot, vehicle, services; when `account_created` is true, a note that the account was created and that the same e-mail and password log in later | — |

Edge cases:

- **409 `SLOT_FULL`** — someone took the last place after step 2. **Nothing is created, not even the account** (the whole CREATE is one transaction; spec 04 "case B never leaves an orphan account"). The wizard returns to the Time step with "That time was just booked by someone else. Please pick another slot." (spec 09 copy), refetches availability (the slot is no longer listed), clears the time selection and keeps services, notes, personal and vehicle details. Confirming again with another slot succeeds. E5 scripts this with two browsers.
- **422 `INVALID_SLOT`** — the slot started while the user was typing, or the owner changed working hours. Same recovery as `SLOT_FULL`.
- **409 `EMAIL_ALREADY_REGISTERED`** — see C3 (c).
- **429 `RATE_LIMITED`** — retry message; inputs kept.
- Wizard state survives a refresh in `sessionStorage` (`bf:wizard:<slug>`), **never the password** (spec 09 R9); after a refresh the user re-types only the password.

### C3 · Book with an existing account

The variants are spec 04's wizard cases: (a) = case A, (b) = case C, (c) = case D (C2 is case B).

| Variant | What the customer does → API | Result |
|---|---|---|
| (a) Logged in (e.g. Ayesha) | The Details step shows "Booking as Ayesha Khan · ayesha.customer@bayflow.test" and **no password field**; a vehicle picker lists My vehicles (`GET /api/v1/me/vehicles`) plus "Add another vehicle"; phone pre-filled → Confirm → `POST /api/v1/bookings` (the cookie identifies the user) | `PENDING` booking on the same account. Picking a known vehicle reuses it and saves any edited details (D35) |
| (b) Not logged in, existing e-mail, **correct** password | Types the existing e-mail and its password → Confirm | Account reused, booking created, customer logged in (cookie set and token returned, `account_created` = false, D32); My bookings shows old and new bookings. The phone is stored only if the account had none (D33) |
| (c) Not logged in, existing e-mail, **wrong** password (or the account is inactive) | Confirm → **409 `EMAIL_ALREADY_REGISTERED`** | **Nothing is created** (D32, spec 04 SEC-18). The Details step shows "An account with this e-mail already exists." with an inline log-in prompt (spec 09); all inputs are kept; after logging in (`POST /api/v1/auth/login`, then `GET /api/v1/me`, D81) the step switches to variant (a). Five failed password checks for one e-mail in 15 minutes (login and wizard combined) → 429 `RATE_LIMITED` (spec 04) |

### C4 · Track a booking

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | My bookings | Open → `GET /api/v1/me/bookings` | — | Cards: reference, shop, vehicle, slot, status label. Bookings that need the customer are pinned on top with the label as a call to action ("Estimate awaiting your approval", "Ready for pick-up") (§7.3) | None yet → "Book your first service" |
| 2 | Customer booking detail | Open a card → `GET /api/v1/me/bookings/{booking_id}` | — | Status timeline, booking and vehicle details, services, estimate card (once a revision has been sent), action buttons from `allowed_actions` | Someone else's booking → 404 (SM-17) |
| 3 | Same | Wait | (changes) | `booking.updated` refetches the page; the bell shows customer notifications (`BOOKING_CONFIRMED`, `ESTIMATE_SENT`, `VEHICLE_READY`, `BOOKING_CANCELLED`) | Push lost → 15 s poll |

Timeline rules:

- One entry per **status change** (events whose `to_status` differs from `from_status`), labelled with the customer-facing label and the time in the shop's timezone. Operations (`START_REPAIR`, `NOTIFY_READY`, reassignments) and internal notes (inspection notes, QC issue text, repair notes) are not shown. A cancel/decline reason **is** shown to the customer.
- Estimate revisions visible to the customer are only those in `SENT`, `APPROVED` or `REJECTED` (D39). Drafts, submitted and superseded versions stay internal — including a sent revision that became `SUPERSEDED` because the booking was cancelled (T22).
- The QC loop is shown honestly as "Waiting for quality check → Quality check in progress → Repair in progress → Waiting for quality check …", without the issue text.

| Status | Customer-facing label (glossary §3) |
|---|---|
| `PENDING` | Booking received |
| `CONFIRMED` | Booking confirmed |
| `ASSIGNED` | Technician assigned |
| `INSPECTING` | Inspection in progress |
| `ESTIMATE_REVIEW` | Preparing your estimate |
| `AWAITING_CUSTOMER` | Estimate awaiting your approval |
| `ESTIMATE_APPROVED` | Estimate approved |
| `ESTIMATE_REJECTED` | Estimate declined — the shop will follow up |
| `PARTS_PENDING` | Checking parts |
| `PARTS_ORDERED` | Parts ordered |
| `PARTS_READY` | Parts ready |
| `IN_REPAIR` | Repair in progress |
| `QC_PENDING` | Waiting for quality check |
| `QC_IN_PROGRESS` | Quality check in progress |
| `READY_FOR_PICKUP` | Ready for pick-up |
| `COMPLETED` | Completed |
| `CANCELLED` | Cancelled |

### C5 · Approve an estimate

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Customer booking detail (`AWAITING_CUSTOMER`) | Banner "Estimate awaiting your approval" → estimate card: itemised parts (name, qty, unit price, line total), labour lines, parts total, labour total, **grand total**, "Revision n", sent time | — | — | — |
| 2 | Same | **Approve** → dialog "Approve PKR 16,100?" → `POST /api/v1/me/bookings/{booking_id}/actions/approve-estimate` `{estimate_id, expected_version}` | `ESTIMATE_APPROVED` | Revision → `APPROVED` with `decided_at`, `decided_by_user_id` (timestamped in-app acceptance, brief §3; locked afterwards, D39). **`ESTIMATE_APPROVED` → SAs of the shop** | 409 `STALE_ESTIMATE` (the page showed an older revision) → refetch shows the current one; 409 `INVALID_TRANSITION` (decided in another tab, or the shop cancelled) → refetch |

### C6 · Reject an estimate with a reason

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Customer booking detail (`AWAITING_CUSTOMER`) | **Decline estimate** → dialog with optional reason (≤ 500 chars) → `POST /api/v1/me/bookings/{booking_id}/actions/reject-estimate` `{estimate_id, reason, expected_version}` | `ESTIMATE_REJECTED` ("Estimate declined — the shop will follow up") | Revision → `REJECTED`, `decided_at`, `decided_by_user_id`, `customer_note` = reason. **`ESTIMATE_REJECTED` → SAs of the shop** (S4 continues) | Same as C5 |
| 2 | Same | Later | `AWAITING_CUSTOMER` again | When the shop sends a new revision: `ESTIMATE_SENT` → customer; a new approval banner; the card shows "You declined revision n on {time}" under history | — |

### C7 · Cancel a booking (only before `IN_REPAIR`)

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Customer booking detail | **Cancel booking** (shown only while `cancel` is in `allowed_actions`, i.e. the 11 cancellable statuses) → dialog with optional reason → `POST /api/v1/me/bookings/{booking_id}/actions/cancel` `{reason, expected_version}` | `CANCELLED` | T22: every reservation released (`RELEASE` movements); slot counter −1 (the slot is bookable again); non-final estimate revisions → `SUPERSEDED`; linked POs stay open (D24). **`BOOKING_CANCELLED` → SAs of the shop + assigned technician + assigned parts person** | From `IN_REPAIR` on there is no button; the page says "Your car is already being repaired — contact the shop to change anything" (+ Call button, bonus B2). Forced call → 409 `INVALID_TRANSITION`. Parts person allocated while the dialog was open → 409 → refetch |

### C8 · Mark picked up

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Customer booking detail (`READY_FOR_PICKUP`) | Banner "Your vehicle is ready for pick-up" (plus "The shop notified you at {time}" once `ready_notified_at` is set) → **I've collected my vehicle** → `POST /api/v1/me/bookings/{booking_id}/actions/complete` | `COMPLETED` | `completed_at` set (T21). No notification; the SA's board updates through `booking.updated` | SA completed it first at the counter (S7) → 409 `INVALID_TRANSITION` → refetch shows Completed |

---

## 2. Owner journeys

The Owner's management controls (shop settings, team, services, parts catalogue) appear because the Owner's membership carries `shop.manage`, `team.manage`, `services.manage` and `parts.manage` (D66); the Owner has no `stock.manage` (D44).

### O1 · Register and create the first shop

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Owner sign-up | Full name, e-mail, password (12–128 characters, D10), optional phone → `POST /api/v1/auth/register-owner` | — | User created and logged in: the response is `{access_token, token_type, expires_in, user}` + the cookie, with no memberships (D81). The web refetches `GET /api/v1/me` (`memberships: []`) and opens Create shop | 409 `EMAIL_ALREADY_REGISTERED` → "Log in instead". Any logged-in user may create a shop (D17), so an existing customer or staff member logs in and goes to step 2 |
| 2 | Create shop · Details | Name, address, city, phone, optional logo URL (D55); the timezone is shown read-only as `Asia/Karachi` (D38, spec 10) | — | — | 422 field errors |
| 3 | Create shop · Hours & slots | Per weekday open/close or Closed (default Mon–Sat 09:00–18:00, Sunday closed); slot duration in minutes (default 60); slot capacity (default 2) → `POST /api/v1/shops` | — | Shop created (`is_listed` true); the caller gets the shop's `OWNER` membership (D15, D17). It appears on the landing page only once it has an active service (D64). Preview line "Mondays: 09:00, 10:00 … 17:00" (the grid is anchored at local midnight; a slot must end by closing time, D37) | 422 close ≤ open, opening or closing time off the slot grid, duration or capacity out of range (D37). A slug clash is resolved by the server |
| 4 | Overview | Redirected to `/pos/shops/{shop_id}/overview` with a setup checklist: **Add services** (required before the shop is listed and customers can book, D64, T01), Add team, Add parts (catalogue only: every new part starts at `on_hand` 0, and the shop's Parts Person enters the opening stock with **Adjust stock**, P7 — priority P0, D44, D82) | — | — | — |

Later edits in Shop settings (`PATCH /api/v1/shops/{shop_id}`) never move existing bookings (D37):

- **Slot duration** (and `timezone`, which the UI shows read-only) is blocked while the shop has future non-cancelled bookings: the server answers 409 `CONFLICT` and the settings form shows its message (e.g. "This shop has upcoming bookings — the slot length can be changed when none are left"). Either change would move the grid under booked slot counters.
- **Capacity and working hours** can always be changed; existing bookings are kept. Lowering capacity below the places already booked shows the slot as full; closing hours over a booked slot keeps that booking, and the slot is simply no longer offered.

### O2 · Add team members

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Team | Open → `GET /api/v1/shops/{shop_id}/members` | — | Members with role, e-mail, active flag | — |
| 2 | Team · Add member | E-mail, full name, role (`SERVICE_ADVISOR`, `TECHNICIAN`, `PARTS_PERSON`, `QC_INSPECTOR`), initial password (12–128 characters, D10; used only if the e-mail is new) → `POST /api/v1/shops/{shop_id}/members` | — | **New e-mail:** user created with the password the Owner typed; the Owner shares it out of band. **Existing e-mail:** only the membership is added; the existing password is never changed (D18); toast "Linked an existing BayFlow account — they sign in with their own password". The new member's shop switcher lists this shop | 409 `CONFLICT` already a member of this shop (one role per shop, D15 — change the role instead); 422 role `OWNER` not allowed; 422 password policy for a new e-mail |

Worked example step 0 ("adds Bilal (SA), Imran (Technician), Sara (QC), Usman (Parts)") is exactly this journey; on the live site it is already done by the seed (spec 11).

### O3 · Edit, deactivate, reactivate a member

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Team | Change role → `PATCH /api/v1/shops/{shop_id}/members/{membership_id}` `{role}` | — | Takes effect on the member's next request (D9). Bookings already assigned stay assigned (D19); the SA moves them with S9 | The `OWNER` row has no controls; a forced call is rejected (403 `FORBIDDEN`) |
| 2 | Team | **Deactivate** → confirm → `PATCH …/members/{membership_id}` `{is_active: false}` | — | **Immediate** (D9, D20): the member's next request to this shop returns 404; once `me` is refetched the shop drops out of their memberships, ShopScope shows its not-found state and the switcher no longer lists it (spec 09). They can still log in (they may be a customer, spec 04); their other shops and their own customer bookings are unaffected. They stop receiving "SAs of the shop" / QC notifications and realtime events (recipients are resolved from active memberships). Their assigned bookings stay assigned and get an "Assignee inactive" badge on the SA board → S9 | — |
| 3 | Team | **Reactivate** → `PATCH …` `{is_active: true}` | — | Immediate; the same session works again without logging in | — |

### O4 · Configure the services catalogue

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Services | Add → name, description, estimated duration (minutes), base price (optional; blank shows "Price after inspection") → `POST /api/v1/shops/{shop_id}/services` | — | Appears in the wizard of this shop only | 409 `CONFLICT` duplicate name in this shop; 422 field errors |
| 2 | Services | Edit or deactivate → `PATCH /api/v1/shops/{shop_id}/services/{service_id}` | — | Deactivated services leave the wizard; existing bookings keep their snapshot (D34) | Deactivating the last active service removes the shop from the public directory (D64); a direct link shows "Not taking online bookings yet" (C1) |

### O5 · Create a second shop and use the shop switcher

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Any POS page | Shop switcher (header) lists every active membership as "Shop · Role" → **+ Create another shop** → O1 steps 2–3 → `POST /api/v1/shops` | — | New shop with its own empty team, services, inventory, slots and bookings (§7.2); not in the public directory until it has an active service (D64) | — |
| 2 | Any POS page | Pick the other shop in the switcher | — | `{shop_id}` in the URL changes; every list reloads for that shop. Nothing is shared between the shops except the Owner; a member of shop A appears in shop B only if added there, possibly with a different role (D15) | Old shop URL bookmarked by a member who was removed → 404 |

Seeded example: Fatima owns **Lahore Auto Care** and **Raza Auto Works** (spec 11).

### O6 · Per-shop overview

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Overview | Open → `GET /api/v1/shops/{shop_id}/overview` | — | Bookings by status (`status_counts` as `[{status, count}]`; click → Bookings board filtered), today's appointments, team list (role, active), inventory summary (parts, low, out, open POs), recent activity (§7.4 Owner) | Priority P1: a multi-shop summary across all owned shops |

### O7 · Open the other role views read-only (D16)

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Owner nav → Technician view / Parts view / QC view | Open → same list endpoints as the role (the Owner sees all shop bookings, D21) | — | Technician view: bookings in `ASSIGNED`, `INSPECTING`, `IN_REPAIR` grouped by technician. Parts view: parts queue for all parts persons + Inventory + Purchase orders. QC view: queue, in progress, history. **No action buttons**: the Owner's `allowed_actions` never contain technician, parts or QC slugs (spec 08), so Start inspection, Order missing parts, Mark parts ready, Allocate, Pick and Pass/Fail never render. Stock buttons (New PO, Receive, Adjust stock) are hidden because the Owner's membership has no `stock.manage`; parts catalogue editing (add/edit part, cost, reorder level) stays available through `parts.manage` (D44, D66) | Forced API call (e.g. `start-inspection`, `pick-qc`, `allocate-parts`) → 403 `FORBIDDEN` (SM-16) |

### O8 · Perform Service Advisor actions

The Owner uses the same screens and calls as S1–S9; events record `actor_role` = `OWNER`. Notifications meant for "SAs of the shop" reach the Owner only when the shop has no active Service Advisor (D26).

---

## 3. Service Advisor journeys

### S1 · Triage a `PENDING` booking

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Bookings board | `BOOKING_CREATED` in the bell / "Pending" filter chip → `GET /api/v1/shops/{shop_id}/bookings?status=PENDING` | — | List with status filters (§7.4) | — |
| 2 | Staff booking detail | Review customer, vehicle, services, notes, slot → **Confirm** → `POST /api/v1/shops/{shop_id}/bookings/{booking_id}/actions/confirm` | `CONFIRMED` | `BOOKING_CONFIRMED` → customer | Another SA confirmed first → 409 `INVALID_TRANSITION` or `CONCURRENT_UPDATE` → refetch |
| 2′ | Same | **Decline** → reason (1–500, required) → `…/actions/decline` `{reason}` | `CANCELLED` | T03: `cancelled_at`, `cancelled_by_user_id`, `cancel_reason`; slot counter −1. `BOOKING_CANCELLED` → customer (sees "Cancelled" + reason) | 422 without a reason |

### S2 · Assign a technician

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Staff booking detail (`CONFIRMED`) | **Assign technician** → dropdown of active technicians of this shop → `…/actions/assign-technician` `{technician_user_id}` | `ASSIGNED` | `technician_user_id` set. **`TECHNICIAN_ASSIGNED` → that technician**; the job appears in their My jobs. Customer: "Technician assigned" | 422 `MEMBER_NOT_ELIGIBLE` (deactivated meanwhile) → dropdown refreshes |

### S3 · Review, edit (new version) and send the estimate

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Staff booking detail (`ESTIMATE_REVIEW`) | `ESTIMATE_SUBMITTED` in the bell → estimate panel: revision 1 (`SUBMITTED`, by the technician), inspection notes, lines with live stock (available + Low/Out badge) | — | — | — |
| 2 | Estimate editor | Optional **Edit** → change lines (e.g. labour 4,000 → 3,500) → Save → `PUT /api/v1/shops/{shop_id}/bookings/{booking_id}/estimate` | `ESTIMATE_REVIEW` | First SA save creates **revision 2 (`DRAFT`, author SA)** and marks revision 1 `SUPERSEDED` → one `EDIT_ESTIMATE` event; later saves update that draft (no event). Totals recomputed on the server (D39, D40) | 422 line validation; 409 `ESTIMATE_LOCKED` if the status changed |
| 3 | Same | **Send to customer** → `…/actions/send-estimate` | `AWAITING_CUSTOMER` | Latest revision → `SENT` (`sent_at`, `sent_by_user_id`). **`ESTIMATE_SENT` → customer** (in-app; + optional e-mail, D26) | 422 `ESTIMATE_EMPTY` |

The SA cannot approve on the customer's behalf: `approve-estimate` is customer-only (spec 08). A phone "yes" is not an approval — the customer's own timestamped click is (brief §3).

### S4 · Handle a rejected estimate

`ESTIMATE_REJECTED` arrives with the customer's reason. The booking shows three buttons (`revise-estimate`, `return-to-technician`, `cancel`) — D23. With the bonus enabled, the SA can call the customer first (B1).

| # | Path | User action → API | Status after | Side effects · notifications |
|---|---|---|---|---|
| a | Revise myself | **Revise estimate** → `…/actions/revise-estimate` → edit in the editor (`PUT …/estimate`) → **Send** (`send-estimate`) | `ESTIMATE_REVIEW` → `AWAITING_CUSTOMER` | T10: new `DRAFT` revision n+1 copied from the rejected one (author SA); edits update it without new events. `ESTIMATE_SENT` → customer |
| b | Back to the technician | **Return to technician** → note for the technician → `…/actions/return-to-technician` `{note}` | `INSPECTING` | T11: new `DRAFT` copy for the technician. `ESTIMATE_RETURNED` → technician; continues at T4 → S3 |
| c | Cancel | **Cancel booking** → reason (required) → `…/actions/cancel` `{reason}` | `CANCELLED` | T22 side effects; `BOOKING_CANCELLED` → customer |

### S5 · Assign a parts person

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Staff booking detail (`ESTIMATE_APPROVED`) | `ESTIMATE_APPROVED` in the bell → **Assign parts person** → dropdown of active parts persons → `…/actions/assign-parts-person` `{parts_person_user_id}` | `PARTS_PENDING` | T12: `booking_parts` created from the **approved** revision's `PART` lines (quantities summed per part). **`PARTS_NEEDED` → that parts person**. Customer: "Checking parts" | 422 `MEMBER_NOT_ELIGIBLE`. Labour-only job (no part lines): still assigned (D31); the panel says "No parts on this job — the parts person confirms and allocates" |

### S6 · Notify the customer that the vehicle is ready

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Bookings board → "Ready for pick-up" | `QC_PASSED` in the bell → booking → **Notify customer** → `…/actions/notify-ready` | `READY_FOR_PICKUP` (unchanged) | Spec 08 O3: `ready_notified_at` = now; event. **`VEHICLE_READY` → customer** (in-app; + optional e-mail, D26) | Repeatable: the button becomes "Notify again" with the last time (D27) |

### S7 · Complete the booking

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Staff booking detail (`READY_FOR_PICKUP`) | Customer collects the car at the counter → **Complete** → `…/actions/complete` | `COMPLETED` | `completed_at` (T21) | Customer already marked pick-up (C8) → 409 `INVALID_TRANSITION` → refetch |

### S8 · Cancel a booking

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Staff booking detail (any of the 11 cancellable statuses) | **Cancel booking** → reason (1–500, required) → `…/actions/cancel` `{reason}` | `CANCELLED` | T22: reservations released, slot freed, non-final revisions `SUPERSEDED`, linked POs stay open (D24). **`BOOKING_CANCELLED` → customer** | From `IN_REPAIR` on: no button; forced call → 409 `INVALID_TRANSITION` |

### S9 · Reassign (priority P1)

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Staff booking detail (`ASSIGNED`, `INSPECTING`, `IN_REPAIR`) | **Reassign technician** → `…/actions/reassign-technician` `{technician_user_id}` | unchanged | Spec 08 O4: the draft estimate stays; the previous technician loses visibility (404 for them, D21). **`TECHNICIAN_ASSIGNED` → new technician** | 422 `MEMBER_NOT_ELIGIBLE` (same person, inactive, wrong role) |
| 2 | Staff booking detail (`PARTS_PENDING`, `PARTS_ORDERED`, `PARTS_READY`) | **Reassign parts person** → `…/actions/reassign-parts-person` `{parts_person_user_id}` | unchanged | Spec 08 O5. **`PARTS_NEEDED` → new parts person** | Same |

Main use: a member was deactivated mid-job (D19).

---

## 4. Technician journeys

### T1 · See assigned jobs only

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | My jobs | Open → `GET /api/v1/shops/{shop_id}/bookings` (the server returns only bookings with `technician_user_id` = me, D21) | — | Groups: **To inspect** (`ASSIGNED`, `INSPECTING`); **In repair** (`IN_REPAIR`, with a "QC failed" badge when an `OPEN` QC issue exists); **Waiting on others** (`ESTIMATE_REVIEW` … `PARTS_READY`, `QC_PENDING`, `QC_IN_PROGRESS`); **Done** (`READY_FOR_PICKUP`, `COMPLETED`, `CANCELLED`) | Another technician's booking URL → 404 (D21) |

### T2 · Start the inspection

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Staff booking detail (`ASSIGNED`) | `TECHNICIAN_ASSIGNED` in the bell → vehicle, services, customer notes → **Start inspection** → `…/actions/start-inspection` | `INSPECTING` | T05: a `DRAFT` revision 1 exists (created if none). Customer: "Inspection in progress" | BayFlow does not block actions before the appointment time, so demos run in minutes |

### T3 · Build the estimate (stock visible) and submit

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Estimate editor | **Add part** → search the shop's active parts; each result shows **available** (`on_hand − reserved`) with Out/Low badge (D40, D45) → quantity (integer ≥ 1), unit price in whole rupees (defaults to the part's unit cost, editable, D41) | `INSPECTING` | An out-of-stock part can still be added; hint "Not in stock — the parts person will order it" (P4) | Inactive part → 422 |
| 2 | Same | **Add labour** → description, quantity (hours, or 1 for a flat fee), unit price in whole rupees → Save → `PUT /api/v1/shops/{shop_id}/bookings/{booking_id}/estimate` (the body may also carry the draft `inspection_notes`, D40) | `INSPECTING` | Lines replaced; totals computed by the server (line totals rounded half-up to whole rupees, D41) and shown back. No booking event (spec 08 O1) | 1–50 lines; quantity ranges per spec 08 → 422 |
| 3 | Same | Inspection notes → **Submit to SA** → `…/actions/submit-estimate` `{inspection_notes}` | `ESTIMATE_REVIEW` | T06: revision → `SUBMITTED`; `inspection_notes` saved. **`ESTIMATE_SUBMITTED` → SAs of the shop**. Editor becomes read-only for the technician. Customer: "Preparing your estimate" | 422 `ESTIMATE_EMPTY`; later edits → 409 `ESTIMATE_LOCKED` |

### T4 · Revise after "return to technician"

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | My jobs → To inspect | `ESTIMATE_RETURNED` in the bell with the SA's note → booking (`INSPECTING`) with a new `DRAFT` copied from the rejected revision | `INSPECTING` | The customer's reason and the SA's note are shown above the editor | — |
| 2 | Estimate editor | Edit lines (e.g. cheaper part) → Save (`PUT …/estimate`) → **Submit to SA** (`submit-estimate`) | `ESTIMATE_REVIEW` | `ESTIMATE_SUBMITTED` → SAs; continues at S3 | As T3 |

### T5 · Start the repair

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | My jobs → In repair | `PARTS_READY` in the bell ("Parts allocated") → booking → **Start repair** → `…/actions/start-repair` | `IN_REPAIR` (unchanged) | Spec 08 O2: `repair_started_at` = now; event | Not required before `send-to-qc` (no guard), but shown first. Repeatable each round |

### T6 · Send to QC

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Staff booking detail (`IN_REPAIR`) | **Send to QC** → optional repair notes → `…/actions/send-to-qc` `{repair_notes}` | `QC_PENDING` | T17: open QC issues → `RESOLVED`; `qc_inspector_user_id` cleared. **`QC_REQUESTED` → every active QC inspector of the shop**. Job moves to Waiting on others; customer "Waiting for quality check" | — |

### T7 · Fix after a QC failure and resubmit

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | My jobs → In repair ("QC failed" badge) | `QC_FAILED` in the bell → booking shows the QC issue card (title, description, inspector, time) | `IN_REPAIR` | The job came back to the **same** technician (D47) | — |
| 2 | Same | Fix → optional **Start repair** again → **Send to QC** with "what I fixed" → `send-to-qc` | `QC_PENDING` | Issue → `RESOLVED` (`resolved_by_user_id` = technician); `QC_REQUESTED` → every active QC inspector of the shop (Sara and Hina at Lahore Auto Care); continues at Q5 | — |

---

## 5. Parts Person journeys

Order missing parts, Mark parts ready and Allocate are booking actions (from `allowed_actions`). Catalogue buttons (Add part, Edit) need `parts.manage`; stock buttons (New PO, Receive, Adjust stock) need `stock.manage`, which only the Parts Person has (D44, D66).

### P1 · View inventory

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Inventory | Open → `GET /api/v1/shops/{shop_id}/parts` | — | Table: SKU, name, unit cost, on hand, reserved, **available**, reorder level, badge — **OUT** when available = 0, **LOW** when available ≤ reorder level (D45; OUT wins), "On order n" from open POs (`stock_state`, `on_order`). Filters All / Low / Out (`?stock_state=LOW`, `?stock_state=OUT`; repeatable) (§7.4) | — |
| 2 | Inventory → part | Open a part → `GET /api/v1/shops/{shop_id}/parts/{part_id}/movements` | — | Ledger of `RECEIVE`, `RESERVE`, `RELEASE`, `CONSUME`, `ADJUST` with links to bookings/POs | — |

### P2 · Jobs awaiting parts — required vs available

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Parts queue | `PARTS_NEEDED` in the bell → `GET /api/v1/shops/{shop_id}/bookings?status=PARTS_PENDING&status=PARTS_ORDERED&status=PARTS_READY` (only bookings with `parts_person_user_id` = me, D21) | — | One card per job | — |
| 2 | Staff booking detail → Parts panel | Open a job → `GET /api/v1/shops/{shop_id}/bookings/{booking_id}/parts` | — | Per part: **required**, reserved for this job, **available** in stock, **short**; linked POs with status. Hint `parts_summary.all_available` highlights Mark parts ready vs Order missing parts (§7.6 "required parts compared to stock automatically") | — |

### P3 · All parts in stock → mark parts ready

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Parts panel (`PARTS_PENDING`, nothing short) | **Mark parts ready** → `…/actions/mark-parts-ready` | `PARTS_READY` | T14: everything outstanding reserved (`RESERVE` movements; `reserved` up, `on_hand` unchanged). Customer: "Parts ready" | 409 `INSUFFICIENT_STOCK` (stock reserved by another job meanwhile) → panel refreshes → P4 |

### P4 · Shortage → order parts

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Parts panel (`PARTS_PENDING`, something short) | **Order missing parts** → dialog pre-filled with the shortages (quantity ≥ shortage, may be more; optional supplier name) → `…/actions/order-parts` `{items: [{part_id, quantity}], supplier_name}` | `PARTS_ORDERED` | T13: parts that are available now are **reserved immediately**; a PO `PO-XXXXXX` (`ORDERED`, linked to the booking) covers the shortages. No notification (glossary §6). Customer: "Parts ordered" | 409 `CONFLICT` when nothing is short ("all parts available — use mark-parts-ready"); 422 quantity below shortage |

### P5 · Receive a PO — partially, then fully

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Purchase orders → PO detail | **Receive** → quantity per item (≤ outstanding) → `POST /api/v1/shops/{shop_id}/purchase-orders/{po_id}/receive` `{items: [{item_id, quantity, expected_received_qty?}]}` — **partial** | **`PARTS_ORDERED` (unchanged)** | T15 side effects: `RECEIVE` movements (`on_hand` up); received quantity reserved for the linked booking first — only while that booking is `PARTS_ORDERED` (D43); PO → `PARTIALLY_RECEIVED`; response `receive_parts_applied: false`. No booking event (brief §5.3 "partial parts delivery"), but `booking.updated` is pushed so the parts panel and the SA board refresh at once (D83) | 422 quantity above outstanding (`exceeds_outstanding`) or all zero; 409 `CONCURRENT_UPDATE` when `expected_received_qty` no longer matches (a duplicated receipt); 409 `CONFLICT` when the PO is already `RECEIVED` |
| 2 | Same | **Receive** the rest | **`PARTS_READY`** | When every `booking_parts` row is fully reserved, **`RECEIVE_PARTS`** fires in the same transaction (booking event, actor = this parts person; response `receive_parts_applied: true`, new status in `purchase_order.booking.status`). PO → `RECEIVED` (or stays `PARTIALLY_RECEIVED` if it also holds extra items not yet received). Excess quantity becomes general available stock | Any active parts person of the shop may receive (T15). PO linked to a cancelled booking → general stock only, no transition (D24) |

`MARK_PARTS_READY` also works from `PARTS_ORDERED` when stock arrived another way (e.g. a general restock, P8).

### P6 · Allocate parts → repair starts

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Parts panel (`PARTS_READY`) | **Allocate parts** → confirm (lists what will be consumed) → `…/actions/allocate-parts` | `IN_REPAIR` | T16: `CONSUME` movements (`on_hand` and `reserved` both down); `booking_parts.consumed_qty` = required. **`PARTS_READY` → assigned technician**. Customer: "Repair in progress" | 409 `INSUFFICIENT_STOCK` if any reservation is incomplete |

### P7 · Manage the parts catalogue

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Inventory | **Add part** (Parts Person or Owner, `parts.manage`) → SKU (unique per shop), name, unit cost (whole rupees), reorder level → `POST /api/v1/shops/{shop_id}/parts` | — | Part with `on_hand` 0 — the form has no quantity field; new parts always start at 0 (D44). The Parts Person then enters the opening stock with **Adjust stock** (row 3) | 409 `CONFLICT` duplicate SKU |
| 2 | Inventory → part | Edit name/cost/reorder level or deactivate → `PATCH /api/v1/shops/{shop_id}/parts/{part_id}` | — | Inactive parts cannot be added to new estimate lines; existing lines are unaffected | — |
| 3 | Inventory → part | **Adjust stock** (priority P0, D82: the only way to enter opening stock for a new part — a separate action after the part is created — and to correct drift, D71) → delta + reason → `POST /api/v1/shops/{shop_id}/parts/{part_id}/adjustments` `{quantity_delta, reason}` | — | `ADJUST` movement (actor = this Parts Person); response `{part, movement}` | A delta that would drop `on_hand` below `reserved` or below zero → 409 `INSUFFICIENT_STOCK`; the dialog shows on hand, reserved and the lowest allowed value. Parts Person only (`stock.manage`, D44, D66): the Owner may edit the catalogue but never sees Adjust stock; a forced call → 403 `FORBIDDEN` |

### P8 · General restock PO

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Purchase orders | **New PO** → parts (Low/Out pre-selected), quantities, supplier → `POST /api/v1/shops/{shop_id}/purchase-orders` `{supplier_name, items: [{part_id, quantity, unit_cost?}]}` (no booking; `unit_cost` defaults to the part's cost) | — | PO `ORDERED`; "On order" shown on those parts | 422 empty items |
| 2 | PO detail | **Receive** (P5) | — | Stock up; Low/Out badges clear when available rises above the reorder level | — |

---

## 6. QC Inspector journeys

### Q1 · The shared QC queue

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | QC queue | `QC_REQUESTED` in the bell → `GET /api/v1/shops/{shop_id}/bookings?status=QC_PENDING&status=QC_IN_PROGRESS` (D21: QC sees these statuses shop-wide, plus bookings they inspected before) | — | **Waiting** cards (oldest first): reference, vehicle, technician, waiting since, "Re-test #n" with the previous issue; **In progress** (mine with buttons; others' without); **History** | — |

### Q2 · Pick a job (first wins)

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | QC queue | **Pick** → `…/actions/pick-qc` | `QC_IN_PROGRESS` | T18: `qc_inspector_user_id` = me; `qc_inspections` row (`picked_at`). The card leaves the other inspectors' Waiting list (`booking.updated`). Customer: "Quality check in progress" | Second inspector clicking a stale card → **409 `ALREADY_PICKED`** → toast + refresh (FAQ "first to pick locks it", SM-06). The booking's own technician can never pick (D47 → 403) |

### Q3 · Pass with the checklist

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | Staff booking detail → QC panel | Tick every checklist item (D46: road test, no warning lights, no leaks, fluid levels, customer complaint resolved) + notes → **Pass** → `…/actions/pass-qc` `{checklist, notes}` | `READY_FOR_PICKUP` | T19: inspection `PASS`, `completed_at`, checklist and notes stored; `qc_inspector_user_id` is kept as the record of who passed it (D47). **`QC_PASSED` → SAs of the shop**. Customer: "Ready for pick-up" | Any item unticked → 422 ("use Fail QC"). Only the picker has buttons; others → 403 `NOT_ASSIGNED` |

### Q4 · Fail with an issue

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | QC panel | **Fail QC** → issue title (1–120), description (1–2000), an optional checklist (when sent, all five D46 items with their pass/fail values, spec 03 §5.2; a partial list → 422 `checklist_incomplete`) and notes → `…/actions/fail-qc` `{issue_title, issue_description, checklist, notes}` | `IN_REPAIR` | T20: inspection `FAIL` (checklist stored when given, D46); `qc_issues` row `OPEN`; picker cleared (D47), so any inspector may take the re-test; job returns to the **same** technician. **`QC_FAILED` → technician**. Customer: "Repair in progress" | 422 missing title/description |

### Q5 · Re-test

| # | Screen | User action → API | Status after | Side effects · notifications | Edge cases / errors |
|---|---|---|---|---|---|
| 1 | QC queue | After T7 the card is back as "Re-test #2" with the resolved issue → **any** inspector picks (D47) → Q3 or Q4 | `QC_IN_PROGRESS` → … | Each round has its own `qc_inspections` row; unlimited rounds (§5.3) | — |

---

## 7. The worked example in UI terms (brief §6)

Same steps and numbers as the trace in spec 08. On the live site **step 0 is done by the seed** (spec 11): Lahore Auto Care, Fatima, Bilal, Imran, Sara, Usman (plus Hamza and Hina), services, and stock **oil filter 10, engine oil 4 L 8, ignition coil 0**. "Ahmed" is created live by the wizard — use a fresh `.test` e-mail such as `ahmed1@bayflow.test` and a password of 12+ characters ("Fresh customers" above; spec 11, judge notes); `ahmed@mail.com` is not seeded (D51). Because `.test` addresses are never e-mailed (D26), Ahmed's notifications in this replay are in-app only. Browser profiles A–D are defined in §10.

| Step | Actor (profile) | Screen → click → API | Status after | Appears for others | Effects (estimate · stock) |
|---|---|---|---|---|---|
| 0 | Fatima (B) | *Seeded.* Live alternative: O1 + O2 with a **different shop name** (a second "Lahore Auto Care" would confuse other testers) | — | — | 1 shop, 5 memberships in the brief (7 seeded) |
| 1 | Ahmed (A) | Landing → sees the 6 seeded shops → (city filter "Lahore") → **Lahore Auto Care** card | — | — | — |
| 2 | Ahmed (A) | **Book a service** → Services: tick "Check engine light" + "Oil change"; notes "Light came on yesterday, car vibrates at idle." | — | — | — |
| 3 | Ahmed (A) | Time: the coming **Friday → 10:00** (if it shows no places left, another Friday or time — D71) → Details: name Ahmed, fresh `.test` e-mail (e.g. `ahmed1@bayflow.test`), a 12+ character password, plate `LEA-1234`, Honda Civic 2016 → Review → **Confirm booking** → `POST /api/v1/bookings` | `PENDING` | **Bilal**: bell +1 `BOOKING_CREATED` ("New booking BF-XXXXXX — Honda Civic, Fri 10:00"); row appears under Pending | Account created, Ahmed logged in (cookie set; the body returns `access_token`, `token_type`, `expires_in`, `account_created` = true and the new booking under `booking`, D32); slot counter Fri 10:00 +1 |
| 4 | Bilal (B) | Bell → booking → **Confirm** (`confirm`) → **Assign technician: Imran** (`assign-technician`) | `CONFIRMED` → `ASSIGNED` | **Ahmed**: `BOOKING_CONFIRMED`, timeline "Booking confirmed", "Technician assigned". **Imran**: `TECHNICIAN_ASSIGNED`; job under To inspect | 2 events |
| 5 | Imran (C) | My jobs → booking → **Start inspection** (`start-inspection`) → editor: + Ignition coil ×1 @ 6,500 (badge **OUT**, available 0), + Oil filter ×1 @ 900 (available 10), + Engine oil 4 L ×1 @ 5,200 (available 8), + Labour 1 × 4,000 → Save (`PUT …/estimate`) → notes "Faulty ignition coil" → **Submit to SA** (`submit-estimate`) | `INSPECTING` → `ESTIMATE_REVIEW` | **Ahmed**: "Inspection in progress", "Preparing your estimate". **Bilal**: `ESTIMATE_SUBMITTED` | Revision 1 `SUBMITTED`, total **16,600** |
| 6 | Bilal (B) | Booking → estimate panel → **Edit** labour 4,000 → **3,500** → Save (`PUT …/estimate`) → **Send to customer** (`send-estimate`) | `AWAITING_CUSTOMER` | **Ahmed**: `ESTIMATE_SENT` in the bell (an e-mail too only when e-mail is configured and the address is deliverable, D26), banner "Estimate awaiting your approval" | Revision 2 (author Bilal) `SENT`, total **16,100**; revision 1 `SUPERSEDED` |
| 7 | Ahmed (A) | **Logs out and back in** with the wizard e-mail and password (proves §7.1 customer login; login returns the token and user, then `GET /api/v1/me` shows no membership, so he lands on My bookings — D81) → banner → estimate (coil 6,500; filter 900; oil 5,200; labour 3,500; **total PKR 16,100**, Revision 2) → **Approve** (`approve-estimate` `{estimate_id}`) | `ESTIMATE_APPROVED` | **Bilal**: `ESTIMATE_APPROVED` | Revision 2 `APPROVED` with `decided_at` |
| 8 | Bilal (B) | Booking → **Assign parts person: Usman** (`assign-parts-person`) | `PARTS_PENDING` | **Usman**: `PARTS_NEEDED`; job in Parts queue. **Ahmed**: "Checking parts" | `booking_parts`: coil 1, filter 1, oil 1 |
| 9 | Usman (D) | Parts queue → booking: coil required 1 / available 0 / **short 1**; filter 1 / 10; oil 1 / 8 → **Order missing parts** (dialog: coil ×1) → `order-parts` | `PARTS_ORDERED` | **Ahmed**: "Parts ordered" (no notification by design) | Filter 10/1, oil 8/1 reserved (on hand/reserved); PO `PO-XXXXXX` `ORDERED` for 1 coil |
| 10 | Usman (D) | "Next day": Purchase orders → that PO → **Receive** coil ×1 (`POST …/purchase-orders/{po_id}/receive`) → booking → **Allocate parts** (`allocate-parts`) | `PARTS_READY` → `IN_REPAIR` | **Ahmed**: "Parts ready", "Repair in progress". **Imran**: `PARTS_READY`; job under In repair | Coil 1/1 after receipt (PO `RECEIVED`); after allocation filter **9/0**, oil **7/0**, coil **0/0** |
| 11 | Imran (C) | Booking → **Start repair** (`start-repair`) → **Send to QC** (`send-to-qc`) | `QC_PENDING` | **Sara + Hina**: `QC_REQUESTED`; card in QC queue. **Ahmed**: "Waiting for quality check" | `repair_started_at` set |
| 12 | Sara (D) | QC queue → **Pick** (`pick-qc`) → road test → untick "No leaks" → **Fail QC** with issue "Oil leak at filter" / "Minor oil leak at the oil filter seal found on the road test." (`fail-qc`) | `QC_IN_PROGRESS` → `IN_REPAIR` | **Imran**: `QC_FAILED`; job back under In repair with the issue card. **Ahmed**: "Quality check in progress", then "Repair in progress" | Inspection 1 `FAIL`; issue `OPEN` |
| 13 | Imran (C) | Fixes the seal → **Send to QC** ("Replaced the filter seal; no leak after 10 min idle") | `QC_PENDING` | **Sara + Hina**: `QC_REQUESTED`; card shows "Re-test #2" | Issue `RESOLVED` |
| 14 | Sara (D) | **Pick** → tick every checklist item → **Pass** (`pass-qc`) | `QC_IN_PROGRESS` → `READY_FOR_PICKUP` | **Bilal**: `QC_PASSED`; booking under Ready for pick-up. **Ahmed**: timeline "Ready for pick-up" (D27) | Inspection 2 `PASS` |
| 15 | Bilal (B) | Booking → **Notify customer** (`notify-ready`) | `READY_FOR_PICKUP` | **Ahmed**: `VEHICLE_READY` "Your vehicle is ready for pick-up" in the bell (+ optional e-mail, D26) | `ready_notified_at` set |
| 16 | Ahmed (A) | **I've collected my vehicle** (`complete`) — or Bilal clicks **Complete** at the counter | `COMPLETED` | **Bilal**: booking moves to Completed | `completed_at`; **21 booking events** in total (22 if Imran also clicks Start repair in round 2) |

**Bonus path at step 6 (priority P2, spec 05):** Bilal is busy, and Ahmed presses **Call the shop** on his booking page. No SA answers within `AI_RING_TIMEOUT_SECONDS` (20), so the AI Front Desk joins the call. It identifies Ahmed (logged-in caller, or by name, phone, e-mail or booking reference), reads his booking through internal tools scoped to him, and tells him the estimate of PKR 16,100 is waiting for his approval in the portal. It never invents data. After the call, Bilal gets the summary (intent, details, sentiment) and an `OPEN` task, "Customer Ahmed asked about estimate; reminded to approve in the portal", linked to the booking and the call log (`CALL_MISSED`, `AI_TASK_CREATED` → SAs). Journey B3.

---

## 8. Edge-case journeys (brief §5.3)

### E1 · Estimate rejected — both revise paths (D23)

Setup: a booking in `AWAITING_CUSTOMER` — seeded **BF-SEED02** (Ayesha, revision 2 sent, PKR 12,000) or your own replay at step 7.

| # | Actor | Action | Status after | Notes |
|---|---|---|---|---|
| 1 | Customer | **Decline estimate** with reason "Labour seems high" (`reject-estimate`) | `ESTIMATE_REJECTED` | Revision 2 `REJECTED` + note; Bilal gets `ESTIMATE_REJECTED` with the reason |
| 2a | Bilal | **Revise estimate** (`revise-estimate`) → labour 3,000 → 2,500 → Save → **Send** | `ESTIMATE_REVIEW` → `AWAITING_CUSTOMER` | Revision 3 `DRAFT` (copy, author Bilal) → `SENT` at PKR 11,500; customer gets `ESTIMATE_SENT` |
| 2b | Bilal → Imran | **Return to technician** with note "Customer asks for an aftermarket link" (`return-to-technician`) → Imran edits (link 4,500 → 3,800 each) → **Submit** → Bilal **Send** | `INSPECTING` → `ESTIMATE_REVIEW` → `AWAITING_CUSTOMER` | Imran gets `ESTIMATE_RETURNED`; Bilal gets `ESTIMATE_SUBMITTED`; revision 3 `SENT` |
| 3 | Customer | **Approve** the new revision | `ESTIMATE_APPROVED` | An old tab approving revision 2 → 409 `STALE_ESTIMATE` (SM-14). Staff history: revisions with status, author, total, decision time (the customer sees only sent, approved and rejected revisions, D39) |
| 2c | Bilal | Or **Cancel booking** with a reason | `CANCELLED` | Customer gets `BOOKING_CANCELLED` |

Automated: SM-08 (revise), SM-09 (return to technician).

### E2 · Parts already in stock

1. Book "Oil change" only (fresh customer). Bilal confirms and assigns Imran; Imran's estimate has oil filter ×1, engine oil 4 L ×1, labour → submit; Bilal sends; customer approves; Bilal assigns Usman.
2. Usman's Parts panel shows nothing short (`parts_summary.all_available`) → **Mark parts ready** → `PARTS_PENDING` → **`PARTS_READY` directly, no PO** (brief: "skip ordering").
3. **Allocate** → `IN_REPAIR`. Clicking Order missing parts here instead → 409 `CONFLICT` "all parts available — use mark-parts-ready".

### E3 · Partial delivery

Seeded **BF-SEED03** (Kamran's Honda City, `PARTS_ORDERED`): front brake pads 1 and brake fluid 1 are reserved; the linked PO orders **2 front brake discs** (stock 0).

| # | Actor | Action | PO | Booking | Front brake disc (on hand/reserved) |
|---|---|---|---|---|---|
| 1 | Usman | Receive **1** disc | `PARTIALLY_RECEIVED` | **stays `PARTS_ORDERED`**, parts panel "1 of 2 reserved" (no booking event; `booking.updated` refreshes open views, D83) | 1/1 |
| 2 | Usman | Receive the **2nd** disc | `RECEIVED` | `RECEIVE_PARTS` → **`PARTS_READY`** | 2/2 |
| 3 | Usman | **Allocate** | — | `IN_REPAIR`; Imran gets `PARTS_READY` | 0/0 (pads 2/1 → 1/0, fluid 7/1 → 6/0) |

Automated: SM-12.

### E4 · QC failure loop, twice

Setup: seeded **BF-SEED05** (Nadia's Yaris, `QC_PENDING`, technician Imran) or any job sent to QC.

1. Sara **Pick** → **Fail QC** with issue "Misfire under load" / "Hesitation above 3,000 rpm on the road test." → `IN_REPAIR`; Imran gets `QC_FAILED`.
2. Imran **Send to QC** ("Reseated plug lead on cylinder 2") → `QC_PENDING`; issue 1 `RESOLVED`.
3. Hina **Pick** (any inspector may re-test) → **Fail QC** with issue "Engine cover rattle" / "Cover not clipped after repair; rattles at idle." → `IN_REPAIR`.
4. Imran **Send to QC** → issue 2 `RESOLVED`.
5. Sara **Pick** → all checks pass → **Pass** → `READY_FOR_PICKUP`.

Result: 3 `qc_inspections` rows (FAIL, FAIL, PASS), 2 issues `RESOLVED`, and the event log shows each round. Automated: SM-10.

### E5 · Slot conflict — two browsers, last place

Setup: a slot with exactly one place left (capacity 2). Seeded **BF-SEED01** holds one of the two places at its slot (spec 11); or book any slot once first.

1. Profiles A and E (both logged out, two fresh `.test` e-mails, e.g. `race1@bayflow.test` and `race2@bayflow.test`) open Lahore Auto Care → same services → **the same date and time** (both show "1 place left", i.e. `remaining` = 1) → Details → Review.
2. Profile A clicks **Confirm** → 201, `PENDING`.
3. Profile E clicks **Confirm** → **409 `SLOT_FULL`** → the wizard returns to the Time step; the slot is gone from the list; E's inputs are kept. No account was created for E's e-mail.
4. Profile E picks the next hour → 201.

The race is safe even with truly simultaneous clicks: the counter row is locked (`SELECT … FOR UPDATE`, D37). Automated: SM-07.

### E6 · Cancellation

**(a) By the customer in `PARTS_ORDERED`** — replay the worked example to step 9 (filter 10/1, oil 8/1, coil PO `ORDERED`), then:

| # | Actor | Action | Result |
|---|---|---|---|
| 1 | Customer | **Cancel booking** (reason optional "Car sold") | `CANCELLED`; Bilal, Imran and Usman get `BOOKING_CANCELLED` |
| 2 | — | Check Inventory | Reservations released: filter **10/0**, oil **8/0** (`RELEASE` movements) |
| 3 | — | Check the wizard | The Friday 10:00 place is bookable again (slot counter −1) |
| 4 | Usman | Purchase orders | The coil PO **stays `ORDERED`** (D24). If received later, the coil becomes **general stock** (no reservation, no transition) |
| 5 | Customer | Try to cancel a booking in `IN_REPAIR` | No button; API 409 `INVALID_TRANSITION` |

Caution for shared demo data (accepted drift, D71): receiving that orphan PO leaves an ignition coil in stock, so the next worked-example replay takes the "parts already in stock" path for the coil. Usman can set it back to 0 with **Adjust stock** (P7) while no job has reserved it (otherwise 409 `INSUFFICIENT_STOCK`). Re-running the seed does **not** undo this — it never touches stock (D60). See spec 11, judge notes.

**(b) By the SA in `PENDING` (decline)** — book with a fresh customer, then Bilal **Decline** with reason "Both bays are booked that morning — please choose Saturday" → `CANCELLED`, slot freed, the customer gets `BOOKING_CANCELLED` and sees "Cancelled" with the reason. Seeded evidence: **BF-SEED09**.

Automated: SM-11.

### E7 · Labour-only job (D31)

1. Book "Wheel alignment". Imran's estimate has only `LABOUR` lines (e.g. "Four-wheel alignment" 1 × 2,000) → submit → send → approve.
2. Bilal assigns Usman (still required). Usman sees "No parts on this job" → **Mark parts ready** (nothing reserved) → **Allocate** (nothing consumed) → `IN_REPAIR`. No shortcut transition exists.

Seeded evidence: **BF-SEED04** (already `IN_REPAIR`; its history shows `MARK_PARTS_READY` and `ALLOCATE_PARTS` with zero parts). Automated: SM-13.

---

## 9. Security journeys (for the demo)

Swagger UI is at `<api-url>/docs`. Call `POST /api/v1/auth/login` (the response is `{access_token, token_type, expires_in, user}`, D81), copy `access_token`, then **Authorize** with it (Bearer, D8); `GET /api/v1/me` then lists the account's memberships and capabilities. IDs come from URLs in the POS or from `GET /api/v1/public/shops`.

### SEC1 · Tenant isolation (§7.1 acceptance)

| # | Who | Action | Expected |
|---|---|---|---|
| 1 | Bilal (Lahore Auto Care) | Swagger: `GET /api/v1/shops/{clifton_car_clinic_id}/bookings` | **404 `NOT_FOUND`** — no membership in that shop (D20) |
| 2 | Bilal | Browser: paste a Clifton booking URL copied from profile E (`sa.clifton-car-clinic@bayflow.test`, e.g. BF-SEED12): `/pos/shops/{clifton_car_clinic_id}/bookings/{booking_id}` | Not-found state — Bilal has no membership there (ShopScope, spec 09) |
| 3 | Bilal | Edit the URL to his own shop with the Clifton booking ID: `/pos/shops/{lahore_auto_care_id}/bookings/{clifton_booking_id}` | Not-found state; the API returns 404 because the booking query is scoped by `shop_id` (composite FKs back this up) |
| 4 | Fatima (owns two shops) | Same Clifton URL | Not-found state — owning shops grants nothing elsewhere |
| 5 | Ayesha (customer) | `/bookings/{ahmed_booking_id}` | Not-found state; API 404 (SM-17) |

### SEC2 · Role isolation

| # | Who | Call | Expected |
|---|---|---|---|
| 1 | Imran (technician) | `POST /api/v1/shops/{lac_id}/bookings/{his_booking_id}/actions/confirm` (any of his jobs, e.g. BF-SEED04) | **403 `FORBIDDEN`** — role check comes before status (glossary §10 check order) |
| 2 | Imran | `…/{BF-SEED05}/actions/pick-qc` | 403 `FORBIDDEN` (not QC) |
| 3 | Fatima (owner) | `…/actions/start-inspection`, `…/actions/allocate-parts`, `…/actions/pick-qc` | 403 `FORBIDDEN` (D16, SM-16) |
| 4 | Hamza (other technician) | `…/{BF-SEED04}/actions/send-to-qc` (Imran's job) | 404 — not visible to him (D21) |
| 5 | Hina (QC) | `…/actions/pass-qc` on a job Sara picked | 403 `NOT_ASSIGNED` |
| 6 | Ayesha (customer token) | `POST /api/v1/shops/{lac_id}/bookings/{BF-SEED02}/actions/send-estimate` | 404 — customers have no membership |

In the UI none of these buttons ever appear; the calls above prove the server enforces it. Automated: SM-03, SM-04, SM-16.

### SEC3 · Deactivated staff blocked immediately

1. Profile E: log in as **Hamza** (`hamza.tech@bayflow.test`), open My jobs.
2. Profile B: **Fatima** → Team → Hamza → **Deactivate**.
3. Profile E: Hamza clicks anything → API 404 → not-found state; after `me` is refetched, Lahore Auto Care is gone from his switcher (he has no other shop, so `/pos` offers "create a shop"). No re-login is needed to prove it: the same token is re-checked against the database on every request (D9), and he receives no further realtime events.
4. Fatima → **Reactivate** → Hamza's next click works with the same session.

Never deactivate the shared cast accounts (Bilal, Imran, Sara, Usman) on the live site: other judges use them. Use Hamza or Hina, and reactivate afterwards. If a demo account is broken anyway (deactivated, re-roled, password changed), re-running the seed repairs it: every run — including the pre-deploy run of each redeploy — reactivates the demo users and memberships, restores their canonical roles and makes `BayFlow@2026` work again, without touching bookings, stock, POs or shop settings (D60, spec 11).

---

## 10. Judge demo script (~10 minutes)

### Browser profiles

The session cookie `bf_session` belongs to the web origin and is shared by every tab and window of the same browser profile. Logging in as Bilal in a second tab logs the customer out of the first. Use one **browser context per person**:

| Profile | Browser context (suggestion) | Logged in as | Used for |
|---|---|---|---|
| **A · Customer** | Chrome, normal window | the fresh customer (created by the wizard) | Customer steps |
| **B · Front desk** | Chrome **Incognito** window | Bilal → later Fatima | SA and Owner steps |
| **C · Workshop** | Firefox, normal window | Imran | Technician steps |
| **D · Back office** | Firefox **Private** window | Usman → later Sara (log out/in) | Parts and QC steps |
| **E · Spare** *(optional)* | Edge, Chrome Guest, or a second Chrome profile | Hina, Hamza, or `sa.clifton-car-clinic@bayflow.test` | QC race, deactivation, tenant isolation |

All Incognito windows of one Chrome profile share one cookie jar, and so do all Firefox Private windows. Firefox Multi-Account Containers give each container tab its own jar, which is an alternative to separate browsers. The minimum is two contexts (customer + staff, switching staff accounts by logging out and in — the DEP-09 checklist in spec 12); four contexts make the 10-minute run realistic and let each person watch notifications arrive.

**Before starting the clock (1 min):** open A–D; log B in as Bilal, C as Imran, D as Usman (credentials are on the login page and in the README). As Usman, glance at Inventory: oil filter and engine oil available, ignition coil 0 (spec 11 judge notes cover the other cases).

**Shared live data.** Every judge works on the same live database, and BayFlow never resets it per judge (D71, D52):

- Replays consume Lahore Auto Care stock and fill Friday 10:00 (capacity 2). If Friday 10:00 is full, take the next Friday or another time. If the ignition coil is already in stock, Usman can **Adjust stock** back to 0 (P7; possible only while no job has reserved it — otherwise 409 `INSUFFICIENT_STOCK`) or the run simply takes the "parts already in stock" path (E2).
- Seeded `BF-SEEDnn` bookings move forward once someone acts on them and stay moved; for a guaranteed clean run, replay the worked example with a fresh customer.
- Demo **accounts**, by contrast, are repaired by re-running the seed (every redeploy runs it): demo users and memberships active again, canonical roles back, password `BayFlow@2026` valid (D60). It never touches bookings, stock, POs or shop settings.
- Automated smoke checks book only at Lyallpur Motors, the smoke-test shop (spec 11), so their `smoke+…@bayflow.test` bookings never appear at Lahore Auto Care.

### Script

| Time | Profile | Do this | Proves |
|---|---|---|---|
| 0:00–1:30 | A | Landing → 6 shops, filter "Lahore" → Lahore Auto Care → wizard: Check engine light + Oil change + notes → coming **Friday 10:00** (if full, next Friday) → Ahmed, **fresh `.test` e-mail** (e.g. `ahmed1@bayflow.test`), a 12+ character password, `LEA-1234` Honda Civic 2016 → Confirm → "Booking received" (now logged in) | §5.1 journey, slot picker, account created by booking |
| 1:30–2:00 | B | Bell (1) → **Confirm** → **Assign Imran** | `PENDING` → `CONFIRMED` → `ASSIGNED`; notifications to the customer and technician |
| 2:00–3:00 | C | **Start inspection** → add coil (OUT badge), filter, oil, labour 4,000 → total 16,600 → **Submit** | Technician estimate with live stock |
| 3:00–3:30 | B | **Edit** labour 3,500 → revision 2 (16,100) → **Send** | SA edit creates a version |
| 3:30–4:30 | A, B | A: **log out and back in** with the wizard credentials → banner → **Decline estimate** ("please re-check labour"). B: **Revise estimate** → send revision 3 unchanged (16,100). A: **Approve** revision 3 | Customer login (§7.1), **estimate-rejected path** (§7.8), versioning |
| 4:30–4:45 | B | **Assign Usman** | `PARTS_PENDING` |
| 4:45–5:45 | D | Parts queue → coil short → **Order missing parts** → Purchase orders → **Receive** 1 → booking `PARTS_READY` → **Allocate** | Shortage → PO → receipt (stock +1) → allocation (stock −3) |
| 5:45–6:15 | C | **Start repair** → **Send to QC** | `IN_REPAIR` → `QC_PENDING`; `QC_REQUESTED` reaches every QC inspector (Sara and Hina) |
| 6:15–7:15 | D, C | D: log out, log in **Sara** → QC queue → **Pick** → **Fail QC** with issue "Oil leak at filter". C: **Send to QC** again. D: **Pick** → tick all → **Pass** | **QC fail loop** (§7.8) |
| 7:15–7:45 | B, A | B: **Notify customer**. A: bell "ready" → **I've collected my vehicle** → `COMPLETED`; show the customer timeline and estimate history (v2 declined, v3 approved). B: the staff booking detail shows the full history, including v1 `SUPERSEDED` and every event (customers only see sent, approved and rejected revisions, D39) | Full lifecycle to `COMPLETED` (§7.8) |
| 7:45–9:00 | Swagger | Bilal token → `GET /api/v1/shops/{clifton_id}/bookings` → **404**. Imran token → `POST …/{your booking}/actions/confirm` → **403 `FORBIDDEN`**. Fatima token → `…/actions/pick-qc` → **403** | Tenant isolation (§7.1), **no role can perform another role's action** (§7.8) |
| 9:00–10:00 | B | Log out Bilal, log in **Fatima** → shop switcher Lahore Auto Care ↔ Raza Auto Works → Overview (bookings by status, team, inventory Low/Out) → Technician view (read-only, no buttons). *(Optional, +1 min with profile E: SEC3 deactivate/reactivate Hamza.)* | Owner multi-shop, per-shop teams, read-only role views |

### README "Try the full flow" list (paste as is; spec 07 README section 2)

````markdown
**Try the full flow (about 10 minutes, two or more browsers):**

1. Open the live site → **Lahore Auto Care** → **Book a service**: "Check engine light" + "Oil change" → the coming **Friday 10:00** → your details with a fresh `.test` e-mail nobody has used yet (e.g. `ahmed1@bayflow.test`; add a number or your initials if it is taken — `.test` addresses are accepted and never e-mailed; please don't use addresses at real providers such as `@mail.com`) and a password of at least 12 characters, vehicle `LEA-1234` Honda Civic 2016 → **Confirm**. You are now logged in as this customer.
2. In another browser, log in as **Bilal** (`bilal.sa@bayflow.test`) → open the new booking → **Confirm** → **Assign technician: Imran**.
3. Log in as **Imran** (`imran.tech@bayflow.test`) → **Start inspection** → add Ignition coil (out of stock), Oil filter, Engine oil 4 L and labour 4,000 → **Submit** (PKR 16,600).
4. As **Bilal** → edit labour to 3,500 → **Send to customer** (PKR 16,100).
5. As the customer → **Approve** (or **Decline estimate** first, then as Bilal **Revise estimate** and send again).
6. As **Bilal** → **Assign parts person: Usman**.
7. As **Usman** (`usman.parts@bayflow.test`) → **Order missing parts** (1 coil) → Purchase orders → **Receive** → back on the job → **Allocate parts**.
8. As **Imran** → **Start repair** → **Send to QC**.
9. As **Sara** (`sara.qc@bayflow.test`) → **Pick** → **Fail QC** with issue "Oil leak at filter"; as Imran → **Send to QC** again; as Sara → **Pick** → **Pass**.
10. As **Bilal** → **Notify customer**; as the customer → **I've collected my vehicle** → `COMPLETED`. Then try the security checks: another shop's booking → not found; another role's action → 403.

All staff passwords: `BayFlow@2026`. The data is shared by every tester: if Friday 10:00 is full or the ignition coil is already in stock, see the judge notes under "Demo accounts".
````

### Definition of Done coverage (§7.8)

| DoD item | Where in the script | Automated proof (spec 12) |
|---|---|---|
| A judge completes the full §5 flow on the live URL with seeded accounts, from booking to `COMPLETED` | 0:00–7:45 | SM-18 (worked example end to end) |
| QC fail loop works | 6:15–7:15 (E4 for two rounds) | SM-10 |
| Estimate-rejected path works | 3:30–4:30 (E1 for return-to-technician) | SM-08, SM-09 |
| No role can perform another role's action | 7:45–9:00 (+ buttons never rendered) | SM-03, SM-04, SM-16 |
| §7.1 acceptance: Shop A staff → Shop B bookings = 403/404 | 7:45–9:00 | SM-05 |

### Video storyboard (3–5 minutes, §9.1 optional)

| Time | Scene | On screen | Caption / voice-over |
|---|---|---|---|
| 0:00–0:15 | Problem | Title card; photo-style slide of a paper job card | "Garages lose information at every hand-off." |
| 0:15–0:35 | Discover | Landing, 6 shops, city filter, rating "New" | "Customers find a shop and see real availability." |
| 0:35–1:05 | Book | Wizard at speed; Friday 10:00; confirmation with `BF-` reference | "Booking creates the account and the job card in one step." |
| 1:05–1:25 | Front desk | Split screen: Bilal confirms/assigns; customer timeline updates live | "Every status has one owner, and everyone sees it change." |
| 1:25–1:50 | Inspect | Imran's estimate editor with the OUT badge on the coil; total 16,600 | "Stock is visible while estimating." |
| 1:50–2:10 | Approve | Bilal edits labour → revision 2 → customer approves with a timestamp | "Versioned estimates end price disputes." |
| 2:10–2:40 | Parts | PO for 1 coil → receive → allocate; inventory numbers change | "Shortages become purchase orders; stock is a ledger." |
| 2:40–3:10 | Quality | Sara fails QC with an issue → Imran fixes → pass | "QC is mandatory, and failures go back with a record." |
| 3:10–3:25 | Done | Notify ready → customer marks pick-up → full audit timeline | "From booking to pick-up, every step is recorded." |
| 3:25–3:50 | Security | Swagger 404 for another shop; 403 for another role; owner shop switcher | "Tenants and roles are isolated on the server." |
| 3:50–4:35 | Bonus | Customer calls; no answer for 20 s; AI Front Desk answers; summary + task appear for Bilal | "Missed calls become answered calls with a follow-up task." |
| 4:35–4:50 | Close | Architecture diagram (modular monolith), live URL, repo link | "One backend, one state machine, deployed and seeded." |

---

## 11. Bonus journeys (priority P2 — only after P0 works end to end on the live URL; spec 05)

| ID | Journey | Steps | Records and notifications |
|---|---|---|---|
| B1 | SA calls customer | Bilal → Staff booking detail → **Call customer** (`POST /api/v1/shops/{shop_id}/bookings/{booking_id}/calls`) → the customer's open BayFlow tab shows the non-modal incoming-call panel (Accept / Decline, D78) via `call.incoming` → Accept (`POST /api/v1/me/calls/{call_id}/accept`) → voice in the browser → either side hangs up (`…/end`) | Call log on the booking (who, when, duration, outcome); states `RINGING` → `CONNECTED` → `ENDED`, or `MISSED` (`DECLINED` / `NO_ANSWER`) |
| B2 | Customer calls shop | Customer booking detail → **Call the shop** (`POST /api/v1/me/bookings/{booking_id}/calls`) → every online SA of the shop sees the incoming-call panel (non-modal and stacked, so it never blocks the page they are working on, D78) → first to accept (`POST /api/v1/shops/{shop_id}/calls/{call_id}/accept`) connects; a second SA clicking Accept gets 409 `CALL_ALREADY_ANSWERED`, and every other panel entry closes on `call.updated` | Same; an unanswered call → `CALL_MISSED` → SAs of the shop |
| B3 | Unanswered call → AI Front Desk | B2, but nobody accepts within `AI_RING_TIMEOUT_SECONDS` (20; the call rings for the full time even when no SA is online, D77) — or every rung SA declines (spec 05) → the call becomes `MISSED` and the API dispatches the AI agent into the same room (D58) → greets, identifies the caller (name, phone, e-mail or booking reference), answers from real booking data via internal tools scoped to that customer (status, appointment time, pending estimate, ready for pick-up), handles simple requests (reschedule request, "what is my status", "how much is the estimate"), never invents data and promises a callback when unsure → hang-up | The call stays `MISSED` (no human answered; the log reads "Missed (no answer) → AI Front Desk", spec 05). AI call summary (intent, details, sentiment, transcript); task "Call back Ahmed about estimate" (`OPEN`) linked to the booking and call log; `CALL_MISSED` and `AI_TASK_CREATED` → SAs |
| B4 | SA follows up | Bilal → **Calls & tasks** (`GET /api/v1/shops/{shop_id}/tasks?status=OPEN` and the call log `GET /api/v1/shops/{shop_id}/calls`) → expands a task to read the AI summary and transcript (`GET /api/v1/shops/{shop_id}/calls/{call_id}`) → calls back (B1) → **Mark as done** with an optional note (shown from `tasks.manage`, which exists only when the calls module is enabled, D66; `POST /api/v1/shops/{shop_id}/tasks/{task_id}/mark-done` `{note?}`) | Task `DONE` (`done_at`, `done_by`, `done_note`) |
| — | Guardrail check | During B3 the caller asks about someone else's booking or plate | The AI says it can only discuss the caller's own bookings — the internal API is scoped to the dispatched customer, not the prompt (D58) |

---

## Assumed endpoints

The glossary §9 patterns (booking actions, wizard, PO receive, estimate `PUT`, realtime ticket) are used as defined. Every endpoint this spec uses is in [03-api-contracts.md](03-api-contracts.md), the authoritative catalogue; its §8.1 maps the endpoint table of [10-screens.md](10-screens.md) (IDs E-01…E-60) onto it, and the notes below follow it. Paginated collections return `{items, total, limit, offset}`; bounded lists (cities, a booking's events, estimate versions and QC rounds, the QC checklist, my vehicles, the owner summary) return `{items}` (spec 03 §1.6).

| Endpoint (spec 10 ID) | Used in | Notes |
|---|---|---|
| `GET /api/v1/public/shops?q=&city=` (E-06), `GET /api/v1/public/cities` (E-07) | C1 | Listed shops with ≥ 1 active service (D64), with `id`, `slug`, rating, services; cities as `{items}` |
| `GET /api/v1/public/shops/{shop_slug}` (E-08) | C1, C2 | Detail, working hours, active services, `is_bookable`; addressed by slug (D68) |
| `GET /api/v1/public/shops/{shop_slug}/availability?date=` (E-09) | C2, E5 | `slots: [{slot_start, slot_end, remaining}]`, only slots with `remaining` ≥ 1 — full slots are omitted (D37, D68) |
| `POST /api/v1/auth/register-owner` (E-03), `POST /api/v1/auth/login` (E-01), `POST /api/v1/auth/logout` (E-02) | O1, all | Login and owner sign-up return `{access_token, token_type, expires_in, user}` + the cookie, with no memberships; the web then calls `GET /api/v1/me` (D81). The token is used for Swagger in §9. `POST /api/v1/bookings` (E-10) returns `{access_token, token_type, expires_in, account_created, booking}` next to the cookie (D32) |
| `GET /api/v1/me` (E-04) | all | Flat `{id, email, full_name, phone, memberships: [{membership_id, shop_id, shop_name, shop_slug, role, capabilities}]}` (active memberships only) for routing after login (D81), the shop switcher and every non-booking button (D66) |
| `GET /api/v1/me/vehicles` (E-16) | C3 | Wizard vehicle picker; `{items}` of vehicles with `color` and `mileage_km` |
| `GET /api/v1/me/bookings` (E-11), `…/{booking_id}` (E-12), `…/events` (E-13), `…/estimates` (E-14) | C4–C8 | Customer-safe timeline (events and estimates as `{items}`); only `SENT`, `APPROVED` and `REJECTED` revisions (D39) |
| `GET /api/v1/me/notifications` (E-17), `…/unread-count` (E-18), `POST …/{notification_id}/read` (E-19), `POST …/read-all` (E-20) | all | Bell |
| `POST /api/v1/shops` (E-21), `GET`/`PATCH /api/v1/shops/{shop_id}` (E-22, E-23), `PUT /api/v1/shops/{shop_id}/working-hours` (E-24) | O1, O5 | Shop settings and hours; `PATCH` of `slot_duration_minutes` or `timezone` → 409 `CONFLICT` while future non-cancelled bookings exist (D37) |
| `GET`/`POST /api/v1/shops/{shop_id}/members` (E-25, E-26), `PATCH …/members/{membership_id}` (E-27) | O2, O3 | Add-member response says whether the user already existed (D18); the `OWNER` row is refused |
| `GET`/`POST /api/v1/shops/{shop_id}/services` (E-28, E-29), `PATCH …/services/{service_id}` (E-30) | O4 | — |
| `GET /api/v1/shops/{shop_id}/overview` (E-31); `GET /api/v1/me/owner-summary` (E-32, priority P1) | O6 | Overview `status_counts` as `[{status, count}]`; owner summary as `{items}` |
| `GET /api/v1/shops/{shop_id}/bookings?status=…` (E-33, `status` repeatable), `…/status-counts` (E-34) | S1, T1, P2, Q1 | Role-scoped by D21; status counts `{items: [{status, count}], total}` (all 17 statuses, zeros included) |
| `GET /api/v1/shops/{shop_id}/bookings/{booking_id}` (E-35), `…/events` (E-36), `…/estimates` (E-38), `…/parts` (E-40, with `all_available`), `…/qc-inspections` (E-41) | all staff | Staff detail panels |
| `GET /api/v1/shops/{shop_id}/qc/checklist` (E-42) | Q3, Q4 | D46 checklist items |
| `GET`/`POST /api/v1/shops/{shop_id}/parts` (E-43 `?q=&stock_state=` with `stock_state` repeatable `OK`/`LOW`/`OUT`, E-44), `PATCH …/parts/{part_id}` (E-45) | P1, P7 | Create takes no quantity: new parts start at `on_hand` 0 (D44); each part carries `available`, `stock_state` and `on_order` |
| `POST /api/v1/shops/{shop_id}/parts/{part_id}/adjustments` (E-46) `{quantity_delta, reason}`; `GET …/movements` (E-47) | P1, P7, E6 | Priority P0 (D82). `ADJUST` movement (opening stock and corrections), response `{part, movement}`; Parts Person only (`stock.manage`, D44, D66); below `reserved` or below zero → 409 `INSUFFICIENT_STOCK` |
| `GET`/`POST /api/v1/shops/{shop_id}/purchase-orders` (E-48, E-49 `{supplier_name?, items[{part_id, quantity, unit_cost?}]}`), `GET …/{po_id}` (E-50), `POST …/{po_id}/receive` (E-51 `{items[{item_id, quantity, expected_received_qty?}]}` → `{purchase_order, receive_parts_applied}`) | P5, P8 | General restock POs have no booking; a partial receipt pushes `booking.updated` for a linked booking (D83) |
| Action bodies (spec 03 §5.2): `order-parts` `{supplier_name?, items?[{part_id, quantity}]}` (items omitted = exactly the shortages); `pass-qc` `{checklist, notes?}`; `fail-qc` `{issue_title, issue_description, checklist?, notes?}` | P4, Q3, Q4 | All action bodies add `expected_version` |
| Bonus: `POST /api/v1/me/bookings/{booking_id}/calls` (E-52), `POST /api/v1/shops/{shop_id}/bookings/{booking_id}/calls` (E-53), `POST /api/v1/me/calls/{call_id}/accept\|decline\|end` (E-54), `POST /api/v1/shops/{shop_id}/calls/{call_id}/accept\|decline\|end` (E-55), call logs (E-56, E-57), `GET /api/v1/shops/{shop_id}/calls` and `GET …/calls/{call_id}` (summary, transcript and tasks; E-58), `GET /api/v1/shops/{shop_id}/tasks` (E-59), `POST /api/v1/shops/{shop_id}/tasks/{task_id}/mark-done` `{note?}` (E-60) | B1–B4 | Behaviour in spec 05 (§8); start and accept return `{call, connection}` |

## Proposed glossary additions

None required. Screen names and routes belong to spec 10; request and response field names are fixed by spec 03 (§3–§5), which the Assumed endpoints table follows.

## Dependencies

- Depends on: [18-glossary.md](18-glossary.md), [17-decisions.md](17-decisions.md), [08-booking-state-machine.md](08-booking-state-machine.md), [11-seed-data.md](11-seed-data.md) (demo cast, `BF-SEEDnn` bookings, stock numbers), [03-api-contracts.md](03-api-contracts.md) (endpoint shapes), [04-auth-and-security.md](04-auth-and-security.md) (wizard cases A–D, rate limits, 404/403 semantics, member rules), [09-frontend-and-ux.md](09-frontend-and-ux.md) (routes, action labels and dialogs, wizard persistence, error copy, ShopScope), [10-screens.md](10-screens.md) (screen IDs, endpoint table E-01…E-60), [05-calling-and-ai-front-desk.md](05-calling-and-ai-front-desk.md) (bonus journeys, call outcomes).
- Used by: [10-screens.md](10-screens.md), [12-quality-and-testing.md](12-quality-and-testing.md) (Playwright smoke, worked-example test SM-18, judge path DEP-09), [15-requirements-traceability.md](15-requirements-traceability.md), README (spec 07: demo section and the "Try the full flow" list in §10).

## Open questions

1. ✅ Resolved by D62: **Demo e-mails vs e-mail validation.** One project `Email` type (`app.shared.email`, `validate_email(value, check_deliverability=False, test_environment=True)`, then lower-cased) replaces Pydantic's `EmailStr`, so every `…@bayflow.test` account and every fresh `.test` judge address validates.
2. ✅ Resolved by D71: **Friday 10:00 capacity on the live site.** Lahore Auto Care keeps `slot_capacity` 2; filling Friday 10:00 is accepted shared-data drift. The script and judge notes say "if full, take the next Friday or another time" (the 30-day horizon gives about four Fridays).
3. **Membership changes are not pushed.** Glossary §11 has no message for membership changes, so a deactivated member finds out on their next request (D9). Enough for the demo; add a `membership.updated` message only if needed.
4. **Partial PO receipts are not booking events.** The booking timeline cannot show "1 of 2 discs received" from events alone. The staff Parts panel reads PO data instead (P5, spec 10 E-40/E-50). ✅ Resolved by D83 for live updates: a partial receipt still writes no booking event, but it pushes `booking.updated` to the booking's viewers, so open Parts panels and the SA board refresh at once.
