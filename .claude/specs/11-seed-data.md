# 11 — Seed Data

**Status:** Draft

## Purpose

Define exactly what the seed creates so that judges can test instantly on the live URL. Brief §7.7: "A seed script creating at least 3 shops, a team for each role, a service catalog, sample inventory and available slots" and "Demo credentials listed in the README (and shown on the live site login page or README only, not hard-coded in code logic)". Brief §9.1 and FAQ: the live site must contain "seeded data and demo accounts for all roles". Brief §6: Ahmed "sees 6 shops" and books at Lahore Auto Care, owned by Fatima Raza with Bilal, Imran, Sara and Usman.

This spec covers the shops, accounts, service catalogues, inventory, purchase orders and sample bookings (with the exact service-layer actions that build each one), how the seed stays idempotent, the commands, and the README text. Names come from [18-glossary.md](18-glossary.md) (demo cast §14), rules from [08-booking-state-machine.md](08-booking-state-machine.md), decisions from [17-decisions.md](17-decisions.md) — D13, D37, D44, D51, D52, D60, D62, D63, D65, D71, D73, D79, D81 and D82 in particular.

## Principles

1. **Idempotent.** The seed inserts only what is missing, detected by natural keys (user e-mail, shop slug, `(shop, sku)`, service name per shop, reserved booking/PO reference). It deletes nothing and never changes data it finds already in place, with two exceptions: its own unfinished work (an interrupted sample script or general-PO receipt is resumed, through the services), and the **demo cast**, which every run reconciles (D60: demo users active, demo memberships active with their canonical role, demo password hash valid for `BayFlow@2026` — see "Demo-cast reconciliation"). Bookings, inventory, purchase orders and shop settings created or changed by judges are never touched. It is safe to run on every deploy (`SEED_ON_DEPLOY=true`, D13) and after judges have changed data.
2. **Through the service layer (D51).** Every record is created by the same service functions the API uses, with the same validation, state machine, stock rules, events and notifications. There are no raw SQL inserts of domain data. So every seeded booking has a legal event history, and its estimates, `booking_parts`, `stock_movements`, purchase orders and QC rows agree with each other.
3. **Real actors.** Each seeded action is performed as the person who would do it: each shop's Owner creates the shop, team and services; Bilal confirms; Imran inspects; Usman sets opening stock, orders and receives; Sara inspects. The service receives the same actor context the API builds from a token. The seed acts as these real demo people and **never uses `SYSTEM`** — not for booking actions, stock, purchase orders or team changes (glossary §2.2) — so seeded timelines and ledgers read exactly like live ones.
4. **Slots are computed (D37).** There are no slot rows to seed. "Available slots" (§7.7) come from each shop's working hours, slot duration and capacity. The only slot data the seed writes are the `slot_counters` increments made by the sample bookings it books.
5. **Realistic time.** Sample histories are back-dated with the `SimulatedClock` of `app.shared.clock` — the single time source every service reads (D63): finished jobs have past slots, pending ones future slots, and every slot is on the shop's grid.
6. **The worked example stays ready.** Sample data never touches Lahore Auto Care's oil filter, engine oil 4 L or ignition coil. After the seed they are **10/0, 8/0, 0/0** (on hand/reserved) — exactly the starting point of spec 08's reservations example — and no seeded booking occupies a 10:00 slot in the future.
7. **No secrets, no back doors.** The only credential is the published demo password **`BayFlow@2026`** (glossary §14), public by design in the README and on the login page (D52). Application logic knows nothing about demo accounts: no bypass, no auto-login, no special-casing of `@bayflow.test`. The list of demo accounts lives only in the seed's data module, and the D60 reconciliation runs only inside the seed script. Accepting `.test` addresses (D62) and never e-mailing reserved TLDs (D26) are generic rules for every address, not demo special cases.
8. **Quiet.** No e-mails and no WebSocket pushes reach anyone while seeding (the seed process runs with `EMAIL_PROVIDER=none`, D26; its `.test` recipients would be skipped anyway). Notification rows are still written (they belong to each action's transaction) and are then mostly marked read (see "Notifications after seeding").

## Execution model

| Aspect | Rule |
|---|---|
| Entry point | `python -m app.scripts.seed` in `apps/api`: runner `app/scripts/seed.py`, data in `app/scripts/seed_data.py` as typed constants (spec 01 repo layout; both match spec 12's lint exemption `app/scripts/seed*.py` for the demo password) |
| Gate | Runs only when `SEED_ON_DEPLOY=true` **or** with `--force`. Otherwise it logs `seed skipped (SEED_ON_DEPLOY is not true)` and exits 0 (spec 07, SEED-09). Every caller relies on this gate: the Railway pre-deploy step, the Compose `migrate` service and the root start scripts, which always call the seed after migrations (D73; `.env.example` sets `SEED_ON_DEPLOY=true` for local development, and `start.* --seed` passes `--force`) |
| Concurrency | Takes a PostgreSQL advisory lock (`pg_try_advisory_lock` on a constant key derived from `bayflow:seed`). If another seed holds it: log and exit 0 |
| Steps and commits | Every step is one ordinary top-level use case, which commits its own transaction exactly as an API request would (spec 01 "only top-level use cases commit", spec 08 principle 4, spec 12 "services commit"). The seed adds no transaction wrapper, so it runs the real transaction boundaries |
| Phase A — base data | Per shop, in order: owner account → shop (with its 7 working-hours rows, spec 02) → memberships (staff accounts) → services → parts (created with `on_hand` 0, D44) → opening stock (`ADJUST` movements performed as the shop's Parts Person — Usman at Lahore Auto Care, D44). Then the general purchase orders. Each step is skipped when its natural key already exists, so an interrupted run simply continues next time |
| Phase R — demo-cast reconciliation (D60) | Runs on **every** run, after Phase A and before Phase B (so a resumed sample script finds its actors active): every seeded account that exists is made active with a password hash that verifies `BayFlow@2026`, and every seeded membership that exists is made active with its canonical role. Writes only what differs and never touches bookings, inventory, POs or shop settings. Details in "Demo-cast reconciliation" below |
| Phase B — sample bookings | Scripts run in ascending order of their CREATE time; inside a script, steps run in order. An interrupted script is **resumed** on the next run (see Idempotency) |
| Actors | For each step the seed loads the actor's user and active membership and passes the same actor context the API builds from a token (user id, actor role, shop id). Customer steps use the customer actor (spec 08 "Who is the actor?") |
| Clock | One time source: `app.shared.clock` (D63). At start the seed reads the real time once from `SystemClock` (`run_now`) and derives `today` and the anchors below from it. It then installs a **`SimulatedClock`** as the process clock and sets it before every step: to the step's scripted time in Phases A and B, and to `run_now` for Phase R and for marking notifications read. **Every seeded timestamp comes from that clock** — `created_at`/`updated_at` of base data, opening-stock movements, POs, booking events, estimates, stock movements, QC rows and notifications — and every time rule is checked against it (D37: a slot must start after "now" and within 30 days), which is how a finished job gets a past slot while still passing the normal CREATE rules. Database `DEFAULT now()` is only a fallback for hand-written SQL (D63); the seed never relies on it. Scripted steps of one booking never share a minute, so the event order `(created_at, seq)` (D79) always follows the script; rows written by one step share its instant and keep insert order through `seq` |
| Wiring | Before Phase A the seed reuses the application's wiring instead of hand-wiring anything (D89): it calls `app.main.wire_modules()` (or builds the app with `create_app()`), so every module's `service.register_ports()` and `handlers.register(bus)` run exactly as in production. That registers the event handlers (bookings' `PurchaseOrderReceiving`, `PurchaseOrderReceived` and `ShopGridChanging` handlers, the notifications handlers) and the D86 read ports — bookings' `register_ports()` calls `shops.service.register_activity_reader(shop_activity_reader)` (`ShopActivityReader`) and `inventory.service.register_booking_ref_reader(get_booking_refs)` (`BookingRefReader`). Without them a PO receipt or a shop read fails loud (`RuntimeError`), and receipts would never reserve stock for BF-SEED03-style bookings |
| Side channels | The seed process runs with `EMAIL_PROVIDER=none` (settings override at start-up, D26), and its realtime hub has no connected clients, so after-commit callbacks (spec 01) send nothing. The seed awaits pending callbacks before exiting |
| Rate limits | Spec 04's limiters (D69) run inside the services with in-memory storage per process. The seed's calls (at most 4 bookings per customer, 2 shops per owner, ≤ 6 members per shop, no failed password checks) stay far below them and never touch the API process's counters. Phase R verifies password hashes through identity's internal `password_matches` (one `verify_password` call), outside the login limiter |
| Failures | A failed step stops that unit (the shop's remaining base data, one reconciliation item, or the rest of that booking's script); the seed continues with the next unit, prints a summary and **exits non-zero if anything failed**, which stops the Railway deploy (D13, SEED-09). Escape hatch: set `SEED_ON_DEPLOY=false` |
| Output | Created/skipped/resumed counts per entity; Phase R repairs with the e-mails concerned (users reactivated, passwords reset, memberships reactivated, roles restored); the `BF-SEEDnn` references; and the line `Lahore Auto Care worked-example stock: oil filter 10/0, engine oil 8/0, ignition coil 0/0`. Never prints passwords or tokens |

## Time anchors

All times are shop-local (`Asia/Karachi`, UTC+5, no DST) and stored in UTC (D38).

| Symbol | Meaning |
|---|---|
| `today` | Current date in `Asia/Karachi` when the seed runs (from `run_now`, read once from `SystemClock`, D63) |
| `B` | `today` − 21 calendar days, 09:00. Timestamp of base data: owners, shops, memberships, services, parts; opening stock at `B` + 1 h |
| `P(n)` | The n-th day **before** today on which the shop is open (its own working hours). `P(1)` = the most recent open day before today. Always strictly in the past, so every time of day on `P(n)` is earlier than now |
| `F(n)` | The n-th open day **after** today. `F(4)` is at most ~5 calendar days ahead, inside the 30-day horizon (D37) |

Rules:

- Every slot is a grid time of its shop (opening time + k × 60 min, ending by closing time).
- No two sample bookings share a slot, so every seeded slot keeps at least one free place (capacity 2).
- No future sample booking at Lahore Auto Care uses 10:00, so **every Friday 10:00 slot is untouched** for the worked example.
- Checked for all seven weekdays the seed could run on: every booking's events are in time order, the slot is after the CREATE time, all events are before the run, all slots are on the grid and on open days.

Example — seed run on Friday 9 Oct 2026, Lahore Auto Care (open Mon–Sat): `B` = Fri 18 Sep 09:00; `P(1)` = Thu 8 Oct, `P(2)` = Wed 7 Oct, `P(3)` = Tue 6 Oct, `P(4)` = Mon 5 Oct, `P(5)` = Sat 3 Oct, `P(6)` = Fri 2 Oct, `P(8)` = Wed 30 Sep, `P(9)` = Tue 29 Sep, `P(10)` = Mon 28 Sep; `F(1)` = Sat 10 Oct, `F(2)` = Mon 12 Oct. The worked example's "Friday 10:00" is then Fri 16 Oct, 10:00 PKT = `2026-10-16T05:00:00Z`.

## Shops (6, D51)

All shops: timezone `Asia/Karachi`, `slot_duration_minutes` **60**, `slot_capacity` **2**, `logo_url` NULL (initials avatar, D55), `is_listed` true.

| Shop | Slug | City | Address | Phone (placeholder) | Owner | Working hours | Rating |
|---|---|---|---|---|---|---|---|
| **Lahore Auto Care** | `lahore-auto-care` | Lahore | Plot 12, Main Boulevard, Gulberg III | `+924200000101` | Fatima Raza | Mon–Sat 09:00–18:00; Sun closed | 4.7 |
| **Raza Auto Works** (Fatima's second shop) | `raza-auto-works` | Lahore | Plot 8, Commercial Area, DHA Phase 6 | `+924200000102` | Fatima Raza | Mon–Sat 10:00–19:00; Sun closed | NULL → shown as "New" (D56) |
| Clifton Car Clinic | `clifton-car-clinic` | Karachi | Shop 3, Block 5, Clifton | `+922100000201` | Asif Memon | Mon–Sat 10:00–19:00; Sun closed | 4.5 |
| Margalla Motor Works | `margalla-motor-works` | Islamabad | Plot 21, I-9 Markaz | `+925100000301` | Nida Abbasi | Mon–Sat 09:00–18:00; Sun closed | 4.6 |
| Pindi Auto Garage | `pindi-auto-garage` | Rawalpindi | Shop 14, Murree Road, Satellite Town | `+925100000401` | Tariq Mehmood | Mon–Sat 09:00–18:00; **Sun 10:00–14:00** | 4.2 |
| Lyallpur Motors | `lyallpur-motors` | Faisalabad | Plot 5, Susan Road, Madina Town | `+924100000501` | Khalid Chaudhry | Mon–Sat 09:00–18:00; Sun closed | 4.4 |

- Lahore Auto Care slots: 09:00 … 17:00 (9 per open day × 2 places). **Friday 10:00 is a valid slot.** Raza Auto Works and Clifton Car Clinic: 10:00 … 18:00. Pindi Auto Garage shows that hours are per weekday: Sunday 10:00 … 13:00.
- Each shop gets its 7 `shop_working_hours` rows when it is created; closed days have `is_closed = true` (spec 02) — 42 rows in total.
- Phone numbers are fake placeholders (subscriber part starts with 0000); nothing in BayFlow dials them (bonus calling is in-app).
- The rating is a seeded placeholder (D56), set through an internal shops service function that is not exposed over HTTP.
- **Lyallpur Motors (`lyallpur-motors`) is the smoke-test shop.** Automated checks against the live URL — spec 07's `scripts/smoke.sh` and spec 12's DEP-10 (worked-example replay) and WEB-08 (Playwright smoke) — create their throw-away customers (`smoke+<n>@bayflow.test`) and bookings **only** there, never at Lahore Auto Care, so the worked-example stock and slots stay as seeded for judges. Like any user's, those runs add bookings, use slot places and stock (DEP-10) and notify Lyallpur Motors' staff; the seed never resets or tops them up (Worked-example readiness).

## Accounts

Every account's password is **`BayFlow@2026`** — 12 characters, so it meets the 12–128 policy (D10). Every e-mail uses the reserved `.test` TLD and passes the project `Email` type (`app.shared.email`, D62), the same validation the API applies to every e-mail field; the seed has no validation bypass. E-mail patterns:

- Lahore Auto Care team and the glossary cast, Hamza and Hina included: `<firstname>.<role-tag>@bayflow.test` (glossary §14.1).
- Every other shop: **`<role-tag>.<shop-slug>@bayflow.test`**, with role tags `owner`, `sa`, `tech`, `qc`, `parts` (glossary §2.3, §14.2). Raza Auto Works has no `owner.` account because its owner is Fatima.
- Seeded customers: `<firstname>.customer@bayflow.test`.
- The platform admin **Areeba Hashmi**, `admin@bayflow.test`, `is_platform_admin = true`, no memberships (D94, spec 19 §8).

### Staff and owners (31 accounts, 32 memberships)

| Shop | Name | Role (`MembershipRole`) | E-mail |
|---|---|---|---|
| Lahore Auto Care | Fatima Raza | `OWNER` | `fatima.owner@bayflow.test` |
| Lahore Auto Care | Bilal | `SERVICE_ADVISOR` | `bilal.sa@bayflow.test` |
| Lahore Auto Care | Imran | `TECHNICIAN` | `imran.tech@bayflow.test` |
| Lahore Auto Care | Hamza *(2nd technician — makes assignment a real choice; isolation and deactivation demos)* | `TECHNICIAN` | `hamza.tech@bayflow.test` |
| Lahore Auto Care | Sara | `QC_INSPECTOR` | `sara.qc@bayflow.test` |
| Lahore Auto Care | Hina *(2nd QC inspector — needed to show "first pick wins")* | `QC_INSPECTOR` | `hina.qc@bayflow.test` |
| Lahore Auto Care | Usman | `PARTS_PERSON` | `usman.parts@bayflow.test` |
| Raza Auto Works | Fatima Raza (same account) | `OWNER` | `fatima.owner@bayflow.test` |
| Raza Auto Works | Adeel Anwar | `SERVICE_ADVISOR` | `sa.raza-auto-works@bayflow.test` |
| Raza Auto Works | Naveed Akhtar | `TECHNICIAN` | `tech.raza-auto-works@bayflow.test` |
| Raza Auto Works | Rabia Saeed | `QC_INSPECTOR` | `qc.raza-auto-works@bayflow.test` |
| Raza Auto Works | Faisal Javed | `PARTS_PERSON` | `parts.raza-auto-works@bayflow.test` |
| Clifton Car Clinic | Asif Memon | `OWNER` | `owner.clifton-car-clinic@bayflow.test` |
| Clifton Car Clinic | Sadia Qureshi | `SERVICE_ADVISOR` | `sa.clifton-car-clinic@bayflow.test` |
| Clifton Car Clinic | Junaid Baloch | `TECHNICIAN` | `tech.clifton-car-clinic@bayflow.test` |
| Clifton Car Clinic | Mehwish Siddiqui | `QC_INSPECTOR` | `qc.clifton-car-clinic@bayflow.test` |
| Clifton Car Clinic | Rizwan Shaikh | `PARTS_PERSON` | `parts.clifton-car-clinic@bayflow.test` |
| Margalla Motor Works | Nida Abbasi | `OWNER` | `owner.margalla-motor-works@bayflow.test` |
| Margalla Motor Works | Waqas Kiani | `SERVICE_ADVISOR` | `sa.margalla-motor-works@bayflow.test` |
| Margalla Motor Works | Zubair Satti | `TECHNICIAN` | `tech.margalla-motor-works@bayflow.test` |
| Margalla Motor Works | Amna Rehman | `QC_INSPECTOR` | `qc.margalla-motor-works@bayflow.test` |
| Margalla Motor Works | Fahad Mirza | `PARTS_PERSON` | `parts.margalla-motor-works@bayflow.test` |
| Pindi Auto Garage | Tariq Mehmood | `OWNER` | `owner.pindi-auto-garage@bayflow.test` |
| Pindi Auto Garage | Saima Bashir | `SERVICE_ADVISOR` | `sa.pindi-auto-garage@bayflow.test` |
| Pindi Auto Garage | Arshad Hussain | `TECHNICIAN` | `tech.pindi-auto-garage@bayflow.test` |
| Pindi Auto Garage | Kiran Aslam | `QC_INSPECTOR` | `qc.pindi-auto-garage@bayflow.test` |
| Pindi Auto Garage | Shoaib Haider | `PARTS_PERSON` | `parts.pindi-auto-garage@bayflow.test` |
| Lyallpur Motors | Khalid Chaudhry | `OWNER` | `owner.lyallpur-motors@bayflow.test` |
| Lyallpur Motors | Mariam Yousaf | `SERVICE_ADVISOR` | `sa.lyallpur-motors@bayflow.test` |
| Lyallpur Motors | Asad Latif | `TECHNICIAN` | `tech.lyallpur-motors@bayflow.test` |
| Lyallpur Motors | Huma Zafar | `QC_INSPECTOR` | `qc.lyallpur-motors@bayflow.test` |
| Lyallpur Motors | Danish Saleem | `PARTS_PERSON` | `parts.lyallpur-motors@bayflow.test` |

Display names of the brief's cast are exactly as in glossary §14 (first names only for Bilal, Imran, Sara, Usman); Hamza and Hina follow the same style.

### Customers (5 accounts, no memberships)

| Name | E-mail | Phone (placeholder, D33) | Vehicles | Why |
|---|---|---|---|---|
| **Ayesha Khan** (glossary cast) | `ayesha.customer@bayflow.test` | `+923000000101` | Toyota Corolla GLi 2018, Suzuki Cultus VXL 2021 | The judge's ready-made customer: an estimate to approve, a car ready for pick-up, history |
| Kamran Shah | `kamran.customer@bayflow.test` | `+923000000102` | Honda City 2019, Toyota Hilux Revo 2020 | Rejected-then-revised estimate, open PO, a declined booking, bookings at Fatima's second shop |
| Zainab Malik | `zainab.customer@bayflow.test` | `+923000000103` | Suzuki Alto VXR 2022, Kia Sportage 2022 | Pending booking (one place left in its slot), labour-only job in repair |
| Nadia Iqbal | `nadia.customer@bayflow.test` | `+923000000104` | Toyota Yaris 2021, Honda BR-V 2019 | Job waiting in the QC queue; bookings in Islamabad and Faisalabad |
| Omar Farooq | `omar.customer@bayflow.test` | `+923000000105` | Toyota Corolla Altis 2020, Suzuki Wagon R 2019 | Pending bookings in Karachi and Rawalpindi |

The four extra customers are part of the canonical cast (glossary §14.1): with ten vehicles, no car is in two active jobs at once and every shop gets at least one booking. **`ahmed@mail.com` is not seeded (D51).**

Totals: **36 users** (5 owners, 26 staff, 5 customers), **32 memberships**.

## Service catalogue

Same nine services everywhere (Raza Auto Works, the newer branch, offers seven). The brief's four examples (§5.1) come first. The base price is the starting price shown in the wizard (labour/diagnosis); parts are quoted on the estimate. **Suspension repair has no base price** (NULL → "Price after inspection") to show that the price is optional (§7.2).

| Service | Description | Duration (min) | Lahore Auto Care | Raza Auto Works | Clifton Car Clinic | Margalla Motor Works | Pindi Auto Garage | Lyallpur Motors |
|---|---|---|---|---|---|---|---|---|
| Oil change | Drain and refill engine oil, replace the oil filter, top up fluids. Oil and filter are quoted on the estimate. | 45 | 1,000 | 1,100 | 1,100 | 1,150 | 950 | 900 |
| Brake failure | Diagnose and repair brake problems: pads, discs, fluid, lines and handbrake. | 120 | 2,500 | 2,750 | 2,750 | 2,900 | 2,400 | 2,250 |
| Check engine light | OBD-II scan, fault-code reading, sensor checks and a road test. | 60 | 2,000 | 2,200 | 2,200 | 2,300 | 1,900 | 1,800 |
| Tire rotation | Rotate tires, set pressures and check tread depth. | 30 | 800 | 900 | 900 | 900 | 750 | 700 |
| General inspection | 40-point check: brakes, suspension, fluids, lights, battery and tires. | 60 | 1,500 | 1,650 | 1,650 | 1,750 | 1,450 | 1,350 |
| AC service | Leak test, gas recharge, cabin filter check and condenser cleaning. | 90 | 4,500 | — | 4,950 | 5,200 | 4,300 | 4,050 |
| Battery replacement | Battery and charging-system test; fit a new battery (battery quoted on the estimate). | 30 | 500 | 550 | 550 | 600 | 500 | 450 |
| Wheel alignment | Computerised four-wheel alignment and steering check. | 45 | 2,000 | 2,200 | 2,200 | 2,300 | 1,900 | 1,800 |
| Suspension repair | Diagnose knocks and vibration; replace links, bushes or shocks. Priced after inspection. | 180 | NULL | — | NULL | NULL | NULL | NULL |

Prices in PKR, whole rupees (D41) — as are every unit cost and estimate line below. "—" = not offered. **52 services** in total. Each is created by the shop's Owner (O4) at time `B`.

## Inventory

Every shop has the same 16-part catalogue (SKU, name, unit cost, reorder level); only quantities differ. Parts are created by the shop's Parts Person at `B` and, like every new part, start at `on_hand` 0 — the create function takes no quantity (D44). A non-zero opening quantity is then one `ADJUST` movement (reason "Opening stock") performed **as that shop's Parts Person** at `B` + 1 h — Usman at Lahore Auto Care; Faisal, Rizwan, Fahad, Shoaib and Danish at the other shops — through the same adjustment service as `POST …/parts/{part_id}/adjustments`, which is P0 because it is the only way to enter opening stock (D82). Stock is never set on part creation and never by an Owner (stock operations are Parts Person only, D44). A part is **LOW** when available ≤ reorder level and **OUT** when available = 0 (D45).

### Lahore Auto Care — the demo shop

| SKU | Name | Unit cost (PKR) | Reorder level | Opening stock (`ADJUST`) | Seeded changes | **After seed: on hand / reserved / available** | Badge |
|---|---|---|---|---|---|---|---|
| `FLT-OIL-01` | Oil filter | 900 | 3 | 10 | none — worked example | **10 / 0 / 10** | — |
| `OIL-4L-01` | Engine oil 4 L | 5,200 | 3 | 8 | none — worked example | **8 / 0 / 8** | — |
| `IGN-COIL-01` | Ignition coil | 6,500 | 2 | 0 | none — worked example | **0 / 0 / 0** | OUT |
| `SPK-PLG-IR` | Spark plug (iridium) | 1,800 | 6 | 4 | +8 PO-SEED01; −4 BF-SEED05 | 8 / 0 / 8 | — |
| `FLT-AIR-01` | Air filter | 1,600 | 3 | 6 | — | 6 / 0 / 6 | — |
| `FLT-CAB-01` | Cabin AC filter | 1,400 | 3 | 3 | −1 BF-SEED06 | 2 / 0 / 2 | LOW |
| `BRK-PAD-F` | Front brake pads (set) | 6,800 | 2 | 3 | −1 BF-SEED07; 1 reserved BF-SEED03 | 2 / 1 / 1 | LOW |
| `BRK-DSC-F` | Front brake disc | 7,500 | 2 | 0 | 2 on order (BF-SEED03's PO) | 0 / 0 / 0 | OUT |
| `BRK-FLD-D4` | Brake fluid DOT 4 (1 L) | 1,500 | 4 | 2 | +6 PO-SEED01; −1 BF-SEED07; 1 reserved BF-SEED03 | 7 / 1 / 6 | — |
| `CLT-1L` | Coolant (1 L) | 1,200 | 5 | 12 | — | 12 / 0 / 12 | — |
| `WPR-PAIR` | Wiper blades (pair) | 2,200 | 2 | 0 | 4 on order (PO-SEED02) | 0 / 0 / 0 | OUT |
| `BAT-45AH` | Battery 12V 45Ah | 18,500 | 2 | 3 | reserved then released by BF-SEED08 | 3 / 0 / 3 | — |
| `AC-R134A` | AC gas R134a (can) | 3,000 | 2 | 6 | −1 BF-SEED06 | 5 / 0 / 5 | — |
| `SUS-STB-LNK` | Front stabilizer link | 4,500 | 2 | 6 | — (BF-SEED02 is not approved yet) | 6 / 0 / 6 | — |
| `TIR-185-65-R15` | Tire 185/65 R15 | 16,000 | 4 | 2 | +2 PO-SEED02 (2 of 4 received) | 4 / 0 / 4 | LOW |
| `BLB-H4` | Headlight bulb H4 | 900 | 4 | 10 | — | 10 / 0 / 10 | — |

Result on first login: **3 OUT** (ignition coil, front brake disc, wiper blades), **3 LOW** (cabin AC filter, front brake pads, tire), reserved quantities visible (pads, brake fluid), and "on order" quantities from both open POs. The ledger is consistent in time order: no running balance ever goes negative and `reserved` never exceeds `on_hand`.

### Other shops — opening quantities

Same SKUs, names, unit costs and reorder levels as above.

| SKU | Raza Auto Works | Clifton Car Clinic | Margalla Motor Works | Pindi Auto Garage | Lyallpur Motors |
|---|---|---|---|---|---|
| `FLT-OIL-01` | 8 (→ 7 after BF-SEED11) | 12 | 10 | 6 | 9 |
| `OIL-4L-01` | 10 (→ 8 after BF-SEED11) | 9 | 12 | 5 | 7 |
| `IGN-COIL-01` | 2 | 1 | 3 | 0 | 2 |
| `SPK-PLG-IR` | 12 | 16 | 8 | 4 | 12 |
| `FLT-AIR-01` | 5 | 6 | 4 | 2 | 6 |
| `FLT-CAB-01` | 4 | 5 | 3 | 0 | 4 |
| `BRK-PAD-F` | 4 | 3 | 5 | 2 | 3 |
| `BRK-DSC-F` | 2 | 4 | 2 | 0 | 2 |
| `BRK-FLD-D4` | 6 | 8 | 6 | 3 | 5 |
| `CLT-1L` | 10 | 15 | 10 | 6 | 8 |
| `WPR-PAIR` | 3 | 6 | 2 | 1 | 4 |
| `BAT-45AH` | 2 | 4 | 3 | 1 | 2 |
| `AC-R134A` | 0 (no AC service) | 8 | 6 | 3 | 5 |
| `SUS-STB-LNK` | 4 | 4 | 4 | 2 | 4 |
| `TIR-185-65-R15` | 8 | 8 | 4 | 4 | 12 |
| `BLB-H4` | 10 | 12 | 8 | 4 | 10 |

Pindi Auto Garage is deliberately the "needs restocking" shop (several OUT and LOW badges). **96 parts** in total.

### General purchase orders (Lahore Auto Care)

Created and received by Usman through the inventory service (P8 in spec 06), keyed by reserved PO numbers. Together with BF-SEED03's linked PO, the Purchase orders screen shows all three brief statuses (§7.6) on first login.

| PO | Created | Supplier | Items (qty @ unit cost) | Receipts | Final status |
|---|---|---|---|---|---|
| `PO-SEED01` | `P(10)` 10:00 | City Auto Parts (demo) | Spark plug (iridium) 8 @ 1,800; Brake fluid DOT 4 (1 L) 6 @ 1,500 | `P(9)` 15:00: everything | `RECEIVED` |
| `PO-SEED02` | `P(3)` 15:00 | City Auto Parts (demo) | Tire 185/65 R15 4 @ 16,000; Wiper blades (pair) 4 @ 2,200 | `P(1)` 11:00: tires 2 | `PARTIALLY_RECEIVED` |
| *(BF-SEED03's PO, random `PO-XXXXXX`)* | `P(3)` 13:40 | City Auto Parts (demo) | Front brake disc 2 @ 7,500 | none | `ORDERED` (linked to BF-SEED03) |

## Customers' vehicles

| Plate | Make · model · year | Color (`color`) | Mileage given at each booking (km, D65) | Owner | Used by |
|---|---|---|---|---|---|
| `LEC-4521` | Toyota · Corolla GLi · 2018 | White | 67,900 → 68,400 | Ayesha Khan | BF-SEED07, BF-SEED02 |
| `LEF-7809` | Suzuki · Cultus VXL · 2021 | Silver | 31,050 → 31,200 | Ayesha Khan | BF-SEED08, BF-SEED06 |
| `LEB-3307` | Honda · City 1.5 Aspire · 2019 | Grey | 54,700 → 54,900 | Kamran Shah | BF-SEED09, BF-SEED03 |
| `LES-8842` | Toyota · Hilux Revo · 2020 | Black | 86,900 → 88,000 | Kamran Shah | BF-SEED11, BF-SEED10 |
| `LEH-2210` | Suzuki · Alto VXR · 2022 | Red | 18,500 | Zainab Malik | BF-SEED01 |
| `LEJ-5512` | Kia · Sportage AWD · 2022 | White | 27,300 | Zainab Malik | BF-SEED04 |
| `LEG-9146` | Toyota · Yaris ATIV · 2021 | Black | 35,600 → 36,800 | Nadia Iqbal | BF-SEED15, BF-SEED05 |
| `LEK-7731` | Honda · BR-V · 2019 | Blue | 61,000 | Nadia Iqbal | BF-SEED13 |
| `BKR-482` | Toyota · Corolla Altis · 2020 | Silver | 45,600 | Omar Farooq | BF-SEED12 |
| `BTA-317` | Suzuki · Wagon R · 2019 | White | 72,100 | Omar Farooq | BF-SEED14 |

Vehicles are created by the first booking that uses them (D35 upsert inside CREATE); later bookings reuse them. Each CREATE passes the mileage listed for that booking (in "Used by" order): the booking keeps it as its own snapshot `bookings.mileage_km` (D65), and the shared vehicle row ends with the latest value (D35). The worked-example plate `LEA-1234` is never seeded. **10 vehicles.**

## Sample bookings

### Summary

References are deterministic: `BF-SEED01` … `BF-SEED15` (see Idempotency). "Events" = `booking_events` rows the script produces (125 in total).

| Ref | Shop | Customer · vehicle | Services | Slot | Final status | Technician · Parts · QC | Estimate | Events |
|---|---|---|---|---|---|---|---|---|
| BF-SEED01 | Lahore Auto Care | Zainab · Alto `LEH-2210` | AC service, General inspection | `F(2)` 11:00 | `PENDING` | — | — | 1 |
| BF-SEED02 | Lahore Auto Care | Ayesha · Corolla `LEC-4521` | Suspension repair | `P(1)` 11:00 | `AWAITING_CUSTOMER` | Imran | v1 12,500 `SUPERSEDED` · **v2 12,000 `SENT`** | 7 |
| BF-SEED03 | Lahore Auto Care | Kamran · City `LEB-3307` | Brake failure | `P(3)` 09:00 | `PARTS_ORDERED` | Imran · Usman | v1 28,300 `REJECTED` · v2 27,300 `APPROVED` | 12 |
| BF-SEED04 | Lahore Auto Care | Zainab · Sportage `LEJ-5512` | Wheel alignment, Tire rotation | `P(1)` 09:00 | `IN_REPAIR` (labour-only, repair started) | Imran · Usman | v1 2,800 `APPROVED` | 11 |
| BF-SEED05 | Lahore Auto Care | Nadia · Yaris `LEG-9146` | Check engine light | `P(2)` 11:00 | `QC_PENDING` | Imran · Usman | v1 9,700 `APPROVED` | 12 |
| BF-SEED06 | Lahore Auto Care | Ayesha · Cultus `LEF-7809` | AC service | `P(2)` 12:00 | `READY_FOR_PICKUP` (customer **not yet notified**) | Hamza · Usman · Sara | v1 8,900 `APPROVED` | 14 |
| BF-SEED07 | Lahore Auto Care | Ayesha · Corolla `LEC-4521` | Brake failure | `P(8)` 09:00 | `COMPLETED` (one QC failure, re-test passed) | Imran · Usman · Sara (fail), Hina (pass) | v1 11,300 `APPROVED` | 20 |
| BF-SEED08 | Lahore Auto Care | Ayesha · Cultus `LEF-7809` | Battery replacement | `P(5)` 11:00 | `CANCELLED` by the customer in `PARTS_READY` (battery released) | Imran · Usman | v1 19,000 `APPROVED` | 10 |
| BF-SEED09 | Lahore Auto Care | Kamran · City `LEB-3307` | Brake failure | `P(5)` 09:00 | `CANCELLED` (declined by Bilal) | — | — | 2 |
| BF-SEED10 | Raza Auto Works | Kamran · Hilux `LES-8842` | Oil change, General inspection | `F(1)` 12:00 | `PENDING` | — | — | 1 |
| BF-SEED11 | Raza Auto Works | Kamran · Hilux `LES-8842` | Oil change | `P(10)` 11:00 | `COMPLETED` (completed by the SA) | Naveed · Faisal · Rabia | v1 12,400 `APPROVED` | 16 |
| BF-SEED12 | Clifton Car Clinic | Omar · Corolla Altis `BKR-482` | Check engine light | `F(1)` 15:00 | `PENDING` | — | — | 1 |
| BF-SEED13 | Margalla Motor Works | Nadia · BR-V `LEK-7731` | Brake failure | `F(3)` 11:00 | `PENDING` | — | — | 1 |
| BF-SEED14 | Pindi Auto Garage | Omar · Wagon R `BTA-317` | Tire rotation, Wheel alignment | `F(2)` 12:00 | `PENDING` | — | — | 1 |
| BF-SEED15 | Lyallpur Motors | Nadia · Yaris `LEG-9146` | Tire rotation | `P(11)` 10:00 | `COMPLETED` (labour-only) | Asad · Danish · Huma | v1 700 `APPROVED` | 16 |

Lahore Auto Care holds every status the brief's edge cases need: `PENDING`, `AWAITING_CUSTOMER`, `PARTS_ORDERED` (open PO, partial reservations), `IN_REPAIR`, `QC_PENDING`, `READY_FOR_PICKUP`, `COMPLETED` (with a QC failure), and two `CANCELLED` (customer cancellation with released stock; SA decline).

### Scripts — Lahore Auto Care

Each numbered step is one service call with its own commit. "PUT estimate" = the `EDIT_ESTIMATE` save (spec 08 O1) through `bookings.service.edit_estimate`; it writes a booking event only when it creates a new version. Every other action is `bookings.service.apply_staff_action` or, for the customer's steps, `apply_customer_action` ("Service functions the seed calls"). A customer's first booking by CREATE time uses the wizard's new-account path (D32, password `BayFlow@2026`, phone); later bookings use the logged-in path. The seed ignores any session token CREATE issues (D32); later steps use the actor context. Every CREATE payload carries the vehicle details and that booking's mileage from the vehicles table (D65). The rule is always: account missing → new-account path; present → logged-in path. Every action runs with real role, assignment and status guards.

Execution order (ascending CREATE time) on a typical run: BF-SEED15, BF-SEED11, BF-SEED07, BF-SEED08, BF-SEED09, BF-SEED03, BF-SEED05, BF-SEED06, BF-SEED02, BF-SEED04, then the five `PENDING` ones created on the evening of `P(1)`. So the first bookings are: Nadia BF-SEED15, Kamran BF-SEED11, Ayesha BF-SEED07, Zainab BF-SEED04, Omar BF-SEED12 or BF-SEED14. The order matters for stock only at Lahore Auto Care (BF-SEED07 before BF-SEED03 for brake pads and fluid), and it matches the timestamps, so the ledger reads correctly in time order.

**BF-SEED07 — `COMPLETED` with one QC failure** (Ayesha's first booking → creates her account)

| # | Time | Actor | Action | Payload / effect | Status after |
|---|---|---|---|---|---|
| 1 | `P(9)` 11:20 | Ayesha (new account) | CREATE | Corolla `LEC-4521`; Brake failure; notes "Brakes squeal and the car pulls to the left when braking."; slot `P(8)` 09:00 | `PENDING` |
| 2 | `P(9)` 11:45 | Bilal | `confirm` | — | `CONFIRMED` |
| 3 | `P(9)` 11:46 | Bilal | `assign-technician` | Imran | `ASSIGNED` |
| 4 | `P(8)` 09:20 | Imran | `start-inspection` | v1 `DRAFT` | `INSPECTING` |
| 5 | `P(8)` 10:25 | Imran | PUT estimate | Front brake pads (set) 1 @ 6,800; Brake fluid DOT 4 (1 L) 1 @ 1,500; Labour "Replace front pads and bleed brakes" 1 × 3,000 → **11,300** | `INSPECTING` |
| 6 | `P(8)` 10:30 | Imran | `submit-estimate` | notes "Front pads worn to 2 mm; brake fluid dark; discs within limits." | `ESTIMATE_REVIEW` |
| 7 | `P(8)` 11:00 | Bilal | `send-estimate` | v1 `SENT` (no edit) | `AWAITING_CUSTOMER` |
| 8 | `P(8)` 11:30 | Ayesha | `approve-estimate` | v1 `APPROVED` | `ESTIMATE_APPROVED` |
| 9 | `P(8)` 11:40 | Bilal | `assign-parts-person` | Usman; `booking_parts`: pads 1, fluid 1 | `PARTS_PENDING` |
| 10 | `P(8)` 12:00 | Usman | `mark-parts-ready` | reserve pads 1, fluid 1 | `PARTS_READY` |
| 11 | `P(8)` 12:10 | Usman | `allocate-parts` | consume pads 1, fluid 1 | `IN_REPAIR` |
| 12 | `P(8)` 12:30 | Imran | `start-repair` | — | `IN_REPAIR` |
| 13 | `P(8)` 15:30 | Imran | `send-to-qc` | "Pads replaced, system bled." | `QC_PENDING` |
| 14 | `P(8)` 15:45 | Sara | `pick-qc` | inspection 1 | `QC_IN_PROGRESS` |
| 15 | `P(8)` 16:15 | Sara | `fail-qc` | issue "Soft brake pedal" / "Pedal travel too long on the road test; air still in the brake lines." | `IN_REPAIR` |
| 16 | `P(8)` 16:30 | Imran | `start-repair` | — | `IN_REPAIR` |
| 17 | `P(8)` 17:15 | Imran | `send-to-qc` | "Re-bled all four wheels; pedal firm." → issue `RESOLVED` | `QC_PENDING` |
| 18 | `P(8)` 17:20 | Hina | `pick-qc` | inspection 2 | `QC_IN_PROGRESS` |
| 19 | `P(8)` 17:45 | Hina | `pass-qc` | all checklist items passed | `READY_FOR_PICKUP` |
| 20 | `P(8)` 17:50 | Bilal | `notify-ready` | `ready_notified_at` | `READY_FOR_PICKUP` |
| 21 | `P(7)` 10:15 | Ayesha | `complete` (customer endpoint, "mark pick-up") | `completed_at` | `COMPLETED` |

**BF-SEED08 — `CANCELLED` by the customer in `PARTS_READY`**

| # | Time | Actor | Action | Payload / effect | Status after |
|---|---|---|---|---|---|
| 1 | `P(6)` 09:10 | Ayesha | CREATE | Cultus `LEF-7809`; Battery replacement; notes "Car won't start on cold mornings."; slot `P(5)` 11:00 | `PENDING` |
| 2 | `P(6)` 09:30 | Bilal | `confirm` | — | `CONFIRMED` |
| 3 | `P(6)` 09:31 | Bilal | `assign-technician` | Imran | `ASSIGNED` |
| 4 | `P(5)` 11:15 | Imran | `start-inspection` | — | `INSPECTING` |
| 5 | `P(5)` 11:35 | Imran | PUT estimate | Battery 12V 45Ah 1 @ 18,500; Labour "Battery and charging test, fit new battery" 1 × 500 → **19,000** | `INSPECTING` |
| 6 | `P(5)` 11:40 | Imran | `submit-estimate` | "Battery fails the load test (9.6 V); alternator charging OK." | `ESTIMATE_REVIEW` |
| 7 | `P(5)` 12:00 | Bilal | `send-estimate` | v1 `SENT` | `AWAITING_CUSTOMER` |
| 8 | `P(5)` 12:20 | Ayesha | `approve-estimate` | v1 `APPROVED` | `ESTIMATE_APPROVED` |
| 9 | `P(5)` 12:25 | Bilal | `assign-parts-person` | Usman; battery 1 | `PARTS_PENDING` |
| 10 | `P(5)` 12:40 | Usman | `mark-parts-ready` | reserve battery 1 (3/1) | `PARTS_READY` |
| 11 | `P(5)` 13:05 | Ayesha | `cancel` (customer endpoint) | reason "I got a battery under warranty from the dealer." → battery released (3/0, `RELEASE`); slot counter −1; v1 stays `APPROVED` (final) | `CANCELLED` |

**BF-SEED09 — declined by the SA** (Kamran's account already exists from BF-SEED11)

| # | Time | Actor | Action | Payload / effect | Status after |
|---|---|---|---|---|---|
| 1 | `P(6)` 10:00 | Kamran | CREATE | City `LEB-3307`; Brake failure; notes "Grinding noise when braking."; slot `P(5)` 09:00 | `PENDING` |
| 2 | `P(6)` 10:30 | Bilal | `decline` | reason "Both bays are booked for an engine job that morning — please choose another day." → slot counter −1 | `CANCELLED` |

**BF-SEED03 — `PARTS_ORDERED` with a rejected-then-revised estimate** (Kamran rebooked after the decline)

| # | Time | Actor | Action | Payload / effect | Status after |
|---|---|---|---|---|---|
| 1 | `P(4)` 12:00 | Kamran | CREATE | City `LEB-3307`; Brake failure; notes "Grinding noise when braking; pedal vibrates."; slot `P(3)` 09:00 | `PENDING` |
| 2 | `P(4)` 12:30 | Bilal | `confirm` | — | `CONFIRMED` |
| 3 | `P(4)` 12:31 | Bilal | `assign-technician` | Imran | `ASSIGNED` |
| 4 | `P(3)` 09:15 | Imran | `start-inspection` | — | `INSPECTING` |
| 5 | `P(3)` 10:25 | Imran | PUT estimate | Front brake pads (set) 1 @ 6,800; Front brake disc 2 @ 7,500; Brake fluid DOT 4 (1 L) 1 @ 1,500; Labour "Replace front discs and pads, bleed brakes" 1 × 5,000 → **28,300** | `INSPECTING` |
| 6 | `P(3)` 10:30 | Imran | `submit-estimate` | "Front discs below minimum thickness; pads worn to the backing plate." | `ESTIMATE_REVIEW` |
| 7 | `P(3)` 11:00 | Bilal | `send-estimate` | v1 `SENT` | `AWAITING_CUSTOMER` |
| 8 | `P(3)` 12:10 | Kamran | `reject-estimate` | reason "Labour seems high compared to other quotes." → v1 `REJECTED` | `ESTIMATE_REJECTED` |
| 9 | `P(3)` 12:30 | Bilal | `revise-estimate` | v2 `DRAFT` copied from v1 (author Bilal) | `ESTIMATE_REVIEW` |
| 10 | `P(3)` 12:35 | Bilal | PUT estimate | labour 5,000 → 4,000 → **27,300** (updates v2; no event) | `ESTIMATE_REVIEW` |
| 11 | `P(3)` 12:40 | Bilal | `send-estimate` | v2 `SENT` | `AWAITING_CUSTOMER` |
| 12 | `P(3)` 13:15 | Kamran | `approve-estimate` | v2 `APPROVED` | `ESTIMATE_APPROVED` |
| 13 | `P(3)` 13:20 | Bilal | `assign-parts-person` | Usman; `booking_parts`: pads 1, disc 2, fluid 1 | `PARTS_PENDING` |
| 14 | `P(3)` 13:40 | Usman | `order-parts` | reserve pads 1 + fluid 1 (available now); disc short 2 → PO `ORDERED` linked to this booking: Front brake disc 2, supplier "City Auto Parts (demo)" | `PARTS_ORDERED` |

**BF-SEED05 — `QC_PENDING`** (Nadia's account already exists from BF-SEED15)

| # | Time | Actor | Action | Payload / effect | Status after |
|---|---|---|---|---|---|
| 1 | `P(3)` 10:00 | Nadia | CREATE | Yaris `LEG-9146`; Check engine light; notes "Engine light came on after refuelling; hesitates when accelerating."; slot `P(2)` 11:00 | `PENDING` |
| 2 | `P(3)` 10:20 | Bilal | `confirm` | — | `CONFIRMED` |
| 3 | `P(3)` 10:21 | Bilal | `assign-technician` | Imran | `ASSIGNED` |
| 4 | `P(2)` 11:10 | Imran | `start-inspection` | — | `INSPECTING` |
| 5 | `P(2)` 11:55 | Imran | PUT estimate | Spark plug (iridium) 4 @ 1,800; Labour "OBD scan, spark plug replacement, throttle body cleaning" 1 × 2,500 → **9,700** | `INSPECTING` |
| 6 | `P(2)` 12:00 | Imran | `submit-estimate` | "Code P0302 (misfire, cylinder 2); plugs worn." | `ESTIMATE_REVIEW` |
| 7 | `P(2)` 12:15 | Bilal | `send-estimate` | v1 `SENT` | `AWAITING_CUSTOMER` |
| 8 | `P(2)` 13:00 | Nadia | `approve-estimate` | v1 `APPROVED` | `ESTIMATE_APPROVED` |
| 9 | `P(2)` 13:05 | Bilal | `assign-parts-person` | Usman; spark plugs 4 | `PARTS_PENDING` |
| 10 | `P(2)` 13:20 | Usman | `mark-parts-ready` | reserve 4 plugs | `PARTS_READY` |
| 11 | `P(2)` 13:25 | Usman | `allocate-parts` | consume 4 plugs | `IN_REPAIR` |
| 12 | `P(2)` 14:00 | Imran | `start-repair` | — | `IN_REPAIR` |
| 13 | `P(1)` 16:40 | Imran | `send-to-qc` | "Plugs replaced, codes cleared, no misfire on a 10 km test." | `QC_PENDING` |

**BF-SEED06 — `READY_FOR_PICKUP`, not yet notified**

| # | Time | Actor | Action | Payload / effect | Status after |
|---|---|---|---|---|---|
| 1 | `P(3)` 21:10 | Ayesha | CREATE | Cultus `LEF-7809`; AC service; notes "AC blows warm air in the afternoon."; slot `P(2)` 12:00 | `PENDING` |
| 2 | `P(2)` 09:05 | Bilal | `confirm` | — | `CONFIRMED` |
| 3 | `P(2)` 09:06 | Bilal | `assign-technician` | **Hamza** | `ASSIGNED` |
| 4 | `P(2)` 12:10 | Hamza | `start-inspection` | — | `INSPECTING` |
| 5 | `P(2)` 12:45 | Hamza | PUT estimate | AC gas R134a (can) 1 @ 3,000; Cabin AC filter 1 @ 1,400; Labour "AC leak test, recharge and condenser cleaning" 1 × 4,500 → **8,900** | `INSPECTING` |
| 6 | `P(2)` 12:50 | Hamza | `submit-estimate` | "Low gas pressure; no leak found with UV dye; cabin filter clogged." | `ESTIMATE_REVIEW` |
| 7 | `P(2)` 13:10 | Bilal | `send-estimate` | v1 `SENT` | `AWAITING_CUSTOMER` |
| 8 | `P(2)` 13:30 | Ayesha | `approve-estimate` | v1 `APPROVED` | `ESTIMATE_APPROVED` |
| 9 | `P(2)` 13:35 | Bilal | `assign-parts-person` | Usman; gas 1, cabin filter 1 | `PARTS_PENDING` |
| 10 | `P(2)` 13:50 | Usman | `mark-parts-ready` | reserve both | `PARTS_READY` |
| 11 | `P(2)` 14:00 | Usman | `allocate-parts` | consume both | `IN_REPAIR` |
| 12 | `P(2)` 14:10 | Hamza | `start-repair` | — | `IN_REPAIR` |
| 13 | `P(2)` 16:30 | Hamza | `send-to-qc` | "Recharged to spec; vent temperature 6 °C." | `QC_PENDING` |
| 14 | `P(1)` 09:20 | Sara | `pick-qc` | — | `QC_IN_PROGRESS` |
| 15 | `P(1)` 09:50 | Sara | `pass-qc` | all checklist items passed; notes "Cooling OK after a 20-minute road test." | `READY_FOR_PICKUP` |

`notify-ready` is intentionally **not** performed, so a judge can do it as Bilal (spec 06 S6) and see `VEHICLE_READY` arrive for Ayesha.

**BF-SEED02 — `AWAITING_CUSTOMER`, revision 2 waiting for Ayesha**

| # | Time | Actor | Action | Payload / effect | Status after |
|---|---|---|---|---|---|
| 1 | `P(2)` 09:30 | Ayesha | CREATE | Corolla `LEC-4521`; Suspension repair (no base price); notes "Knocking from the front left over speed breakers."; slot `P(1)` 11:00 | `PENDING` |
| 2 | `P(2)` 10:00 | Bilal | `confirm` | — | `CONFIRMED` |
| 3 | `P(2)` 10:01 | Bilal | `assign-technician` | Imran | `ASSIGNED` |
| 4 | `P(1)` 11:10 | Imran | `start-inspection` | — | `INSPECTING` |
| 5 | `P(1)` 11:55 | Imran | PUT estimate | Front stabilizer link 2 @ 4,500; Labour "Replace both front stabilizer links + alignment check" 1 × 3,500 → **12,500** | `INSPECTING` |
| 6 | `P(1)` 12:00 | Imran | `submit-estimate` | "Both front stabilizer links have play; bushes OK." | `ESTIMATE_REVIEW` |
| 7 | `P(1)` 12:20 | Bilal | PUT estimate | labour 3,500 → 3,000 → v2 `DRAFT` **12,000**; v1 `SUPERSEDED` (`EDIT_ESTIMATE` event) | `ESTIMATE_REVIEW` |
| 8 | `P(1)` 12:25 | Bilal | `send-estimate` | v2 `SENT` | `AWAITING_CUSTOMER` |

No parts are reserved yet; stabilizer links are reserved only after approval (T12–T14).

**BF-SEED04 — labour-only job in repair (D31)** (Zainab's first booking → creates her account)

| # | Time | Actor | Action | Payload / effect | Status after |
|---|---|---|---|---|---|
| 1 | `P(2)` 16:00 | Zainab (new account) | CREATE | Sportage `LEJ-5512`; Wheel alignment + Tire rotation; notes "Steering wheel off-centre after a pothole; car pulls left."; slot `P(1)` 09:00 | `PENDING` |
| 2 | `P(2)` 16:20 | Bilal | `confirm` | — | `CONFIRMED` |
| 3 | `P(2)` 16:21 | Bilal | `assign-technician` | Imran | `ASSIGNED` |
| 4 | `P(1)` 09:10 | Imran | `start-inspection` | — | `INSPECTING` |
| 5 | `P(1)` 09:35 | Imran | PUT estimate | Labour "Four-wheel alignment" 1 × 2,000; Labour "Tire rotation" 1 × 800 → **2,800** | `INSPECTING` |
| 6 | `P(1)` 09:40 | Imran | `submit-estimate` | "Front toe out of spec; no suspension damage." | `ESTIMATE_REVIEW` |
| 7 | `P(1)` 09:50 | Bilal | `send-estimate` | v1 `SENT` | `AWAITING_CUSTOMER` |
| 8 | `P(1)` 10:05 | Zainab | `approve-estimate` | v1 `APPROVED` | `ESTIMATE_APPROVED` |
| 9 | `P(1)` 10:10 | Bilal | `assign-parts-person` | Usman; no `booking_parts` rows | `PARTS_PENDING` |
| 10 | `P(1)` 10:15 | Usman | `mark-parts-ready` | nothing to reserve | `PARTS_READY` |
| 11 | `P(1)` 10:16 | Usman | `allocate-parts` | nothing consumed | `IN_REPAIR` |
| 12 | `P(1)` 10:30 | Imran | `start-repair` | `repair_started_at` | `IN_REPAIR` |

**BF-SEED01 — `PENDING`, one place left in its slot**

| # | Time | Actor | Action | Payload / effect | Status after |
|---|---|---|---|---|---|
| 1 | `P(1)` 20:15 | Zainab | CREATE | Alto `LEH-2210`; AC service + General inspection; notes "AC not cooling well; want a full check before a trip to Murree."; slot **`F(2)` 11:00** (1 of 2 places used — the slot-conflict demo, spec 06 E5) | `PENDING` |

### Scripts — other shops (compact)

| Ref | Steps (actor: action) | Key data |
|---|---|---|
| BF-SEED15 (Lyallpur Motors) | `P(12)` 10:00 Nadia (new account): CREATE → 10:30 Mariam: `confirm` → 10:31 Mariam: `assign-technician` Asad → `P(11)` 10:05 Asad: `start-inspection` → 10:15 PUT estimate → 10:20 `submit-estimate` → 10:25 Mariam: `send-estimate` → 10:40 Nadia: `approve-estimate` → 10:45 Mariam: `assign-parts-person` Danish → 10:46 Danish: `mark-parts-ready` → 10:47 `allocate-parts` (labour-only, nothing reserved or consumed) → 10:50 Asad: `start-repair` → 11:20 `send-to-qc` → 11:25 Huma: `pick-qc` → 11:35 `pass-qc` → 11:40 Mariam: `notify-ready` → 17:00 Nadia: `complete` | Yaris `LEG-9146`; Tire rotation; slot `P(11)` 10:00; Labour "Tire rotation" 1 × 700 → **700** |
| BF-SEED11 (Raza Auto Works) | `P(11)` 18:00 Kamran (new account): CREATE → `P(10)` 10:05 Adeel: `confirm` → 10:06 `assign-technician` Naveed → 11:10 Naveed: `start-inspection` → 11:25 PUT estimate → 11:30 `submit-estimate` → 11:40 Adeel: `send-estimate` → 11:55 Kamran: `approve-estimate` → 12:00 Adeel: `assign-parts-person` Faisal → 12:05 Faisal: `mark-parts-ready` → 12:10 `allocate-parts` → 12:15 Naveed: `start-repair` → 13:00 `send-to-qc` → 13:10 Rabia: `pick-qc` → 13:30 `pass-qc` → 13:35 Adeel: `notify-ready` → 16:00 Adeel: `complete` (staff endpoint) | Hilux `LES-8842`; Oil change; slot `P(10)` 11:00; Oil filter 1 @ 900, Engine oil 4 L 2 @ 5,200, Labour "Oil change" 1 × 1,100 → **12,400**; Raza Auto Works stock: filter 8 → 7, oil 10 → 8 |
| BF-SEED10 (Raza Auto Works) | `P(1)` 17:30 Kamran (logged in): CREATE | Hilux `LES-8842`; Oil change + General inspection; notes "Due for the 90,000 km service."; slot `F(1)` 12:00 |
| BF-SEED12 (Clifton Car Clinic) | `P(1)` 21:00 Omar: CREATE | Corolla Altis `BKR-482`; Check engine light; notes "Engine light on since the weekend."; slot `F(1)` 15:00 |
| BF-SEED13 (Margalla Motor Works) | `P(1)` 19:00 Nadia (logged in): CREATE | BR-V `LEK-7731`; Brake failure; notes "Brake warning light flickers on downhill roads."; slot `F(3)` 11:00 |
| BF-SEED14 (Pindi Auto Garage) | `P(1)` 18:30 Omar: CREATE | Wagon R `BTA-317`; Tire rotation + Wheel alignment; notes "Car pulls to the right."; slot `F(2)` 12:00 (Pindi's open days include Sunday: 12:00 fits Sunday's 10:00–14:00) |

`P(n)`/`F(n)` are computed per shop from its own hours. Omar's first booking by CREATE time creates his account; the other uses the logged-in path.

## Notifications after seeding

The actions above create notification rows exactly as live actions would (glossary §6). To avoid a wall of stale unread items, the seed then marks them read through the notifications service (`read_at` = `run_now` from the `SimulatedClock`, D63), **except** the latest notification per (recipient, booking) when the recipient currently owns the booking's next step. "Owns the next step" = SAs of the shop for `PENDING`, `CONFIRMED`, `ESTIMATE_REVIEW`, `ESTIMATE_APPROVED`, `ESTIMATE_REJECTED`, `READY_FOR_PICKUP`; the assigned technician for `ASSIGNED`, `INSPECTING`, `IN_REPAIR`; the customer for `AWAITING_CUSTOMER`; the assigned parts person for `PARTS_*`; all QC inspectors for `QC_PENDING`; the picker for `QC_IN_PROGRESS`; nobody for terminal statuses. The rule is applied only to the notifications of sample bookings completed in the current run, so later runs never touch what judges have read or not read.

### What each demo account sees on first login

The first screen follows the normal login routing: `POST /api/v1/auth/login` returns the token and the user only, the web then reads the memberships from `GET /api/v1/me` (D81) and opens the POS for staff and owners (Fatima's first `OWNER` shop by name, Lahore Auto Care) or My bookings for customers (spec 09 `resolveHome`). Counts are as seeded, before any judge or smoke run.

| Account | First screen | Unread |
|---|---|---|
| Ayesha | My bookings: **BF-SEED02 "Estimate awaiting your approval" (PKR 12,000, revision 2)** pinned on top; BF-SEED06 "Ready for pick-up"; BF-SEED07 Completed; BF-SEED08 Cancelled | 1 — `ESTIMATE_SENT` (BF-SEED02) |
| Bilal | Bookings board, 9 bookings: Pending 1 (BF-SEED01), Awaiting customer 1, Parts ordered 1, In repair 1, QC pending 1, Ready for pick-up 1 (not notified), Completed 1, Cancelled 2 | 2 — `BOOKING_CREATED` (BF-SEED01), `QC_PASSED` (BF-SEED06) |
| Imran | My jobs: In repair BF-SEED04 (labour-only, send to QC); Waiting BF-SEED02, BF-SEED03, BF-SEED05; Done BF-SEED07, BF-SEED08 | 1 — `PARTS_READY` (BF-SEED04) |
| Hamza | My jobs: Done BF-SEED06 | 0 |
| Usman | Parts queue: BF-SEED03 (`PARTS_ORDERED`, 2 discs on order); Inventory with 3 OUT / 3 LOW; Purchase orders: `ORDERED`, `PARTIALLY_RECEIVED`, `RECEIVED` | 1 — `PARTS_NEEDED` (BF-SEED03) |
| Sara | QC queue: BF-SEED05 waiting; history BF-SEED06 (pass), BF-SEED07 (fail) | 1 — `QC_REQUESTED` (BF-SEED05) |
| Hina | QC queue: BF-SEED05 waiting; history BF-SEED07 (re-test pass) | 1 — `QC_REQUESTED` (BF-SEED05) |
| Fatima | Overview of Lahore Auto Care (9 bookings by status, team of 7, inventory 3 OUT / 3 LOW, 2 open POs); switcher → Raza Auto Works (2 bookings, team of 5) | 0 (both shops have an active SA, D26) |
| SA of each other shop | Their own bookings only: a `PENDING` one (Raza Auto Works also has a `COMPLETED` one; Lyallpur Motors only a `COMPLETED` one) | 1 at Raza Auto Works, Clifton Car Clinic, Margalla Motor Works and Pindi Auto Garage; 0 at Lyallpur Motors (until smoke runs add theirs: it is the smoke-test shop) |

Lahore Auto Care is the demo shop. Technician, QC and parts dashboards at the other shops are intentionally sparse.

## Worked-example readiness

- **Stock:** no sample booking or seeded PO touches `FLT-OIL-01`, `OIL-4L-01` or `IGN-COIL-01` at Lahore Auto Care, so a judge starts from **10/0, 8/0, 0/0** — the coil shortage triggers the PO path (spec 08 reservations example; spec 06 §7). Brake, AC, battery, spark-plug and suspension parts carry the sample activity instead.
- **Slots:** the only future sample booking at Lahore Auto Care is BF-SEED01 at `F(2)` 11:00. Every Friday 10:00 slot starts empty, with 2 places.
- **Many judges (accepted drift, D71):** each complete replay consumes 1 oil filter and 1 engine oil and leaves the coil at 0 (received 1, consumed 1). After about 8 replays the oil runs out too; `order-parts` then orders oil as well — still the PO path, still a working flow. Two replays fill one Friday's 10:00 slot (capacity 2); later testers take the next Friday (four within the 30-day horizon) or another time.
- **Drift (D71):** if a tester cancels in `PARTS_ORDERED` and someone later receives that orphan coil PO, the coil becomes general stock (D24), and the next replay takes the "parts already in stock" path. Fix through the product, not the seed: Usman uses **Adjust stock** (spec 06 P7; P0 for exactly this drift correction, D82) to set the coil back to 0 — possible only while no job has reserved it, because an adjustment below `reserved` or below zero returns 409 `INSUFFICIENT_STOCK` — or simply demonstrates E2.
- **No top-ups by design:** the seed never changes existing stock, even when judges deplete it — D60's reconciliation repairs accounts and memberships only. Restocking goes through a general PO or an adjustment by the Parts Person (D82), recorded in the ledger like any real change.
- **Automation stays away:** every automated run against the live URL (spec 07 `scripts/smoke.sh`, spec 12 DEP-10 and WEB-08) books at the smoke-test shop Lyallpur Motors (see Shops), so only people ever change Lahore Auto Care's stock, slots and bookings.

## Idempotency mechanics

| Entity | Natural key (existence check) | If it exists | If it is missing |
|---|---|---|---|
| User | e-mail (stored lower-case, `uq_users_email`, spec 02) | Name and phone untouched. **Reconciled (D60, Phase R):** made active again if inactive, and its password hash replaced when it no longer verifies `BayFlow@2026`. Accounts the seed does not define are never touched. When the seed links an already-existing account to something it is creating now (a shop, membership or sample booking), it reuses the account and logs a note | Owners via the owner-registration service; staff via add-member as the owner (creates the user, D18); customers via the wizard path of their first sample booking (D32) |
| Shop | `slug` (`uq_shops_slug`) | Untouched — settings, hours, slot duration/capacity, rating, listing are never reverted | Created as its owner; the seed asserts the created slug equals the expected one (a mismatch aborts the run, preventing duplicates later); rating set |
| Working hours | `(shop_id, weekday)` | All 7 rows are created together with a new shop and never touched again, so the seed never reopens a day an owner closed | — |
| Membership | `(shop_id, user_id)` (`uq_shop_memberships_shop_id_user_id`) | **Reconciled (D60, Phase R):** reactivated if inactive and set back to its canonical role if changed, as the shop's Owner. Memberships the seed does not define (e.g. a judge's shop that added a demo user) are never touched | Added by the owner (add-member creates the user and the membership in one use case) |
| Service | `(shop_id, lower(name))` over **all** rows, active or not | Untouched (price, active flag). Checking inactive rows too matters: spec 02's unique index covers active names only, so a deactivated seeded service would otherwise be recreated | Created by the owner |
| Part | `(shop_id, sku)` (`uq_parts_shop_id_sku`) | Untouched — **no stock top-up** | Created by the shop's Parts Person; opening quantity as one `ADJUST` movement right after (a part found with zero movements and a non-zero opening quantity in the seed data gets its movement on the next run) |
| General PO | `(shop_id, po_number)` (`PO-SEED01`, `PO-SEED02`; unique per shop, spec 02) | Receipts still missing from its script are applied; otherwise untouched | Created and received per its script, by Usman |
| Sample booking | `reference` (`BF-SEED01` … `BF-SEED15`; `uq_bookings_reference` is global, spec 02) | Compare its `booking_events`, in order, with the script's expected events (action and actor): **complete** — the first N events are the script's N events (anything judges did afterwards is ignored) → skip; **incomplete** — fewer events, all matching the script → resume at the next step (a repeated "PUT estimate" is harmless: it replaces the lines with the same lines); **diverged** — an event that is not the script's (someone acted on a half-built booking) → skip with a warning. Never reset, never re-run from scratch | The whole script, step by step |
| Vehicle | `(owner_user_id, registration_key)` (D35) | Reused by CREATE | Created by CREATE |
| Notification read state | — | Applied only to sample bookings completed in the current run | — |

**Reserved references.** Sample bookings get deterministic references `BF-SEED01` … `BF-SEED15`. `S`, `E`, `D` and the digits all belong to the Crockford alphabet of glossary §1, so the format `BF-XXXXXX` and spec 02's format checks (e.g. `^PO-[0-9A-HJKMNP-TV-Z]{6}$`) still hold. General POs use `PO-SEED01`, `PO-SEED02`. To make the keys collision-proof, the random code generators (spec 02 "Generated codes") never emit a code starting with `SEED`. The seed passes these values through an internal keyword argument of the create functions; it is not part of any HTTP schema (spec 04: the wizard body rejects `reference` with `extra="forbid"`). No new column is needed. Booking-linked POs created by `order-parts` keep random numbers; they are covered by their booking's key.

Seeded e-mails are claimed on the first deploy, before the URL is shared, so "someone registered a seeded e-mail first" is not a practical risk; the log note exists only to make it visible. (It matters more under D60: such an account would also be reset to the demo password, which is one more reason the first deploy seeds before the URL is shared.)

**When the seed runs again after judges changed data:**

| Judges did… | Next seed run |
|---|---|
| Approved/rejected BF-SEED02, received BF-SEED03's PO, picked BF-SEED05, completed BF-SEED06 | Nothing — those scripts are complete; the extra events are the judges' and are ignored. No reset, no duplicates |
| Deactivated Hamza, changed Imran's role to `SERVICE_ADVISOR` | **Repaired (D60):** Hamza's membership is active again and Imran is `TECHNICIAN` again (done as Fatima, the Owner). Bookings assigned meanwhile are not changed |
| Changed a demo account's password, or a demo user ended up inactive | **Repaired (D60):** user active again; password hash reset so `BayFlow@2026` works |
| Changed Lahore Auto Care's hours or capacity, a service price, a part's cost | Untouched |
| Consumed stock, received POs, adjusted stock | Untouched (no top-up) |
| Registered new owners, shops, customers, bookings — including memberships of demo users in judges' own shops | Not seed-keyed → untouched |
| A new sample is added to `seed_data.py` in a later commit | Created on the next deploy, dated relative to that run |

The seed deletes nothing, ever.

### Demo-cast reconciliation (D60)

Shared demo accounts can be broken by one judge (e.g. by deactivating Bilal), and "insert only what is missing" alone would never repair them. So every run — including the pre-deploy run of every Railway redeploy (`SEED_ON_DEPLOY=true` there, spec 07), which is how the team repairs the cast during judging — performs Phase R over the **demo cast**: the 36 accounts and 32 memberships defined in `seed_data.py` (see "Accounts"). It writes only what differs, so a run with nothing to repair changes no row.

| Check (existing rows only) | Repair | Performed as / through |
|---|---|---|
| `users.is_active` is false | Set it back to true | `identity.service.set_user_active`, an internal function not exposed over HTTP (like `set_rating`) |
| `identity.service.password_matches(user_id, "BayFlow@2026")` is false (password changed, or the hash is unusable; it runs `verify_password` on the stored hash) | Store a fresh Argon2id hash of `BayFlow@2026` (D10) | `identity.service.set_password`, internal like the above. D18 still holds for add-member: an owner adding an existing e-mail never changes its password; only this seed step resets passwords, and only for the demo cast |
| Membership inactive, or role ≠ its canonical role | Reactivate it and/or restore the role | The shop's **Owner** (Fatima at Lahore Auto Care and Raza Auto Works) through the same update-member service function as `PATCH /api/v1/shops/{shop_id}/members/{membership_id}`, so it is validated and logged like an owner's change. `OWNER` memberships never need it: they cannot be deactivated or re-roled (D19) |
| Account or membership missing | Not this phase's job: Phase A creates owners and staff, Phase B creates customers through the wizard path | — |

Users are reconciled before memberships, so the acting Owner is always active. Never touched: names and phones; accounts and memberships the seed does not define; and everything outside `users` and `shop_memberships` — bookings (assignments included, D19), estimates, inventory, POs, services, shop settings and notifications. The verification (`password_matches`, one `verify_password` call per demo account, a few seconds per run) bypasses the login path, so it never counts as a failed login for the per-account limiter (D69). Each repair is logged with the e-mail and what changed, never the password. Covered by SEED-19.

## Commands

Makefile targets, Compose services and the pre-deploy command are owned by [07-deployment-and-docs.md](07-deployment-and-docs.md); this table restates them for the seed.

| Command | Where | What it does |
|---|---|---|
| `python -m app.scripts.seed` | Railway pre-deploy (D13): `/bin/sh -c "alembic upgrade head && python -m app.scripts.seed"`; Compose `migrate` service | Seeds only when `SEED_ON_DEPLOY=true` (otherwise logs `seed skipped (SEED_ON_DEPLOY is not true)` and exits 0, spec 07); idempotent; reconciles the demo cast (D60), so a manual redeploy repairs broken demo accounts; exits non-zero if any unit failed (stops the deploy) |
| `./start.sh` / `start.bat` (`--seed` optional) | Local, native (D73, amended) | After `alembic upgrade head` it **always** runs `python -m app.scripts.seed`, which acts when `SEED_ON_DEPLOY=true` — `.env.example` sets it for local development — so a fresh local database gets the demo data and later starts only repair the demo cast; `--seed` passes `--force` (spec 07) |
| `python -m app.scripts.seed --force` | Any environment, run by a human | Seeds regardless of `SEED_ON_DEPLOY` |
| `make seed` | Local | `cd apps/api && uv run python -m app.scripts.seed --force` (spec 07) |
| `make db-reset` | **Local only** | Spec 07's recipe: the guard below, then `docker compose exec db psql -U bayflow -d bayflow -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"`, then `make migrate seed` |

Guard on the destructive reset (spec 07):

1. **Refusal before the drop:** the recipe exits with code 2 and changes nothing when `APP_ENV` (from the shell or the root `.env`) is `production`, or when the `DATABASE_URL` host is not local (`localhost`, `127.0.0.1`, `::1`, `db`). The host check matters because the follow-up `make migrate seed` uses `DATABASE_URL`: harmless in itself (migrations, an idempotent seed and the D60 reconciliation), but a "local reset" must never touch a remote database.
2. **Structural:** the drop itself runs *inside the local Compose `db` container* through `docker compose exec`, so it can never reach the Railway database, whatever `DATABASE_URL` says.

The seed itself needs no guard: it never deletes.

## README demo-credentials block (paste as is)

````markdown
## Demo accounts

All demo accounts use the password **`BayFlow@2026`**. The worked example from the brief (§6) runs at **Lahore Auto Care**.

| Role | Name | E-mail | Password | Shop |
|---|---|---|---|---|
| Owner | Fatima Raza | `fatima.owner@bayflow.test` | `BayFlow@2026` | Lahore Auto Care **and** Raza Auto Works (shop switcher) |
| Service Advisor | Bilal | `bilal.sa@bayflow.test` | `BayFlow@2026` | Lahore Auto Care |
| Technician | Imran | `imran.tech@bayflow.test` | `BayFlow@2026` | Lahore Auto Care |
| QC Inspector | Sara | `sara.qc@bayflow.test` | `BayFlow@2026` | Lahore Auto Care |
| Parts Person | Usman | `usman.parts@bayflow.test` | `BayFlow@2026` | Lahore Auto Care |
| Customer | Ayesha Khan | `ayesha.customer@bayflow.test` | `BayFlow@2026` | — (sample bookings at Lahore Auto Care) |
| Technician (2nd) | Hamza | `hamza.tech@bayflow.test` | `BayFlow@2026` | Lahore Auto Care |
| QC Inspector (2nd) | Hina | `hina.qc@bayflow.test` | `BayFlow@2026` | Lahore Auto Care |
| New customer (you) | Ahmed in the brief | a **fresh `.test` address**, e.g. `ahmed1@bayflow.test` | your own, at least 12 characters | — (the booking wizard creates the account; see judge note 1) |

**Every other shop has its own full team.** Log in as `<role>.<shop-slug>@bayflow.test`, where `<role>` is `owner`, `sa`, `tech`, `qc` or `parts` (Raza Auto Works is owned by Fatima, so it has no `owner.` account). Same password.

| Shop | City | Slug | Example |
|---|---|---|---|
| Raza Auto Works | Lahore | `raza-auto-works` | `sa.raza-auto-works@bayflow.test` |
| Clifton Car Clinic | Karachi | `clifton-car-clinic` | `sa.clifton-car-clinic@bayflow.test` |
| Margalla Motor Works | Islamabad | `margalla-motor-works` | `tech.margalla-motor-works@bayflow.test` |
| Pindi Auto Garage | Rawalpindi | `pindi-auto-garage` | `parts.pindi-auto-garage@bayflow.test` |
| Lyallpur Motors | Faisalabad | `lyallpur-motors` | `qc.lyallpur-motors@bayflow.test` |

More customers (same password): `kamran.customer@bayflow.test`, `zainab.customer@bayflow.test`, `nadia.customer@bayflow.test`, `omar.customer@bayflow.test`.

### Sample bookings at Lahore Auto Care

| Reference | Status | Open it as | Try this |
|---|---|---|---|
| BF-SEED01 | `PENDING` | Bilal | Confirm → assign a technician, or Decline with a reason. Its slot has 1 place left: race for it from two browsers |
| BF-SEED02 | `AWAITING_CUSTOMER` | Ayesha | Approve, or Decline estimate → then as Bilal: Revise estimate, or Return to technician |
| BF-SEED03 | `PARTS_ORDERED` | Usman | Receive the linked PO one disc at a time (stays `PARTS_ORDERED`, then `PARTS_READY`) → Allocate |
| BF-SEED04 | `IN_REPAIR` (labour-only) | Imran | Send to QC |
| BF-SEED05 | `QC_PENDING` | Sara **and** Hina, two browsers | Both click Pick — only one wins (409) — then Fail or Pass |
| BF-SEED06 | `READY_FOR_PICKUP` | Bilal, then Ayesha | Notify customer → as Ayesha: "I've collected my vehicle" |
| BF-SEED07 | `COMPLETED` | anyone | Full history, including a failed QC and the re-test |
| BF-SEED08 / BF-SEED09 | `CANCELLED` | Bilal | Customer cancellation (reserved battery released) / SA decline with reason |

### Judge notes

1. **Replay the worked example with a fresh `.test` customer e-mail** that nobody has used on the site, e.g. `ahmed1@bayflow.test` (if it is taken, add a number or your initials: `ahmed7@bayflow.test`, `ahmed.hr@bayflow.test`), and a password of at least 12 characters. `.test` addresses are accepted and are never e-mailed, so no real inbox is involved — please don't use addresses at real providers such as `@mail.com`. Reusing an address someone else registered returns "e-mail already registered". (Only if you want to see the optional e-mail and it is enabled on the live site: use an inbox you own — anyone logged in as that shop's staff will see the address.)
2. **`ahmed@mail.com` is not seeded.** The wizard creates the customer account during booking (brief §5.1). Please don't book with it: `mail.com` is a real e-mail provider.
3. **Seeded bookings, stock and slots are shared and never reset.** Once someone moves BF-SEED02 forward, it stays moved, and every replay uses stock and a place in its slot. For a guaranteed clean run, replay the worked example with a fresh customer.
4. **Use one browser profile per person** (e.g. Chrome, Chrome Incognito, Firefox, Firefox Private). Tabs of the same profile share one session, so logging in as Bilal in a second tab logs the customer out of the first.
5. **Friday 10:00 full?** Two testers already booked it — pick the next Friday or another time.
6. **Ignition coil already in stock?** A tester received an orphaned coil order. As Usman, use Adjust stock to set it back to 0 to see the purchase-order path (this works only while no job has reserved the coil — otherwise the adjustment is refused), or continue (the flow takes the "parts already in stock" path).
7. **Please don't deactivate the shared accounts** (Bilal, Imran, Sara, Usman). To test deactivation, use Hamza or Hina, and reactivate afterwards. If a demo account stops working anyway (deactivated, role or password changed), the next seed run — every deploy runs it — repairs it: demo accounts and memberships active again, roles restored, password back to `BayFlow@2026`. Bookings, stock, purchase orders and shop settings are never reset.
8. API docs (Swagger): `<api-url>/docs`. Log in with `POST /api/v1/auth/login` (it returns the token and your user), copy `access_token`, click Authorize; `GET /api/v1/me` then lists your shops, roles and capabilities.
9. **Lyallpur Motors is the smoke-test shop.** Automated post-deploy checks book there, and only there, with throw-away `smoke+…@bayflow.test` customers, so its lists may show their bookings and its staff their notifications. Replay the worked example at Lahore Auto Care, which automation never touches.
````

The live login page shows the same accounts as plain text (D52) from `apps/web/src/content/demo-accounts.ts` — data only: no auto-fill, no "log in as" buttons, no bypass (spec 09 R11). Keep that file and this block in sync when the cast changes.

Traceability of the judge notes: note 1 = fresh `.test` e-mails (D62, D26); notes 3, 5 and 6 = accepted shared-data drift (D71; note 6's adjustment is D82); note 7 = demo-cast repair on every seed run (D60); note 8 = login returns token + user, memberships from `/me` (D81); note 9 = the smoke-test shop (Shops; spec 07 `scripts/smoke.sh`, spec 12 DEP-10 and WEB-08).

## Verification (spec 12)

Spec 12's SEED catalogue covers this spec as follows (layer D, real PostgreSQL, the real seed entry function, a `SimulatedClock` installed behind `app.shared.clock`, D63):

| Spec 12 ID | What it proves here |
|---|---|
| SEED-01 | 6 listed shops, each with a full team, catalogue, inventory and working hours |
| SEED-02 | Running the seed again, with the clock one day later, changes no row count |
| SEED-03 | Every shop has bookable slots (`remaining` > 0, D68) in the next 7 days (computed slots, D37) |
| SEED-04 | Lahore Auto Care: oil filter and engine oil 4 L available, ignition coil 0, prices 900 / 5,200 / 6,500 |
| SEED-05 | `ahmed@mail.com` does not exist |
| SEED-06 | Ayesha's bookings cover several statuses and pass `assert_invariants` (event chain, one open estimate version, ledger) |
| SEED-07 | Every seeded glossary §14 account logs in with `BayFlow@2026` (guards D62: `.test` e-mails pass the project `Email` type) |
| SEED-08 | Fatima owns Lahore Auto Care and Raza Auto Works |
| SEED-09 | The pre-deploy entry point honours `SEED_ON_DEPLOY` and exits non-zero on failure |
| SEED-10 | The worked example (SM-18) passes on the seeded database with a fresh customer |

Additions adopted by spec 12 §5 with these numbers (SEED-11 … SEED-19; spec 12 open question 10):

| ID | Test |
|---|---|
| SEED-11 | Exact snapshot: 36 users, 32 memberships, 42 working-hours rows, 52 services, 96 parts, 10 vehicles, 2 general POs, 15 sample bookings in the statuses of the summary table (each with the `mileage_km` of the vehicles table, D65), 125 booking events; `assert_invariants` holds for **every** sample booking; no event has `actor_role` = `SYSTEM` (glossary §2.2); every event's `created_at` equals its scripted `SimulatedClock` time (D63) |
| SEED-12 | Lahore Auto Care stock equals the inventory table (on hand / reserved per SKU); PO statuses `RECEIVED`, `PARTIALLY_RECEIVED`, `ORDERED`; in every shop, each non-zero opening quantity is exactly one `ADJUST` movement whose actor is that shop's Parts Person, and no part received stock at creation (D44) |
| SEED-13 | Every one of the 36 seeded accounts logs in (extends SEED-07 to the non-cast staff and customers) |
| SEED-14 | Judge data survives a re-run: approve BF-SEED02, consume an oil filter, adjust a part's stock, change Lahore Auto Care's hours and capacity and a service price → seed again → none of those rows changed (D60 never touches bookings, inventory, POs or settings). Demo-cast changes are the exception: SEED-19 |
| SEED-15 | Resume: stop the seed after step 7 of BF-SEED03 (fault injection) → run again → BF-SEED03 ends in `PARTS_ORDERED` with exactly 12 events; a booking that someone else moved is skipped with a warning |
| SEED-16 | `make db-reset` with `APP_ENV=production` or a non-local `DATABASE_URL` host → exit code 2 before the drop, database untouched (spec 07's guard) |
| SEED-17 | Future sample slots: none at 10:00 at Lahore Auto Care; ≤ 1 sample booking per slot; all slots on the shop grid and within 30 days — for a seed clock on each of the 7 weekdays |
| SEED-18 | Unread counts per account match "What each demo account sees on first login" |
| SEED-19 | **Demo-cast reconciliation (D60):** deactivate Hamza's membership, change Imran's role to `SERVICE_ADVISOR`, set Sara's `users.is_active` to false and give Usman a different password hash; in the same test approve BF-SEED02, consume an oil filter and change Lahore Auto Care's capacity; add a demo user to a non-seeded shop as a judge would → seed again → Hamza active, Imran `TECHNICIAN`, Sara active, Usman logs in with `BayFlow@2026`; the booking, stock, capacity and the judge's membership are unchanged; a further run writes no row (no `updated_at` changes) |

## Service functions the seed calls

Signatures as defined by the module specs (`modules/*.md`), which are authoritative. `uow` is a write transaction that the top-level use case commits; `ctx` is the `ShopContext` and `customer` the `CurrentUser` the seed builds for each scripted actor, exactly as `app.shared.auth` builds them for a request (spec 08 "Who is the actor?").

| Module | Function the seed calls | Also used by |
|---|---|---|
| identity | `register_owner(uow, *, email, full_name, password, phone=None)` (Phase A owners; the returned token is ignored); internal only, never over HTTP (D60, Phase R): `set_user_active(uow, *, user_id, is_active)`, `password_matches(session, *, user_id, password)` (one Argon2 verify, no limiter, no rehash), `set_password(uow, *, user_id, new_password)` — [modules/identity.md](modules/identity.md) §5 | `POST /api/v1/auth/register-owner` |
| shops | `create_shop(uow, *, actor_user_id, data: ShopCreate)` (with its 7 working-hours rows and slot settings); `set_rating(uow, *, shop_id, rating)` (internal only); `add_member(uow, *, shop_id, actor_user_id, data: MemberCreate)` (`MemberCreate.password` is used only for a new e-mail, D18); `update_member(uow, *, shop_id, actor_user_id, membership_id, data: MemberUpdate)` (D60 reconciliation, as the Owner); `create_service(uow, *, shop_id, actor_user_id, data: ServiceCreate)` — [modules/shops.md](modules/shops.md) §5.1 | Shops and team endpoints (`PATCH …/members/{membership_id}` for `update_member`) |
| inventory | `create_part(uow, ctx, data: PartCreate)` (no quantity: parts start at 0, D44); `adjust_stock(uow, ctx, *, part_id, quantity_delta, reason)` (Parts Person only; opening stock, D44, D82); `create_purchase_order(uow, ctx, data: PurchaseOrderCreate, *, po_number=None)` — **general restock only** (`PO-SEED01`, `PO-SEED02`): its body has no `booking_id`, because booking-linked POs come only from the `order-parts` action (D43, spec 03 §4.10), which is how BF-SEED03's PO is created; `receive_purchase_order(uow, ctx, po_id, data: PurchaseOrderReceive)` — [modules/inventory.md](modules/inventory.md) | Inventory and PO endpoints |
| bookings | `create_booking(uow, *, caller: CurrentUser \| None, data: BookingCreate, reference=None)` (wizard rules, D32); `apply_staff_action(uow, ctx, *, booking_id, action, payload)` and `apply_customer_action(uow, customer, *, booking_id, action, payload)` for every scripted action (incl. `ORDER_PARTS`); `edit_estimate(uow, ctx, *, booking_id, body: EstimateUpdate)` for every "PUT estimate" step — it locks the booking, calls `estimates.replace_lines` and writes the `EDIT_ESTIMATE` event when a new version is created, which only bookings may do — [modules/bookings.md](modules/bookings.md) §5.1 | `POST /api/v1/bookings`, both `/actions/{slug}` families, `PUT …/estimate` |
| notifications | `list_for_bookings(session, *, shop_id, booking_ids)` and `mark_read_bulk(uow, *, user_id, notification_ids)` ("Notifications after seeding") — [modules/notifications.md](modules/notifications.md) | Bell endpoints |
| shared | `app.shared.clock` (D63): `SystemClock` (read once for `run_now`) and the settable `SimulatedClock` the seed installs as the process clock and sets before each step | Every service that writes timestamps or checks "now" |
| core | `app.core.security`: `verify_password`, `hash_password` — called inside identity's internal functions above; the seed never reads `users.password_hash` itself | Login, registration, add-member |
| settings | `EMAIL_PROVIDER=none` for the seed process (override at start-up, D26) | Notifications e-mail channel |

`reference=` and `po_number=` are keyword-only, internal, and absent from the HTTP request schemas. The seed never calls the estimates module directly: estimate lines change only through `bookings.service.edit_estimate`.

## Proposed glossary additions

1. ✅ merged — **Seeded shops** (glossary §14.2).
2. ✅ merged — **Additional demo cast**: Hamza, Hina, Kamran, Zainab, Nadia, Omar and the `<role-tag>.<shop-slug>@bayflow.test` pattern (glossary §14.1 and §14.2).
3. ✅ merged — **Reserved reference prefixes** `BF-SEED` / `PO-SEED`; random codes never start with `SEED` (glossary §1 "Booking reference", §14).
4. **Seed data module:** `app/scripts/seed_data.py` (typed seed constants, next to spec 01's `app/scripts/seed.py`). The `--force` flag and the `seed` / `db-reset` Make targets are already listed by spec 07. *(pending)*
5. ✅ merged — **`SimulatedClock`** (glossary §1 "Clock", §7 `app.shared.clock`; D63).
6. **Advisory lock key** `bayflow:seed` (hashed to a constant) for the seed. *(pending)*
7. **Smoke-test shop:** Lyallpur Motors (`lyallpur-motors`), the only shop automated live checks write to (spec 07 `scripts/smoke.sh`, spec 12 DEP-10 and WEB-08); a note for glossary §14.2. *(pending)*

## Dependencies

- Depends on: [18-glossary.md](18-glossary.md) (cast, statuses, slugs, enums), [17-decisions.md](17-decisions.md) (D10, D13, D15–D19, D24, D26, D31, D32–D35, D37–D47, D51, D52, D55, D56, D60, D62, D63, D65, D69, D71, D73, D79, D81, D82, D86, D89), [03-api-contracts.md](03-api-contracts.md) (the HTTP fields behind each service call, e.g. `MemberCreate.password`; the login body, D81), [08-booking-state-machine.md](08-booking-state-machine.md) (every script is a legal path), [01-architecture.md](01-architecture.md) (use cases commit, after-commit callbacks, repo layout, `app.shared.clock`), [02-data-model.md](02-data-model.md) (unique keys, format checks, 7 working-hours rows, generated codes, DI-1…7), [04-auth-and-security.md](04-auth-and-security.md) (wizard cases A–D, in-service rate limiters, add-member and update-member rules), [12-quality-and-testing.md](12-quality-and-testing.md) (SEED tests), `modules/*.md` (service functions).
- Used by: [06-workflows.md](06-workflows.md) (BF-SEED references, demo script), [07-deployment-and-docs.md](07-deployment-and-docs.md) (pre-deploy command, start scripts, Makefile and `db-reset` guard, README block, the smoke script's shop `lyallpur-motors`), [09-frontend-and-ux.md](09-frontend-and-ux.md) and [10-screens.md](10-screens.md) (login-page demo list), [12-quality-and-testing.md](12-quality-and-testing.md) (SEED-01…SEED-10 and the proposed additions).

## Open questions

1. ✅ Resolved by D62: **`.test` e-mails and validation.** One project `Email` type (`app.shared.email`: `validate_email(value, check_deliverability=False, test_environment=True)`, then lower-cased) replaces Pydantic's `EmailStr`, so every `@bayflow.test` account validates in login, add-member, the wizard and this seed. SEED-07 guards it.
2. ✅ Resolved by D26: **E-mail delivery to reserved TLDs.** The sender never e-mails reserved/test TLDs (`.test`, `.example`, `.invalid`, `.localhost`); production uses an HTTPS e-mail API (`EMAIL_PROVIDER=http`) because Railway Hobby blocks outbound SMTP, and e-mail stays optional.
3. ✅ Resolved by D63: **One source of "now".** `app.shared.clock` is the single time source (`SystemClock` in production, `SimulatedClock` in the seed and tests); services assign every timestamp from it and check every "now" rule against it; database `DEFAULT now()` remains only a fallback for hand-written SQL. The seed's back-dated histories rely on this (Execution model, Clock).
4. ✅ Resolved by D71: **Lahore Auto Care capacity** stays 2 as briefed. Friday 10:00 filling up after two replays is accepted shared-data drift; judge note 5 tells testers to take the next Friday or another time.
5. ✅ Resolved by D51 and glossary §14.1: **Four extra customers** (Kamran, Zainab, Nadia, Omar) are part of the canonical seeded cast.
