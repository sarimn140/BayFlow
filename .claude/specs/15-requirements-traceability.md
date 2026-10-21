# 15 — Requirements Traceability

**Status:** Draft
**Audit:** 2026-10-09. Inputs: brief v1.1 (`helping-folder/Web Dev - Virtual.pdf`); the specs as they stood at 16:36 that day; and a snapshot of the working tree at 16:37, on top of commit `59e1864` ("first commit"). The backend build had just started (D89), so code in flight at the snapshot is listed separately in §1.4.
**Update 2026-10-10:** notes dated 2026-10-10 (R-7.3-1, R-10-3, §4) record the web redesign (D101), built on the mock store of D102; every Status value and the §3.1 counts are still the 2026-10-09 audit's until it is re-run (§7).

## Purpose

The brief is the judges' checklist. This spec takes every sentence of it that asks for something to be built, delivered, checked or judged, gives it a stable ID, and traces it to:

1. the spec that defines it,
2. the test IDs that prove it, and
3. the state of the code today.

It answers three questions at any point in the hackathon:

- **Is every brief requirement specified?** Yes: every row cites a spec. The nearest miss is G9 (§3.3).
- **Is every requirement provable by a named test?** Almost. The exceptions are process and document requirements, plus three P0 items whose only tests are P1. They are listed as gaps G1–G8 (§3.3), each with a proposed home.
- **How far is the code?** The foundation is built, but the business product is not. Of 227 rows, 144 are "Spec only", 61 "Foundation", 11 "Built" and 11 "Not applicable" (§3.1).

This spec does not restate rules. Behaviour lives in the cited specs, and spec 17 wins over anything written here. Spec 14 reads this file at PH7 (hardening) and PH10 (submission). Re-run the audit at each checkpoint (§7).

## 1. How to read it

### 1.1 IDs

An ID has the form `R-<brief section>-<n>`.

- **Brief section:** as printed in the brief — `1`, `2`, `3`, `4`, `5` (the §5 introduction), `5.1`…`5.4`, `6`, `7.1`…`7.8`, `8` (the §8 introduction), `8.1`…`8.3`, `9.1`…`9.4`, `10`, `11`.
- **`n`:** the requirement's order inside that section.
- **Exception for §6:** IDs use the worked-example step number (`R-6-0`…`R-6-16`). The bonus path is `R-6-17`.

Some brief bullets carry several obligations, e.g. §9.1's GitHub row: public, meaningful history, organised folders, no secrets. These are split so each row has one status.

IDs are never renumbered. A requirement split later gets new numbers at the end of its section.

Do not confuse these IDs with spec 09's UX rules `R1`…`R12`, which have no section part.

### 1.2 Columns

| Column | Meaning |
|---|---|
| Requirement (brief) | A short quote ("…") or close paraphrase. The brief section is the ID's section. |
| Pri | Priority per D36. **P0** = brief core (§7 plus what it rests on: §3–§6, §9, §10). **P1** = a cheap extra that strengthens judging. **P2** = bonus track (§8), started only after P0 works end to end on the live URL. **P3** = post-hackathon; used only for the five brief items the specs explicitly defer, all "Not applicable". |
| Spec(s) | Where the requirement is defined, written as spec number + section, heading or row. Forms: `08 T13`, `04 "RBAC matrix" D`, `modules/inventory.md "Purchase-order receipt"` (headings are shortened), `17 D20` (decision), `18 §6` (glossary section). `06 C2` and `10 P-03` are journey and screen IDs. "08 trace step n" means the step-n row of spec 08's "Worked example trace (brief §6)". |
| Tests | Catalogue IDs only: SM (spec 08); SEC (spec 04); IDN, SHP, SCH, BK, EST, INV, QC, NOT, RPT, API, SEED, WEB, CON, DEP, DEV (spec 12); CALL, FD, AG (spec 05). Spec 12 §5 has numbered the module-spec proposals, including CALL-17…CALL-21 and FD-13…FD-15, which spec 05 §14.1 has adopted, so they are cited like any other ID. A proposal that only a module spec holds is marked "(proposed)". Markers: ★ = in spec 12's 21-test minimum proof set; ✓ = a test with this ID (at least the half named in §3.2) exists in the repo today; "(P1)" = the test is only P1. "—" = no test ID; the gap is listed in §3.3. |
| Status | See §1.3. |
| Notes | What exists, what is missing, and the decision behind any interpretation. |

### 1.3 Status values

| Status | Meaning in this spec |
|---|---|
| **Spec only** | Specified and given test IDs, but not implemented. Generic scaffolding does not change this status: the 23 tables of the D84 baseline migration, the empty module packages and the placeholder pages. Notes mention such scaffolding where useful. |
| **Foundation** | The mechanism the requirement is *about* is implemented, and tested as noted. Examples: the auth and tenancy dependencies, the state-machine rule table, database constraints, shared types and components, tooling, deploy config. But no route, screen, seed data or deployment lets the requirement's actor use it yet — "infrastructure exists but the feature is not wired". |
| **Built** | Implemented and tested. For documents, configuration and tooling, it means the item is present and was checked against the brief's wording in this audit; the note says how. |
| **Not applicable** | Nothing to build: a permission, a scoring rule, a process rule or an explicit exclusion. |

### 1.4 What the code contains (the basis for the Status column)

**`apps/api`:**

- **App:** the app factory serves only `GET /health`, returning the D84 body. Module wiring by convention (D89: `MODULES` and `wire_modules()` in `app/main.py`) landed at 16:20 with `tests/unit/test_main_wiring.py`. No module exports a router yet.
- **`app.core`:**
  - settings, with production guards;
  - Argon2id hashing;
  - JWT issue and decode on the D63 clock;
  - rate-limit helpers;
  - RFC 9457 error handlers;
  - middleware: request ID, security headers, `Cache-Control: no-store`, CORS, a 64 KiB body cap.
- **`app.shared`:**
  - cookie-or-Bearer auth, `require_shop_member`, `require_roles`, `shop_scoped_router()`;
  - the clock, the `Email`, `Money` and `Phone` types (`app/shared/phone.py` landed at 16:35), timestamps, enums;
  - event bus, unit of work, pagination, and the shop-scoped repository base.
- **Schema:** SQLAlchemy models and one Alembic baseline migration. It creates all 23 tables (20 core, 3 bonus) with 59 foreign keys, including the composite tenant FKs, and 126 named CHECK constraints.
- **State machine:** the pure rule table in `app/modules/bookings/domain/state_machine.py`.
- **Modules:** every module's `service.py` is an empty stub, except the two look-ups that `app.shared.auth` needs. No module has a router, a repository beyond those look-ups, or a use case.
- **In flight at the snapshot (no tests yet, so no status changed):** pure domain code was being written while this audit ran, without tests in `tests/unit/estimates`, `tests/unit/qc` or `tests/unit/inventory` (those folders were still empty at 16:37). Files:
  - `app/modules/estimates/domain/` (`totals.py`, `versions.py`, `lines.py`);
  - `app/modules/qc/domain/` (`checklist.py`, `rules.py`) and `app/modules/qc/schemas.py`;
  - `app/modules/inventory/domain/stock.py`.
  
  The affected rows (R-3-7, R-7.4-7, R-7.4-13, R-7.5-4, R-7.6-2) say so in their Notes.
- **Seed:** `python -m app.scripts.seed` honours `SEED_ON_DEPLOY` and `--force` but defines no data.

**API tests (snapshot at 16:37):**

- 1,393 tests are collected. 42 carry the `db` marker and need PostgreSQL. **They were not run here**, because no database was listening on port 5434; D84 records the suite green when it held 1,369 tests.
- Run here with `pytest -m "not db"`: 1,351 tests, of which **1,350 pass and 1 fails**. The failure is a case in `tests/unit/shared/test_phone.py`, which was being written at the time.
- The 1,351 include the 1,131 exhaustive state-machine cases.
- Gates run at about 16:03, before the in-flight code, all green: Ruff check, Ruff format, mypy strict (74 files), import-linter (8 of 8 contracts kept).

**`apps/web`:**

- A Next.js 16 shell, with all 27 P0 routes of spec 10 §1 as placeholder pages. 26 of them use `ScreenPlaceholder`; the landing page has its hero.
- Design tokens, shadcn/ui primitives and `StatusBadge`.
- Formatters and the status vocabulary.
- The `openapi-fetch` client, with problem-code mapping.
- The optimistic `proxy.ts` auth gate.
- Security headers and the `/api/*` rewrite.
- `DemoCredentialsPanel` on `/login`.
- 67 Vitest tests and ESLint pass in this audit.
- The committed `src/lib/api/openapi.json` is still a placeholder with no paths (Open question 6).

**Repo root:**

- README with sections 1–18, several marked "to be completed".
- `.env.example` with 33 variables.
- `docker-compose.yml`, `Makefile`, and `start`/`stop` scripts (`.sh` and `.bat`).
- `.github/workflows/ci.yml` with jobs `api`, `web`, `contract` and `secrets`.
- PR template, pre-commit config, `scripts/smoke.sh` and `apps/api/railway.json`.
- One git commit. Nothing is deployed.

## 2. The matrix

### 2.1 §1 Hackathon at a glance

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-1-1 | A multi-tenant platform for independent repair shops: customers discover a shop, book a service and track their vehicle; staff run the whole job, check-in to pick-up, in one role-based POS | P0 | 00 "Purpose", "What we build (brief §3)"; 01 "System topology" | SM-18 ★, DEP-09 | Spec only | Umbrella row, broken down in R-3-* to R-7.8-* |
| R-1-2 | "design and ship a working version of this product, with a clean architecture and a live deployment" | P0 | 01 "Architectural style (D3)", "ADR-001"; 07 "Hosts overview", "Deploy flow at a glance"; 14 PH0 | DEP-01, DEP-05, DEP-06, DEP-09 | Foundation | Modular-monolith foundation passes Ruff, mypy strict and 8/8 import contracts. Railway config and Dockerfiles exist. Nothing is deployed (README: "Live URL: to be added") |
| R-1-3 | "Build a full working product: customer web app + shop POS + backend API" | P0 | 00 "What we build (brief §3)"; 01 "Web structure (`apps/web`)", "Backend folder structure (`apps/api`)"; 10 §1 | DEP-02, DEP-09 | Foundation | Every P0 route of 10 §1 exists as a placeholder page; the API serves only `/health` |
| R-1-4 | "Tech stack: Free choice. Pick what you can ship well and defend in the review" | P0 | 17 D1, D2, D3, D11; 00 "Locked tech stack"; 01 "ADR-001" | — | Not applicable | The stack is chosen and justified in D1–D3 |
| R-1-5 | "AI tooling: Allowed and encouraged … You remain responsible for the quality of what ships" | P0 | 12 §2.3, §2.4; 07 "Repository standards"; 14 §6 | — (G2) | Foundation | The PR template carries the AI-assistance attestation. Same obligation as R-9.4-8 and R-11-2 |
| R-1-6 | "Must submit: Public GitHub repository and a live URL (plus README and .env.example in repo root)" | P0 | 14 §7; 07 "Hosts overview", "README outline", "Root `.env.example`" | DEP-01, DEP-02, DEP-07, DEP-14 | Foundation | Detail in R-9.1-*. README and `.env.example` are in the root; there is no live URL |
| R-1-7 | "Scope tiers: Core features (mandatory) and bonus features (optional, judged separately)" | P0 | 17 D4, D36; 00 "Scope"; 14 §1.1 | — | Not applicable | A scoring rule; it drives the priority column of this matrix |

### 2.2 §2 Problem statement — the core problems as outcomes

The brief's "How it is done today" table describes the status quo, not something to build. Each pain in it is answered by a row of §3's "How BayFlow solves the problems" table (R-3-5 … R-3-12), and is traced there. The five "Core problems to solve" are traced below as outcomes.

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-2-1 | "No visibility: neither customer nor owner can see where a vehicle is in the process" | P0 | 09 §1 (G5, G6), §4.4; 10 C-02, O-01; modules/reporting.md "`OverviewRead`" | BK-17, BK-19, RPT-01, WEB-03 ✓, WEB-11 | Spec only | Only the status vocabulary exists (`apps/web/src/lib/status.ts`). The timeline and the owner overview do not |
| R-2-2 | "No accountability: approvals, estimates and QC results are not recorded" | P0 | 08 "Principles" (4, 5); 02 §3.10, §3.11, §3.18, §3.19, §8; 17 D39, D46, D47 | SM-20 ★, EST-12, EST-13, QC-06, BK-19 | Foundation | `booking_events` and `stock_movements` are append-only and `seq`-ordered, with DB tests in `tests/db/test_constraints.py`. Nothing writes them yet |
| R-2-3 | "Inventory chaos: parts availability is unknown at estimate time" | P0 | 17 D40, D42, D45; 09 §4.5; modules/estimates.md §7.4; modules/inventory.md "Quantities" | EST-18, INV-15, INV-16, INV-01 ★ | Spec only | The stock CHECKs exist (INV-14 ✓). Availability in the estimate editor does not |
| R-2-4 | "Communication overload: advisors lose time and customers on phone calls, and missed calls are never followed up" | P0 | 17 D14, D26, D88; modules/notifications.md "Trigger table"; 05 §1.1 | NOT-01, NOT-05, BK-17, WEB-11, CALL-04, FD-10 | Spec only | Core answer: the bell plus the customer dashboard. The missed-call half is the P2 bonus (R-8.1-7, R-8.2-6) |
| R-2-5 | "No multi-shop control: an owner with several branches cannot manage separate teams and records cleanly" | P0 | 17 D15, D17, D20; 04 "Tenant isolation — defence in depth (D20)"; modules/shops.md §7.2, §7.9; 10 S-01 | SEC-01 ★, SEC-02, SEC-45 ✓, SEC-46, SEED-08 | Foundation | The tenancy dependency and composite FKs are built and tested. Shop routes, the switcher and the seed are missing |

### 2.3 §3 What you will build

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-3-1 | "a single platform with three surfaces that share one backend" | P0 | 00 "What we build (brief §3)"; 01 "System topology", "Monorepo root layout (D5)"; 09 §2.3, §2.5 | DEP-02, DEP-03 | Foundation | Route groups `(public)`, `(customer)` and `(pos)`; one `apps/api`. The `/api/*` rewrite (D7) is tested in `next.config.test.ts` |
| R-3-2 | Customer portal: "public landing page listing all shops, a guided booking wizard, and a login area where the customer tracks bookings and approves estimates" | P0 | 10 P-01, P-03, P-04, C-01, C-02; 06 §1 (C1–C8); 09 §1 (G1, G2, G5) | BK-16, BK-01, BK-17, EST-13, DEP-02, DEP-09 | Spec only | Only the hero and placeholder pages exist. Detail in R-7.3-* |
| R-3-3 | Shop POS: a role-based dashboard for Owner, SA, Technician, QC Inspector and Parts Person; "Each role only sees the work that is theirs" | P0 | 10 §1, S-04, SA-01, T-01, PP-01, QI-01, O-01; 04 "RBAC matrix" C; 17 D21; 09 §1 (G3) | SEC-08, SEC-09, SEC-10, BK-18, BK-40, WEB-09, DEP-09 | Spec only | The POS shell and placeholder role pages exist; D21 visibility is not implemented. Detail in R-7.4-* |
| R-3-4 | Backend API: "multi-tenant, authenticated, with a booking state machine that enforces who can move a job to which step" | P0 | 01 "Authentication and tenant dependencies (D8, D9, D20, D21)"; 04 "Per-request checks (D9, D20, D21)"; 08 (all); modules/bookings.md §7.4 | SM-01 ★✓, SM-03 ★✓, SM-04 ✓, SM-05 ★, SEC-01 ★, SEC-02, SEC-04 ✓ | Foundation | Built and tested: `app/shared/auth.py` and the rule table (1,131 domain cases). Missing: the action executor and every business route |
| R-3-5 | "Finding and booking: Public shop directory, service picker, real time slot availability, instant booking" | P0 | modules/shops.md §7.8; modules/scheduling.md §7.3, §7.5; modules/bookings.md §7.1; 03 §4.5, §4.6 | BK-16, BK-11, BK-27, BK-01, SM-07 ★ | Spec only | "Real time" means availability is computed per request (D37), with 15 s polling (D14) |
| R-3-6 | "Lost information: Customer's reported problem, vehicle details and every step are stored against one booking" | P0 | 02 §3.7–§3.10; 17 D34, D35, D65; 08 "Principles" (5) | BK-06, BK-07, BK-13, BK-19, BK-28, SM-20 ★ | Foundation | `vehicles`, `bookings` (`customer_notes`, `mileage_km`), `booking_services` and `booking_events` exist. DB-tested constraints: a booking uses its own customer's vehicle; events are append-only. Booking creation is not built |
| R-3-7 | "Disputed estimates: Itemized estimate with parts and labour, sent to the customer, accepted in-app with timestamp" | P0 | 08 T06–T09, "Estimate versions (D39)"; 17 D39–D41; modules/estimates.md §7.1, §7.6, §7.7; 10 C-02 | EST-05 ★, EST-13, EST-14, EST-20 ✓, SEC-12, SM-14 | Spec only | Only the whole-rupee `Money` type and the DB check exist (both halves of EST-20). The estimate domain (`totals.py`, `versions.py`, `lines.py`) was being written at the snapshot, untested (§1.4) |
| R-3-8 | "Wrong stock: Live inventory per shop; missing parts flagged; receiving parts updates stock automatically" | P0 | 17 D42–D45; 08 "Parts reservations (D42, D43)"; modules/inventory.md "The ledger", "Purchase-order receipt" | INV-01 ★, INV-05, INV-06, INV-15, INV-22, INV-14 ✓ | Spec only | The stock CHECKs and the append-only ledger table exist; there is no inventory service |
| R-3-9 | "Unclear ownership: Booking state machine: every status has exactly one responsible role" | P0 | 08 "Principles" (6), "Transition table (the rules)"; 18 §3 | SM-03 ★✓, SM-19 ✓, SEC-07 | Foundation | Encoded in the `RULES` actors and unit-tested; not yet enforced over HTTP |
| R-3-10 | "Skipped quality checks: Mandatory QC stage; failed QC returns the job to the technician with a recorded issue" | P0 | 08 T17–T20, "QC loop (D46, D47)"; 17 D46, D47; modules/qc.md "A QC round" | SM-10 ★, QC-03, QC-05, QC-08 ✓, SM-01 ★✓ | Foundation | Unit-tested in the domain: the only way to `READY_FOR_PICKUP` is `PASS_QC`; `FAIL_QC` goes to `IN_REPAIR`; the picker may not be the technician. The issue record (`qc_issues`) is not written yet |
| R-3-11 | "Customer anxiety: Customer dashboard shows status and pending actions; notifications at key steps" | P0 | 10 C-01, C-02; 09 §4.11; 18 §6; modules/notifications.md "Trigger table" | BK-17, BK-19, NOT-01, WEB-11 | Spec only | |
| R-3-12 | "Multi-branch chaos: Tenant isolation: each shop has its own team, inventory, slots and bookings; one owner can run many shops" | P0 | 17 D15, D17, D20; 02 §4; 04 "Tenant isolation — defence in depth (D20)" | SEC-01 ★, SEC-02, SEC-40, SEC-45 ✓, SEC-46, SEED-08 | Foundation | Same state as R-2-5 |
| R-3-13 | "Every shop-owned record (team memberships, services, slots, inventory, bookings, estimates) carries a shop identifier" | P0 | 02 §2.1, §4.1, §4.2; 18 §1 ("Shop-owned record"); 17 D20 | SEC-45 ✓ | Built | Every shop-owned table in the baseline migration has `shop_id` and composite tenant FKs. SEC-45 lives in `tests/db/test_constraints.py`; not re-run here (§1.4) |
| R-3-14 | "every API query is scoped by it" | P0 | 04 "Tenant isolation — defence in depth (D20)" (layers 1, 2); 01 "Authentication and tenant dependencies"; 17 D20, D80 | SEC-02, SEC-03, SEC-01 ★ | Foundation | `shop_scoped_router()` (router-level dependency, tested) and `ShopScopedRepository` exist; no shop route uses them yet |
| R-3-15 | "A staff member of Shop A must never be able to read or change data of Shop B, even by guessing IDs" | P0 | 04 "Tenant isolation — defence in depth (D20)" ("Why 404 and not 403", "IDs"); 03 §7.6; 17 D20 | SEC-01 ★, SEC-02, SM-05 ★, SEC-45 ✓ | Foundation | `require_shop_member` returns the same 404 for every shop without an active membership (tested at dependency level). The sweep needs routes |
| R-3-16 | "An owner can own several shops and each shop has its own separate team" | P0 | 17 D15, D17; modules/shops.md §7.2, §7.6; 02 §3.4 | SEC-40, SEC-46, SEED-08, SEC-15 ✓ | Spec only | The DB enforces one `OWNER` per shop (DB half of SEC-15); shop creation is not built |
| R-3-17 | "Customers are global accounts and can book at any shop" | P0 | 18 §1 ("Customer"); 17 D15, D32; 02 §3.1 | BK-01, BK-02, SEC-03 | Spec only | `users` has no `shop_id`, by design |

### 2.4 §4 Users and roles

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-4-1 | Customer: "Browse shops, book, log in, view bookings, approve or reject estimates, mark pick-up" | P0 | 06 §1 (C1–C8); 08 T01, T08, T09, T21, T22; 04 "RBAC matrix" D; 17 D28 | BK-01, BK-17, SM-08 ★, SM-02 ✓, BK-23 | Spec only | The four customer slugs exist in the domain (unit-tested); there are no routes |
| R-4-2 | Owner: "Registers an account, creates shops, adds team members with roles, creates more shops later; full visibility of their shops" | P0 | 06 §2 (O1–O8); 04 "Owner registration", "Shop creation (D17)", "Staff accounts"; 17 D16–D18 | IDN-01, SEC-21, SEC-40, SEC-46, RPT-01 | Spec only | |
| R-4-3 | Service Advisor: "Confirms bookings, assigns technicians, reviews estimates, sends them to customer, assigns parts person, notifies customer when ready, closes booking" | P0 | 06 §3 (S1–S9); 08 T02–T04, T07, T10–T12, T21, O3; 04 "RBAC matrix" D | SM-02 ✓, SM-03 ★✓, SEC-07, BK-21, BK-23 | Spec only | The SA guards are unit-tested in `RULES`; there are no executor, routes or screens |
| R-4-4 | Technician: "Sees assigned jobs, inspects the vehicle, adds required parts and cost estimate, performs repair, sends to QC" | P0 | 06 §4 (T1–T7); 08 T05, T06, T17, O1, O2; 17 D21, D25 | SEC-08, SM-04 ✓, EST-02, BK-24, QC-05 | Spec only | The `ASSIGNED_TECHNICIAN` guard is unit-tested |
| R-4-5 | Parts Person: "Views stock, orders missing parts, confirms receipt (stock increases), allocates parts to a booking" | P0 | 06 §5 (P1–P8); 08 T13–T16; 17 D42–D44; modules/inventory.md "Booking parts", "Purchase-order receipt" | INV-02, INV-05, INV-06, INV-11, INV-18, INV-22 | Spec only | |
| R-4-6 | QC Inspector: "Any QC person can pick a job from the QC queue, test it, then pass it or raise an issue" | P0 | 06 §6 (Q1–Q5); 08 T18–T20; 17 D46, D47; modules/qc.md "A QC round" | SM-06 ★, QC-01, QC-02, QC-04, QC-07, QC-10 | Spec only | |
| R-4-7 | "Roles are scoped per shop. A user can hold a role in one shop and a different role in another" | P0 | 17 D15; 18 §1 ("Membership"), §2.1; 04 "One user, many hats"; 02 §3.4 | SEC-46, SEC-40, SEC-07 | Foundation | Built: `shop_memberships` (one row per `(shop_id, user_id)`) and `require_shop_member`, which resolves the role per request (tested). Membership management is not built |
| R-4-8 | "An Owner can do everything inside their own shops" | P0 | 17 D16; 04 "RBAC matrix" A, B, D (notes); 08 "Assignment guards" | SEC-05, SEC-06, SM-16 ★✓ | Foundation | D16 reads this as full management plus every SA booking action; the technician, parts and QC views are read-only, citing the FAQ (R-11-7) and §7.8 (R-7.8-4). "Owner = SA actions" is unit-tested |
| R-4-9 | "Shop staff accounts are created by the Owner, never by self sign-up" | P0 | 17 D18; 04 "Staff accounts — created by the Owner (D18, D19)", "Threat model" (4); modules/shops.md §7.6 | SEC-16, SEC-21, SEC-05 | Spec only | |
| R-4-10 | "Technician sees only bookings assigned to them" | P0 | 17 D21; 04 "Booking visibility predicate (D21)", "RBAC matrix" C; modules/bookings.md §7.5 | SEC-08, BK-40, SM-04 ✓ | Spec only | The action guard exists; list and detail visibility do not |
| R-4-11 | "QC sees the shared QC queue" | P0 | 17 D21; 04 "RBAC matrix" C; modules/qc.md "Who sees QC data"; 10 QI-01 | QC-07, SEC-10, QC-16 | Spec only | |
| R-4-12 | "SA and Owner see all bookings of the shop" | P0 | 17 D21; 04 "RBAC matrix" C; modules/bookings.md §7.5 | BK-18, BK-40, RPT-01 | Spec only | |
| R-4-13 | "The customer only sees their own bookings" | P0 | 17 D21; 04 "RBAC matrix" C; 08 "Who is the actor?" | SEC-11, SM-17, BK-17 | Spec only | |

### 2.5 §5 The complete booking lifecycle (introduction)

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-5-1 | "The booking moves through a fixed set of statuses. Each status has one responsible role and a limited set of allowed next actions" | P0 | 08 "State diagram", "Transition table (the rules)"; 18 §3, §4; 17 D22 | SM-01 ★✓, SM-02 ✓, SM-19 ✓ | Foundation | 17 statuses and 27 actions in `RULES`; `allowed_actions` is a pure function; all unit-tested |
| R-5-2 | "Implement this as an explicit state machine in the backend and reject any invalid transition" | P0 | 08 "Principles" (1–3), "How an action is executed (service layer)", "Error mapping"; 01 "Layers inside a module"; 17 D22 | SM-01 ★✓, API-10, CON-01 | Foundation | The domain rejects every pair outside the table (exhaustive test). The executor (locks, events, routes) is not built, so no HTTP request is rejected yet |

### 2.6 §5.1 Customer-side booking journey

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-5.1-1 | "Open the landing page and browse all listed shops" | P0 | 10 P-01; 06 C1; modules/shops.md §7.8; 03 §4.5; 17 D64 | BK-16, BK-26, DEP-02 | Spec only | The landing hero exists; the directory does not |
| R-5.1-2 | "Select a shop and start a booking" | P0 | 10 P-02, P-03 (W1); 06 C2; 17 D68 | BK-26, BK-27, WEB-06 | Spec only | |
| R-5.1-3 | "Choose the problem or service … (multiple selections allowed, plus free-text notes)" | P0 | 17 D34; 08 T01; 10 P-03 (W2); modules/bookings.md §7.1 | BK-06, BK-07 | Spec only | |
| R-5.1-4 | "See that shop's available time slots and pick one" | P0 | 17 D37, D38, D68; modules/scheduling.md §7.1–§7.3; 10 P-03 (W3) | BK-08, BK-11, BK-12, BK-30, SCH-02, SCH-03, SM-07 ★ | Spec only | |
| R-5.1-5 | "Enter personal details (name, email, password) and vehicle details (registration number, make, model, year, optional color/mileage)" | P0 | 17 D10, D33, D35, D62, D65; 10 P-03 (W4); 03 §4.6; modules/bookings.md §7.2 | BK-20, BK-13, BK-28, SEC-29 ✓, SEC-48, API-12 ★✓ | Spec only | The project `Email` type exists and is unit-tested (unit half of API-12) |
| R-5.1-6 | "Review and confirm. The booking is created with status PENDING" | P0 | 08 T01; 03 §4.6, §7.1; 10 P-03 (W5), C-03; modules/bookings.md §7.1, §7.3 | BK-01, BK-14, SM-18 ★, NOT-01 | Spec only | |
| R-5.1-7 | "the customer account is created (or the existing account is reused when the email already exists and the password matches / the user is logged in)" | P0 | 17 D32; 04 "Customer account inside the booking wizard — `POST /api/v1/bookings` (D32)"; modules/bookings.md §7.1 | BK-01, BK-02, BK-03 ★, BK-04, SEC-18, SEC-19, SEC-20 | Spec only | `get_optional_user` (the D32 entry point) exists in `app/shared/auth.py` |

### 2.7 §5.2 Shop-side workflow (one row per status)

Every transition below exists as a rule in `state_machine.py` and passes the domain tests (the domain halves of SM-01, SM-02 and SM-03). In every row, the executor (locks, side effects, events, notifications), the route and the screen are missing. The notes add only what is specific to the row.

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-5.2-1 | `PENDING` (Service Advisor): "Booking appears on SA dashboard (with notification). SA reviews and confirms or declines" → `CONFIRMED` / `CANCELLED` | P0 | 08 T01–T03; 06 S1; 10 SA-01, SA-02; 18 §6 (`BOOKING_CREATED`) | SM-02 ✓, BK-10, BK-22, NOT-01 | Spec only | A decline frees the slot (D24) |
| R-5.2-2 | `CONFIRMED` (Service Advisor): "SA assigns a technician" → `ASSIGNED` | P0 | 08 T04; 06 S2; 17 D21 | SM-02 ✓, BK-21, NOT-01 | Spec only | |
| R-5.2-3 | `ASSIGNED` (Technician): "Technician sees it on their dashboard and inspects the vehicle physically" → `INSPECTING` | P0 | 08 T05; 06 T1, T2; 10 T-01 | SM-02 ✓, SEC-08, EST-01 | Spec only | |
| R-5.2-4 | `INSPECTING` (Technician): "Technician adds needed parts, labour and total cost estimate, then submits to SA" → `ESTIMATE_REVIEW` | P0 | 08 T06, O1; 17 D39–D41; modules/estimates.md §7.3–§7.5; 10 T-02 | SM-02 ✓, EST-02, EST-05 ★, EST-08, EST-10 | Spec only | |
| R-5.2-5 | `ESTIMATE_REVIEW` (Service Advisor): "SA reviews and edits if needed, then sends to customer" → `AWAITING_CUSTOMER` | P0 | 08 T07, O1, "Estimate versions (D39)"; 06 S3; modules/estimates.md §7.1, §7.2 | SM-02 ✓, EST-03, EST-04, EST-11 ✓, NOT-01 | Spec only | The status ownership for `EDIT_ESTIMATE` is unit-tested (domain half of EST-11) |
| R-5.2-6 | `AWAITING_CUSTOMER` (Customer): "Customer logs in, sees the pending estimate, accepts or rejects" → `ESTIMATE_APPROVED` / `ESTIMATE_REJECTED` | P0 | 08 T08, T09; 06 C5, C6; 10 C-02; modules/estimates.md §7.6, §7.7 | SM-02 ✓, EST-13, EST-14, SEC-12, SM-14 | Spec only | |
| R-5.2-7 | `ESTIMATE_APPROVED` (Service Advisor): "SA is notified and assigns a parts person" → `PARTS_PENDING` | P0 | 08 T08 (notification), T12; 06 S5; 18 §6 | SM-02 ✓, NOT-01, BK-21 | Spec only | |
| R-5.2-8 | `PARTS_PENDING` (Parts Person): "Checks inventory against required parts; creates purchase orders for missing items" → `PARTS_ORDERED` or `PARTS_READY` | P0 | 08 T13, T14; 17 D42, D43; modules/inventory.md "Booking parts"; 06 P2–P4 | SM-02 ✓, INV-02, INV-03, INV-10, INV-16 | Spec only | |
| R-5.2-9 | `PARTS_ORDERED` (Parts Person): "When parts arrive, confirms receipt: inventory increases" → `PARTS_READY` | P0 | 08 T15; 17 D43; 03 §5.3; modules/inventory.md "Purchase-order receipt"; modules/bookings.md §7.7 | INV-05, INV-06, SM-12 ★ | Spec only | `RECEIVE_PARTS` is a rule, but only the PO receipt (not built) fires it |
| R-5.2-10 | `PARTS_READY` (Parts Person): "Allocates parts to this booking (inventory reserved/deducted)" → `IN_REPAIR` | P0 | 08 T16; 17 D25, D42; modules/inventory.md "Booking parts" | SM-02 ✓, INV-11, INV-12 | Spec only | D25: `ALLOCATE_PARTS` is the step that moves the booking to `IN_REPAIR` |
| R-5.2-11 | `IN_REPAIR` (Technician): "Job returns to the same technician, who performs the work and sends it to QC" → `QC_PENDING` | P0 | 08 T17, O2; 17 D25, D47; 06 T5, T6 | SM-02 ✓, BK-24, QC-05, NOT-01 | Spec only | |
| R-5.2-12 | `QC_PENDING` (any QC person): "Any QC inspector picks the job from the queue" → `QC_IN_PROGRESS` | P0 | 08 T18; 17 D30, D47; 06 Q1, Q2; modules/qc.md "A QC round" | SM-06 ★, QC-07, QC-08 ✓, QC-10 | Spec only | The `ALREADY_PICKED` mapping is unit-tested; the row lock is not built |
| R-5.2-13 | `QC_IN_PROGRESS` (QC Inspector): "Tests the vehicle. If all good: confirm. If problem: create an issue" → `READY_FOR_PICKUP` / `IN_REPAIR` | P0 | 08 T19, T20; 17 D46, D47; modules/qc.md "The checklist (D46)" | QC-01, QC-02, QC-03, QC-04, QC-11 | Spec only | |
| R-5.2-14 | `READY_FOR_PICKUP` (Service Advisor): "SA notifies the customer that the vehicle is ready" → `COMPLETED` | P0 | 08 O3; 17 D27; 06 S6 | BK-23, NOT-01 | Spec only | `PASS_QC` reaches this status; `NOTIFY_READY` is a repeatable operation (D27) |
| R-5.2-15 | `COMPLETED` (Customer / SA): "Customer picks up the vehicle and the booking is completed" → final | P0 | 08 T21, "Principles" (7); 17 D28; 06 C8, S7 | BK-23, SM-02 ✓, API-10 | Spec only | Terminal statuses accept no action (unit-tested) |

### 2.8 §5.3 Edge cases to handle

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-5.3-1 | "Estimate rejected: SA is notified and can revise the estimate with the technician, or cancel the booking" | P0 | 17 D23; 08 T09–T11, T22; 06 E1, S4; modules/estimates.md §7.1 | SM-08 ★, SM-09, EST-15, NOT-01, DEP-09 | Spec only | The `REVISE_ESTIMATE`, `RETURN_TO_TECHNICIAN` and `CANCEL` rules from `ESTIMATE_REJECTED` are unit-tested |
| R-5.3-2 | "Parts already in stock: skip ordering and go straight from PARTS_PENDING to PARTS_READY" | P0 | 08 T14; 06 E2, P3; modules/inventory.md "Booking parts" | INV-10, INV-03, SM-13 | Spec only | |
| R-5.3-3 | "Partial parts delivery: receiving only some items keeps the booking in PARTS_ORDERED" | P0 | 17 D43, D83; 08 T15; 06 E3; modules/bookings.md §7.7 | SM-12 ★, INV-05, INV-24, BK-33 | Spec only | |
| R-5.3-4 | "QC failure loop: a failed QC creates an Issue record and returns the job to the technician; it can repeat until QC passes" | P0 | 17 D47; 08 "QC loop (D46, D47)"; 06 E4; modules/qc.md "A QC round" | SM-10 ★, QC-03, QC-05, QC-06, QC-10 | Spec only | |
| R-5.3-5 | "Slot conflicts: two customers must not be able to book the same slot beyond its capacity (use a transaction or unique constraint)" | P0 | 17 D30, D37; 02 §7.4; modules/scheduling.md §7.5; 06 E5 | SM-07 ★, BK-09, BK-10 | Spec only | `slot_counters` and its `booked_count >= 0` CHECK exist as backstops; the locking algorithm is not built |
| R-5.3-6 | "Cancellation: allowed by customer or SA before IN_REPAIR; reserved parts must be released back to stock" | P0 | 17 D24; 08 T22; 18 §3 ("Cancellable statuses"); 06 E6, C7, S8 | SM-11 ★, INV-13, BK-10, BK-22, EST-17 | Spec only | The 11 cancellable statuses are unit-tested; release and slot decrement are not built |

### 2.9 §5.4 Notifications (minimum)

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-5.4-1 | "New booking created" → "Service Advisors of that shop" | P0 | 18 §6 (`BOOKING_CREATED`); 17 D26; 08 T01; modules/notifications.md "Trigger table", "Recipient resolution" | NOT-01, NOT-03 | Spec only | No active SA → the Owner receives it (D26) |
| R-5.4-2 | "Technician assigned" → "That technician" | P0 | 18 §6 (`TECHNICIAN_ASSIGNED`); 08 T04 | NOT-01 | Spec only | |
| R-5.4-3 | "Estimate submitted by technician" → "Service Advisor" | P0 | 18 §6 (`ESTIMATE_SUBMITTED`); 08 T06 | NOT-01, NOT-03 | Spec only | |
| R-5.4-4 | "Estimate sent to customer" → "Customer" | P0 | 18 §6 (`ESTIMATE_SENT`); 08 T07 | NOT-01, NOT-11 | Spec only | |
| R-5.4-5 | "Customer accepted or rejected estimate" → "Service Advisor" | P0 | 18 §6 (`ESTIMATE_APPROVED`, `ESTIMATE_REJECTED`); 08 T08, T09 | NOT-01, NOT-03 | Spec only | |
| R-5.4-6 | "Parts ordered needed / parts ready" → "Parts Person / Technician" | P0 | 18 §6 (`PARTS_NEEDED`, `PARTS_READY`); 08 T12, T16 | NOT-01 | Spec only | "Needed" fires when the parts person is assigned (T12); "ready" goes to the technician at allocation (T16) |
| R-5.4-7 | "Sent to QC / QC failed" → "QC queue / Technician" | P0 | 18 §6 (`QC_REQUESTED`, `QC_FAILED`); 08 T17, T20 | NOT-01, NOT-12 (P1) | Spec only | "QC queue" = every active QC inspector of the shop |
| R-5.4-8 | "Vehicle ready for pickup" → "Customer" | P0 | 18 §6 (`VEHICLE_READY`); 08 O3; 17 D27 | NOT-01, BK-23 | Spec only | |
| R-5.4-9 | "In-app notifications (bell icon with unread count) are enough for core" | P0 | 17 D14, D88; 09 §4.10; 10 X-01, S-01; 03 §4.12 | NOT-05, NOT-06, NOT-10, SEC-34, WEB-11 | Spec only | 15 s polling is the P0 freshness path (D88) |
| R-5.4-10 | "Email is a nice addition" | P1 | 17 D26; modules/notifications.md "E-mail (P1, D26)"; 07 "Day-1 verification checklist" (11) | NOT-09 (P1) | Foundation | `EMAIL_PROVIDER` validation and the reserved-TLD rule (`is_reserved_domain`) are built and unit-tested; there is no sender |

### 2.10 §6 Worked example

On the live site, step 0 is done by the seed (06 §7). SM-18 ★ (API scenario), DEP-10 (scripted live replay) and DEP-09 (manual judge path) cover every step; the Tests column lists only step-specific proofs on top of SM-18. No step can run today.

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-6-0 | Step 0, Fatima (Owner): signs up, creates "Lahore Auto Care" and adds Bilal (SA), Imran (Technician), Sara (QC), Usman (Parts) | P0 | 08 trace step 0; 06 §7 (step 0), O1, O2; 11 "Shops (6, D51)", "Accounts"; 18 §14.1 | SM-18 ★, SEED-01, SEED-07 ★, SEED-08, IDN-01 | Spec only | SM-18 runs step 0 through the API; the live site seeds it |
| R-6-1 | Step 1, Ahmed: "Opens BayFlow, sees 6 shops, selects Lahore Auto Care" | P0 | 17 D51; 11 "Shops (6, D51)"; 06 §7 (step 1); 10 P-01 | BK-16, SEED-01, DEP-02 | Spec only | |
| R-6-2 | Step 2: selects "Check engine light" and "Oil change"; adds notes | P0 | 11 "Service catalogue"; 06 §7 (step 2); 10 P-03 (W2) | BK-06 | Spec only | |
| R-6-3 | Step 3: Friday 10:00 AM; name, email, password, plate LEA-1234, Honda Civic 2016; confirms → `PENDING` | P0 | 08 trace steps 1–3; 06 §7 (step 3); 03 §7.1; 11 "Worked-example readiness"; 17 D51, D71 | BK-01, BK-12, SEED-03, SEED-05, SEED-17, DEP-08 | Spec only | `ahmed@mail.com` is not seeded (D51); judges use a fresh `.test` address |
| R-6-4 | Step 4, Bilal: sees the booking on his dashboard, confirms it, assigns Imran → `CONFIRMED` then `ASSIGNED` | P0 | 08 trace step 4; 06 §7 (step 4); 03 §7.5 | NOT-01, CON-01 | Spec only | |
| R-6-5 | Step 5, Imran: inspects; coil 6,500, filter 900, oil 5,200, labour 4,000 = PKR 16,600; submits → `ESTIMATE_REVIEW` | P0 | 08 trace step 5; 06 §7 (step 5); 18 §14.1; 11 "Inventory" | EST-05 ★, EST-18, SEED-04 | Spec only | |
| R-6-6 | Step 6, Bilal: labour → 3,500 (PKR 16,100); sends → `AWAITING_CUSTOMER` | P0 | 08 trace step 6, "Estimate versions (D39)"; 06 §7 (step 6) | EST-03, EST-04, EST-05 ★ | Spec only | v2 is `SENT`, v1 `SUPERSEDED` |
| R-6-7 | Step 7, Ahmed: logs in with the same email and password, sees the pending-estimate banner, accepts → `ESTIMATE_APPROVED` | P0 | 08 trace step 7; 06 §7 (step 7); 03 §7.2; 01 "Request lifecycle — customer approves an estimate (worked example step 7)" | EST-13, BK-17 | Spec only | |
| R-6-8 | Step 8, Bilal: gets the notification, assigns Usman → `PARTS_PENDING` | P0 | 08 trace step 8; 06 §7 (step 8) | NOT-01 | Spec only | |
| R-6-9 | Step 9, Usman: oil and filter in stock, coil missing; PO for 1 coil → `PARTS_ORDERED` | P0 | 08 trace step 9, "Parts reservations (D42, D43)"; 06 §7 (step 9); 03 §7.3 | INV-02, INV-20 | Spec only | |
| R-6-10 | Step 10, Usman: next day confirms receipt (stock +1), allocates all 3 parts (stock deducted) → `PARTS_READY` then `IN_REPAIR` | P0 | 08 trace step 10; 06 §7 (step 10); 03 §7.4 | INV-06, INV-11, INV-01 ★ | Spec only | |
| R-6-11 | Step 11, Imran: sees the job back, repairs, sends to QC → `QC_PENDING` | P0 | 08 trace step 11; 06 §7 (step 11) | BK-24, NOT-01 | Spec only | |
| R-6-12 | Step 12, Sara: picks it up, road test, oil leak at the filter, creates an issue → `IN_REPAIR` (QC failed) | P0 | 08 trace step 12; 06 §7 (step 12) | QC-02, QC-03 | Spec only | |
| R-6-13 | Step 13, Imran: fixes the seal, resubmits to QC → `QC_PENDING` | P0 | 08 trace step 13; 06 §7 (step 13) | QC-05 | Spec only | |
| R-6-14 | Step 14, Sara: re-tests, all fine, confirms → `READY_FOR_PICKUP` (to SA) | P0 | 08 trace step 14; 06 §7 (step 14); 17 D27 | QC-01, QC-11 | Spec only | |
| R-6-15 | Step 15, Bilal: sends "Your vehicle is ready for pick-up" → `READY_FOR_PICKUP` | P0 | 08 trace step 15; 06 §7 (step 15) | BK-23 | Spec only | |
| R-6-16 | Step 16, Ahmed: collects the car; booking completed → `COMPLETED` | P0 | 08 trace step 16; 06 §7 (step 16); 17 D28 | SEED-10 ★, DEP-09, DEP-10 | Spec only | |
| R-6-17 | Bonus path at step 6: Ahmed phones while Bilal is busy; the AI Front Desk answers, looks him up by phone or booking ID, says the estimate awaits his approval, and leaves Bilal a summary and a task | P2 | 05 §1.2, §4, §6, §15; 06 §7 ("Bonus path at step 6"), §11 (B3, B4) | CALL-04, FD-02, FD-03, FD-05, FD-07, FD-10, AG-06 | Spec only | The scripted demo call (05 §14.3) has no ID (G8) |

### 2.11 §7.1 Authentication and multi-tenancy

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-7.1-1 | "Owner sign up and login" | P0 | 04 "Owner registration — `POST /api/v1/auth/register-owner`", "Login — `POST /api/v1/auth/login`"; modules/identity.md §7.3, §7.4; 03 §4.3; 10 P-05, P-04 | IDN-01, SEC-22, SEC-23, SEC-27 ✓, API-12 ★✓ | Spec only | No `/api/v1/auth/*` route exists |
| R-7.1-2 | "staff login with credentials created by the Owner" | P0 | 17 D18; 04 "Staff accounts — created by the Owner (D18, D19)"; modules/shops.md §7.6; modules/identity.md §7.8 | SEC-21, SEC-22, SEED-07 ★ | Spec only | |
| R-7.1-3 | "customer login with the email and password given during booking" | P0 | 17 D32; 04 "Customer account inside the booking wizard"; 06 §7 (step 7) | BK-01, SEC-19, DEP-09 | Spec only | |
| R-7.1-4 | "Secure password hashing" | P0 | 17 D10; 04 "Password policy and hashing (D10)"; modules/identity.md §7.1 | SEC-44 ✓, SEC-22, SEC-29 ✓ | Foundation | Built and unit-tested in `app/core/security.py`: Argon2id (`pwdlib`), dummy-hash timing and rehash. Nothing calls them yet |
| R-7.1-5 | "token or session based auth" | P0 | 17 D8, D9, D70; 04 "Tokens and cookies"; 01 "Authentication and tenant dependencies" | SEC-04 ✓, SEC-23, SEC-24 ✓, SEC-25 ✓, SEC-26 ✓ | Foundation | Built and tested: JWT on the D63 clock, `bf_session` cookie helpers, and `get_current_user` (cookie or Bearer). No login route issues a token yet |
| R-7.1-6 | "role checks on every protected endpoint" | P0 | 04 "Per-request checks (D9, D20, D21)", "RBAC matrix"; 17 D16, D21, D66, D80; 08 "How an action is executed" | SEC-05, SEC-06, SEC-07, SEC-46, SM-03 ★✓ | Foundation | `require_roles` (403 on a visible shop, tested) and the state-machine role check exist; no protected business endpoint does yet |
| R-7.1-7 | "Tenant isolation enforced server side (shop ID scoped queries or row-level policies)" | P0 | 17 D20, D80; 04 "Tenant isolation — defence in depth (D20)"; 02 §4 | SEC-01 ★, SEC-02, SEC-03, SEC-45 ✓ | Foundation | Layers 1–3 of spec 04's table exist: router dependency (tested), scoped repository base, composite FKs (DB-tested) |
| R-7.1-8 | "Acceptance: a staff token for Shop A gets 403/404 when requesting Shop B's bookings" | P0 | 04 "Acceptance tests" (SEC-01); 03 §7.6; 06 SEC1 | SEC-01 ★, SM-05 ★, DEP-09 | Foundation | The 404 for a non-member shop is proven at dependency level (`test_everything_outside_an_active_membership_is_404`). SEC-01 itself needs the booking routes |

### 2.12 §7.2 Owner: shops and team management

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-7.2-1 | "Create a shop (name, address, city, phone, working hours, slot duration/capacity, logo optional)" | P0 | 17 D17, D37, D38, D55; modules/shops.md §7.1, §7.2; 02 §3.2, §3.3; 03 §4.9; 10 S-03, O-04 | SEC-40, BK-29, BK-30, SHP-01, SHP-02, SHP-03 | Spec only | |
| R-7.2-2 | "Add team members to a shop with a role (SA, Technician, QC, Parts Person)" | P0 | 17 D15, D18; modules/shops.md §7.6; 04 "Staff accounts — created by the Owner (D18, D19)"; 10 O-02 | SEC-05, SEC-16, SEC-21, SEC-27 ✓, API-12 ★✓, SHP-06 | Spec only | |
| R-7.2-3 | "edit or deactivate them" | P0 | 17 D9, D19; modules/shops.md §7.6; 06 O3, SEC3 | SEC-13 ✓, SEC-14, SEC-15 ✓, SEC-17 | Spec only | Immediate revocation (D9) is built in the auth dependency (SEC-13, dependency level); the member PATCH route is not |
| R-7.2-4 | "Create additional shops later; each shop has an independent team, services, slots and inventory" | P0 | 17 D17, D20; modules/shops.md §7.2; 02 §4; 06 O5; 10 O-05 | SEC-40, SEC-02, SEC-45 ✓, INV-17, SEED-08 | Spec only | |
| R-7.2-5 | "Shop switcher in the dashboard for owners with multiple shops" | P0 | 10 S-01; 06 O5; 09 §1 (G7); 17 D66 | SEC-46, SHP-09, SEED-08, DEP-09 | Spec only | |
| R-7.2-6 | "Configure the service catalog (name, description, estimated duration, base price optional)" | P0 | 17 D34, D64; modules/shops.md §7.7; 02 §3.5; 10 O-03 | SEC-05, BK-07, BK-26, SHP-05 | Spec only | |

### 2.13 §7.3 Customer portal

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-7.3-1 | "Landing page: hero section, list or grid of all shops (name, city, rating placeholder, services offered), basic search or city filter" | P0 | 10 P-01; 09 §1 (G1), §6; 17 D56, D64; modules/shops.md §7.8; 03 §4.5 | BK-16, BK-26, DEP-02 | Spec only | 2026-10-10: the directory is built on the mock store (D102): the grid (name, city, rating or "New", first services), the search and the city filter are at `/book` (10 P-03 W1). The landing `/` is the previous marketing page, which the owner chose to keep (spec 16 A25): it lists no shops and is **not linked to `/book`** — nothing on `/`, in the header or in the footer points there (a known gap; the directory is reached from the shop pages, the login page, My bookings and the README). The brief puts the grid on the landing page itself; closing the gap is the owner's call (10 P-01) |
| R-7.3-2 | "Booking wizard: shop > services/problems > time slot > personal and vehicle details > review and confirm" | P0 | 10 P-03 (W1–W5), C-03; 09 §1 (G2), §2.10, §7 (R9); 06 C2, C3 | WEB-06, BK-01, BK-03 ★, DEP-09, WEB-08 (P1) | Spec only | |
| R-7.3-3 | "Slot picker shows only available slots for the chosen date, per shop" | P0 | 17 D37, D68; modules/scheduling.md §7.2, §7.3; 10 P-03 (W3) | BK-11, BK-27, SCH-04, SEED-03 | Spec only | |
| R-7.3-4 | "Customer dashboard: list of bookings with live status timeline" | P0 | 10 C-01, C-02; 09 §4.4; 17 D14, D79; 03 §6.6 | BK-17, BK-19, BK-31, WEB-11, NOT-08 (P1) | Spec only | The status labels exist (WEB-03 ✓) |
| R-7.3-5 | "pending actions highlighted (for example 'Estimate awaiting your approval')" | P0 | 09 §4.11 (`ActionNeededCallout`); 10 C-01, C-02; 17 D48 | BK-17, WEB-04 | Spec only | |
| R-7.3-6 | "estimate detail with itemized parts and labour, accept/reject buttons" | P0 | 09 §4.5; 10 C-02; modules/estimates.md §7.7; 08 T08, T09 | EST-13, EST-14, SEC-12, WEB-04, WEB-01 ✓ | Spec only | |
| R-7.3-7 | "ready-for-pickup message" | P0 | 09 §4.11 (`ReadyForPickupBanner`); 17 D27; 10 C-02 | BK-23, NOT-01 | Spec only | |
| R-7.3-8 | "Responsive design that works on mobile" | P0 | 09 §1 (G8), §5, §6; 10 §12.1 ("All screens (09 §6)") | DEP-12 (P1), WEB-08 (P1) | Foundation | Responsive shells, the mobile sidebar sheet and the tokens exist; there is no real screen to check yet. Only P1 tests cover this P0 item (G6) |

### 2.14 §7.4 Shop POS dashboards

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-7.4-1 | SA: "Bookings list with filters by status" | P0 | 10 SA-01; 09 §4.7; 03 §4.8 (`bookings_list_shop_bookings`, `bookings_get_status_counts`) | BK-18, API-05 ✓, API-06 | Spec only | |
| R-7.4-2 | SA: "confirm/decline; assign technician" | P0 | 10 SA-02; 08 T02–T04; 06 S1, S2; 03 §5.2 | SM-02 ✓, BK-21, BK-22, CON-01 | Spec only | |
| R-7.4-3 | SA: "review/edit estimate; send to customer" | P0 | 10 SA-02; 08 O1, T07; 09 §4.5; 06 S3 | EST-03, EST-04, EST-11 ✓, SEC-35 | Spec only | |
| R-7.4-4 | SA: "assign parts person; notify ready; complete booking" | P0 | 10 SA-02; 08 T12, O3, T21; 06 S5–S7 | SM-02 ✓, BK-21, BK-23 | Spec only | |
| R-7.4-5 | SA: "notification bell" | P0 | 10 S-01, X-01; 09 §4.10; 03 §4.12 | NOT-05, NOT-10, WEB-11 | Spec only | |
| R-7.4-6 | Technician: "My assigned jobs; booking and vehicle detail" | P0 | 10 T-01, T-02; 17 D21; 06 T1 | SEC-08, BK-40 | Spec only | |
| R-7.4-7 | Technician: "add estimate line items (part, quantity, unit cost, labour); submit to SA" | P0 | 10 T-02; 09 §4.5; 08 O1, T06; modules/estimates.md §7.3, §7.4; 17 D40 | EST-02, EST-07, EST-08, EST-09, EST-10, EST-18, EST-24 | Spec only | Line rules in `estimates/domain/lines.py` were in flight at the snapshot, untested (§1.4) |
| R-7.4-8 | Technician: "start repair; send to QC; view QC issues sent back" | P0 | 10 T-02; 08 O2, T17; 06 T5–T7; 03 §4.8 (`bookings_list_booking_qc_inspections`) | BK-24, QC-05, QC-09 | Spec only | |
| R-7.4-9 | Parts Person: "Inventory table (SKU, name, quantity, reorder level, cost)" | P0 | 10 PP-03; 03 §4.10; modules/inventory.md "Catalogue (D44)", "Quantities"; 17 D44, D45 | INV-15, INV-17, INV-21, INV-22, INV-23 | Spec only | |
| R-7.4-10 | Parts Person: "jobs awaiting parts with required vs available" | P0 | 10 PP-01, PP-02; 03 §4.8 (`bookings_get_booking_parts`); modules/inventory.md "Booking parts" | INV-16, BK-37 | Spec only | |
| R-7.4-11 | Parts Person: "create purchase orders; receive orders (stock increases); allocate parts to booking" | P0 | 10 PP-02, PP-04, PP-05; 08 T13, T15, T16; modules/inventory.md "Purchase orders and numbers (D43)", "Purchase-order receipt" | INV-02, INV-05, INV-06, INV-08, INV-11, INV-18 | Spec only | |
| R-7.4-12 | QC Inspector: "Shared QC queue; pick a job" | P0 | 10 QI-01; 08 T18; modules/qc.md "Who sees QC data" | QC-07, QC-10, SM-06 ★ | Spec only | |
| R-7.4-13 | QC Inspector: "checklist/notes; pass or create issue (title, description) which returns the job to the technician" | P0 | 10 QI-02; 17 D46, D47; 08 T19, T20; modules/qc.md "The checklist (D46)" | QC-01, QC-02, QC-03, QC-11, QC-12, QC-13 | Spec only | `qc/domain/checklist.py`, `rules.py` and `qc/schemas.py` were in flight at the snapshot, untested (§1.4) |
| R-7.4-14 | Owner: "Overview of each shop: bookings by status, team list, inventory summary" | P0 | 10 O-01; modules/reporting.md "`OverviewRead`"; 03 §4.13 | RPT-01, RPT-03, RPT-04, RPT-06, RPT-07 | Spec only | |
| R-7.4-15 | Owner: "can open any role view for support" | P0 | 17 D16; 10 O-06; 06 O7; 09 §4.11 (`ReadOnlyBanner`) | SM-16 ★✓, SM-19 ✓, BK-40, WEB-09 | Spec only | The tests prove the Owner cannot act in these views, and BK-40 covers the Owner's visibility predicate; none opens the views as the Owner (G7) |

### 2.15 §7.5 Booking engine and state machine

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-7.5-1 | "Single source of truth for statuses and allowed transitions, enforced in the service layer" | P0 | 08 "Principles" (1, 2), "Implementation sketch"; 17 D22, D48; modules/bookings.md §7.4, §7.8 | SM-01 ★✓, SM-19 ✓, API-06, BK-42 | Foundation | `RULES` is the only table (`check`, `allowed_actions`); the service-layer executor is not built |
| R-7.5-2 | "Every transition recorded in a booking history/audit log (who, when, from, to, note)" | P0 | 08 "Principles" (5), "How an action is executed" (step 12); 02 §3.10, §8; 17 D30, D79 | SM-20 ★, BK-19, BK-31 | Foundation | `booking_events` is append-only with `seq` (DB-tested); nothing writes events yet |
| R-7.5-3 | "Role guard per transition (for example only a Technician assigned to the booking can submit an estimate)" | P0 | 08 "Assignment guards", "Transition table (the rules)"; 04 "RBAC matrix" D | SM-03 ★✓, SM-04 ✓, SEC-07 | Foundation | Role and assignment guards are unit-tested per rule, in the check order role → assignment → status |
| R-7.5-4 | "Estimate versioning or at least a revision count when SA edits before sending" | P0 | 17 D39; 08 O1, "Estimate versions (D39)"; modules/estimates.md §7.1, §7.2 | EST-03, EST-12, EST-16, EST-22, SM-18 ★ | Spec only | Version rules in `estimates/domain/versions.py` were in flight at the snapshot, untested (§1.4) |

### 2.16 §7.6 Inventory and procurement

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-7.6-1 | "Per-shop parts catalog and quantity on hand" | P0 | 17 D44; 02 §3.13; modules/inventory.md "Catalogue (D44)", "Adjustment (D82)"; 03 §4.10 | INV-17, INV-21, INV-22, INV-23, INV-14 ✓ | Spec only | `parts` (per-shop SKU, stock CHECKs) exists; there are no catalogue routes |
| R-7.6-2 | "Required parts compared to stock automatically to show shortages" | P0 | 02 §6 ("Outstanding", "Shortage"); 08 T13; modules/inventory.md "Booking parts" | INV-16, INV-02, INV-15, EST-18 | Spec only | `inventory/domain/stock.py` was in flight at the snapshot, untested (§1.4) |
| R-7.6-3 | "Purchase orders with items and statuses (ORDERED, PARTIALLY_RECEIVED, RECEIVED)" | P0 | 17 D43; 18 §5 (`PurchaseOrderStatus`); 02 §3.16, §3.17; modules/inventory.md "Purchase orders and numbers (D43)" | INV-05, INV-06, INV-07, INV-20 | Spec only | |
| R-7.6-4 | "Receiving increases inventory" | P0 | 08 T15; 17 D42, D43; modules/inventory.md "Purchase-order receipt" | INV-05, INV-06, INV-08, INV-09 | Spec only | |
| R-7.6-5 | "allocation decreases it and links parts to the booking" | P0 | 08 T16; 18 §1 ("Allocation"); 02 §3.14 | INV-11, INV-12, INV-01 ★ | Spec only | |
| R-7.6-6 | "cancellation returns reserved parts" | P0 | 17 D24, D42; 08 T22 | INV-13, SM-11 ★, CON-02 (P1) | Spec only | |

### 2.17 §7.7 Seed data

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-7.7-1 | "A seed script creating at least 3 shops, a team for each role, a service catalog, sample inventory and available slots, so judges can test instantly" | P0 | 17 D13, D51, D60; 11 (all); 07 "Pre-deploy: migrations and seed (D13)" | SEED-01, SEED-02 ★, SEED-03, SEED-04, SEED-09, SEED-12, SEED-19 | Foundation | `python -m app.scripts.seed` exists with the `SEED_ON_DEPLOY` gate and `--force`. It is wired into Railway's pre-deploy step, `start.sh` and `make seed`, but creates no data yet ("no seed data defined yet"). No SEED test exists |
| R-7.7-2 | "Demo credentials listed in the README (and shown on the live site login page or README only …)" | P0 | 17 D52; 11 "README demo-credentials block (paste as is)"; 09 §4.12; 10 P-04; 07 "README outline" (section 2) | SEED-07 ★, SEED-13, DEP-07 | Foundation | README §2 lists every role, and `/login` renders `DemoCredentialsPanel` from `src/content/demo-accounts.ts`. None of the accounts exists until the seed is written, and there is no live site |
| R-7.7-3 | "… not hard-coded in code logic" | P0 | 17 D52; 04 "Logging, errors and secrets"; 09 §4.12, §7 (R11) | SEC-47 (P1) | Foundation | True today: `demo-accounts.ts` is data only, and the API has no code path for demo users. Its only test is P1 (G6) |

### 2.18 §7.8 Core definition of done

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-7.8-1 | "A judge can complete the full flow in section 5 on the live URL, from customer booking to COMPLETED, using seeded accounts" | P0 | 06 §10 ("Script", "Definition of Done coverage (§7.8)"); 14 §1.3, PH6 (CP4), PH7; 12 §3.6, §3.10 | SM-18 ★, SEED-10 ★, DEP-07, DEP-08, DEP-09, DEP-10 | Spec only | See §5 |
| R-7.8-2 | "the QC fail loop … work[s]" | P0 | 06 E4, §10; 08 "QC loop (D46, D47)" | SM-10 ★, QC-03, QC-05, QC-06, DEP-09 | Spec only | |
| R-7.8-3 | "the estimate-rejected path work[s]" | P0 | 06 E1, §10; 17 D23 | SM-08 ★, SM-09, EST-15, DEP-09 | Spec only | |
| R-7.8-4 | "No role can perform another role's action" | P0 | 08 "Error mapping", "`allowed_actions`"; 04 "RBAC matrix" D; 06 SEC2; 09 §7 (R1) | SM-01 ★✓, SM-03 ★✓, SM-04 ✓, SM-16 ★✓, SM-17, SEC-07, WEB-04, WEB-09, DEP-09 | Foundation | Every wrong-role and wrong-assignee cell is rejected in the domain matrix (unit). The API action matrix (SEC-07) and the UI are not built |

### 2.19 §8 Bonus features (introduction)

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-8-1 | "Bonus features are optional and scored separately. Do not start them until the core flow works end to end" | P2 | 17 D36; 05 header, §16 (B0); 14 PH8 ("Dependencies"), §5 | DEP-09, DEP-10 | Not applicable | A process gate, respected so far: only the D84 baseline bonus tables and the blank `CALL_PROVIDER_*` switches exist |

### 2.20 §8.1 In-app calling between Service Advisor and customer

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-8.1-1 | "Allow the SA and the customer to call each other directly from their dashboards, without sharing phone numbers" | P2 | 05 §1.1, §2, §8.3, §13; 17 D57; 04 "RBAC matrix" E | CALL-01, CALL-02, CALL-10, CALL-14 | Spec only | |
| R-8.1-2 | "Call button on the booking page for both parties (SA to customer and customer to shop's SA)" | P2 | 05 §8.1, §8.2, §9.2; 10 B-01; 06 §11 (B1, B2) | CALL-01, CALL-10, CALL-12, SEC-50 | Spec only | |
| R-8.1-3 | "Browser-based voice using WebRTC, or a provider SDK such as … LiveKit …" | P2 | 17 D57; 05 §2, §17; 07 "9. Agent service (bonus, spec 05)" | CALL-02, CALL-12 | Spec only | |
| R-8.1-4 | "Incoming call popup with accept and decline" | P2 | 17 D78; 05 §9.3; 10 B-01; 09 §4.13 | CALL-16, CALL-03, CALL-06, CALL-18, CALL-19 | Spec only | |
| R-8.1-5 | "call state: ringing, connected, ended, missed" | P2 | 18 §5 (`CallStatus`); 05 §3.1, §3.2; modules/calls.md "Lifecycle" | CALL-01, CALL-02, CALL-04, CALL-07, CALL-09 | Spec only | |
| R-8.1-6 | "Call log stored against the booking (who, when, duration, outcome)" | P2 | 05 §3.8, §7.1, §9.5; 10 B-03 | CALL-09, CALL-10, CALL-14 | Spec only | `call_logs` exists only as a baseline table |
| R-8.1-7 | "A missed call must be recorded and, in the AI track, can trigger the AI Front Desk" | P2 | 05 §3.6, §3.7; 17 D58, D77; 18 §6 (`CALL_MISSED`) | CALL-04, CALL-06, CALL-07, CALL-08, CALL-15, NOT-13 | Spec only | |

### 2.21 §8.2 AI Front Desk

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-8.2-1 | "If a customer calls and no SA picks up within a set time (for example 20 seconds), an AI voice agent answers instead" | P2 | 17 D58, D77; 05 §3.5, §3.7; 18 §12 (`AI_RING_TIMEOUT_SECONDS`) | CALL-04, CALL-05, CALL-06, CALL-15, FD-09 | Spec only | |
| R-8.2-2 | "Greets the customer, asks who they are and why they are calling, and identifies them by name, phone, email or booking reference" | P2 | 05 §4.1, §4.2; 17 D33, D58 | FD-02, FD-03, AG-06 | Spec only | |
| R-8.2-3 | "Fetches the customer's booking(s) … through tool calls and answers accurately (current status, appointment time, pending estimate, ready for pick-up)" | P2 | 05 §4.3, §5.2, §5.3 | FD-04, FD-05, FD-06, AG-01 | Spec only | |
| R-8.2-4 | "Handles simple requests: reschedule request, 'what is my status', 'how much is the estimate'" | P2 | 05 §4.4, §6.4 | FD-06, FD-07, AG-04 | Spec only | A reschedule request becomes a task; the booking and its slot stay unchanged (FD-07) |
| R-8.2-5 | "Never invents data. If it cannot answer, it says so and promises a callback" | P2 | 05 §4.5, §4.6, §12 | AG-04, FD-09, FD-11, FD-14 | Spec only | |
| R-8.2-6 | "After the call, generates a summary (intent, details, sentiment) and creates a Task for the SA … linked to the booking and the call log" | P2 | 05 §6.1–§6.4, §7.2, §7.3; 18 §6 (`AI_TASK_CREATED`) | FD-07, FD-10, FD-11, FD-12, AG-02, AG-03, NOT-13 | Spec only | |
| R-8.2-7 | "SA dashboard section: AI call summaries and open tasks, with mark-as-done" | P2 | 05 §6.5, §8.2, §9.6; 10 B-04; 06 §11 (B4); 04 "RBAC matrix" E | SEC-50, FD-10, CALL-10 | Spec only | |
| R-8.2-8 | Building blocks: an LLM with function calling, speech-to-text/text-to-speech or a realtime voice API, "and guardrails that limit the agent to the caller's own data" | P2 | 17 D58; 05 §2, §5.1, §13; 04 "Bonus: AI agent and LiveKit webhook (D58)", "Threat model" (26, 28) | SEC-36, FD-01, FD-04, AG-05 | Spec only | The guardrails are enforced by the API, not the prompt (D58) |

### 2.22 §8.3 Other optional ideas and the evidence table

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-8.3-1 | "Email … notifications" | P1 | 17 D26; modules/notifications.md "E-mail (P1, D26)"; 07 "Day-1 verification checklist" (11) | NOT-09 (P1) | Foundation | Same state as R-5.4-10 |
| R-8.3-2 | "SMS notifications; PWA or push notifications" | P3 | 00 "Out of scope for the hackathon"; modules/notifications.md "Out of scope"; 17 D4 | — | Not applicable | Deferred |
| R-8.3-3 | "Owner analytics: revenue, average turnaround time, QC fail rate per shop" | P3 | modules/reporting.md "Out of scope"; 13 §2 (AI-34) | — | Not applicable | In-scope reporting is the P0 overview (R-7.4-14) and the P1 multi-shop summary (RPT-02) |
| R-8.3-4 | "Invoice PDF generation and payment status" | P3 | 00 "Out of scope for the hackathon"; modules/estimates.md §2; modules/bookings.md §2 | — | Not applicable | See also R-11-4 |
| R-8.3-5 | "Vehicle service history per car number" | P3 | 17 D35 ("enables … later") | — | Not applicable | Only D35's rationale mentions it; no spec records the deferral (G9) |
| R-8.3-6 | "Real-time dashboard updates using WebSockets or server-sent events" | P1 | 17 D14, D70, D88; 03 §6; 01 "Realtime hub (D14; P1, D88)"; modules/notifications.md "Realtime hub", "Push path (after commit)" | NOT-08 (P1), NOT-12, SEC-33, SEC-38 ✓, WEB-10 (P1), DEP-04 (P1), NOT-16 (P1), NOT-17 (P1) | Foundation | `typ = ws` tickets valid 60 s and ticket redaction in logs are built and unit-tested. The hub, the ticket route and `/api/v1/ws` are not |
| R-8.3-7 | Evidence for in-app calling: "Two browsers calling each other on the live site; call log entry" | P2 | 05 §1.2, §15 (scene 1), §16 (B2 "Evidence 1"); 14 PH8, §7 | CALL-01, CALL-02, CALL-09 | Spec only | The CALL tests prove it at API level only; the live two-browser evidence has no ID (G8) |
| R-8.3-8 | Evidence for the AI Front Desk: "Demo video or live demo of unanswered call, conversation, then summary and task in SA dashboard" | P2 | 05 §1.2, §14.3, §15, §16 (B6 "Evidence 2"); 14 PH9 | CALL-04, FD-07, FD-10, AG-04, AG-05, AG-06 | Spec only | The 05 §14.3 scripted runs have no ID (G8) |

### 2.23 §9.1 What you must submit

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-9.1-1 | GitHub repository: "Public repo" | P0 | 14 §7; 07 "Hosts overview", "Repository standards"; 12 §2.5 | DEP-14 | Foundation | Remote `origin` is set (github.com/Haseebraza12/bayflow-loopverse-hackhathon-). Public visibility was not verified in this audit |
| R-9.1-2 | "meaningful commit history (not a single commit)" | P0 | 12 §2.1, §2.2; 07 "Repository standards"; 14 §1.1 (8), §7 | — (G1) | Foundation | Today the history is a single commit, "first commit". The rules, PR template and hooks are in place |
| R-9.1-3 | "organized folders" | P0 | 01 "Monorepo root layout (D5)", "Backend folder structure (`apps/api`)"; 07 "Repository standards"; 17 D5 | — (G3) | Built | The layout matches spec 01, and 8/8 import-linter contracts are kept (run in this audit) |
| R-9.1-4 | "no committed secrets" | P0 | 12 §2.5; 07 "Repository standards"; 17 D85 | DEP-14, SEC-37 ✓ | Built | Inspected: the only tracked env file is `.env.example`, which holds placeholders that production refuses (D85); `.env` is git-ignored. gitleaks runs in CI and pre-commit but was not run here |
| R-9.1-5 | Live URL: "Deployed and reachable without local setup" | P0 | 07 "Hosts overview", "Railway setup (API, PostgreSQL, bonus agent)", "Vercel setup (web)", "Day-1 verification checklist"; 14 PH0, §7 | DEP-01, DEP-02, DEP-03, DEP-05, DEP-06, DEP-15 | Foundation | `apps/api/railway.json`, both Dockerfiles, the `next.config.ts` rewrite and `scripts/smoke.sh` exist. Nothing is deployed |
| R-9.1-6 | Live URL: "seeded demo data and demo accounts for every role" | P0 | 11 (all); 17 D51, D52, D60; 07 "Pre-deploy: migrations and seed (D13)" | SEED-01, SEED-07 ★, SEED-13, DEP-07, DEP-08 | Foundation | Only the seed entry point exists (R-7.7-1) |
| R-9.1-7 | README.md (repo root): "Project overview, tech stack, prerequisites, install steps, how to run locally, how to seed, how to run tests, demo credentials, deployment notes, architecture summary" | P0 | 07 "README outline"; 14 §7; 12 §4.7 | DEP-07 (G4) | Foundation | Sections 1–18 exist. "Tests" (11), "Deployment" (14), "Design decisions" (15) and the live URL are still "to be completed". §2 and §10 describe seed data that does not exist yet |
| R-9.1-8 | .env.example (repo root): "Every environment variable the project needs, with placeholder values and a short comment on each. Real values must never be committed" | P0 | 07 "Root `.env.example`", "Environment variable inventory"; 18 §12; 17 D85 | SEC-37 ✓, DEP-14 (G5) | Built | Inspected: 33 variables, matching glossary §12 exactly, each with a comment line and a placeholder value |
| R-9.1-9 | Optional: "Short demo video (3 to 5 minutes)" | P1 | 06 §10 ("Video storyboard (3–5 minutes, §9.1 optional)"); 05 §15; 14 PH9, §5 (6), §7 | — (G8) | Spec only | |
| R-9.1-10 | Optional: "architecture diagram" | P1 | 01 "System topology"; 07 "README outline" (section 4); 14 §7 | — (G8) | Foundation | The topology diagram is in spec 01 (tracked). README §4 links to spec 01 but does not show the diagram yet |
| R-9.1-11 | Optional: "API docs (Swagger/OpenAPI or Postman collection)" | P1 | 03 §1.11, §8.2; 17 D50, D76; 07 "README outline" (section 12) | API-09 (P1), DEP-13 (P1), WEB-07 | Foundation | Swagger UI at `/docs` lists only `/health`; the committed `openapi.json` is a placeholder (Open question 6) |

### 2.24 §9.2 README must include

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-9.2-1 | "Prerequisites: exact runtime and tool versions" | P0 | 07 "README outline" (section 6); 17 D1, D11, D12 | — (G4) | Built | README §6 pins Python 3.12.x, uv 0.12.x, Node 24 LTS, pnpm 10.34.6, PostgreSQL 16 and Docker Compose v2 |
| R-9.2-2 | "Install dependencies: exact commands for each app (frontend, backend)" | P0 | 07 "README outline" (section 8); 17 D5 | — (G4) | Built | README §8: `cd apps/api && uv sync`, `cd apps/web && pnpm install`, `make setup` |
| R-9.2-3 | "Environment setup: copy .env.example to .env and explain each variable" | P0 | 07 "README outline" (section 9), "Environment variable inventory" | — (G4) | Foundation | README §9 covers the copy step and the key notes. The per-variable table is "to be completed"; every variable is commented in `.env.example` |
| R-9.2-4 | "Database: how to create, migrate and seed" | P0 | 07 "README outline" (section 10), "Makefile (repo root)" | SEED-09, SEED-16 | Foundation | README §10 is written, but the seed loads nothing yet, so the text describes data that does not exist |
| R-9.2-5 | "Run: one command or a few clear commands to start everything; ideally also docker compose up" | P0 | 17 D73; 07 "Local development" (Options A, B), "README outline" (sections 7, 8) | DEV-01 (P1) | Built | `start.sh`/`start.bat`, `docker compose up` and `make dev` exist and are documented (README §7). DEV-01 passed by hand on Linux (spec 12 §5 DEV-01; spec 14 PH0 exit status). The stack it starts has no features yet. Only a P1 check covers this P0 item (G6) |
| R-9.2-6 | "Demo accounts: email and password for Owner, SA, Technician, QC, Parts and Customer" | P0 | 11 "README demo-credentials block (paste as is)"; 07 "README outline" (section 2); 18 §14 | DEP-07, SEED-07 ★, SEC-47 (P1) | Foundation | Listed in README §2; not seeded yet |
| R-9.2-7 | "Project structure and design decisions in a short section" | P0 | 07 "README outline" (sections 5, 15); 01 "Monorepo root layout (D5)", "ADR-001" | — (G4) | Foundation | README §5 (structure) is done; §15 (design decisions) is "to be completed" |

### 2.25 §9.3 Example .env.example

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-9.3-1 | The sample's groups and names: App (`NODE_ENV`, `PORT`, `CLIENT_URL`), Database (`DATABASE_URL`), Auth (`JWT_SECRET`, `JWT_EXPIRES_IN`), Email optional (`SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`) | P0 | 18 §12; 07 "Root `.env.example`", "README outline" (section 9); 17 D8, D85 | SEC-24 ✓, SEC-37 ✓ (G5) | Built | Same groups and names, with two documented deviations: `APP_ENV` replaces `NODE_ENV` because the API is Python (README §9), and the `JWT_SECRET` placeholder is at least 32 characters, which production refuses anyway (D85) |
| R-9.3-2 | "Bonus: calling / AI (leave blank if not used)": `CALL_PROVIDER_API_KEY`, `LLM_API_KEY`, `STT_TTS_API_KEY` | P0 | 18 §12; 05 §10; 07 "Root `.env.example`" | CALL-20 | Built | The bonus variables are present and blank. The API's feature switches follow them, unit-tested in `tests/unit/core/test_config.py` |

### 2.26 §9.4 Code quality expectations

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-9.4-1 | "Clean, readable code with consistent formatting (linter and formatter configured)" | P0 | 12 §1.1, §1.2, §6; 17 D53, D80; 07 "Repository standards" (pre-commit hooks) | — (12 §6 gates; G3) | Built | Ruff, Ruff format, ESLint (`--max-warnings 0`) and Prettier are configured, passed in this audit, and run in the CI `api` and `web` jobs |
| R-9.4-2 | "Input validation on all endpoints" | P0 | 17 D49; 03 §1.5, §2.3; 04 "Hardening tiers" (Tier 1, 5); 12 §1.1 | API-02 ✓, API-03 ✓, SEC-17, SEC-29 ✓, SEC-30 ✓ | Foundation | The error handlers turn every validation failure into a 422 with field errors (tested); the business schemas are not written |
| R-9.4-3 | "consistent error responses; proper HTTP status codes" | P0 | 17 D49; 03 §2; 01 "Error handling (D49)"; 18 §10 | API-01 ★✓, API-03 ✓, API-04 ✓, API-13 ✓, SEC-28 ✓ | Foundation | RFC 9457 responses for every glossary §10 code — including 404, 405, 413, 429 and 500 — are built and tested on test routes |
| R-9.4-4 | "Reusable UI components" | P0 | 09 §3.12, §4; 12 §1.2 ("Components") | WEB-03 ✓, WEB-04 (G3) | Foundation | shadcn/ui primitives, `StatusBadge` and the layout shells exist; the feature components do not |
| R-9.4-5 | "centralized API client" | P0 | 17 D50, D76; 09 §2.6; 12 §1.2, §3.9 | WEB-05 ✓, WEB-07 | Foundation | One `openapi-fetch` client (`src/lib/api/client.ts`) and an ESLint ban on raw `fetch`. WEB-07 currently fails: the committed `openapi.json` is stale (Open question 6) |
| R-9.4-6 | "typed code (TypeScript or Python type hints) is preferred" | P0 | 17 D50, D53; 12 §1.1, §1.2 | WEB-07 (and the 12 §6 gates; G3) | Built | mypy strict passes on 74 files; TypeScript `strict` with `no-explicit-any`. Only the generated API types are still pending |
| R-9.4-7 | "Sensible commit messages and small commits" | P0 | 12 §2.1; 07 "Repository standards"; 18 §13 | — (G1) | Foundation | The Conventional Commits rule, PR template and pre-commit hooks are in place; there is one commit so far |
| R-9.4-8 | "AI-generated code must be reviewed and understood by the team" | P0 | 12 §2.3, §2.4; 14 §6 | — (G2) | Foundation | The PR template's attestation and the reviewer's "explain it" rule |

### 2.27 §10 Judging criteria

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-10-1 | Core flow completeness (35 %): "Full lifecycle works live, including QC loop and estimate approval" | P0 | 00 "Judging criteria (brief §10) → where we earn the points"; 14 §1.2, §1.3 | SM-18 ★, SM-08 ★, SM-09, SM-10 ★, DEP-09, DEP-10 | Spec only | See §4 |
| R-10-2 | Architecture and code quality (20 %): "Clean structure, state machine, tenant isolation, validation" | P0 | 00; 01; 08; 12 §6 | SM-01 ★✓, SM-19 ✓, SEC-02, SEC-45 ✓, API-01 ★✓, API-02 ✓ | Foundation | |
| R-10-3 | Product and UX (15 %): "Clear landing page and booking wizard; role dashboards that show only relevant work" | P0 | 09 §1, §7; 10 §12.1 (the §10 row) | WEB-04, WEB-06, WEB-09, DEP-02, DEP-09, DEP-12 (P1) | Spec only | 2026-10-10: the directory (`/book`), the booking wizard (`1f09ead`) and every role dashboard are built in the D101 design on the mock store (D102); none reads the API yet. The landing lists no shops and does not link to `/book` (R-7.3-1) |
| R-10-4 | Deployment and docs (10 %): "Live URL works; README and .env.example let a stranger run it in minutes" | P0 | 07; 14 PH7 (the "stranger" exit check), §7 | DEP-01, DEP-02, DEP-03, DEP-07, DEV-01 (P1) | Foundation | |
| R-10-5 | Multi-tenancy and security (10 %): "Owner multi-shop, per-shop teams, access control" | P0 | 04; 17 D15–D21 | SEC-01 ★, SEC-02, SEC-07, SEC-45 ✓, SEC-46, SEED-08 | Foundation | |
| R-10-6 | Bonus features (10 %): "Working calling and/or AI Front Desk with demo" | P2 | 05; 14 PH8, PH9 | CALL-01…CALL-16, FD-01…FD-12, AG-01…AG-06, SEC-36, SEC-49, SEC-50 | Spec only | |
| R-10-7 | Tip: "deploy early and keep deploying" | P0 | 07 "Day-1 verification checklist"; 14 PH0, §6 (CP1, "Deploy rules") | DEP-01, DEP-05, DEP-06 | Foundation | The deploy config exists; nothing is deployed, so CP1 has not been reached |

### 2.28 §11 FAQ (answers that constrain behaviour)

| ID | Requirement (brief) | Pri | Spec(s) | Tests | Status | Notes |
|---|---|---|---|---|---|---|
| R-11-1 | Tech stack: "Any … Judges evaluate the result and the code quality, not the brand of the framework" | P0 | 17 D1–D3; 01 "ADR-001" | — | Not applicable | Same as R-1-4 |
| R-11-2 | AI tools: "You must understand and be able to explain all code, and the output must still meet the clean-code standards" | P0 | 12 §2.3, §2.4; 14 §6 | — (G2) | Foundation | Same as R-9.4-8 |
| R-11-3 | Bonus: "Core features are mandatory and judged first. Bonus features … only count if the core flow works" | P2 | 17 D36; 14 PH8; 05 §16 (B0) | — | Not applicable | Same as R-8-1 |
| R-11-4 | Payments: "No. Cost estimates and approval are enough. Payment integration is optional" | P3 | 00 "Out of scope for the hackathon"; modules/estimates.md §2; modules/bookings.md §2 | — | Not applicable | The approval half is covered by R-3-7 and R-7.3-6 |
| R-11-5 | Customer login: "With the email and password entered during booking. If that email already exists, reuse the account instead of creating a duplicate" | P0 | 17 D32; 04 "Customer account inside the booking wizard" | BK-02, BK-03 ★, SEC-18, SEC-19 | Spec only | Same as R-5.1-7 and R-7.1-3 |
| R-11-6 | Multiple roles: "per shop … each role's view and permissions must still work … one role per shop membership" | P0 | 17 D15; 04 "One user, many hats"; 08 "Who is the actor?" | SEC-07, SEC-40, SEC-46 | Foundation | Same as R-4-7 |
| R-11-7 | Owner as other roles: "Owners should at least be able to view and manage all bookings in their shops. Allowing them to perform other roles' actions for support is optional" | P0 | 17 D16; 10 O-06; 06 O7, O8 | SM-16 ★✓, SM-19 ✓, BK-18, BK-40, WEB-09 | Foundation | "Owner = SA actions" is built in the domain; read access to the other role views is untested (G7) |
| R-11-8 | Multiple shops: "One owner account can create many shops. Each shop has its own team members, services, slots, inventory and bookings, with a shop switcher in the POS" | P0 | 17 D17, D20; modules/shops.md §7.2, §7.9; 10 S-01, O-05 | SEC-02, SEC-40, SEC-46, SEED-08 | Spec only | Same as R-7.2-4 and R-7.2-5 |
| R-11-9 | QC pick: "Any QC person of that shop. Make sure two people cannot pick the same job at once (first to pick locks it)" | P0 | 17 D30, D47; 08 T18; 02 §7; modules/qc.md "Concurrency and transactions" | SM-06 ★, QC-07, QC-10, BK-39 | Foundation | The first-wins outcome (`ALREADY_PICKED`) is in the domain and unit-tested; the row lock that makes it hold under concurrency is not built |
| R-11-10 | Live site: "Seeded data and demo accounts for all roles so judges can test without setup" | P0 | 11; 17 D51, D60 | SEED-01, SEED-07 ★, DEP-07, DEP-08 | Foundation | Same as R-9.1-6 |
| R-11-11 | Slots: "Per-shop working hours with fixed duration slots and a capacity is enough. Booked slots must not be double-booked" | P0 | 17 D37; modules/scheduling.md §7.1–§7.5; modules/shops.md §7.1 | BK-08, BK-09, BK-30, SCH-02, SM-07 ★, CON-05 (P1) | Spec only | |
| R-11-12 | "Prioritize a working end-to-end flow over extra polish. A smaller, correct, deployed product beats a large broken one" | P0 | 17 D4, D36; 14 §5 ("Never cut"), §6 | — | Not applicable | A process rule, implemented by spec 14's never-cut list and the ★ minimum proof set |
| R-11-13 | AI Front Desk test: "a simulated unanswered call, the AI identifying the customer, answering from real booking data, and a summary plus task appearing in the SA dashboard" | P2 | 05 §1.2, §14.3, §15 | CALL-04, FD-02, FD-03, FD-05, FD-10 | Spec only | Same as R-8.3-8 |
| R-11-14 | Submission: "GitHub repo link, live URL, README and .env.example in the repo root, and optionally a demo video" | P0 | 14 §7, PH10 | DEP-01, DEP-14 | Foundation | Same as R-1-6 |

## 3. Coverage summary

### 3.1 Counts

| Brief section | Rows | P0 | P1 | P2 | P3 | Spec only | Foundation | Built | Not applicable |
|---|---|---|---|---|---|---|---|---|---|
| §1 | 7 | 7 | 0 | 0 | 0 | 1 | 4 | 0 | 2 |
| §2 | 5 | 5 | 0 | 0 | 0 | 3 | 2 | 0 | 0 |
| §3 | 17 | 17 | 0 | 0 | 0 | 8 | 8 | 1 | 0 |
| §4 | 13 | 13 | 0 | 0 | 0 | 11 | 2 | 0 | 0 |
| §5 | 2 | 2 | 0 | 0 | 0 | 0 | 2 | 0 | 0 |
| §5.1 | 7 | 7 | 0 | 0 | 0 | 7 | 0 | 0 | 0 |
| §5.2 | 15 | 15 | 0 | 0 | 0 | 15 | 0 | 0 | 0 |
| §5.3 | 6 | 6 | 0 | 0 | 0 | 6 | 0 | 0 | 0 |
| §5.4 | 10 | 9 | 1 | 0 | 0 | 9 | 1 | 0 | 0 |
| §6 | 18 | 17 | 0 | 1 | 0 | 18 | 0 | 0 | 0 |
| §7.1 | 8 | 8 | 0 | 0 | 0 | 3 | 5 | 0 | 0 |
| §7.2 | 6 | 6 | 0 | 0 | 0 | 6 | 0 | 0 | 0 |
| §7.3 | 8 | 8 | 0 | 0 | 0 | 7 | 1 | 0 | 0 |
| §7.4 | 15 | 15 | 0 | 0 | 0 | 15 | 0 | 0 | 0 |
| §7.5 | 4 | 4 | 0 | 0 | 0 | 1 | 3 | 0 | 0 |
| §7.6 | 6 | 6 | 0 | 0 | 0 | 6 | 0 | 0 | 0 |
| §7.7 | 3 | 3 | 0 | 0 | 0 | 0 | 3 | 0 | 0 |
| §7.8 | 4 | 4 | 0 | 0 | 0 | 3 | 1 | 0 | 0 |
| §8 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 1 |
| §8.1 | 7 | 0 | 0 | 7 | 0 | 7 | 0 | 0 | 0 |
| §8.2 | 8 | 0 | 0 | 8 | 0 | 8 | 0 | 0 | 0 |
| §8.3 | 8 | 0 | 2 | 2 | 4 | 2 | 2 | 0 | 4 |
| §9.1 | 11 | 8 | 3 | 0 | 0 | 1 | 7 | 3 | 0 |
| §9.2 | 7 | 7 | 0 | 0 | 0 | 0 | 4 | 3 | 0 |
| §9.3 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 2 | 0 |
| §9.4 | 8 | 8 | 0 | 0 | 0 | 0 | 6 | 2 | 0 |
| §10 | 7 | 6 | 0 | 1 | 0 | 3 | 4 | 0 | 0 |
| §11 | 14 | 11 | 0 | 2 | 1 | 4 | 6 | 0 | 4 |
| **Total** | **227** | **194** | **6** | **22** | **5** | **144** | **61** | **11** | **11** |

Status by priority:

| Priority | Rows | Spec only | Foundation | Built | Not applicable |
|---|---|---|---|---|---|
| P0 | 194 | 123 | 56 | 11 | 4 |
| P1 | 6 | 1 | 5 | 0 | 0 |
| P2 | 22 | 20 | 0 | 0 | 2 |
| P3 | 5 | 0 | 0 | 0 | 5 |

**What "Built" means today.** The eleven Built rows are:

- the tenant identifier on every record (R-3-13);
- repository hygiene: folders and no committed secrets (R-9.1-3, R-9.1-4);
- `.env.example` (R-9.1-8, R-9.3-1, R-9.3-2);
- the README's prerequisites, install commands and one-command start (R-9.2-1, R-9.2-2, R-9.2-5);
- the code-quality tooling (R-9.4-1, R-9.4-6).

No user-facing feature is Built yet.

### 3.2 Tests with code today

38 catalogue IDs have at least part of their test in the repo (snapshot 16:37). They fall into two groups, depending on whether the test carries its ID.

**Cited by ID (31 IDs).** In the state-machine file the test function names start with the ID, as spec 12 §1.4 requires. The other files cite the ID in their module docstrings.

- **Domain halves, unit:** SM-01, SM-02, SM-03, SM-04, SM-16, SM-19, QC-08 (complete) and EST-11, in `apps/api/tests/unit/bookings/test_state_machine.py` (1,131 cases).
- **Auth dependencies:** SEC-04, SEC-13, SEC-25, SEC-26, at dependency level, in `tests/api/test_auth_dependencies.py`.
- **Tokens:** SEC-24 and SEC-25 in `tests/unit/core/test_security.py`.
- **Config:** SEC-24 (`JWT_EXPIRES_IN` parsing) and SEC-37 (production guards) in `tests/unit/core/test_config.py`.
- **Error model:** SEC-28, SEC-29 (the "422 never echoes input" half), SEC-30, API-01, API-02, API-03 and API-04 in `tests/api/test_error_handlers.py`.
- **Health:** API-08 in `tests/api/test_health.py`, with the D84 body.
- **Database:** SEC-15 (DB half), SEC-45 and INV-14 in `tests/db/test_constraints.py`.
- **Email:** API-12 (unit half) in `tests/unit/shared/test_email.py`.
- **Web:** WEB-01 and WEB-02 in `src/lib/format.test.ts`; WEB-03 in `src/lib/status.test.ts`; WEB-05 in `src/lib/api/errors.test.ts`; SEC-32 (web half) in `apps/web/next.config.test.ts`.

**Behaviour covered, but the test does not carry the ID (7 more IDs).** Rename these tests (§7) so that a grep finds them.

- SEC-27 (the per-account limiter and the per-IP 429 problem) — `tests/unit/core/test_security.py`, `tests/api/test_error_handlers.py`.
- SEC-31 (CORS) and SEC-32 (API half) — `tests/api/test_middleware.py`.
- SEC-38 (ticket redaction) — `tests/unit/core/test_logging.py`.
- SEC-44 (Argon2id storage) — `tests/unit/core/test_security.py`.
- EST-20 (whole rupees) — `tests/db/test_constraints.py` and `tests/unit/shared/test_money.py`.
- API-05 (pagination defaults on a test route) and API-13 (`no-store` on test routes) — `tests/api/test_error_handlers.py`, `tests/api/test_middleware.py`.

**Not counted:**

- **SM-20.** Only the state-machine module's docstring range ("SM-01…SM-20") mentions it (spec 12 §5's status line no longer lists it, Open question 5). Writing one event per action needs the executor, so no SM-20 test exists yet.
- **Tests without a catalogue ID.** `tests/unit/test_main_wiring.py` (D89) and `tests/unit/shared/test_phone.py` (the `Phone` type) are new and carry no catalogue ID.

**The ★ set.** Of the 21 ★ tests, five have code, mostly halves: SM-01, SM-03, SM-16, API-01, API-12. The other 16 need routes, the seed or scenarios.

**Missing groups.** No test exists yet in these groups: SEED, IDN, SHP, SCH, BK, INV (except INV-14), QC (except QC-08), NOT, RPT, CON, DEP, CALL, FD or AG. DEV-01 is a manual check, recorded as passed on Linux.

### 3.3 Gaps

**No requirement lacks a spec section.** The nearest miss is G9.

The gaps below are requirements without a catalogue test ID, or proven only by lower-priority tests. Each comes with a proposed home. No new IDs are invented here: spec 12 (or spec 05) assigns them.

| Gap | Requirements | What is missing | Proposed home |
|---|---|---|---|
| G1 | R-9.1-2, R-9.4-7 | No check that the history is "meaningful … not a single commit" or that commits are small and follow Conventional Commits. Today there is one commit | spec 12 §6: a commit-message lint gate on pull requests. Spec 12 §5 DEP group: a pre-submission check on commit count and that every team member authored commits. Spec 14 §7 already has the checklist boxes |
| G2 | R-1-5, R-9.4-8, R-11-2 | "AI-generated code reviewed and understood" cannot be automated. The evidence is the PR-template attestation (12 §2.3) and the explain-it round (14 §6) | spec 14 §7: a box "every merged PR carries the attestation". Accept as a manual check, without a catalogue ID |
| G3 | R-9.1-3, R-9.4-1, R-9.4-4, R-9.4-6 | Proven by the CI gates of 12 §6 (Ruff, format, mypy, `tsc`, ESLint, Prettier, import-linter), which have no catalogue IDs. "Reusable UI components" is checked only in review (12 §2.4) | spec 12 §6: give the gates stable IDs so this matrix can cite them |
| G4 | R-9.1-7, R-9.2-1, R-9.2-2, R-9.2-3, R-9.2-7 | Only DEP-07 touches the README (demo accounts). Spec 14 PH7's exit check — "a teammate who did not write the README follows it on a clean machine … under 15 minutes" — has no ID | spec 12 §5 DEP (or DEV) group: number that check and have it tick spec 07's "README outline" table row by row |
| G5 | R-9.1-8, R-9.3-1, R-9.3-2 | SEC-37 and DEP-14 prove no secrets are tracked. Nothing proves every variable the code reads is listed in `.env.example` with a comment | spec 12 §5: a unit test comparing the `Settings` fields and glossary §12 with the keys and comment lines of `.env.example` |
| G6 | R-7.3-8, R-7.7-3, R-9.2-5 | P0 brief items whose only tests are P1: responsive design (DEP-12, WEB-08), demo credentials not hard-coded (SEC-47), run in one command (DEV-01) | spec 12: raise DEP-12 and SEC-47 to P0 (both cheap). Make DEV-01, or the G4 check, P0 for the README "Run" item. Spec 14 PH3's unnumbered "on the live URL at phone width" exit check can become DEP-12 |
| G7 | R-7.4-15, R-11-7 (and R-4-8) | Tests prove the Owner cannot act in the technician, parts and QC views (SM-16, SM-19, WEB-09). BK-40 checks the D21 visibility predicate for every role, the Owner included. But no test has the Owner open those views or their reads — T-01, PP-01, QI-01, `GET …/bookings/{booking_id}/parts`, `…/qc-inspections` — and BK-37 lists the QC inspector and technician cases, not the Owner | spec 12 §5: add Owner read cells to the action matrix (12 §3.4, SEC-07), and an Owner case to BK-37 |
| G8 | R-6-17, R-8.3-7, R-8.3-8, R-11-13, R-9.1-9, R-9.1-10 | The demo evidence and optional deliverables are manual and unnumbered: spec 05 §14.3 scripted demo call, §16 "Evidence 1" and "Evidence 2", the video, the architecture diagram | spec 05 §14: number the evidence checks. Spec 14 §7 references them. The optional items may stay manual |
| G9 | R-8.3-5 | "Vehicle service history per car number" appears only in D35's rationale. No spec records that it is deferred | spec 00 "Out of scope for the hackathon", or `modules/bookings.md` §2 "Out of scope", pointing to D35 and `GET /api/v1/me/vehicles` (P1) |

## 4. Judging-criteria map (brief §10)

| Criterion | Weight | What judges look for | Requirement IDs | Tests that earn it | Today |
|---|---|---|---|---|---|
| Core flow completeness | 35 % | "Full lifecycle works live, including QC loop and estimate approval" | R-5-1, R-5-2, R-5.1-1…R-5.1-7, R-5.2-1…R-5.2-15, R-5.3-1…R-5.3-6, R-5.4-1…R-5.4-9, R-6-0…R-6-16, R-7.5-1…R-7.5-4, R-7.6-1…R-7.6-6, R-7.8-1…R-7.8-4, R-10-1 | SM-18 ★, SM-02, SM-08 ★, SM-09, SM-10 ★, SM-11 ★, SM-12 ★, SM-13, NOT-01, INV-01 ★, SEED-10 ★, DEP-09, DEP-10 | Domain rules only; no part of the flow can run |
| Architecture and code quality | 20 % | "Clean structure, state machine, tenant isolation, validation" | R-1-2, R-3-4, R-3-13, R-3-14, R-3-15, R-5-2, R-7.1-7, R-7.5-1…R-7.5-3, R-9.1-3, R-9.4-1…R-9.4-8, R-10-2 | SM-01 ★, SM-19, SM-20 ★, SEC-02, SEC-45, API-01 ★, API-02, API-03, API-07, WEB-07, the 12 §6 gates | The strongest area today: gates green, state-machine domain and tenancy layers built. WEB-07 currently fails (Open question 6) |
| Product and UX | 15 % | "Clear landing page and booking wizard; role dashboards that show only relevant work" | R-3-2, R-3-3, R-4-10…R-4-13, R-7.3-1…R-7.3-8, R-7.4-1…R-7.4-15, R-10-3 | WEB-01…WEB-06, WEB-09, WEB-11, BK-16, BK-17, BK-19, DEP-02, DEP-09, DEP-12 (P1), WEB-08 (P1) | 2026-10-10: the spec 10 screens are built in the D101 design on the mock store (D102) — landing, directory and wizard (`1f09ead`), customer area, every role dashboard and the admin console — but the web does not call the API yet, and `/` neither lists shops nor links to `/book` (R-7.3-1) |
| Deployment and docs | 10 % | "Live URL works; README and .env.example let a stranger run it in minutes" | R-1-6, R-7.7-1…R-7.7-3, R-9.1-1…R-9.1-11, R-9.2-1…R-9.2-7, R-9.3-1, R-9.3-2, R-10-4, R-10-7, R-11-10, R-11-14 | DEP-01…DEP-08, DEP-14, DEP-15, DEV-01 (P1), SEED-01, SEED-02 ★, SEED-07 ★, SEED-09 | `.env.example` complete; README partial; not deployed; seed empty |
| Multi-tenancy and security | 10 % | "Owner multi-shop, per-shop teams, access control" | R-2-5, R-3-12…R-3-17, R-4-7…R-4-13, R-7.1-1…R-7.1-8, R-7.2-1…R-7.2-5, R-10-5, R-11-6, R-11-8 | SEC-01 ★, SEC-02, SEC-03, SEC-05…SEC-17, SEC-21…SEC-27, SEC-45, SEC-46, SM-05 ★, SM-17, SEED-08 | Mechanisms built (auth, tenancy dependency, composite FKs); no routes |
| Bonus features | 10 % | "Working calling and/or AI Front Desk with demo" | R-6-17, R-8-1, R-8.1-1…R-8.1-7, R-8.2-1…R-8.2-8, R-8.3-7, R-8.3-8, R-10-6, R-11-3, R-11-13 | CALL-01…CALL-16, FD-01…FD-12, AG-01…AG-06, SEC-36, SEC-49, SEC-50, NOT-13 | Not started, by design (D36) |

The bonus scores only if the core flow works (R-11-3). Every point above therefore depends first on the §7.8 checklist below.

## 5. Definition-of-done checklist (brief §7.8)

Spec 14 §5 never cuts these items. Spec 06 §10 ("Definition of Done coverage (§7.8)") maps each one to the judge script. Tick a box only when the automated proof is green in CI **and** the live check has passed on the deployed commit.

- [ ] **The full §5 flow on the live URL, from customer booking to `COMPLETED`, with seeded accounts** (R-7.8-1)
  - Automated: SM-18 ★, SEED-10 ★, and the prerequisites SEED-01 and SEED-07 ★.
  - Live: DEP-07, DEP-08, DEP-10 (scripted, at `lyallpur-motors`), DEP-09 (manual, two browsers).
  - Today: not met — no endpoints, no seed data, no deployment.
- [ ] **The QC fail loop works** (R-7.8-2)
  - Automated: SM-10 ★, QC-03, QC-05, QC-06, QC-10.
  - Live: DEP-09 (06 §10 at 6:15–7:15; E4 for two rounds).
  - Today: not met; only the rule exists.
- [ ] **The estimate-rejected path works** (R-7.8-3)
  - Automated: SM-08 ★, SM-09, EST-14, EST-15.
  - Live: DEP-09 (06 §10 at 3:30–4:30; E1).
  - Today: not met; only the rules exist.
- [ ] **No role can perform another role's action** (R-7.8-4)
  - Automated: SM-01 ★, SM-03 ★, SM-04, SM-16 ★, SM-17, SEC-07, WEB-04, WEB-09.
  - Live: DEP-09 (7:45–9:00).
  - Today: the domain halves of SM-01, SM-03, SM-04 and SM-16 are green; the API matrix and the UI are not built.
- [ ] **Implied by §7.1: a Shop A staff token on Shop B's bookings gets 403/404** (R-7.1-8)
  - Automated: SEC-01 ★, SM-05 ★, SEC-02.
  - Live: DEP-09.
  - Today: only the dependency-level 404 is proven.

## 6. Submission checklist (brief §9.1–§9.4, FAQ "What goes in the submission?")

Spec 14 §7 is the operational checklist. This table maps each item to the files and specs behind it and records the state found in this audit.

| Item (brief) | Requirement | File(s) | Spec | Proof | State today |
|---|---|---|---|---|---|
| Public GitHub repository (§9.1) | R-9.1-1 | git remote `origin` | 14 §7; 07 "Hosts overview" | Link opens when logged out; DEP-14 | Remote set; visibility not verified |
| Meaningful commit history (§9.1) | R-9.1-2 | `git log` | 12 §2.1; 07 "Repository standards" | 14 §7 box (G1) | **No** — one commit |
| Organised folders (§9.1) | R-9.1-3 | `apps/api`, `apps/web`, `scripts/`, `.github/`, `.claude/specs/` | 01 "Monorepo root layout (D5)" | import-linter gate | Yes |
| No committed secrets (§9.1) | R-9.1-4 | `.gitignore`, `.env.example`, `.pre-commit-config.yaml`, CI job `secrets` | 12 §2.5 | DEP-14, SEC-37 | Yes, by inspection; confirm gitleaks on GitHub |
| Live URL, reachable without setup (§9.1) | R-9.1-5 | `apps/api/railway.json`, `apps/api/Dockerfile`, `apps/web/next.config.ts`, `scripts/smoke.sh` | 07 | DEP-01…DEP-03, DEP-15 | **No** — not deployed |
| Seeded data and demo accounts for every role (§9.1) | R-9.1-6 | `apps/api/app/scripts/seed.py` | 11 | SEED-01, SEED-07 ★, DEP-07, DEP-08 | **No** — the seed is empty |
| README: overview, tech stack (§9.1) | R-9.1-7 | `README.md` §1, §3 | 07 "README outline" | G4 | Yes (screenshot pending) |
| README: prerequisites with exact versions (§9.2) | R-9.2-1 | `README.md` §6 | 07 "README outline" | G4 | Yes |
| README: install commands per app (§9.2) | R-9.2-2 | `README.md` §8 | 07 "README outline" | G4 | Yes |
| README: environment setup, every variable explained (§9.2) | R-9.2-3 | `README.md` §9, `.env.example` | 07 "Environment variable inventory" | G4 | Partial — the table is "to be completed" |
| README: database create, migrate, seed (§9.2) | R-9.2-4 | `README.md` §10, `Makefile` | 07 "Makefile (repo root)" | SEED-09, SEED-16 | Written; the seed loads nothing |
| README: run with one command / `docker compose up` (§9.2) | R-9.2-5 | `README.md` §7, `start.sh`, `start.bat`, `docker-compose.yml` | 07 "Local development"; 17 D73 | DEV-01 (P1) | Yes — DEV-01 passed by hand on Linux (spec 14 PH0) |
| README: how to run tests (§9.1) | R-9.1-7 | `README.md` §11 | 12 §4.7 | G4 | **No** — "to be completed" |
| README: demo credentials for all six roles (§9.1, §9.2) | R-9.2-6 | `README.md` §2 | 11 "README demo-credentials block (paste as is)" | DEP-07, SEED-07 ★ | Listed; accounts not seeded |
| README: deployment notes (§9.1) | R-9.1-7 | `README.md` §14 | 07 "README outline" (section 14) | G4 | **No** — "to be completed" |
| README: architecture summary; structure and design decisions (§9.1, §9.2) | R-9.1-7, R-9.2-7 | `README.md` §4, §5, §15 | 07 "README outline" (sections 4, 5, 15) | G4 | Partial — §15 is "to be completed" |
| `.env.example` in the repo root (§9.1, §9.3) | R-9.1-8, R-9.3-1, R-9.3-2 | `.env.example` | 07 "Root `.env.example`"; 18 §12 | SEC-37, DEP-14 (G5) | Yes — 33 variables, all commented |
| Optional demo video (§9.1) | R-9.1-9 | README §13 link | 06 §10 "Video storyboard"; 05 §15 | 14 §7 (G8) | No |
| Optional architecture diagram (§9.1) | R-9.1-10 | spec 01, README §4 | 01 "System topology" | 14 §7 (G8) | Partial — in spec 01, not yet in the README |
| Optional API docs (§9.1) | R-9.1-11 | `/docs`, `apps/web/src/lib/api/openapi.json` | 03 §1.11, §8.2 | API-09, DEP-13, WEB-07 | Partial — the snapshot is stale |
| Linter and formatter configured (§9.4) | R-9.4-1 | `apps/api/pyproject.toml`, `apps/web/eslint.config.mjs`, `apps/web/prettier.config.mjs`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml` | 12 §1, §6 | 12 §6 gates (G3) | Yes — green in this audit |
| Input validation on all endpoints (§9.4) | R-9.4-2 | `apps/api/app/core/error_handlers.py`, per-route Pydantic schemas | 03 §2.3 | API-02, API-03, SEC-17, SEC-29, SEC-30 | Mechanism only |
| Consistent errors, proper status codes (§9.4) | R-9.4-3 | `apps/api/app/core/errors.py`, `apps/api/app/core/error_handlers.py` | 03 §2 | API-01 ★, API-03, API-04, API-13, SEC-28 | Mechanism built and tested |
| Reusable UI components (§9.4) | R-9.4-4 | `apps/web/src/components/**` | 09 §3.12, §4 | WEB-03, WEB-04 (G3) | Primitives and shells only |
| Centralised API client (§9.4) | R-9.4-5 | `apps/web/src/lib/api/client.ts` | 09 §2.6; 17 D50, D76 | WEB-05, WEB-07 | Client built; generated types stale |
| Typed code (§9.4) | R-9.4-6 | mypy strict, TypeScript `strict` | 12 §1.1, §1.2 | 12 §6 gates, WEB-07 | Yes |
| Sensible commit messages, small commits (§9.4) | R-9.4-7 | `.github/pull_request_template.md`, `.pre-commit-config.yaml` | 12 §2.1 | G1 | **No** — one commit |
| AI-generated code reviewed and understood (§9.4) | R-9.4-8 | `.github/pull_request_template.md` (attestation) | 12 §2.3, §2.4 | G2 | Template in place |
| Submission form: repo link, live URL, optional video (FAQ) | R-11-14 | — | 14 PH10, §7 ("Final gate") | DEP-09 in the final 3 hours | Not yet |

## 7. Keeping this spec current

1. **When a test with a catalogue ID lands,** add ✓ to its ID wherever it appears, and update the row's status: Spec only → Foundation → Built.
2. **Finding tests by ID.**
   - Backend: test functions must start with the lower-case ID (12 §1.4). `grep -rE "def test_(sm|sec|idn|shp|sch|bk|est|inv|qc|not|rpt|api|seed|con|dep|dev)[0-9]{2}" apps/api/tests` finds them.
   - Web: tests name the ID in their `describe` title.
   - Today only the state-machine tests follow the backend naming rule. The other foundation tests cite their IDs in docstrings; renaming them makes the grep complete.
3. **When a module spec's proposal is adopted** into spec 12 or spec 05, drop its "(proposed)" marker here.
4. **When the brief is re-interpreted,** record the decision in spec 17 first, then change the affected rows' Notes. Never renumber an `R-` ID.
5. **Re-run the audit at CP2, CP3, CP4, PH7 exit and PH10** (spec 14 §4.1, §6). Recompute §3.1 by counting the Status and Pri columns.

## Proposed glossary additions

| Kind | Name | Meaning |
|---|---|---|
| ID prefix | `R-<brief section>-<n>` | A brief requirement in this spec (§1.1). It has a section part, so it is distinct from spec 09's UX rules `R1`…`R12` |
| Status vocabulary | `Spec only`, `Foundation`, `Built`, `Not applicable` | Implementation status of a requirement (§1.3) |
| Gap IDs | `G1`…`G9` | Coverage gaps of §3.3. Local to this spec; they disappear when closed |

## Dependencies

- **Depends on:**
  - the brief;
  - [00-overview.md](00-overview.md) — scope, out of scope, judging table;
  - [17-decisions.md](17-decisions.md) — D36 priorities, and every decision cited in the Notes;
  - [18-glossary.md](18-glossary.md) — names, §6 notification types, §12 variables, §14 cast;
  - [08-booking-state-machine.md](08-booking-state-machine.md) — T01–T22, O1–O5, SM-01…SM-20, worked-example trace;
  - [12-quality-and-testing.md](12-quality-and-testing.md) — the §5 catalogue, §6 gates, ★ set;
  - [04-auth-and-security.md](04-auth-and-security.md) — SEC-01…SEC-50, RBAC;
  - [05-calling-and-ai-front-desk.md](05-calling-and-ai-front-desk.md) — CALL, FD, AG; §1.1–§1.2; §14–§16;
  - [03-api-contracts.md](03-api-contracts.md) — §4, §5, §8.2;
  - [06-workflows.md](06-workflows.md) — journeys, edge cases, §10 DoD coverage;
  - [07-deployment-and-docs.md](07-deployment-and-docs.md) — README outline, CI, deployment;
  - [09-frontend-and-ux.md](09-frontend-and-ux.md), [10-screens.md](10-screens.md) — §12.1 coverage, screen IDs;
  - [11-seed-data.md](11-seed-data.md) — verification;
  - [14-roadmap.md](14-roadmap.md) — §1.2, §1.3, §5, §7;
  - [01-architecture.md](01-architecture.md), [02-data-model.md](02-data-model.md);
  - every `modules/*.md` — their Tests sections and proposed IDs.
- **Used by:**
  - [14-roadmap.md](14-roadmap.md) — PH7 lists this spec under "Specs to read"; the PH10 submission;
  - [16-open-questions-and-risks.md](16-open-questions-and-risks.md) (risks);
  - the team's checkpoint reviews.

## Open questions

Contradictions found while tracing come first (1–5, all resolved by the 2026-10-09 sweep). This spec edits no other spec; each item names the spec that should change.

Three conflicts found earlier in this audit were fixed by other specs' edits before it closed, and are not repeated:

- spec 03 and spec 04 now mark the WebSocket layer P1, per D88;
- `/health` now has one body everywhere (D84, spec 03 §4.2, spec 12 API-01 and API-08, and the code);
- `modules/calls.md` and spec 12 §5 now agree on CALL-17…CALL-20, and `app/shared/phone.py` now exists, as D84 states.

1. ✅ **Resolved: `INVALID_SLOT` reason code (spec 12 SCH-07 vs glossary §10).** Fixed in the 2026-10-09 sweep: spec 12 §5's SCH-07 now says an off-grid time in the past → `off_grid`, as glossary §10, spec 03 §2.3 and `modules/scheduling.md` (§7.4 and its own SCH-07) do. `not_on_grid` stays the field code for a working-hours time off the grid (`modules/shops.md` §7.1, BK-30).
2. ✅ **Resolved: OpenAPI drift check (spec 00 vs D76).** Fixed in the 2026-10-09 sweep: spec 00 no longer lists the drift check under "P1 — Recommended extras"; its P0 submission row names it as the D76 gate, as spec 12 WEB-07 and §6 and spec 14 §5 do.
3. ✅ **Resolved by D75 (amended): ID collision `INV-n` vs `INV-nn`.** Spec 02 §6's invariants are now `DI-1`…`DI-7` (glossary §13); `INV-xx`, always two digits, stays spec 12's inventory test prefix (`INV-01`…`INV-34`). `modules/estimates.md`, `modules/scheduling.md` and `modules/inventory.md` now cite `DI-5`, `DI-4` and `DI-1…DI-3`. Code comments that still say `INV-n` are tracked in spec 16 C.3.
4. ✅ **Resolved: missing spec 16.** [16-open-questions-and-risks.md](16-open-questions-and-risks.md) now exists (risks, owner decisions, every spec's open questions, pending glossary additions, day-1 records).
5. ✅ **Resolved: SM-20 status (spec 12 §5 vs the tests).** Fixed in the 2026-10-09 sweep: spec 12 §5's status line no longer claims SM-20 (§3.2). No test exercises SM-20 yet.
6. **Stale OpenAPI snapshot (code state, not a spec conflict).** The committed `apps/web/src/lib/api/openapi.json` is a placeholder (version 0.1.0, no paths), while the API exports `/health` at version 1.0.0. `make gen-api` therefore produces a diff, and the CI `contract` job (WEB-07) fails until both generated files are regenerated and committed.
7. **README ahead of the code.** README §2 and §10 promise seeded demo accounts and "6 shops with full teams …" that the seed does not create yet. This is acceptable while the README says "under active development", but it must be true by PH7.
8. ✅ **Resolved: stale wording in spec 11.** Fixed in the 2026-10-09 sweep: spec 11 "Verification (spec 12)" now introduces SEED-11…SEED-19 as additions adopted by spec 12 §5 with these numbers.
9. ✅ **Resolved: unnumbered proposal.** Spec 12 §5's bonus block now numbers CALL-21 (an active SA who was not rung may accept a ringing customer → shop call; the Owner only when the shop has no active SA), and spec 14's PH8 exit list includes it.
10. **Owner of the gap fixes.** Who adds the IDs proposed in §3.3 — process checks (G1, G2), quality gates (G3), README and `.env.example` checks (G4, G5) and demo evidence (G8)? And who decides on raising DEP-12 and SEC-47 to P0 (G6)? Proposal: spec 12's owner, in one pass before CP3.
11. **Test priority below requirement priority.** Should a test ever be lower priority than the requirement it proves? G6 lists the three cases where it is today.
