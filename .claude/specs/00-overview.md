# 00 — Overview

**Status:** ✅ Locked

## Purpose

BayFlow is a **multi-tenant auto repair shop management platform** for independent garages in Pakistan and similar markets. Customers discover a shop online, book a service and track their vehicle; shop staff run the entire repair job — check-in, inspection, estimate, parts, repair, quality check, pick-up — in one role-based POS. An owner can run several shops, each with its own team, inventory, slots and bookings.

This folder is the **spec-driven blueprint**: code is written from these specs, and the specs are updated first whenever a decision changes. Requirements source: `helping-folder/Web Dev - Virtual.pdf` (BayFlow Hackathon Brief v1.1, October 2026); "§n" below refers to its sections.

## The problem (brief §2)

Garages run on paper job cards, WhatsApp and memory. Information is lost at every hand-off between customer, front desk, technician, parts counter and QC. Core problems: **no visibility**, **no accountability** (approvals, estimates and QC not recorded), **inventory chaos**, **communication overload**, **no multi-shop control**.

## What we build (brief §3)

One platform, three surfaces, one backend:

1. **Customer portal** — public landing page listing all shops, guided booking wizard, customer area to track bookings and approve/reject estimates.
2. **Shop POS** — role-based dashboards for Owner, Service Advisor, Technician, QC Inspector and Parts Person; each role sees only its own work.
3. **Backend API** — multi-tenant, authenticated, with an explicit booking state machine (spec 08) that enforces who can move a job to which step.

## Scope

### P0 — Core (mandatory, judged first; brief §7)

| Area | Brief | Spec |
|---|---|---|
| Authentication & multi-tenancy (owner sign-up, staff created by owner, customer via wizard, hashing, role checks, tenant isolation) | §7.1, §3, §4 | 04, 02, `modules/identity.md`, `modules/shops.md` |
| Owner: shops, team, shop switcher, service catalogue | §7.2 | `modules/shops.md`, 10 |
| Customer portal: landing, wizard, slot picker, dashboard, responsive | §7.3, §5.1 | 09, 10, `modules/bookings.md`, `modules/scheduling.md` |
| Shop POS dashboards for all five roles | §7.4 | 09, 10 |
| Booking engine & state machine, audit log, role guards, estimate versioning | §7.5, §5.2, §5.3 | 08, `modules/bookings.md`, `modules/estimates.md` |
| Inventory & procurement | §7.6 | `modules/inventory.md` |
| QC queue, checklist, issues, fail loop | §7.4, §5.3 | `modules/qc.md` |
| Notifications (in-app bell + unread count) | §5.4 | `modules/notifications.md` |
| Seed data + demo credentials | §7.7 | 11 |
| Submission: public repo, live URL, README, `.env.example`, code quality (CI, incl. the OpenAPI drift check, D76) | §9 | 07, 12 |

**Core definition of done (§7.8):** a judge completes the full lifecycle on the live URL with seeded accounts, from customer booking to `COMPLETED`; the QC-fail loop and the estimate-rejected path work; no role can perform another role's action.

### P1 — Recommended extras (cheap, strengthen judging)

Extra notifications (spec 18 §6), WebSocket live updates (D88; polling is the P0 path), technician/parts reassignment, owner multi-shop summary, e-mail for customer-facing events, Playwright smoke test.

### P2 — Bonus track (only after P0 works end-to-end on the live URL; §8)

In-app calling between SA and customer, and the AI Front Desk — spec 05.

### Out of scope for the hackathon

Real payments (FAQ "Do we need real payments? No"), native mobile apps (web is responsive), file uploads (logo is a URL), SMS/WhatsApp, the AI feature backlog (spec 13), platform super-admin.

## Users and roles (brief §4)

| Role | Who | Main responsibilities |
|---|---|---|
| Customer | Vehicle owner | Browse shops, book, log in, view bookings, approve/reject estimates, mark pick-up |
| Owner | Shop owner | Register, create shops, add team members with roles, create more shops later, full visibility of their shops |
| Service Advisor (SA) | Front desk | Confirm bookings, assign technicians, review/edit/send estimates, assign parts person, notify customer when ready, close bookings |
| Technician | Mechanic | See assigned jobs, inspect, add parts and labour estimate, repair, send to QC |
| Parts Person | Inventory & procurement | View stock, order missing parts, confirm receipt (stock up), allocate parts to a booking |
| QC Inspector | Quality control | Pick a job from the shared QC queue, test it, pass or raise an issue |

## Judging criteria (brief §10) → where we earn the points

| Criterion | Weight | How we win it | Specs |
|---|---|---|---|
| Core flow completeness | 35 % | Every status, edge case and notification of §5 implemented; worked example runs as an automated test and on the live site | 08, 06, 11, 12 |
| Architecture & code quality | 20 % | Modular monolith with clean layers; declarative state machine; tenant isolation in one dependency + composite FKs; validation everywhere; typed code; linted | 01, 02, 08, 12 |
| Product & UX | 15 % | Clear landing + wizard; dashboards show only relevant work; `allowed_actions`-driven buttons; live status timeline; mobile-friendly | 09, 10 |
| Deployment & docs | 10 % | Live URL from day 1; README + `.env.example` let a stranger run it in minutes; `docker compose up` | 07 |
| Multi-tenancy & security | 10 % | Owner multi-shop with switcher; per-shop teams; 404 for cross-tenant access; Argon2id; httpOnly cookie | 04 |
| Bonus features | 10 % | Working in-app calling + AI Front Desk with demo | 05 |

## Hackathon constraints (brief §1, §9, FAQ)

- Build a full working product: customer web app + shop POS + backend API.
- Tech stack free choice — must be shippable and defensible in review.
- AI tools allowed; the team must understand and explain all code.
- Must submit: **public GitHub repository** with meaningful commit history and no committed secrets, **live URL** reachable without local setup with seeded data and demo accounts for every role, **README.md** and **.env.example** in the repo root.
- Optional: 3–5 min demo video, architecture diagram, API docs (Swagger/OpenAPI or Postman).
- Bonus features count only if the core flow works.
- Tip from the brief: deploy early and keep deploying.

## Locked tech stack (details and versions in spec 17)

- **Web:** Next.js 16 (App Router, TypeScript), Tailwind CSS 4, shadcn/ui, TanStack Query 5, React Hook Form + Zod — on **Vercel**.
- **API:** FastAPI + Pydantic v2 + SQLAlchemy 2 (async) + Alembic, Python 3.12 — **modular monolith** on **Railway** (Docker).
- **Database:** PostgreSQL 16+ on Railway.
- **Bonus:** LiveKit Cloud + LiveKit Agents (Python) + OpenAI `gpt-realtime-2.1-mini`.

## Judge-defensible narratives

1. **The state machine is data, not scattered if-statements.** One rule table drives execution, the UI's buttons (`allowed_actions`) and an exhaustive test that rejects every pair not in the table.
2. **Tenant isolation is enforced three times:** one shop-membership dependency on every staff route, repositories that require `shop_id`, and composite foreign keys that make cross-shop references impossible in the database.
3. **Every money and stock number is explainable.** Estimates are versioned and locked once approved with a timestamp; stock changes are a ledger of movements.
4. **Concurrency is handled, not hoped for.** Row locks make "first QC to pick wins" and "no slot overbooking" true under parallel requests — and tests prove it.
5. **Modular monolith by choice.** One transaction can update booking, stock and slots atomically; modules own their tables and talk through services and events, so any module could be extracted later.
6. *(Bonus)* **The AI cannot leak data even if prompted to:** its tools call internal endpoints that the API scopes to the caller's own customer ID.

## Spec map and reading order

| # | File | What it defines | Status |
|---|---|---|---|
| 00 | [00-overview.md](00-overview.md) | This file | ✅ Locked |
| 18 | [18-glossary.md](18-glossary.md) | Canonical names (read second) | ✅ Locked |
| 17 | [17-decisions.md](17-decisions.md) | Every decision and interpretation (read third) | ✅ Locked |
| 08 | [08-booking-state-machine.md](08-booking-state-machine.md) | The booking lifecycle rules | ✅ Locked |
| 01 | [01-architecture.md](01-architecture.md) | Modular monolith, layers, modules, events, repo layout | Draft |
| 02 | [02-data-model.md](02-data-model.md) | PostgreSQL schema, constraints, indexes | Draft |
| 03 | [03-api-contracts.md](03-api-contracts.md) | Every endpoint, schema, error and realtime message | Draft |
| 04 | [04-auth-and-security.md](04-auth-and-security.md) | Auth flows, RBAC matrix, tenant isolation, threats | Draft |
| 05 | [05-calling-and-ai-front-desk.md](05-calling-and-ai-front-desk.md) | Bonus: in-app calling + AI Front Desk | Draft |
| 06 | [06-workflows.md](06-workflows.md) | User journeys per role, worked example, demo script | Draft |
| 07 | [07-deployment-and-docs.md](07-deployment-and-docs.md) | Hosting, Docker, CI/CD, env vars, README, repo standards | Draft |
| 09 | [09-frontend-and-ux.md](09-frontend-and-ux.md) | Web architecture, design system, UX rules | Draft |
| 10 | [10-screens.md](10-screens.md) | Every page/route with data and actions | Draft |
| 11 | [11-seed-data.md](11-seed-data.md) | Demo shops, accounts, inventory, sample bookings | Draft |
| 12 | [12-quality-and-testing.md](12-quality-and-testing.md) | Code standards, test plan, CI gates | Draft |
| 13 | [13-ai-backlog.md](13-ai-backlog.md) | Post-hackathon AI features (not built now) | Draft |
| 14 | [14-roadmap.md](14-roadmap.md) | Build phases and exit criteria | Draft |
| 15 | [15-requirements-traceability.md](15-requirements-traceability.md) | Every brief requirement → spec → test | Draft |
| 16 | [16-open-questions-and-risks.md](16-open-questions-and-risks.md) | Risks, gaps, open decisions | Draft |
| — | `modules/*.md` | One spec per backend module: identity, shops, scheduling, bookings, estimates, inventory, qc, notifications, reporting, calls | Draft |

## Dependencies

- Root spec. Everything else depends on it, together with 17 and 18.

## Open questions

- Hackathon duration (deadline) and team size are not stated in the brief — they affect the roadmap's timing (spec 14) but not scope.
