# BayFlow

**Multi-tenant auto repair shop platform** — customers find a garage and book a service online; shop staff run every job (check-in, inspection, estimate, parts, repair, quality check, pick-up) in one role-based POS; one owner can run several shops.

- **Live URL:** _to be added after the first deploy_ (`https://<project>.vercel.app`)
- **API docs (Swagger):** _to be added_ (`https://<api>.up.railway.app/docs`); locally at <http://localhost:4000/docs>
- **Demo video (3–5 min):** _to be added before submission_

> **Status: under active development.** Sections marked _to be completed_ are filled in as features land. The specs in [`.claude/specs/`](.claude/specs/) are the source of truth: they change first, then the code.

## Contents

1. [Overview](#1-overview)
2. [Demo accounts](#2-demo-accounts)
3. [Tech stack](#3-tech-stack)
4. [Architecture](#4-architecture)
5. [Project structure](#5-project-structure)
6. [Prerequisites](#6-prerequisites)
7. [Quick start](#7-quick-start)
8. [Local development](#8-local-development)
9. [Environment variables](#9-environment-variables)
10. [Database](#10-database)
11. [Tests](#11-tests)
12. [API documentation](#12-api-documentation)
13. [Demo video](#13-demo-video)
14. [Deployment](#14-deployment)
15. [Design decisions](#15-design-decisions)
16. [Contributing](#16-contributing)
17. [Specs](#17-specs)
18. [Troubleshooting](#18-troubleshooting)

## 1. Overview

Garages run on paper job cards, WhatsApp and memory, so information is lost at every hand-off between customer, front desk, technician, parts counter and quality control. BayFlow puts the whole job on one explicit, audited booking state machine. It has three surfaces and one backend:

- **Customer portal** — public list of shops, guided booking wizard, customer area to track bookings and approve or reject estimates.
- **Shop POS** — role-based dashboards for Owner, Service Advisor, Technician, QC Inspector and Parts Person; each role sees only its own work.
- **Backend API** — multi-tenant, authenticated, with a declarative state machine that decides who may move a job to which step.

_Screenshot: to be completed._

## 2. Demo accounts

All demo accounts use the password **`BayFlow@2026`**. The worked example from the brief (§6) runs at **Lahore Auto Care**. (Demo data is loaded by the seed — see [Database](#10-database).)

| Role | Name | E-mail | Password | Shop |
|---|---|---|---|---|
| Owner | Fatima Raza | `fatima.owner@bayflow.test` | `BayFlow@2026` | Lahore Auto Care **and** Raza Auto Works (shop switcher) |
| Service Advisor | Bilal | `bilal.sa@bayflow.test` | `BayFlow@2026` | Lahore Auto Care |
| Technician | Imran | `imran.tech@bayflow.test` | `BayFlow@2026` | Lahore Auto Care |
| QC Inspector | Sara | `sara.qc@bayflow.test` | `BayFlow@2026` | Lahore Auto Care |
| Parts Person | Usman | `usman.parts@bayflow.test` | `BayFlow@2026` | Lahore Auto Care |
| Customer | Ayesha Khan | `ayesha.customer@bayflow.test` | `BayFlow@2026` | — (sample bookings at Lahore Auto Care) |
| Technician (2nd) | Hamza | `hamza.tech@bayflow.test` | `BayFlow@2026` | Lahore Auto Care |
| QC Inspector (2nd, "first pick wins") | Hina | `hina.qc@bayflow.test` | `BayFlow@2026` | Lahore Auto Care |
| Platform admin (super admin) | Areeba Hashmi | `admin@bayflow.test` | `BayFlow@2026` | — (the `/admin` console across every shop: tenants, accounts, bookings, audit log; spec 19) |

**Every other shop has its own full team.** Log in as `<role>.<shop-slug>@bayflow.test`, where `<role>` is `owner`, `sa`, `tech`, `qc` or `parts` (Raza Auto Works is owned by Fatima, so it has no `owner.` account). Same password.

| Shop | City | Slug | Example |
|---|---|---|---|
| Raza Auto Works | Lahore | `raza-auto-works` | `sa.raza-auto-works@bayflow.test` |
| Clifton Car Clinic | Karachi | `clifton-car-clinic` | `sa.clifton-car-clinic@bayflow.test` |
| Margalla Motor Works | Islamabad | `margalla-motor-works` | `tech.margalla-motor-works@bayflow.test` |
| Pindi Auto Garage | Rawalpindi | `pindi-auto-garage` | `parts.pindi-auto-garage@bayflow.test` |
| Lyallpur Motors | Faisalabad | `lyallpur-motors` | `qc.lyallpur-motors@bayflow.test` |

More customers (same password): `kamran.customer@bayflow.test`, `zainab.customer@bayflow.test`, `nadia.customer@bayflow.test`, `omar.customer@bayflow.test`.

**Notes for judges**

- **Ahmed from the worked example is not seeded.** Book through the wizard with a **fresh `.test` address** (e.g. `ahmed1@bayflow.test`) to replay §6. `.test` is a reserved domain: the API accepts it and never e-mails it. Use a new address each time — an existing e-mail with a different password is refused with `EMAIL_ALREADY_REGISTERED`.
- Passwords for new accounts need **12–128 characters**, e.g. `Ahmed@2026-demo`.
- **Shared demo data drifts:** every replay consumes stock and fills a slot (the worked example's Friday 10:00 slot has capacity 2). If it is full, pick another slot; if the ignition coil is out, Usman can adjust stock or order it.
- **If a demo account stops working** (e.g. someone deactivated Bilal), re-running the seed repairs the demo cast without touching anyone's bookings.
- Please don't deactivate the shared accounts (Bilal, Imran, Sara, Usman); use Hamza or Hina to try deactivation.
- _"Try the full flow" in 10 steps: to be completed (spec 06)._

## 3. Tech stack

Latest **compatible** versions (decision D11), pinned in `apps/web/pnpm-lock.yaml` and `apps/api/uv.lock`.

| Layer | Technology |
|---|---|
| Web | Next.js 16.4 (App Router), React 19, TypeScript 5.9.3, Tailwind CSS 4.3, shadcn/ui (Radix), TanStack Query 5, React Hook Form + Zod, ESLint 9.39 |
| API | FastAPI 0.143, Pydantic 2.14 + pydantic-settings 2, SQLAlchemy 2.1 (`sqlalchemy[asyncio]`, asyncpg), Alembic 1.20, pwdlib (Argon2id) |
| Database | PostgreSQL 16 |
| Tooling | Python 3.12 + uv, Node.js 24 + pnpm 10.34.6, Docker Compose, GitHub Actions |
| Hosting | Vercel (web), Railway (API + PostgreSQL) |
| Bonus | LiveKit (in-app calling) + OpenAI `gpt-realtime-2.1-mini` (AI Front Desk) |

TypeScript and ESLint are deliberately not the npm `latest` majors: `openapi-typescript`, `typescript-eslint` and the plugins of `eslint-config-next` do not support them yet (D11).

## 4. Architecture

_To be completed — summary below; details in [`.claude/specs/01-architecture.md`](.claude/specs/01-architecture.md)._

- **Modular monolith:** one FastAPI app, one PostgreSQL database; each module (identity, shops, scheduling, bookings, estimates, inventory, qc, notifications, reporting, calls) owns its tables and talks to others through services and in-process events.
- The browser calls `/api/*` on the web origin; Next.js rewrites it to the API (same-origin cookie, no CORS). WebSockets go directly to the API with a short-lived ticket.
- One transaction per booking action (row locks for "first QC pick wins" and "no slot overbooking").
- Tenant isolation is enforced three times: a shop-membership dependency on every staff route, repositories that require `shop_id`, and composite foreign keys.

## 5. Project structure

```
.
├── apps/
│   ├── api/                 # FastAPI modular monolith (uv project)
│   ├── web/                 # Next.js customer portal + shop POS (pnpm project)
│   └── agent/               # bonus AI Front Desk worker (later)
├── scripts/
│   └── smoke.sh             # post-deploy smoke test (make smoke)
├── .github/workflows/ci.yml # CI: api, web, contract, secrets
├── .claude/specs/           # the spec-driven blueprint (source of truth)
├── helping-folder/          # the hackathon brief
├── start.sh / stop.sh       # one-command local stack (Linux, macOS)
├── start.bat / stop.bat     # the same for Windows
├── docker-compose.yml       # PostgreSQL (+ optional full stack, Mailpit, bonus agent)
├── Makefile                 # developer shortcuts: make help
├── .env.example             # every environment variable, with comments
└── README.md
```

`logs/` (service logs) and `.run/` (PID files) are created by the start scripts and git-ignored.

## 6. Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| Docker with Compose v2 (`docker compose`) | current Docker Desktop / Engine (Compose 2.24 or newer) | PostgreSQL; or the whole stack in Docker |
| Python | 3.12.x (`uv python install 3.12` installs it; `uv sync` does it automatically) | API |
| uv | 0.12.x (CI pins 0.12.24) | API dependencies and commands |
| Node.js | 24 LTS | web |
| pnpm | 10.34.6 (pinned by `"packageManager"` in `apps/web/package.json`; `corepack enable pnpm` provides it) | web |
| PostgreSQL | 16 (Docker image `postgres:16`; nothing to install) | database |
| GNU Make | any (macOS/Linux; on Windows use `start.bat` / `stop.bat`) | `make` shortcuts |
| curl, jq | any | start scripts (curl), smoke test (curl + jq) |

Free local ports: web **3000**, API **4000**, PostgreSQL **5434** (change with `POSTGRES_HOST_PORT` and the port in `DATABASE_URL` together), Mailpit 8025/1025 (optional).

## 7. Quick start

**Linux / macOS**

```bash
git clone <repo-url> bayflow && cd bayflow
./start.sh
```

**Windows** (Command Prompt or a double click):

```bat
start.bat
```

On the first run the script creates `.env` from `.env.example`, installs the API and web dependencies, starts PostgreSQL 16 in Docker, applies the migrations, loads the demo data, then starts the API and the web app. Open <http://localhost:3000> and log in with a [demo account](#2-demo-accounts).

| URL | What |
|---|---|
| <http://localhost:3000> | Web app (customer portal + shop POS) |
| <http://localhost:4000/docs> | API docs (Swagger UI) |
| <http://localhost:4000/health> | API health check |
| `localhost:5434` | PostgreSQL (database, user and password: `bayflow`) |
| <http://localhost:8025> | Mailpit inbox, only if started (`docker compose --profile mail up -d mailpit`) |

**Stopping**

- `./start.sh` keeps streaming the API and web logs (prefixed `[api]` / `[web]`); press **Ctrl+C** to stop everything.
- `./stop.sh` (Windows: `stop.bat`) stops the API and the web app, frees ports 3000 and 4000 and stops the PostgreSQL container. `--keep-db` leaves PostgreSQL running. The data is always kept; `make db-reset` wipes it.
- `start.bat` waits for a key press in its window, then runs `stop.bat`.

**Start-script flags** (the same for `start.sh` and `start.bat`)

| Flag | Effect |
|---|---|
| `--detach` | start everything and return (stop later with `./stop.sh` / `stop.bat`) |
| `--seed` | load the demo data even when `SEED_ON_DEPLOY` is not `true` (`seed --force`) |
| `--no-install` | never install dependencies; fail if `apps/api/.venv` or `apps/web/node_modules` is missing |
| `--help` | show the help |

What the scripts do, in order: check the tools (Docker + Compose v2, uv, Node 24+, pnpm, curl) → create `.env` if missing → install dependencies if missing → free ports 3000 and 4000 (`./stop.sh --keep-db --quiet` / `stop.bat --keep-db --quiet`: stale BayFlow processes and *any other* program listening there are stopped and named; Docker, VM and SSH port forwarders are never killed, so then the script names the holder and exits) → `docker compose up -d --wait db` → `uv run alembic upgrade head` → `uv run python -m app.scripts.seed` (acts only when `SEED_ON_DEPLOY=true`, the `.env.example` default; idempotent) → API on :4000 (`uvicorn --reload`) and web on :3000 (`pnpm dev`) → wait until both answer → print the URLs. Logs: `logs/api.log`, `logs/web.log`; PIDs: `.run/`.

**Everything in Docker instead** (no Python/Node needed):

```bash
cp .env.example .env
docker compose up --build
```

## 8. Local development

_To be completed with module-level details._ Per-app installs (`make setup` runs both and installs the git hooks):

```bash
cd apps/api && uv sync          # API (creates apps/api/.venv)
cd apps/web && pnpm install     # web
```

Then `./start.sh` (or `make dev` in the foreground). Manual equivalents:

```bash
docker compose up -d --wait db                                   # PostgreSQL on localhost:5434
cd apps/api && uv run alembic upgrade head                        # migrations
cd apps/api && uv run python -m app.scripts.seed --force          # demo data
cd apps/api && uv run uvicorn app.main:app --reload --port 4000   # API
cd apps/web && pnpm dev                                           # web on :3000
```

`make help` lists every shortcut: `setup`, `up`, `down`, `db-up`, `migrate`, `seed`, `db-reset`, `api`, `web`, `dev`, `test`, `lint`, `fmt`, `gen-api`, `smoke`.

## 9. Environment variables

Copy `.env.example` to `.env` (the start scripts do it for you); **the defaults work locally**. There is one `.env`, in the repo root: the API reads it, and the scripts and `make web` export it for the web app. Every variable has a one-line comment in [`.env.example`](.env.example).

- **`APP_ENV`, not `NODE_ENV`:** the brief's sample uses `NODE_ENV`, but the API is Python and reads `APP_ENV`. Next.js sets `NODE_ENV` itself, so never put it in `.env`.
- On Vercel, `API_BASE_URL` and every `NEXT_PUBLIC_*` value are fixed at build time: change them, then redeploy.
- `POSTGRES_HOST_PORT` is read only by Docker Compose; keep the port in `DATABASE_URL` equal to it.

_A condensed table of all variables: to be completed (spec 07 "Environment variable inventory")._

## 10. Database

- **Create:** Docker Compose creates the `bayflow` database (user and password `bayflow`) on host port 5434 — `docker compose up -d --wait db` or `make db-up`.
- **Migrate:** `make migrate` (`uv run alembic upgrade head` in `apps/api`).
- **Seed:** `make seed` loads 6 shops with full teams, service catalogues, inventory and sample bookings (idempotent; re-running it repairs the demo cast). The start scripts run the seed on every start; it acts when `SEED_ON_DEPLOY=true`.
- **Reset:** `make db-reset` wipes the **local** Docker database, then migrates and seeds. It refuses `APP_ENV=production` or a non-local `DATABASE_URL` (exit code 2).

## 11. Tests

_To be completed._ `make test` (pytest on a real PostgreSQL + Vitest), `make lint` (Ruff, mypy, import contracts, ESLint, Prettier, `tsc`). CI runs the same gates on every pull request — see [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## 12. API documentation

_To be completed._ Swagger UI at `/docs`: call `POST /api/v1/auth/login`, copy `access_token`, click **Authorize**. Raw schema at `/openapi.json`; the typed web client is generated with `make gen-api`.

## 13. Demo video

_To be added before submission._

## 14. Deployment

_To be completed._ Web on Vercel (root `apps/web`), API and PostgreSQL 16 on Railway (pre-deploy `alembic upgrade head && python -m app.scripts.seed`, health check `/health`). Post-deploy check: `make smoke WEB_URL=https://<web> API_URL=https://<api>`. Details: [spec 07](.claude/specs/07-deployment-and-docs.md).

## 15. Design decisions

_To be completed._ Key decisions are recorded in [`.claude/specs/17-decisions.md`](.claude/specs/17-decisions.md).

## 16. Contributing

_To be completed._ Conventional Commits (`feat(bookings): …`), small commits, CI green before merge.

## 17. Specs

| Spec | Topic |
|---|---|
| [00-overview](.claude/specs/00-overview.md) | Scope and judging criteria |
| [18-glossary](.claude/specs/18-glossary.md) | Canonical names, environment variables, demo cast |
| [17-decisions](.claude/specs/17-decisions.md) | Every decision (wins over other specs) |
| [08-booking-state-machine](.claude/specs/08-booking-state-machine.md) | Booking lifecycle |
| [01-architecture](.claude/specs/01-architecture.md) | Modular monolith, layers, repo layout |
| [02-data-model](.claude/specs/02-data-model.md) | PostgreSQL schema |
| [04-auth-and-security](.claude/specs/04-auth-and-security.md) | Auth, roles, tenant isolation |
| [05-calling-and-ai-front-desk](.claude/specs/05-calling-and-ai-front-desk.md) | Bonus: calling and AI Front Desk |
| [06-workflows](.claude/specs/06-workflows.md) | User journeys and the worked example |
| [07-deployment-and-docs](.claude/specs/07-deployment-and-docs.md) | Hosting, Docker, CI, env vars, README |
| [09-frontend-and-ux](.claude/specs/09-frontend-and-ux.md) / [10-screens](.claude/specs/10-screens.md) | Web architecture and screens |
| [11-seed-data](.claude/specs/11-seed-data.md) | Demo data |
| [12-quality-and-testing](.claude/specs/12-quality-and-testing.md) | Code standards, tests, CI gates |
| [13-ai-backlog](.claude/specs/13-ai-backlog.md) / [14-roadmap](.claude/specs/14-roadmap.md) | Backlog and build phases |

## 18. Troubleshooting

- **"Port 3000 (or 4000) is still in use by …"** — the start and stop scripts stop any program listening on 3000 or 4000, except other Docker containers, Docker/VM/SSH port forwarders and processes of another user. Stop the holder the message names (for a container it prints the `docker stop` command; for a hidden process, `sudo lsof -nP -iTCP:3000 -sTCP:LISTEN` shows it), then run the script again.
- **Port 5434 is taken** — set `POSTGRES_HOST_PORT` in `.env` and change the port in `DATABASE_URL` to match.
- **"Docker is installed but not running"** — start Docker Desktop (Linux: `sudo systemctl start docker`).
- **The API or web app does not come up** — the start script prints the last 40 log lines; full logs are in `logs/api.log` and `logs/web.log` (`docker compose logs db` for PostgreSQL).
- **No demo accounts** — set `SEED_ON_DEPLOY=true` in `.env` or run `./start.sh --seed` / `make seed`.
