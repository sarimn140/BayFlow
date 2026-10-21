# 12 — Quality & Testing

**Status:** Draft
**Code homes:** `apps/api/pyproject.toml` (Ruff, mypy, import-linter, pytest), `apps/api/tests/`, `apps/web/eslint.config.mjs`, `apps/web/vitest.config.mts`, `.github/workflows/ci.yml`, `.github/pull_request_template.md` (all exist since PH0); P1, not yet created: `apps/web/playwright.config.ts`, `apps/web/e2e/`, `.github/workflows/smoke.yml`

## Purpose

This spec sets the rules that keep BayFlow's code clean and let us prove its behaviour. It covers coding standards (Python, TypeScript, SQL), git and review rules, the test strategy, the test infrastructure and a test catalogue with stable IDs. It also defines the CI gates that protect `main` and the definition of done. Specs 14 (roadmap) and 15 (traceability) refer to the test IDs defined here.

Why it matters for judging (brief §10, §9.4, §7.8):

- **Architecture & code quality (20 %)** — judges look for "clean structure, state machine, tenant isolation, validation". Linters, strict type checkers and import contracts check the structure automatically on every PR. The SM and SEC test groups prove the state machine and tenant isolation.
- **Core flow completeness (35 %)** — the §7.8 definition of done is automated: the worked example (SM-18), the estimate-rejected paths (SM-08, SM-09), the QC-fail loop (SM-10) and "no role can perform another role's action" (SM-03, SM-16 plus the action matrix) run in CI. Scripted versions also run against the live URL (DEP-10).
- **Brief §9.4 code-quality expectations** — each one is enforced by a tool, a test or a review rule:

| §9.4 expectation | Enforced by |
|---|---|
| Clean, readable code; consistent formatting (linter + formatter configured) | Ruff lint + format, ESLint + Prettier; CI fails on any finding (§6 below) |
| Input validation on all endpoints | Pydantic request models on every route (Ruff `FAST` rules, mypy strict); API-02, API-03; validation rows in BK, EST, INV, QC |
| Consistent error responses; proper HTTP status codes | One RFC 9457 handler (D49); API-01 to API-05; the action matrix checks the glossary §10 check order for every role and status |
| Reusable UI components; centralized API client | shadcn/ui primitives + shared components (spec 09); a single typed `openapi-fetch` client (D50); an ESLint rule bans raw `fetch` outside the client |
| Typed code | mypy `strict`, TypeScript `strict`, generated API types (D50), `no-explicit-any` |
| Sensible commit messages and small commits | Conventional Commits, PR template, rebase-merge (§2 below) |
| AI-generated code reviewed and understood by the team | PR-template attestation + reviewer "explain it" rule (§2.4); brief FAQ "You must understand and be able to explain all code" |

The README's "How to run tests" section (brief §9.1) is copied from §4.7.

**Section references:** "brief §n" is the hackathon brief. Brief subsections (§5.3, §7.8, §9.1 …) always mean the brief, as in specs 08, 17 and 18. A bare top-level "§n" in prose means a section of this spec.

---

## 1. Code standards

### 1.1 Python (`apps/api`)

**Toolchain** (D53; version lines checked on PyPI 2026-10-09; exact versions live in `uv.lock`):

| Tool | Version line | Command | Gate |
|---|---|---|---|
| Ruff — lint + format | 0.16.x (D11) | `uv run ruff check .` · `uv run ruff format --check .` | CI |
| mypy + Pydantic plugin | mypy 2.4.x | `uv run mypy` | CI |
| import-linter | 2.15 | `uv run lint-imports` | CI |
| pytest + pytest-asyncio | 9.1.x + 1.4.x | `uv run pytest` | CI |
| httpx + asgi-lifespan | 0.28.x + 2.1.x | (test client) | — |
| pytest-cov | 7.1.x | `--cov` | report (domain gate P1) |

**Dependency gotcha (verified; locked in D11):** SQLAlchemy 2.1 moved `greenlet` into the `[asyncio]` extra. Without the extra, async sessions fail at runtime, so D11 pins the dependency as `sqlalchemy[asyncio]` 2.1.x. SQLAlchemy 2.1 also requires Python ≥ 3.11 (we use 3.12, D2).

**Ruff** — validated with Ruff 0.16.10 on 2026-10-09:

```toml
# apps/api/pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = [
  "E", "W",  # pycodestyle
  "F",       # Pyflakes
  "I",       # isort
  "N",       # pep8-naming
  "UP",      # pyupgrade
  "B",       # flake8-bugbear
  "SIM",     # flake8-simplify
  "C4",      # flake8-comprehensions
  "RET",     # flake8-return
  "PERF",    # Perflint
  "ASYNC",   # flake8-async: blocking calls inside async code
  "S",       # flake8-bandit: security (incl. S608 string-built SQL)
  "DTZ",     # flake8-datetimez: naive datetimes
  "T20",     # flake8-print: no print()
  "ERA",     # eradicate: no commented-out code
  "TID",     # flake8-tidy-imports: banned APIs below (TID251)
  "PGH",     # pygrep-hooks: PGH003 forbids blanket `# type: ignore`
  "PT",      # flake8-pytest-style
  "C90",     # mccabe complexity
  "PL",      # Pylint: size limits below
  "FAST",    # FastAPI: FAST001 redundant response model, FAST002 non-Annotated dependency, FAST003 unused path param
  "RUF",     # Ruff-specific
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "S105", "S106", "PLR2004"]  # asserts, fixture passwords, magic numbers
"app/scripts/seed*.py" = ["S105", "S106"]          # demo credentials are seed data, not logic (D52)
"app/shared/clock.py" = ["TID251"]                   # the single source of "now" (D63)
"app/shared/enums.py" = ["S105"]                     # PASS / PASS_QC are enum values, not passwords
"app/core/errors.py" = ["N818"]                      # spec 01 names the AppError subclasses after the codes
"alembic/versions/*.py" = ["PLR0915"]                # migrations: one statement per table, index, trigger

[tool.ruff.lint.isort]
known-third-party = ["alembic"]  # the local alembic/ folder holds migrations, not the package

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.ruff.lint.pylint]
max-args = 6          # PLR0913 — use keyword-only args / a small command dataclass beyond this
max-statements = 40   # PLR0915
max-branches = 12     # PLR0912
max-returns = 6

[tool.ruff.lint.flake8-tidy-imports.banned-api]
"datetime.datetime.now".msg = "Use app.shared.clock.utcnow() or get_clock() (D63; spec 12 §4.4)."
"datetime.datetime.utcnow".msg = "Use app.shared.clock.utcnow() or get_clock() (D63; spec 12 §4.4)."
"datetime.date.today".msg = "Use app.shared.clock.utcnow() or get_clock() (D63; spec 12 §4.4)."
"time.time".msg = "Use app.shared.clock.utcnow() or get_clock() (D63; spec 12 §4.4)."
"pydantic.EmailStr".msg = "Use the project Email type from app.shared.email (D62)."
"pydantic.networks.EmailStr".msg = "Use the project Email type from app.shared.email (D62)."

[tool.ruff.format]
docstring-code-format = true
```

Rule sets deliberately **not** enabled:
- `ANN` — mypy `strict` already enforces annotations.
- `TC` — moving imports under `if TYPE_CHECKING:` breaks the annotations that FastAPI and Pydantic evaluate at runtime.
- `D` — docstrings are written only where the code is not obvious.
- `TRY` — too noisy for the value it adds.

Ruff 0.16.10 confirmed that the banned-api entries flag `datetime.now(UTC)`, `dt.datetime.now(tz=UTC)`, `date.today()` and `time.time()`. Re-checked with Ruff 0.16.4 on 2026-10-09 after the consolidation: the clock messages point at `app.shared.clock` (D63), `time.monotonic()` stays allowed, and the two `EmailStr` entries flag `from pydantic import EmailStr`, `from pydantic.networks import EmailStr` and `pydantic.EmailStr` (D62).

`app/shared/clock.py` is the only file-level `TID251` exemption (the other per-file ignores above are narrow false positives: enum values named like passwords, error classes named after their codes, long migration functions): JWT `iat` / `exp` are issued and checked with the app clock too (D63). `app.core.security.issue_token` / `decode_token` take `now` as an argument, because `app.core` may not import `app.shared` (spec 01), and their callers pass `utcnow()`; PyJWT's own system-time checks are switched off (spec 04). D63's single exception is the rate-limit windows, which slowapi and `limits` keep on system time inside the libraries; if our code must compare with a library timestamp (e.g. turning `limits`' `reset_time` into `Retry-After`), that one line carries `# noqa: TID251  # D63 exception: rate-limit window`.

**mypy:**

```toml
[tool.mypy]
python_version = "3.12"
strict = true
files = ["app"]                 # D53: mypy on app/
plugins = ["pydantic.mypy"]
warn_unreachable = true

[tool.pydantic-mypy]
init_forbid_extra = true
init_typed = true
warn_required_dynamic_aliases = true
```

- **No SQLAlchemy mypy plugin.** It has been deprecated since SQLAlchemy 2.0 and was announced for removal in 2.1. It only supports mypy up to 1.10.1, and its page no longer exists in the 2.1 docs. Models declared with `Mapped[...]` and `mapped_column()` type-check without it.
- `[[tool.mypy.overrides]]` with `ignore_missing_imports = true` is allowed only for untyped third-party packages, with a comment naming the package.
- Every `# type: ignore[...]` carries an error code (enforced by PGH003) and a short reason comment.

**Typing and value rules:**
- Every function is fully annotated. No `Any` in service, domain or repository signatures.
- Money is `Decimal`, never `float` (D41). Datetimes are timezone-aware UTC (`DTZ` rules; D38). IDs are `uuid.UUID`.
- Enums are `StrEnum` classes in `app.shared.enums` (D74) whose `UPPER_SNAKE` members equal the stored value (glossary §13; spec 08 sketch).
- Pydantic v2 schemas are named `XxxCreate`, `XxxUpdate` and `XxxRead` (glossary §13). Request models forbid unknown fields (`extra="forbid"`), so a stray `shop_id` in a staff request body is a 422 and is never silently trusted (D20; spec 04 Tier 1 item 5; SEC-17).
- E-mail fields use the project `Email` type from `app.shared.email` (D62: `email_validator.validate_email(value, check_deliverability=False, test_environment=True)`, then lower-cased), so the `.test` demo addresses validate. Pydantic's `EmailStr` is banned by the TID251 entries above (API-12, SEC-48). Password fields follow D10: 12–128 characters (SEC-29).

**Async SQLAlchemy rules** (from the SQLAlchemy asyncio docs; they prevent the classic async bugs):
- One `AsyncSession` per request or task. A single `AsyncSession` is not safe to share between concurrent tasks.
- `async_sessionmaker(..., expire_on_commit=False)`.
- Relationships default to `lazy="raise"`. Repositories load related data explicitly with `selectinload()` or `joinedload()` (§8 below).
- Row locks use `with_for_update()` in repositories, in the D30 order: booking → purchase order → parts (ascending `id`) → slot counter.

**Layers and size — no business logic in routers** (D3). This is a summary; the full layer table, including `schemas`, `events` and `handlers`, is in spec 01:

| Layer | May do | Must not do |
|---|---|---|
| `router` | Declare the route, parse/validate with Pydantic, resolve `Annotated` dependencies (auth, membership, clock), call **one** service function, return a response schema | SQL, status rules, `if role == …`, commits, calls to other modules |
| `service` | Run one use case in **one** transaction (spec 08 "How an action is executed"): call domain rules, repositories, other modules' services; publish events; commit | Import FastAPI request objects; build HTTP responses |
| `domain` | Pure functions and dataclasses: state machine, `allowed_actions`, totals, slot grid, reference format. `now` is passed in as a value | I/O of any kind: DB, HTTP, clock, environment |
| `repository` | SQLAlchemy queries. Every method on shop-owned data takes `shop_id` as a required keyword argument (D20) | Commit, apply business rules |

Illustrative router (dependency names other than `shop_scoped_router()` are placeholders; spec 01 defines the real ones). Every staff route group is built with `app.shared.auth.shop_scoped_router()`, which attaches `require_shop_member` at router level, so no shop route can forget the tenant check (D80, D20; SEC-02 sweeps them all):

```python
router = shop_scoped_router()        # D80: prefix /api/v1/shops/{shop_id}, require_shop_member on every route

@router.post("/bookings/{booking_id}/actions/confirm", response_model=BookingRead)
async def confirm(booking_id: UUID, body: ConfirmIn, member: CurrentMember, bookings: BookingServiceDep) -> BookingRead:
    return await bookings.perform(member, booking_id, BookingAction.CONFIRM, body)
```

- **Size guidance.**
  - Router handlers: about 15 lines or fewer.
  - Service functions: about 40 lines or fewer (PLR0915), split into private helpers named after spec 08 steps (`_reserve_outstanding`, `_release_reservations`).
  - Cyclomatic complexity: 10 or less. Arguments: 6 or fewer.
  - The state machine's size lives in the `RULES` table (data), not in branches.
- **Docstrings only where non-obvious.** `__init__.py` files stay empty (spec 01 rule 5, D84); each module's `models.py` opens with a short docstring naming its tables (glossary §7) and its spec, and its `service.py` with one naming its use cases (as built, the not-yet-built modules' `service.py` / `schemas.py` are docstring-only stubs, D84). Comments explain *why* and cite the rule they implement, e.g. `# D30: lock order booking → PO → parts → slot`, `# spec 08 T13`. Judges can trace code back to specs this way.
- **Errors.** Services raise typed application errors. One handler in `app.core` maps them to RFC 9457 problem+json with the glossary §10 `code` (D49). Routers never build error dicts. Bare `except:` is forbidden (E722). Broad `except Exception` exists only in the global 500 handler.
- **Logging.** Use the `logging` module (no `print`, T20). Never log passwords, tokens, cookies or full request bodies.

**Layering enforced by import-linter.** The contracts live in spec 01 (§Dependency rules) and in `apps/api/pyproject.toml`: `app-layers`, `module-direction`, `module-internal-layers` (router optional, because `estimates` has no router; `service` and `schemas` are required, which is why every module has both files — docstring-only stubs until it is built, D84), `public-surface`, `pure-domain`, `thin-routers`, `seed-through-services` and `no-module-cycles` (acyclic siblings). CI runs all eight with `uv run lint-imports` (§6 below); all are KEPT as built (D84).

✅ Adopted: this spec proposed the two contracts below; spec 01 and `apps/api/pyproject.toml` now contain them. They encode rules spec 01 states in prose but its layer contracts cannot express. Both were validated with import-linter 2.15 on 2026-10-09 against a skeleton of the module layout:
- `module-internal-layers` alone stays KEPT when a router imports its own module's repository, because a layers contract allows a higher layer to skip lower ones. `thin-routers` reports it as BROKEN.
- `seed-through-services` reports `app.scripts.seed → app.modules.inventory.repository` as BROKEN (D51: the seed goes through the service layer).

```toml
[[tool.importlinter.contracts]]
id = "thin-routers"
name = "Routers never import a repository or ORM models, not even their own module's (spec 01 router row)"
type = "forbidden"
source_modules = ["app.modules.*.router"]
forbidden_modules = ["app.modules.*.repository", "app.modules.*.models"]
allow_indirect_imports = true          # router -> service -> repository is the intended path

[[tool.importlinter.contracts]]
id = "seed-through-services"
name = "The seed goes through services only (D51)"
type = "forbidden"
source_modules = ["app.scripts"]
forbidden_modules = ["app.modules.*.repository", "app.modules.*.models"]
allow_indirect_imports = true
```

Verified import-linter facts that spec 01 and these contracts rely on:
- Forbidden contracts check indirect imports by default.
- External packages need `include_external_packages = true` and must be named at top level (`sqlalchemy`, not `sqlalchemy.orm`).
- `containers` accept wildcards, and a layer written in parentheses is optional.

### 1.2 TypeScript (`apps/web`)

**Toolchain** (version lines checked on npm 2026-10-09):

| Tool | Version line | Script (`package.json`) |
|---|---|---|
| TypeScript | **5.9.3** (D11; pinned — see below) | `"typecheck": "next typegen && tsc --noEmit"` (D80: route types are generated before type-checking) |
| ESLint (flat config) | **9.39.x** (D11) | `"lint": "eslint . --max-warnings 0"` |
| eslint-config-next | 16.4.x (same as `next`) | — |
| Prettier + prettier-plugin-tailwindcss | 3.x + 0.8.x | `"format": "prettier --write ."`, `"format:check": "prettier --check ."` |
| Vitest + React Testing Library + jsdom | Vitest 5.0.x on Vite 8, jsdom 30 | `"test": "vitest run"`, `"test:watch": "vitest"` |
| Playwright *(P1)* | 1.64.x | `"test:e2e": "playwright test"` — not in `package.json` yet (added with WEB-08) |
| openapi-typescript + openapi-fetch | 7.13.x + 0.17.x | `"api:types": "openapi-typescript src/lib/api/openapi.json -o src/lib/api/schema.d.ts"`; `make gen-api` runs the API export, then this script (D76) |
| pnpm | **10.34.6** (D1, D11), pinned by `"packageManager": "pnpm@10.34.6"` in `apps/web/package.json` — there is no root `package.json` (D5); Vercel supports pnpm 6–10 | — |

- **TypeScript 5.9.3 (D11).** npm's `latest` tag is TypeScript **7.0.2**, the native compiler, which does not yet provide the JavaScript compiler API.
  - Next.js 16.4 can type-check with TS 7 (it shells out to `tsc`).
  - `typescript-eslint` 8.71.1, which `eslint-config-next/typescript` uses, declares `typescript >=4.8.4 <6.1.0`.
  - `openapi-typescript` 7.13.0 declares `typescript ^5.x`.
  - 5.9.3 is the only line that satisfies every peer range (Next ≥ 5.1). Revisit when those two packages support 6 or 7.
- **ESLint 9.39.x, not 10 (D11).** eslint-config-next 16.4 itself supports both, but the plugins it pulls in — `eslint-plugin-react` 7.37, `eslint-plugin-import` 2.32 and `eslint-plugin-jsx-a11y` 6.10 — declare peer `eslint` up to `^9` only, so ESLint 10 warns or fails with strict peers.
- **Next 16 removed `next lint`, and `next build` no longer lints.** CI must run `pnpm lint` (`eslint . --max-warnings 0`, D80) as its own step. `next build` still fails on type errors, but CI runs `pnpm typecheck` (`next typegen && tsc --noEmit`, D80) first for faster feedback.

```js
// apps/web/eslint.config.mjs
import { defineConfig, globalIgnores } from 'eslint/config'
import nextVitals from 'eslint-config-next/core-web-vitals'
import nextTs from 'eslint-config-next/typescript'
import prettier from 'eslint-config-prettier/flat'

export default defineConfig([
  ...nextVitals,            // Next + React + React Hooks (+ jsx-a11y) rules
  ...nextTs,                // typescript-eslint recommended (incl. no-explicit-any)
  prettier,                 // turn off rules that fight Prettier
  {
    rules: {
      '@typescript-eslint/no-explicit-any': 'error',
      'no-console': ['error', { allow: ['warn', 'error'] }],
      'no-restricted-syntax': ['error', {
        selector: "CallExpression[callee.name='fetch']",
        message: 'Use the typed API client in src/lib/api (D50).',
      }],
    },
  },
  { files: ['src/lib/api/**'], rules: { 'no-restricted-syntax': 'off' } },
  globalIgnores(['.next/**', 'out/**', 'build/**', 'coverage/**', 'next-env.d.ts', 'src/lib/api/schema.d.ts']),
])
```

`tsconfig.json` sets `"strict": true` plus `"noUncheckedIndexedAccess": true`, `"noFallthroughCasesInSwitch": true` and `"noImplicitOverride": true`.

Rules:
- **No `any`.** Untrusted data is `unknown`, narrowed with Zod. Casting API data with `as` is forbidden; the generated types are already exact. Every `// @ts-expect-error` carries a reason.
- **Generated API types only** (D50; glossary §13 "never hand-written"). `python -m app.scripts.export_openapi` writes the committed `src/lib/api/openapi.json`, and the web script `api:types` generates `src/lib/api/schema.d.ts` from it; `make gen-api` runs both (D76; §3.9). Both generated files are excluded from ESLint and Prettier. One `openapi-fetch` client module is the only code that talks to `/api/*`. TanStack Query hooks wrap it, one file per resource, and query keys live in one place. Paths follow spec 09.
- **Components.**
  - Names `PascalCase`, files `kebab-case.tsx`, hooks `useXxx` (glossary §13). One exported component per file; props type named `XxxProps`.
  - Server Components by default. `"use client"` only for interactive leaves.
  - shadcn/ui primitives under `components/ui` are composed, not forked ad hoc.
- **The UI never decides the workflow.**
  - Booking action buttons come only from `allowed_actions` (D48); non-booking buttons (team, services, parts, stock, tasks) only from the membership's `capabilities` in `GET /api/v1/me` (D66).
  - Status labels come from one map keyed by `BookingStatus` (glossary §3: staff labels in the POS, customer-facing labels in the portal).
  - Money goes through one `formatPKR` (D41, `Intl.NumberFormat('en-PK', { style: 'currency', currency: 'PKR' })`). Dates go through one `formatDateTime` in the shop's timezone (D38; `formatSlot` is its alias for slot times). Both live in `apps/web/src/lib/format.ts`.
  - API errors are mapped to messages by problem `code`, never by parsing `detail`.
- **Forms.** React Hook Form + Zod. Field errors from 422 responses (API-02) are mapped back onto the form fields.

### 1.3 SQL and migrations

- **Alembic is the only path to a schema**, in production (D13 pre-deploy) and in tests (§4.1). `metadata.create_all()` is never used.
- **Constraint naming convention:** spec 02's `NAMING_CONVENTION` on `Base.metadata`. It is the Alembic recipe, with `%(column_0_N_name)s` so composite keys and FKs get full names. Inside migrations, explicit names are wrapped in `op.f()` (spec 02). Predictable names are what autogenerate and dropping constraints rely on.
- **Autogenerate is a draft.** Every migration is read and fixed by hand: CHECK constraints (D29 enums, D42 stock), composite FKs (D20), partial or unique indexes, server defaults. `downgrade()` is implemented.
- **A merged migration is immutable.** Fix forward with a new revision. Use one migration per module per PR, with message `"<module>: <change>"`. As built, the whole schema — bonus tables included — is one baseline revision, `23165172278b` (spec 02 §9, D84); D29 enums are rendered into migrations by the `alembic/env.py` `render_item` hook.
- **Drift gate.** `alembic check` (Alembic ≥ 1.9) fails CI when models and migrations disagree. The **round trip** runs on every CI run inside pytest: `tests/db/test_migrations.py` does `downgrade base → upgrade head → check` on `<db>_test` and asserts a single head (D84); the `api` job then runs `alembic upgrade head` + `alembic check` on the empty `bayflow` database (§6).
- **Put rules in the database where they belong:**
  - stock `CHECK`s (`on_hand ≥ 0`, `reserved ≥ 0`, `reserved ≤ on_hand`, D42)
  - money `CHECK`s: `≥ 0` and whole rupees (`ck_<table>_whole_rupees`, D41, spec 02)
  - enum `CHECK`s (D29)
  - uniqueness: booking `reference`, `(shop_id, sku)`, one membership per `(shop_id, user_id)`, `(shop_id, slot_start)` for slot counters
  - composite FKs that make cross-shop references impossible (D20)
  
  Tests INV-14, EST-20 and SEC-45 prove these hold even when the service layer is bypassed. As built, `apps/api/tests/db/test_constraints.py` already covers them at the schema level (stock CHECKs, whole rupees, one owner, active owner membership, composite tenant FKs, assignee membership, own-vehicle FK, enum CHECKs, lower-case e-mail, append-only ledgers, `seq`, ids and clock timestamps), with rows built directly by `tests/rows.py`.
- **Types.** Money is `numeric(12,2)` (D41). Timestamps are `timestamptz` in UTC (D38). Primary keys are `uuid` (D50).
- **Queries.** SQLAlchemy expressions only. Raw SQL is allowed only as `text()` with bound parameters (Ruff `S608` flags string-built SQL). Locks are taken with `with_for_update()` inside the action's single transaction, in the D30 order.
- **The seed is not a migration** (D13, D51). It is an idempotent script that runs through the service layer.

### 1.4 Naming

Glossary §13 is binding: DB `snake_case` plural tables, `<entity>_id`, `<role>_user_id`; Python `snake_case` / `PascalCase` / `XxxCreate|Update|Read`; TS components `PascalCase` in `kebab-case.tsx`, hooks `useXxx`; URLs `kebab-case`; Conventional Commits. In addition, for tests:

| Item | Convention | Example |
|---|---|---|
| Test file | `test_<unit>.py` / `<unit>.test.ts(x)` | `test_state_machine.py`, `format.test.ts` |
| Test function | Starts with the lower-case catalogue ID, then intent | `test_sm06_two_qc_inspectors_pick_concurrently` |
| Builders | `make_<thing>`, `drive_booking_to` | `make_shop(capacity=1)` |
| Commit scope | A glossary §7 module, or `web`, `api`, `infra`, `ci`, `seed`, `specs`, `deps` | `test(qc): prove first pick wins (SM-06)` |

---

## 2. Git and review

### 2.1 Commits

- **Conventional Commits 1.0.0:** `<type>[optional scope]: <description>`.
  - Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`, `build`, `perf`, `style`.
  - Breaking changes use `!` or a `BREAKING CHANGE:` footer.
  - Examples: `feat(bookings): add confirm and decline actions (T02, T03)`, `fix(inventory): release reservations on cancel (D24)`, `test(scheduling): last slot under concurrency (SM-07)`.
- **Small and meaningful** (brief §9.1 "meaningful commit history (not a single commit)", §9.4 "small commits"):
  - One logical change per commit, ideally under about 300 changed lines.
  - Tests go in the same commit as the code they test.
  - Every commit passes `make lint` (spec 07). No `wip` or `fix typo` commits reach `main` (amend or fix up before review).
- **Every team member commits under their own git identity**, with an e-mail linked to their GitHub account, so each person's work shows in the history. From PH0 onwards everyone owns at least one deliverable (spec 14; roadmap phases are PH0…PH10, D75).
- The commit body cites the spec or decision it implements (`Implements spec 08 T13; D42`). This makes the history readable for judges and for spec 15.

### 2.2 Branches, pull requests and merging

- Trunk-based. Short-lived branches (`feat/bookings-confirm`, `fix/inventory-release`) open a PR to `main` within hours, not days. `main` is always deployable: every merge auto-deploys to Vercel and Railway (spec 07).
- **Branch protection on `main`**, turned on at the PH0 exit (spec 14). It is available for public repositories on GitHub Free, and the repo must be public anyway (§9.1).
  - Require a pull request with **1 approval**.
  - Require the status checks `api`, `web`, `contract` and `secrets` (§6 below; `contract` is the D76 drift gate).
  - Reviewers answer within ~30 minutes during the hackathon. Pair-review counts.
- **Merge method: "Rebase and merge"** keeps every author's small commits in `main`, which is the history judges read. Use "Squash and merge" only for single-purpose PRs with noisy commits, and then the PR title must itself be a Conventional Commit.

### 2.3 PR template (`.github/pull_request_template.md`)

```markdown
## What and why
<!-- One paragraph. Link the spec rows / decisions implemented, e.g. "spec 08 T13–T15, D42, D43". -->

## Changes
-

## Tests
- Catalogue IDs covered: <!-- e.g. INV-02, INV-05, SM-12 -->
- [ ] `make lint` and `make test` pass locally (spec 07 Makefile)
- [ ] Negative paths covered (403 / 404 / 409 / 422 as applicable)

## Screens / API examples
<!-- Screenshot (mobile + desktop) for UI changes; request/response for API changes. -->

## Checklist
- [ ] Specs updated first if behaviour or a decision changed (decisions → spec 17; new names → "Proposed glossary additions")
- [ ] Names match spec 18 exactly
- [ ] No secrets or real credentials; any new env var is in `.env.example` with a one-line comment
- [ ] Migrations reviewed (upgrade + downgrade); `alembic check` clean
- [ ] API changed → `make gen-api` run and the regenerated `openapi.json` + `schema.d.ts` committed
- [ ] Seed still works and demo data still shows this feature
- [ ] AI assistance used? (yes/no, where): ______ — I have read, run and understood every line and can explain it in the judges' review
```

### 2.4 Review checklist (reviewer)

| Area | Check |
|---|---|
| Spec fidelity | Behaviour matches the spec row cited; names from spec 18; no invented statuses, actions, error codes or env vars |
| Tenancy & security | `shop_id` only from the path on staff routes; repository calls pass `shop_id`; invisible → 404, wrong role → 403 `FORBIDDEN`, not the assignee → 403 `NOT_ASSIGNED` (glossary §10 order); no secrets or PII in code or logs; demo credentials appear only in seed data, README and the login page (D52) |
| Transactions & concurrency | One action = one transaction; booking row locked first, D30 lock order; side effects through the owning module's service; WebSocket and e-mail only after commit (D14) |
| Validation & errors | Pydantic model on every input; problem+json with the right `code`; no stack traces in responses |
| Tests | Catalogue IDs named in the test function; happy and negative paths; no `sleep()`-based timing (use the lock gate, §3.5); clock injected, not real time |
| Code quality | Thin router; size limits respected; no dead or commented-out code; no `Any`/`any`; comments say *why* |
| UX (web) | Loading, empty and error states; mobile width; buttons from `allowed_actions`; money and dates through the shared formatters |
| **AI-generated code** | The reviewer may ask the author to explain any hunk. Code nobody can explain is rewritten or removed (brief §9.4, FAQ). Generated tests must assert real behaviour, not echo mocks. Never paste secrets or `.env` values into AI tools |
| Docs | README / `.env.example` updated if commands, env vars or demo accounts changed |

### 2.5 No secrets

- `.env` and `.env.*` (except `.env.example`) are in `.gitignore`. `.env.example` in the repo root lists every glossary §12 variable with a placeholder and a one-line comment (§9.1, §9.3). Real values live only in Vercel/Railway settings and GitHub Actions secrets.
- **GitHub push protection** is enabled by default for users pushing to public repos. It blocks pushes that contain supported secret types. Keep the repo public from day 1 (spec 14 PH0).
- **gitleaks in CI.** Job `secrets` runs `gitleaks/gitleaks-action@v3` with `fetch-depth: 0`, so it scans the whole history.
  - A personal-account repo needs no license. An organization-owned repo needs a free `GITLEAKS_LICENSE` secret; alternatively run the gitleaks CLI v8.30.x (`gitleaks git`) in the job.
  - False positives are allowlisted per finding via fingerprints in `.gitleaksignore`, never per file. This includes the intentionally public demo password (D52) and the throwaway CI Postgres credentials.
- If a real secret is ever pushed, **rotate it immediately**. Rewriting history is not enough on a public repo.

---

## 3. Test strategy

### 3.1 The pyramid

| Layer | Tool | Database | What it proves | Speed |
|---|---|---|---|---|
| **Domain unit** (U) | pytest | none | The `RULES` table, `allowed_actions`, totals, slot grid, reference format; exhaustive | < 5 s total |
| **Integration** (I) | pytest + async SQLAlchemy | real PostgreSQL | Transactions, row locks, CHECK and composite-FK violations, ledger arithmetic | fast |
| **API** (A) | httpx `AsyncClient` + `ASGITransport` | real PostgreSQL | Status codes, RFC 9457 bodies + `code`, auth, roles, tenancy, pagination, `allowed_actions` | fast |
| **Concurrency** (C) | API tests + lock gate | real PostgreSQL | "Exactly one wins" for QC pick, last slot, last stock unit, double-submit | seconds |
| **Scenario** (S) | API tests | real PostgreSQL | Worked example, estimate-rejected paths, QC loop, cancellation with release, partial receipt | seconds |
| **Seed** (D) | pytest | real PostgreSQL | Idempotency, demo cast, worked-example stock | seconds |
| **Web unit** (W) | Vitest + RTL + jsdom | none | Formatters, status map, action bar, error mapping, form schemas | seconds |
| **Contract** (X) | openapi-typescript | none | Committed TS types = OpenAPI schema = running API | seconds |
| **Live** (L) | httpx script, Playwright, manual checklist | live | The deployed URL works end to end with seeded accounts | minutes |

Rule of thumb: put each rule's exhaustive check at the lowest layer that can see it, and keep one end-to-end proof per rule at the API layer.

### 3.2 Domain unit tests (no DB)

- **SM-01, exhaustive.** Generated from the enums: 17 `BookingStatus` × 27 `BookingAction` × 7 `ActorRole` = 3,213 cases. For each case, compare `RULES` against an expected verdict written in the test from spec 08's tables. This is deliberately a second, independent statement of the spec: the two must agree. Every pair not in the table must yield `INVALID_TRANSITION` when role and guard pass.
- **`allowed_actions`** for every (status, actor role, guard set) (SM-19, domain half). It must never list `CREATE` or `RECEIVE_PARTS`. Customers only ever see `approve-estimate`, `reject-estimate`, `cancel`, `complete`. The Owner sees SA actions only (D16).
- Pure helpers:
  - Estimate totals: `Decimal`; line totals rounded half-up to whole rupees (EST-20); worked example 16,600.00 → 16,100.00 (EST-05).
  - Slot grid from working hours, duration and timezone, anchored at local midnight (D37, D38; BK-30).
  - Reference and PO-number format and alphabet; random codes never start with `SEED` (BK-14, INV-20).
  - Low/out stock classification (D45).
  - Capabilities per membership role (glossary §2.4, D66; the API half is spec 04's SEC-46).
  - The QC picker ≠ technician guard (QC-08).
- The state-machine part of this group (SM-01, the domain half of SM-19, QC-08) is PH0 work (D72: the pure state-machine domain and its exhaustive tests come before any module feature); the other helpers arrive with their modules.
- **(P1) Domain coverage gate:** `uv run pytest tests/unit/bookings --cov=app.modules.bookings.domain --cov-branch --cov-fail-under=100`.
- **Status (D72):** these tests already exist in `apps/api/tests/unit/bookings/test_state_machine.py` — 1,131 pytest items, 100 % branch coverage of the domain package (2026-10-09).

### 3.3 Integration tests (service and repository against real PostgreSQL)

These call services and repositories directly, with the real async engine:
- **Transaction atomicity.** A failure in a side effect rolls back status, events, stock, slot counter and notifications together (NOT-07, spec 08 principle 4).
- **Database constraints.**
  - CHECK violations: INV-14 (stock), EST-20 (whole rupees).
  - Composite-FK violations: SEC-45 (spec 04) — a `booking_parts` row pointing at another shop's part, or an `estimates` row for another shop's booking.
  - Unique violations: SEC-15, SEC-21, INV-17.
- **Ledger invariants** after every stock operation (INV-01).
- **Repository contracts.** Every shop-scoped repository method rejects a call without `shop_id` (type-level), and returns nothing for another shop's IDs.

### 3.4 API tests (httpx + ASGITransport)

- The client is `httpx.AsyncClient(transport=httpx.ASGITransport(app=manager.app), base_url="http://test")`, created inside `asgi_lifespan.LifespanManager(app)`. `ASGITransport` does not run lifespan events on its own (FastAPI docs).
- Every endpoint gets a happy-path test plus one test per error `code` it can return. All error assertions go through `assert_problem(resp, status, code)` (§4.5).
- **Action matrix** (`tests/security/test_action_matrix.py`, marker `slow`). This is spec 04's SEC-07 and the API half of SM-03, SM-04, SM-05, SM-16, SM-17 and SM-19; one implementation serves them all.
  - Set-up: one booking is driven to each of the 17 statuses with `drive_booking_to` (§4.3). There is a cast of callers: booking customer, another customer, Owner, SA, assigned technician, other technician, assigned parts person, other parts person, QC picker, other QC inspector, and an SA of Shop B.
  - For every (status, slug, caller), an **oracle** written from spec 08 and glossary §10 predicts the outcome, applying the check order: visible? (404) → role (403 `FORBIDDEN`) → assignment (403 `NOT_ASSIGNED`) → status (409 `INVALID_TRANSITION`, or `ALREADY_PICKED` for `pick-qc` on `QC_IN_PROGRESS`). `EDIT_ESTIMATE` is exercised through `PUT …/estimate`, where the status verdict is 409 `ESTIMATE_LOCKED`: the bookings `edit_estimate` use case maps the domain's `INVALID_TRANSITION` to `ESTIMATE_LOCKED`, and the estimates service raises `ESTIMATE_LOCKED` itself as a backstop for a version that is no longer editable (EST-11; `modules/bookings.md`, `modules/estimates.md`). A slug that the caller's endpoint family does not serve — a staff slug such as `confirm` on `/api/v1/me/bookings/{booking_id}/actions/…`, or `approve-estimate` / `reject-estimate` on the staff route — is an unknown route: 404 `NOT_FOUND` before any other check (spec 03).
  - Every predicted rejection is sent and must match the HTTP status and `code` exactly. The booking row and its events must be unchanged afterwards.
  - Every predicted "allowed" must appear in that caller's `allowed_actions`, and is not executed (SM-02 covers execution).
  - Rejected requests change nothing, so the 17 bookings are reused for the whole matrix inside one test function.
- **Route sweep** (SEC-02, spec 04). Enumerate every operation under `/api/v1/shops/{shop_id}/` from the generated OpenAPI document and call each one twice:
  - with another shop's `shop_id`;
  - with your own `shop_id` and another shop's resource ID.
  
  Both must give 404, never 2xx or 403. New routes are covered automatically.
- **Route enumeration rule.** Every test that enumerates routes (SEC-02, SEC-04, API-09, API-13) reads the generated OpenAPI document — `GET /openapi.json` through the test client, the same document `make gen-api` exports to `apps/web/src/lib/api/openapi.json` (D76) — and **never walks `app.routes`**. In FastAPI 0.143, `include_router` stores an included router lazily (an internal `_IncludedRouter`), so `app.routes` misses every included route (executed in spec 04's verification). The WebSocket route never appears in OpenAPI; SEC-33 covers it separately.

### 3.5 Concurrency tests (prove exactly one wins)

Firing two requests with `asyncio.gather` and hoping they overlap is not a proof. They often run one after the other, and naive code then passes. We use a **lock gate** instead, which makes the race deterministic:

1. The test opens its **own** connection, begins a transaction, and runs `SELECT … FOR UPDATE` on the contended row: the booking (SM-06, CON-01, CON-04), the slot counter (SM-07), the part (INV-19) or the shop row (CON-05).
2. It starts both requests as tasks through the same `AsyncClient`. Each request gets its own session and connection (§4.1 `NullPool`), so both block on the gate's lock.
3. It polls `pg_stat_activity` until **two** backends of the test database show `wait_event_type = 'Lock'` (wait events `transactionid` / `tuple`), with an `asyncio.timeout(5)`.
4. It rolls back the gate transaction and awaits both responses.
5. It asserts exactly one success and one expected 409, then checks the database: one `qc_inspections` row, one `PICK_QC` event, `booked_count = capacity`, `reserved ≤ on_hand`.

**Why this works** (validated on PostgreSQL 16 with asyncpg 0.32 on 2026-10-09, using a throwaway container):
- With `SELECT … FOR UPDATE`, both requests queue on the row lock. After release, the second one re-reads the committed row (`QC_IN_PROGRESS`) and returns 409 `ALREADY_PICKED`.
- A naive read-then-update implementation lets both requests read `QC_PENDING`. Both then "win", and the test fails as it should.

D37's slot algorithm (`INSERT … ON CONFLICT DO NOTHING`, then `SELECT … FOR UPDATE`, check, increment) was also checked under a burst of 6 parallel bookings on a counter row that did not exist yet: exactly `capacity` won.

Helpers live in `tests/lockgate.py`: `hold_row_lock(table, **key)` (async context manager) and `wait_for_lock_waiters(n, timeout_s)`. A second, ungated **burst** variant of SM-07 (capacity 1, fresh slot, 6 parallel requests) covers the "counter row does not exist yet" path. As a safety net, the test database runs with `lock_timeout = '5s'`, so a bug fails within seconds instead of hanging CI (§4.1). PostgreSQL also detects deadlocks on its own.

### 3.6 Scenario tests (end-to-end over the API)

Scenario tests are multi-step journeys over HTTP using the real roles. After each step they assert the status, the key side effects and **the notifications created** (recipient + type, spec 08 trace table). At the end, they assert the shared invariants (§4.5).

| Scenario | Proves |
|---|---|
| **Worked example** (SM-18) | Steps 0–16 of spec 08's trace with the brief's exact cast. Step 0 runs through the API: Fatima registers, creates Lahore Auto Care and adds Bilal, Imran, Sara and Usman. The clock is set to Wed 14 Oct 2026 09:00 PKT and Ahmed books Fri 16 Oct 10:00 PKT (`2026-10-16T05:00:00Z`). It checks estimate v1 16,600.00 → v2 16,100.00 (v1 `SUPERSEDED`), stock filter 10/0 → 10/1 → 9/0, oil 8/0 → 8/1 → 7/0, coil 0/0 → 1/1 → 0/0, the PO `ORDERED` → `RECEIVED`, a QC fail with issue `OPEN` → `RESOLVED` → pass, `notify-ready`, `complete`. The trace's 13 notifications reach exactly the listed people (11 until the P1 "Extra" types `BOOKING_CONFIRMED` and `QC_PASSED` exist) |
| Estimate rejected → revise (SM-08) | reject → `revise-estimate` (v3 `DRAFT` by the SA) → send → approve |
| Estimate rejected → technician (SM-09) | reject → `return-to-technician` → technician edits v3 → submit → send → approve |
| QC loop (SM-10) | fail → fix → resend (issues resolved) → fail again → resend → pass. Three `qc_inspections` rows |
| Cancellation (SM-11) | Cancel in `PARTS_ORDERED`: releases reservations (10/0, 8/0, 0/0), frees the slot, supersedes non-final estimates. The PO stays open. Receiving it later adds general stock (INV-09) |
| Partial receipt (SM-12) | PO for 2 coils: receive 1 → `PARTIALLY_RECEIVED`, booking stays `PARTS_ORDERED`; receive 1 → `RECEIVED`, booking `PARTS_READY` |
| Labour-only (SM-13) | Zero `booking_parts`; `mark-parts-ready` then `allocate-parts` pass trivially (D31) |

The same scenario code can run against a live deployment, using an httpx transport to the web origin's `/api/*` rewrite instead of `ASGITransport`. That is DEP-10.

### 3.7 Seed tests

These run the real seed entry function against the empty test database, with a `SimulatedClock` installed behind `app.shared.clock` (D63; spec 11 "Verification").
- Run the seed twice, **with the `SimulatedClock` moved forward one day between runs**: deploys happen on different days and must not create duplicates (SEED-02).
- Check the demo cast and the worked-example stock (SEED-04).
- **Vandalise the demo cast, then seed again** (deactivate a membership, change a role, deactivate a user, change a password): the cast is repaired, while bookings, stock, POs and shop settings changed in the same test stay untouched, and a further run writes no row (D60; SEED-14, SEED-19).
- Check that the worked example replays on seeded data (SEED-10).
- Check the pre-deploy entry point and its `SEED_ON_DEPLOY` switch in a subprocess (SEED-09).

### 3.8 Web tests

- **Vitest + React Testing Library + jsdom.** Packages: `vitest` 5, `vite` 8, `@vitejs/plugin-react`, `jsdom` 30, `@testing-library/react`, `@testing-library/dom`, `@testing-library/jest-dom` (Next.js guide). No `vite-tsconfig-paths`: Vite 8 resolves the `@/*` alias from `tsconfig.json` itself with `resolve.tsconfigPaths: true`, as `apps/web/vitest.config.mts` does; it runs `src/**/*.test.{ts,tsx}` and the root `*.test.ts` (e.g. `next.config.test.ts`), with `vitest.setup.ts` registering jest-dom and RTL's cleanup.
  - **Status (2026-10-09):** 7 test files, **67 tests**, all green — `src/lib/format.test.ts` (WEB-01, WEB-02), `src/lib/status.test.ts` (WEB-03), `src/lib/api/errors.test.ts` (WEB-05), `next.config.test.ts` (SEC-32, web half), plus `src/components/status-badge.test.tsx`, `src/lib/api/query-client.test.ts` (spec 09 §2.7 retry policy) and `src/proxy.test.ts` (spec 09 §2.8 session gate), which carry no catalogue ID yet.
  - Vitest 5 requires Node `^22.12 || ^24 || ≥26`, which our Node 24 (D1) satisfies.
  - Vitest does **not** support async Server Components. Those are covered by Playwright, as the Next.js docs recommend.
  - Hooks are tested with the API client module mocked (`vi.mock`). There are no network calls in unit tests.
- **Playwright smoke (P1, WEB-08 / DEP-11).** It runs against the deployed URL, with `use.baseURL` read from `WEB_URL` (the input name of spec 07's `scripts/smoke.sh`), `retries: process.env.CI ? 2 : 0` and `trace: 'on-first-retry'`. There are two projects: Desktop Chrome and one mobile device profile. The journey:
  1. A fresh customer `smoke+<timestamp>@bayflow.test` books through the wizard.
  2. Seeded staff, each in their own browser context, take the booking through confirm → assign → inspect → **labour-only** estimate → send.
  3. The customer approves.
  4. The parts person runs mark-parts-ready → allocate (D31).
  5. The technician sends to QC; the QC inspector picks and passes; the SA runs notify-ready.
  6. The customer completes the booking, and the test asserts `COMPLETED`.
  
  The labour-only estimate means the smoke run never changes live stock. Like spec 07's `scripts/smoke.sh`, it books at the smoke-test shop `lyallpur-motors` (spec 11) so Lahore Auto Care stays clean for judges.
- **Never assert WebSocket close codes in a browser.** A handshake the API rejects before `accept` closes with **1008** on the server (D70), but a browser only ever reports **1006** (abnormal closure). Close-code assertions (SEC-33, SEC-42, NOT-12) therefore use the server-side `TestClient` (§4.2). Playwright and the web client treat any failed or dropped socket alike: fetch a new ticket and reconnect (WEB-10).

### 3.9 Contract test (generated types in sync)

- `make gen-api` (D76; spec 07) runs `uv run python -m app.scripts.export_openapi ../web/src/lib/api/openapi.json` in `apps/api`, then the web script `pnpm api:types` (`openapi-typescript src/lib/api/openapi.json -o src/lib/api/schema.d.ts`) in `apps/web`. Both files are committed. The OpenAPI snapshot doubles as the "API docs" optional deliverable (§9.1).
- CI job `contract` (spec 07) runs `make gen-api`, then `git status --porcelain -- apps/web/src/lib/api` and fails on any output (as built; unlike `git diff --exit-code` it also catches a generated file that was never committed). Any API change made without regenerating `openapi.json` and `schema.d.ts` fails the build (WEB-07). D76 makes this a standing CI rule, so the gate is P0, not an optional extra. `openapi-typescript --check` is an equivalent shortcut for the TS half.

### 3.10 Live checks

The DEP group (§5 below) runs after every production deploy:
- **Scripted:**
  - spec 07's `make smoke WEB_URL=… API_URL=…` (its checks are listed in spec 07; it books and cancels at the smoke-test shop `lyallpur-motors`);
  - a `pytest -m live` module for DEP-07, DEP-08, DEP-10 and DEP-15;
  - the Playwright smoke (P1).
- **Manual:** the judge path (DEP-09), a checklist run in two browsers.
- **Documented limitation — shared demo data drifts (D71).** Replays of the worked example consume Lahore Auto Care stock and fill the Friday 10:00 slot (capacity 2), and the seed never tops stock up (D51, D60). This is accepted, not fixed: DEP-08 detects it, and the judge notes (spec 11, README) say how to continue — pick another slot; Usman adjusts stock (`ADJUST`, INV-21). Broken demo *accounts* are different: re-running the seed repairs them (D60, SEED-19).

---

## 4. Test infrastructure

### 4.1 Test database — separate DB, migrate once, truncate per test

- **Separate database.** Tests use the `DATABASE_URL` database name plus `_test` (`bayflow` → `bayflow_test`), as spec 07 expects. It sits on the same server: locally the Docker PostgreSQL on host port **5434** (`make db-up` or `./start.sh`; local `DATABASE_URL` = `postgresql://bayflow:bayflow@localhost:5434/bayflow`, D73), in CI the service container. The session fixture creates it when missing (through the `postgres` maintenance database) and **refuses to run unless the name ends in `_test`**, so a dev or production database can never be wiped.
- **Migrate once per session.** At session start:
  1. `DROP SCHEMA public CASCADE; CREATE SCHEMA public;`
  2. `alembic upgrade head`, run as a **subprocess** — the same command Railway's pre-deploy runs (D13). This avoids Alembic's async `env.py` calling `asyncio.run()` inside pytest's loop.
  3. `ALTER DATABASE <db>_test SET lock_timeout = '5s'` and `statement_timeout = '30s'`.
- **Isolation: TRUNCATE after each DB test, not transaction rollback.** After every test marked `db`, one statement runs: `TRUNCATE <every app table> RESTART IDENTITY CASCADE` (`alembic_version` is kept). We chose truncation because rollback-based isolation (SQLAlchemy's "join the session into an external transaction" recipe with `join_transaction_mode="create_savepoint"`) cannot work with this codebase:
  1. **Services commit.** Spec 08 makes each action one transaction committed in the service. The recipe would turn those commits into savepoint releases on one shared connection, so the test would no longer run the real transaction boundaries.
  2. **Concurrency tests need ≥ 2 real connections.** A transaction never blocks on its own row locks, so row-lock contention is invisible inside one outer transaction. Also, a single `AsyncSession` or asyncpg connection cannot serve two concurrent tasks (SQLAlchemy asyncio docs).
  3. **After-commit effects only happen on real commits.** This includes WebSocket pushes and e-mail (D14, NOT-07, NOT-08).
  4. **The seed commits through its own entry point** (SEED-xx).
  
  The cost is one `TRUNCATE` per DB test. Pure unit and web tests never touch the database.
- **Engine with `NullPool` in tests.** Every session gets a fresh connection, so there is no pooled connection reuse across event loops (SQLAlchemy's recommendation). Concurrency requests are guaranteed distinct backends, and the sync WebSocket `TestClient` (which runs the app in its own loop) is safe.
- **No shared fixtures in the database.** Each test builds its own shops with builders and never relies on seed data. Only SEED tests run the seed.
- (P1, only if the backend suite exceeds about 3 minutes) Shard with pytest-xdist, one database per worker (`bayflow_test_gw0`, …). Not needed at hackathon size.
- **As built (D84).** `apps/api/tests/conftest.py` implements all of the above: it derives `<db>_test`, refuses any other name, creates it through the `postgres` database, resets `public`, runs `alembic upgrade head` as a subprocess, sets the two timeouts and truncates every app table (`RESTART IDENTITY CASCADE`) after each `db` test. **The `db` marker and the `db` fixture imply each other** (a collection hook adds whichever is missing), so every test that touches PostgreSQL is marked and **`uv run pytest -m "not db"` runs without a database**: on 2026-10-09 that is 1,329 of the 1,371 collected tests (42 are `db`). It also pins the test environment (`APP_ENV=development`, a test `JWT_SECRET`, `COOKIE_SECURE=false`, `EMAIL_PROVIDER=none`, `SEED_ON_DEPLOY=false`) before importing the app, whatever the developer's root `.env` says.

### 4.2 The app under test

- The app is built by the app factory (spec 01) with test settings:
  - `DATABASE_URL` pointing at the derived `<db>_test` database;
  - `COOKIE_SECURE=false`, so the httpx cookie jar sends `bf_session` back over `http://test` (standard cookie semantics; not re-verified);
  - `EMAIL_PROVIDER=none`, so e-mail is disabled (D26; NOT-09 injects a fake mailer);
  - rate limits raised through a test-settings override of spec 04's constants, except in SEC-27 and BK-32, which use the real thresholds; the in-memory limiter storage is reset after every test. The limiters keep their windows on system time (the one D63 exception, §4.4), so tests reset them instead of moving the clock. As built, the reset exists (`app.core.security.reset_rate_limits()`, called by an autouse fixture before and after every test); the override seam that raises the limits is still to be built with the first rate-limited route (Open question 6).
- The client wraps `LifespanManager(app)` (asgi-lifespan) + `AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test")`.
- **Auth helpers.** `as_user(user)` returns a client that sends `Authorization: Bearer <token>`. This is fast and avoids a login round-trip; D8 accepts Bearer everywhere. The SEC tests use the real login and cookie flow.
- **Clock and overrides.** The `clock` fixture installs a `SimulatedClock` as the process clock in `app.shared.clock` and restores `SystemClock` on teardown (D63; §4.4). `app.dependency_overrides` (FastAPI "Testing Dependencies with Overrides") is used only for collaborators such as a fake mailer, and is reset with `app.dependency_overrides = {}` in teardown.
- **Event loop.** pytest-asyncio with one session-wide loop, so session-scoped async fixtures and asyncpg agree on the loop:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
asyncio_default_test_loop_scope = "session"
# importlib mode: test files in different folders may share a basename without __init__.py files.
addopts = "--strict-markers -ra --import-mode=importlib"
markers = [
  "db: uses the PostgreSQL test database (<db>_test); tables truncated after the test",
  "concurrency: parallel requests through the lock gate",
  "scenario: multi-step journey; shared invariants asserted at the end",
  "seed: runs the seed entry point",
  "slow: > 5 s (action matrix, route sweep); deselect with -m \"not slow\"",
  "live: runs against WEB_URL / API_URL only when they are set",
]
```

We picked pytest-asyncio over the AnyIO pytest plugin that FastAPI's docs use because of its explicit loop-scope settings. If anyone switches, note that AnyIO's default `anyio_backend` runs every backend, and asyncpg is asyncio-only, so the fixture must be overridden to return `"asyncio"`. Never mix the two plugins' markers.

- **WebSocket tests** (NOT-08, NOT-12, SEC-33, SEC-42) use FastAPI's sync `TestClient` and `client.websocket_connect(...)` in their own module. The hub's routing logic is unit-tested with fake connections.
  - A rejected handshake (missing, expired, tampered or `typ` = `session` ticket, foreign `Origin`, deactivated user) is asserted server-side: `websocket_connect` raises `starlette.websockets.WebSocketDisconnect` with `code == 1008` (D70; verified with FastAPI 0.143.0 / Starlette 1.7.0). Browsers only see 1006 for the same rejection, so no browser or Playwright test asserts a close code (§3.8).
  - Ticket expiry follows the app clock (D63): the test advances the `SimulatedClock` by more than 60 s between fetching the ticket and the handshake (SEC-33); a socket that is already open stays open after its ticket expires.
  - **`TestClient` only for WebSockets.** Starlette 1.7's `TestClient` warns that its `httpx` usage is deprecated, so every HTTP test uses `httpx.AsyncClient` + `ASGITransport` (above) and only the WebSocket modules use `TestClient`, each with a filter scoped to that module and that message. Verified with FastAPI 0.143.0, Starlette 1.7.0, httpx 0.28.1 and pytest 9.1.1: the module passes under `-W error` with the mark and fails without it.

```python
# apps/api/tests/modules/notifications/test_realtime_ws.py (the WebSocket modules only)
pytestmark = pytest.mark.filterwarnings(
    "ignore:Using `httpx` with `starlette.testclient`:Warning"  # Starlette 1.7 TestClient deprecation
)
```

### 4.3 Builders and `drive_booking_to`

Builders are plain async functions in `tests/builders.py`. They call the **real service layer** with a real actor, never raw SQL, so test data is always reachable and consistent. Factory libraries add little here, because every builder must go through async services. *As built (2026-10-09):* `tests/builders.py` does not exist yet — the services arrive from PH1. The schema-level tests use `tests/rows.py` instead, which builds ORM rows directly (`make_user`, `make_shop`, … with the same names) **on purpose**, to prove what the database enforces with the services bypassed (INV-14, SEC-45); feature tests must never use it.

| Builder | Creates (through services) |
|---|---|
| `make_user(email=None, password=TEST_PASSWORD)` | A user (identity service); unique e-mails like `user-<n>@bayflow.test` (valid under D62); `TEST_PASSWORD` is 12–128 characters (D10) |
| `make_shop(owner=None, *, capacity=2, slot_minutes=60, hours=MON_SAT_9_TO_18, timezone="Asia/Karachi", listed=True)` | A shop + `OWNER` membership + working hours |
| `add_member(shop, role, user=None, active=True)` | A membership (D18 rules) |
| `make_team(shop)` | SA, Technician, Parts Person and **two** QC inspectors (SM-06 needs two); returns a `Team` dataclass |
| `make_services(shop)` | Catalogue incl. "Check engine light" and "Oil change" |
| `make_parts(shop, *, stock="short")` | Creates the parts in the catalogue (they start at `on_hand = 0`, D44), then sets opening stock with one `ADJUST` per part **as the shop's Parts Person**: oil filter 10 @ 900, engine oil 4 L 8 @ 5,200, ignition coil 0 @ 6,500 (spec 08 numbers); `stock="available"` also stocks the coil |
| `make_booking(shop, customer=None, *, services=…, slot=next_free_slot(shop))` | A `PENDING` booking via the `CREATE` service path (D32 rules, reference, slot counter) |
| **`drive_booking_to(status, *, shop=None, stock="short" or "available", labour_only=False, cancel_from=None)`** | A booking in any of the 17 statuses, reached by **performing the real actions** below. Returns a `BookingCtx` (booking, team, customer, estimate ids, PO id) |

Canonical paths used by `drive_booking_to` (each arrow is a real service call by the right actor):

| Target status | Path from `CREATE` (`PENDING`) |
|---|---|
| `CONFIRMED` | `confirm` |
| `ASSIGNED` | … → `assign-technician` |
| `INSPECTING` | … → `start-inspection` |
| `ESTIMATE_REVIEW` | … → edit estimate (worked-example lines, or one labour line if `labour_only`) → `submit-estimate` |
| `AWAITING_CUSTOMER` | … → `send-estimate` |
| `ESTIMATE_APPROVED` | … → `approve-estimate` |
| `ESTIMATE_REJECTED` | `AWAITING_CUSTOMER` → `reject-estimate` |
| `PARTS_PENDING` | `ESTIMATE_APPROVED` → `assign-parts-person` |
| `PARTS_ORDERED` | … → `order-parts` (needs `stock="short"`) |
| `PARTS_READY` | `stock="short"`: … → receive the whole PO (`RECEIVE_PARTS`); `stock="available"` or labour-only: `PARTS_PENDING` → `mark-parts-ready` |
| `IN_REPAIR` | … → `allocate-parts` |
| `QC_PENDING` | … → `send-to-qc` |
| `QC_IN_PROGRESS` | … → `pick-qc` (QC #1) |
| `READY_FOR_PICKUP` | … → `pass-qc` |
| `COMPLETED` | … → `complete` |
| `CANCELLED` | `decline` from `PENDING`, or `cancel_from=<any cancellable status>` → `cancel` |

Because builders use the real transitions, a broken transition fails the builder loudly, and every builder call doubles as a smoke test of the happy path.

### 4.4 Time control — one swappable clock (D63)

- **Single source of "now" (D63):** `app.shared.clock` holds the process-wide `Clock`: `get_clock()` returns it, and `utcnow()` is shorthand for `get_clock().now()` (a timezone-aware UTC datetime). It is `SystemClock` in production and `SimulatedClock` in the seed and tests. Services read it **once per action, after taking the action's row locks**, and assign that instant to every `*_at`, `created_at` and `updated_at` the action writes (spec 02 "Action times"). Domain functions never read the time; they receive `now` as a value. The database's `DEFAULT now()` is only a fallback for hand-written SQL.
- Ruff `TID251` bans every other way of reading the time (§1.1). That forces every business decision through the clock:
  - slot "in the past" and the 30-day horizon (D37); the bonus ring deadlines (spec 05);
  - JWT `iat` / `exp`, for both issuing and validating (D63; spec 04);
  - `created_at`, `updated_at`, `sent_at`, `decided_at`, `repair_started_at`, `ready_notified_at`, `completed_at`, `cancelled_at`, `picked_at`.
- **Test clocks — one class, `SimulatedClock`.** The `clock` fixture installs one as the process clock and restores `SystemClock` on teardown. It is used in two ways:
  - **Frozen** at an instant until the test moves it (`set` / `advance`): `SimulatedClock(datetime(2026, 10, 14, 4, 0, tzinfo=UTC))` — Wednesday 14 Oct 2026 09:00 PKT — for slot tests (BK-08, BK-11, BK-12) and for the same-instant ordering proof (BK-31). The worked example's "Friday 10:00" is then `2026-10-16T05:00:00Z`, matching glossary §9's example.
  - **Stepping:** `SimulatedClock(start, step=timedelta(seconds=1))` advances by `step` on every `now()` read. It is the default for scenario tests, so each action gets its own instant and orderings such as `sent_at < decided_at` can be asserted.
  
  `step`, `set` and `advance` are this spec's proposal for the test-facing API (Proposed glossary additions); spec 01 owns the class, and spec 11's seed uses the same `set`.
- **Ledger order (D79).** `booking_events` and `stock_movements` carry `seq` (`bigint GENERATED ALWAYS AS IDENTITY`, spec 02). Rows written by one action share that action's instant, so lists and running balances order by `(created_at, seq)`, never by the random UUID. Invariant checks (§4.5) never depend on the order of rows inside one action (BK-31, INV-26).
- **JWT times follow the clock too (D63).** `issue_token` / `decode_token` take `now` (callers pass `utcnow()`), so tokens and tickets are stamped and validated with the app clock: PyJWT's own system-time `exp` / `iat` checks are switched off while `require` and the signature check stay (spec 04, executed with PyJWT 2.15). Expiry tests therefore just advance the `SimulatedClock` — past `exp` for sessions (SEC-25), by more than 60 s for tickets (SEC-33).
- **The one exception (D63): rate-limit windows.** slowapi and `limits` keep their windows on system time inside the libraries (spec 04 "Rate limiting"). Tests reset the limiter storage instead of moving the clock (§4.2).
- **Seed.** The seed installs a `SimulatedClock` and sets it before each scripted step, so finished sample jobs get past slots through the normal rules (spec 11). Seed tests move it forward between runs (SEED-02).

### 4.5 Shared assertions (`tests/assertions.py`)

- `assert_problem(resp, status, code)`. Checks:
  - `Content-Type: application/problem+json`;
  - the RFC 9457 members defined in spec 03 are present, and `status` equals the HTTP status;
  - `code` equals the expected glossary §10 code;
  - the body contains no stack trace, SQL text or exception class name.
- `assert_invariants(session)` runs automatically after every `scenario` test, and in SEED-06. It checks:
  - **Ledger:** summing the signed `on_hand_delta` / `reserved_delta` of `stock_movements` (D42) reproduces each part's `on_hand` and `reserved`. `booking_parts.reserved_qty` and `consumed_qty` match the movements per booking. `0 ≤ reserved ≤ on_hand` (INV-01). These are sums, so the order of rows inside one action never changes the verdict (D79; INV-26).
  - **Estimates:** at most one version per booking is `DRAFT`, `SUBMITTED` or `SENT` (EST-16).
  - **Slots:** each `slot_counters.booked_count` equals the number of non-`CANCELLED` bookings in that slot. The count never goes below 0.
  - **Event chain:** each booking's `booking_events`, in `(created_at, seq)` order (D79), form a continuous chain (each `from_status` equals the previous `to_status`), starting with `CREATE` (— → `PENDING`) and ending at the booking's current `status`.
  - **Tenancy:** every notification recipient is the booking's customer or an active member of the booking's shop (NOT-04).

### 4.6 Layout

The planned layout mirrors `app/modules`, as spec 01 sets out, plus a few cross-cutting folders. **As built (2026-10-09)** the foundation tests (PH0) live in `unit/`, `api/` and `db/`; the other folders are created by the phases that need them. There are no `__init__.py` files: pytest runs with `--import-mode=importlib`, so test files in different folders may share a basename.

```
apps/api/tests/      # as built: conftest.py, rows.py, unit/, api/, db/ — everything marked "planned" comes later
  conftest.py        # test database (<db>_test), NullPool engine, migrate-once, truncate, app + clients (`client` without lifespan, `db_client` with it), clock fixture; planned: as_user
  rows.py            # direct ORM rows for schema-level tests (services bypassed on purpose, §4.3)
  builders.py        # planned (PH1): make_*, drive_booking_to
  assertions.py      # built: assert_problem, assert_invariants (+ invariant_violations)
  lockgate.py        # built: hold_row_lock(db, table, **key), wait_for_lock_waiters(db, n)
  unit/              # pure, DB-free (no marker): core/ (config, errors, logging, security), shared/ (clock, email, event bus, money, timestamps), bookings/test_state_machine.py (SM-01, SM-19 domain half, QC-08)
  api/               # the app through httpx (some `db`): auth dependencies, database-error mapping, error handlers, health, middleware
  db/                # schema level (`db`): constraints (INV-14, SEC-45, …), the migration round trip and single head
  modules/<module>/  # planned: DB-backed service, repository and API tests (`db`), concurrency tests (`concurrency`), WebSocket modules
  security/          # planned: spec 04 SEC catalogue, incl. the action matrix (SEC-07) and the route sweep (SEC-02)
  e2e/               # planned: scenarios — test_worked_example.py (SM-18) and SM-08 … SM-13 (`scenario`)
  seed/              # planned: SEED-xx (`seed`)
  live/              # planned: DEP scripted checks (`live`)
apps/web/
  src/**/*.test.ts(x), next.config.test.ts   # Vitest, next to the code under test (as built: 7 files, 67 tests)
  e2e/smoke.spec.ts     # Playwright smoke (P1, planned)
```

### 4.7 Running tests locally (copied into the README, brief §9.1)

The Make targets come from spec 07.

```bash
./start.sh                         # whole app locally: PostgreSQL :5434, migrations, seed, API :4000, web :3000 (D73)
./stop.sh                          # stops API + web, frees 3000/4000, stops the DB container (volume kept)
                                   # Windows: start.bat / stop.bat
make db-up                         # PostgreSQL only (Docker, host port 5434); the test session creates <db>_test itself
make test                          # API tests (pytest, real PostgreSQL) + web unit tests (Vitest)
make lint                          # Ruff, format check, mypy, import contracts, ESLint, Prettier, tsc

cd apps/api
uv run pytest                      # all backend tests
uv run pytest tests/unit           # pure, DB-free tests only: seconds
uv run pytest -m "not db"          # every test that needs no PostgreSQL (no Docker needed)
uv run pytest -m "not slow"        # quick loop
uv run pytest tests/e2e -k worked_example -vv

cd apps/web
pnpm test                          # Vitest, single run
WEB_URL=https://<live-web-url> pnpm test:e2e                     # Playwright smoke (P1)

make smoke WEB_URL=https://<web> API_URL=https://<api>          # post-deploy smoke (spec 07)
cd apps/api && WEB_URL=https://<web> API_URL=https://<api> uv run pytest -m live   # DEP-07, DEP-08, DEP-10, DEP-15
```

---

## 5. Test catalogue

**Columns.**
- **Layer:** U domain unit, I integration, A API, C concurrency, S scenario, D seed, W web unit, X contract, L live.
- **Pri:** P0 = must exist and pass before submission; P1 = recommended extra; P2 = bonus track, built only after the core works end to end on the live URL (D36). Bonus-track tests (calling, AI Front Desk) belong to spec 05. **Realtime (WebSocket) tests are P1** (D88: the hub, `GET /api/v1/realtime/ticket` and `/api/v1/ws` are P1; the bell kept fresh by 15 s polling is the P0 path) — they become mandatory only with the bonus calling (P2), which needs the socket.

**Markers.**
- **★** = the *minimum proof set*: 21 tests that must exist by the 50 % checkpoint (CP3, spec 14) and are never cut.
- **†** = the exact error code was proposed here where the foundation specs didn't pin it; spec 03 (draft) has since confirmed every one (Open question 2).

**Naming.** Test functions start with the lower-case ID (§1.4), so spec 15 can trace requirement → test by grep.

**ID prefixes (D75).** `QC-xx` is this spec's QC *test* prefix; QC Inspector *screens* are `QI-xx` (spec 10). AI Front Desk tests are `FD-xx` (spec 05); `AI-xx` is spec 13's backlog prefix. Roadmap phases are `PH0…PH10`; a bare `P0…P3` is always a D36 priority.

**Groups owned by other specs:**
- SM rows come unchanged from spec 08.
- SEC IDs and their expected results belong to spec 04.
- SEED-11…SEED-19 come from spec 11 ("Verification"); this spec assigned the numbers.
- Bonus tests CALL-xx (calling), FD-xx (AI Front Desk API, D75) and AG-xx (agent) belong to spec 05; the bonus rows below only index the ones that touch this spec's groups.
- **Module-spec proposals** (`modules/*.md`, "Tests"): this spec numbers them. New groups IDN (identity), SHP (shops) and SCH (scheduling); the next free numbers of BK, EST, INV, QC, NOT and RPT; the calls module's proposals become CALL-17…CALL-21 and FD-13…FD-15 (spec 05 already owns CALL-15 and CALL-16). Rows taken from a module spec name it in brackets; the module spec still holds the detail.

This catalogue lists them all so CI and spec 15 have one index.

**Status (2026-10-09, as built).** API: **1,371** pytest items collected (D84 recorded 1,369 when the foundation gates first went green), **1,131** of them the exhaustive state-machine tests (`tests/unit/bookings/test_state_machine.py`); 42 need PostgreSQL (`db`), so 1,329 run with `pytest -m "not db"`. The foundation tests reference SM-01…SM-04, SM-16, SM-19 (domain halves), QC-08, API-01, API-04, API-08, API-12, SEC-04, SEC-13, SEC-15, SEC-24…SEC-26, SEC-28, SEC-30, SEC-37, SEC-45, INV-14 and the domain half of EST-11; module feature tests start with PH1 (spec 14). Web: **67** Vitest tests in 7 files (§3.8). Ruff, mypy, the eight import contracts and the Alembic upgrade / check / downgrade round trip are green (D84).

### SM — booking state machine (copied unchanged from spec 08)

| ID | Test (verbatim from spec 08) | ★ | Layer | Pri | How (spec 12) |
|---|---|---|---|---|---|
| SM-01 | Every (status, action) pair **not** in the rule table is rejected with 409 `INVALID_TRANSITION` (exhaustive, generated from the enums) | ★ | U + A | P0 | §3.2 exhaustive; action matrix §3.4 |
| SM-02 | Each of T02–T22 and O1–O3 succeeds from its allowed status with the right actor |  | A | P0 | One test per row via `drive_booking_to` |
| SM-03 | Role matrix: each action by every wrong role → 403 `FORBIDDEN` | ★ | U + A | P0 | Action matrix (= spec 04 SEC-07). At the API level, a slug outside the caller's endpoint family is 404 (spec 03: e.g. a customer sending `confirm`, an SA sending `approve-estimate`); the domain half still expects `FORBIDDEN` |
| SM-04 | Unassigned technician / parts person / non-picker QC → 403 `NOT_ASSIGNED` (or 404 where not visible) |  | A | P0 | Action matrix (D21 visibility decides 404 vs 403) |
| SM-05 | Staff of Shop A acting on a Shop B booking → 404 | ★ | A | P0 | Action matrix + SEC-02 sweep |
| SM-06 | Two QC inspectors pick concurrently → exactly one 200, one 409 `ALREADY_PICKED` | ★ | C | P0 | Lock gate on the booking row |
| SM-07 | Two customers book the last place in a slot concurrently → exactly one 201, one 409 `SLOT_FULL` | ★ | C | P0 | Lock gate on the slot counter + ungated burst |
| SM-08 | Estimate-rejected path: reject → revise → send → approve | ★ | S | P0 | §3.6 |
| SM-09 | Reject → return-to-technician → submit → send → approve |  | S | P0 | §3.6 |
| SM-10 | QC fail loop twice, then pass | ★ | S | P0 | §3.6 |
| SM-11 | Cancel in `PARTS_ORDERED` releases reservations and frees the slot | ★ | S | P0 | §3.6 |
| SM-12 | Partial PO receipt keeps `PARTS_ORDERED`; full receipt → `PARTS_READY` | ★ | S | P0 | §3.6 |
| SM-13 | Labour-only job passes through the parts steps with zero parts |  | S | P0 | §3.6 |
| SM-14 | Approving a superseded estimate version → 409 `STALE_ESTIMATE` |  | A | P0 | — |
| SM-15 | `expected_version` mismatch → 409 `CONCURRENT_UPDATE` |  | A | P0 | — |
| SM-16 | Owner cannot perform technician, parts or QC actions (403) but can perform every SA action | ★ | A | P0 | Action matrix + SM-02 with Owner as SA. The 403 cases are the 11 technician / parts / QC actions: `start-inspection`, `submit-estimate`, `start-repair`, `send-to-qc`, `order-parts`, `mark-parts-ready`, PO receive (`RECEIVE_PARTS`), `allocate-parts`, `pick-qc`, `pass-qc`, `fail-qc`. An Owner `PUT …/estimate` during `INSPECTING` is 409 `ESTIMATE_LOCKED`, not 403 (EST-11) |
| SM-17 | Customer acting on another customer's booking → 404 |  | A | P0 | Action matrix |
| SM-18 | The worked example end to end (table above) | ★ | S | P0 | "Table above" = spec 08 "Worked example trace"; §3.6 |
| SM-19 | `allowed_actions` is correct for every role in every status |  | U + A | P0 | §3.2 + action matrix |
| SM-20 | Every action writes exactly one `booking_events` row with correct from/to/actor | ★ | A + S | P0 | O1 writes one only when it creates a new version (spec 08 O1); event chain invariant §4.5 |

### SEC — authentication, roles, tenant isolation (brief §7.1, §4; owned by spec 04)

Spec 04 defines SEC-01…SEC-43 and the expected result of each. This table repeats the subject so the catalogue is complete.
- SEC-01…SEC-40 are spec 04's Tier 1 ("must ship") → P0.
- SEC-41…SEC-43 are Tier 2 → P1.
- SEC-44…SEC-50 were added by spec 04's consolidation (SEC-44…SEC-47 started as this spec's proposals): SEC-44…SEC-46 and SEC-48 → P0, SEC-47 → P1, SEC-49 and SEC-50 are bonus → P2.

| ID | Test (subject; the exact expected result is in spec 04) | Layer | Pri |
|---|---|---|---|
| SEC-01 ★ | **Brief §7.1 acceptance:** a Shop A staff token on Shop B's booking list and booking detail → 404 | A | P0 |
| SEC-02 | Cross-tenant sweep over every `/api/v1/shops/{shop_id}/…` operation enumerated from the generated `openapi.json` (never `app.routes`, §3.4) → 404, never 2xx / 403 / 422 | A | P0 |
| SEC-03 | Non-members (a customer, another shop's owner) on Shop A routes → 404 | A | P0 |
| SEC-04 | No, garbage or expired token on protected routes → 401; public routes and `/health` stay open | A | P0 |
| SEC-05 | Management matrix: non-owners on shop settings, hours, members and services → 403 | A | P0 |
| SEC-06 | Inventory matrix: who may adjust stock, create and receive POs, and edit the catalogue (D44) | A | P0 |
| SEC-07 | Booking-action matrix: every slug × every role, generated from the rule table (the action matrix, §3.4) | A | P0 |
| SEC-08 | Technician vs a booking assigned to another technician → absent from lists, 404 | A | P0 |
| SEC-09 | Parts person vs a booking assigned to another parts person → absent, 404 | A | P0 |
| SEC-10 | QC visibility (queue + previously inspected); non-picker pass/fail → 403 `NOT_ASSIGNED` | A | P0 |
| SEC-11 | Customer vs another customer's booking → 404 | A | P0 |
| SEC-12 | The customer never sees `DRAFT` / `SUBMITTED` estimates, internal notes or event `metadata` | A | P0 |
| SEC-13 | Deactivated staff are blocked on the next request with the same token (D9, D19) | A | P0 |
| SEC-14 | Reactivation restores access with the same token | A | P0 |
| SEC-15 | The `OWNER` membership can't be deactivated or re-roled; no second `OWNER` | A + I | P0 |
| SEC-16 | No staff self-sign-up (extra `role` / `shop_id` / `memberships` rejected) | A | P0 |
| SEC-17 | Mass assignment (`shop_id`, `user_id`, `on_hand`, `status`, `reference` …) → 422, nothing changed | A | P0 |
| SEC-18 | Wizard: existing e-mail + wrong password creates nothing (D32) | A | P0 |
| SEC-19 | Wizard: existing e-mail + correct password reuses the account | A | P0 |
| SEC-20 | Wizard while logged in, or with an expired cookie | A | P0 |
| SEC-21 | Owner adds staff with an existing e-mail (password unchanged), and the same person twice | A | P0 |
| SEC-22 | Login with an unknown e-mail, a wrong password or a deactivated user → identical 401 `INVALID_CREDENTIALS` | A | P0 |
| SEC-23 | `bf_session` cookie flags; logout | A | P0 |
| SEC-24 | Token payload and `JWT_EXPIRES_IN` parsing | U + A | P0 |
| SEC-25 | Token rejection (expired, tampered, `alg: none`, wrong `typ` …) → 401 | A | P0 |
| SEC-26 | Valid cookie + invalid Bearer; an invalid cookie alone | A | P0 |
| SEC-27 | Rate limits (D69): the per-account limit on failed credential checks (login + wizard, sent from two IPs) applies whatever the IP; per-IP ceiling on login; owner registration, shop creation and member creation over their limits → 429 `RATE_LIMITED` with `Retry-After` (booking creation: BK-32) | A | P0 |
| SEC-28 | No stack trace in a 500 | A | P0 |
| SEC-29 | Validation responses: 11- and 129-character passwords → 422, `BayFlow@2026` (12) accepted (D10); enum injection; quoted search | A | P0 |
| SEC-30 | CSRF: JSON endpoints reject `text/plain`, form-encoded and missing `Content-Type` | A | P0 |
| SEC-31 | CORS allows only `CLIENT_URL` | A | P0 |
| SEC-32 | Security headers on web and API, incl. `Cache-Control: no-store` on every `/api/*` response, public ones included (D61; the per-operation sweep is API-13) | A + W | P0 |
| SEC-33 | WebSocket ticket (D70: `typ` = `ws`, 60 s by the test clock), `Origin` and deactivation checks: every rejected handshake closes with 1008, asserted with the server-side `TestClient` (§4.2) — browsers would only see 1006; no `booking.updated` for bookings the user cannot see (glossary §11) | A | P1 (D88) |
| SEC-34 | Notifications: another user's notification → 404 | A | P0 |
| SEC-35 | Estimate integrity: locked edits, stale approval, server-side totals | A | P0 |
| SEC-36 | Bonus internal API guarded by `AGENT_SERVICE_TOKEN` and scoped to the caller | A | P2 (with PH9) |
| SEC-37 | Production config guards — incl. D85: a `JWT_SECRET` **containing** `change-me`, `replace-me`, `dev-only` or `placeholder` is refused whatever its length (`.env.example`'s value, CI's `ci-placeholder-…`, the built-in dev secret), as is `COOKIE_SECURE=false`; no tracked `.env`. As built: `tests/unit/core/test_config.py::test_production_refuses_weak_or_placeholder_settings` | U + X | P0 |
| SEC-38 | Log hygiene: no passwords, tokens, tickets or `Authorization` headers in logs | A | P0 |
| SEC-39 | Login `next` redirect sanitiser | W | P0 |
| SEC-40 | Any user (e.g. a technician) can create a shop and owns only that shop (D17) | A | P0 |
| SEC-41 | *(Tier 2)* Cross-site `Origin` / `Sec-Fetch-Site` on cookie-authenticated writes → 403 | A | P1 |
| SEC-42 | *(Tier 2)* WebSocket ticket reuse is refused (1008, server-side `TestClient`, §4.2) | A | P1 |
| SEC-43 | *(Tier 2)* A password change revokes older tokens | A | P1 |
| SEC-44 | Passwords at rest and in responses (D10): only `$argon2id$…` hashes are stored, and no response schema in `openapi.json` has a `password` or `password_hash` field | I + A | P0 |
| SEC-45 | DB level: a child row referencing another shop's parent (`booking_parts` → Shop B part; `estimates` → Shop B booking) violates the composite FK (D20) | I | P0 |
| SEC-46 | `GET /api/v1/me`: every active membership (shop + role) with server-computed `capabilities` per glossary §2.4 — Fatima sees both her shops (§7.2); capabilities are hints, so a member without one still gets 403 `FORBIDDEN` from the server (D66) | A | P0 |
| SEC-47 | No demo bypass: no special case for demo e-mails in auth code; CI grep finds the demo password only in seed data, README and the login page (D52) | X | P1 |
| SEC-48 | The project `Email` type on register-owner, login and the wizard: spaces and mixed case are accepted and stored or matched lower-case; `x@localhost`, `bad@@x` → 422; no `EmailStr` in `apps/api` (D62; API-12 is the `.test` half) | A | P0 |
| SEC-49 | *(bonus)* LiveKit webhook authentication and replay (≙ spec 05 CALL-13) | A | P2 |
| SEC-50 | *(bonus)* Calls and tasks RBAC (≙ spec 05 CALL-10) | A | P2 |

### IDN — identity (from `modules/identity.md` §12)

| ID | Test | Layer | Pri |
|---|---|---|---|
| IDN-01 | Register-owner: 201, cookie set, body `user` has no `memberships` key (D81), `last_login_at` set; a following `GET /api/v1/me` returns `memberships: []` | A | P0 |
| IDN-02 | Transparent rehash: a stored hash with outdated Argon2 parameters is replaced after a successful login and still verifies; a failed login never rewrites it | A + I | P1 |
| IDN-03 | Limiter cleared on success (D69): 4 failures, 1 success, then 4 more failures still log in on the 5th try with the right password; the 5th failure blocks | A | P0 |
| IDN-04 | A user whose every membership is inactive logs in (200); an inactive user with the right password → 401 and counts as a failure (D9) | A | P0 |
| IDN-05 | Internal functions are idempotent: `set_user_active` / `set_password` on an already-correct account change no column (`updated_at` unchanged); `password_matches` never touches the limiter (supports SEED-19, D60) | I | P0 |
| IDN-06 | Logout is idempotent with no cookie, with an expired cookie and with a valid one (always 204 + clearing header); the Bearer token still works after logout (documented stateless caveat) | A | P0 |

### SHP — shops, team and catalogue (from `modules/shops.md` §12)

| ID | Test | Layer | Pri |
|---|---|---|---|
| SHP-01 | Slugs (D68): "Lahore Auto Care" → `lahore-auto-care`; a second shop with the same name → `lahore-auto-care-2`; an Urdu-only name → `shop`; renaming never changes the slug | U + A | P0 |
| SHP-02 | Shop creation is atomic: an invalid working-hours row → 422 and no `shops`, `shop_working_hours` or `shop_memberships` row exists; a valid one creates exactly 1 + 7 + 1 rows | A | P0 |
| SHP-03 | Working-hours validation codes: duplicate weekday, missing times, `closes_at ≤ opens_at`, off-grid time, closed day with times (accepted, stored NULL), 6 or 8 entries | A | P0 |
| SHP-04 | Duration change without future bookings (D37): hours on the new grid → 200; hours off it → 422 `hours_not_on_grid`; with a future booking → 409 even when the hours would fit | A | P0 |
| SHP-05 | Services: duplicate active name (case-insensitive) → 409; a deactivated duplicate is allowed; reactivating it → 409; the same name in another shop → 201 | A | P0 |
| SHP-06 | Members list: Owner sees all incl. inactive and `OWNER`; SA sees only active T and PP; T/PP/QC → 403; order role → name | A | P0 |
| SHP-07 | `open_jobs` (through the D86 `ShopActivityReader`) counts bookings where the member is technician, parts person or current QC picker, excluding `READY_FOR_PICKUP`, `COMPLETED`, `CANCELLED` | A | P0 |
| SHP-08 | Cities list: one entry per case-insensitive city of directory shops only (unlisted or service-less shops excluded, D64) | A | P0 |
| SHP-09 | `/me` excludes inactive memberships, sorts by shop name, and capabilities equal `CAPABILITY_ROLES` for each role; `tasks.manage` absent while calling is disabled (D66) | A | P0 |
| SHP-10 | Route guards and capabilities agree: every route guarded with `CAPABILITY_ROLES[c]` returns 403 for exactly the roles whose `/me` lacks `c` (generated) | A | P0 |

### SCH — scheduling (from `modules/scheduling.md` §12)

| ID | Test | Layer | Pri |
|---|---|---|---|
| SCH-01 | DST zone (`Europe/London`, spring-forward date, hours 00:00–04:00, 60-minute slots): the non-existent 01:00 local slot is skipped; every `slot_end = slot_start + duration` (PKT has no DST, D38, so this guards other zones) | U | P1 |
| SCH-02 | Horizon boundary (D37): the last slot of `today + 30` (local) is offered and bookable; any slot on `today + 31` → `slots: []` and 422 `INVALID_SLOT` `beyond_horizon` | U + A | P0 |
| SCH-03 | A slot starting exactly at `now` is neither offered nor bookable (`in_past`, D63) | U | P0 |
| SCH-04 | Capacity lowered below `booked_count` → slot omitted (no negative `remaining`); raising it again reopens the slot | A | P0 |
| SCH-05 | Availability of a listed shop with no active service returns its slots (spec 03 §4.5); an unlisted shop → 404 (D64) | A | P0 |
| SCH-06 | `release_slot` on a missing counter raises (500); a double release cannot drive the count below 0 | I | P0 |
| SCH-07 | Reason precedence of `modules/scheduling.md` §7.4 (e.g. an off-grid time in the past → `off_grid`; a past on-grid time on a closed day → `in_past`; an on-grid time after closing → `outside_hours`) | U | P0 |

### BK — booking creation, scheduling and booking operations (brief §5.1, §7.3)

| ID | Test | Layer | Pri |
|---|---|---|---|
| BK-01 | New e-mail → user, vehicle and `PENDING` booking created; session cookie set **and** `access_token`, `expires_in`, `account_created: true` returned in the body; the same e-mail/password logs in later (§5.1, D32) | A | P0 |
| BK-02 | Existing e-mail + correct password → the existing user is reused (no second `users` row), booking attached, logged in (D32, FAQ) | A | P0 |
| BK-03 ★ | Existing e-mail + wrong password → 409 `EMAIL_ALREADY_REGISTERED`; nothing is created (no booking, vehicle, slot-counter change or notification) (D32) | A | P0 |
| BK-04 | A logged-in customer books without a password; the booking belongs to the session user (D32) | A | P0 |
| BK-05 | Optional phone is saved to `users.phone` only when it is empty; an existing phone is never overwritten (D33) | A | P1 |
| BK-06 | Zero services, an inactive service or another shop's service → 422 `VALIDATION_ERROR`; several services + free-text notes accepted (§5.1, D34) | A | P0 |
| BK-07 | Service name and base price are snapshotted in `booking_services`; later catalogue edits leave existing bookings unchanged (D34) | A | P0 |
| BK-08 | 422 `INVALID_SLOT` for each case: off-grid start, in the past, outside working hours, ends after closing, closed weekday, beyond 30 days (frozen clock; parametrized) (D37) | A | P0 |
| BK-09 | Capacity: with `slot_capacity = 2`, a third booking for the same slot → 409 `SLOT_FULL`; other slots unaffected (§5.3, D37) | A | P0 |
| BK-10 | `cancel` and `decline` decrement `slot_counters` so the slot is bookable again; the counter never goes below 0 (D24, D37) | A | P0 |
| BK-11 | Availability returns only on-grid, future, ≤ 30-day slots with `remaining` > 0 for the chosen date; full slots are excluded (§7.3 "only available slots"; D37, D68) | A | P0 |
| BK-12 | Availability is computed in the shop's timezone and serialized as UTC `Z`: a Friday 10:00 PKT slot is `2026-10-16T05:00:00Z` (D38, glossary §9) | A + U | P0 |
| BK-13 | Vehicle reuse: re-booking with `lea 1234` vs `LEA-1234` reuses the customer's vehicle (`registration_key`) and updates its details; another customer with the same plate gets their own vehicle (D35) | A | P0 |
| BK-14 | `reference` matches `^BF-[0-9A-HJKMNP-TV-Z]{6}$` (Crockford alphabet) and is unique; a random reference never starts with `SEED` (reserved for seed data) (glossary §1) | U + A | P0 |
| BK-15 | Booking at an unknown or unlisted shop → 404 `NOT_FOUND` † (spec 08 T01 guard; a shop without an active service: BK-26) | A | P0 |
| BK-16 | Public directory lists only listed shops that have at least one active service (D64), with name, city, rating placeholder ("New" when null) and services; city filter and text search work; pagination envelope (§7.3, D56) | A | P0 |
| BK-17 | Customer dashboard list: only own bookings, each with status and `allowed_actions`; a booking awaiting approval is identifiable (`approve-estimate` present) (§7.3 "pending actions highlighted") | A | P0 |
| BK-18 | Staff booking list filters by one or several statuses and paginates (§7.4 SA) | A | P0 |
| BK-19 | Booking detail returns the event timeline in chronological order — `(created_at, seq)`, D79 — with actor role, from/to and note (§7.3 live timeline, §7.5) | A | P0 |
| BK-20 | Vehicle fields (`VehicleWrite`): `registration_number`, `make`, `model` and `year` required (year within the range spec 03 sets †); `color` and `mileage_km` optional → 422 otherwise (§5.1) | A | P0 |
| BK-21 | `assign-technician` / `assign-parts-person` with a user who is not an active member with the required role in this shop (wrong role, inactive, other shop, unknown) → 422 `MEMBER_NOT_ELIGIBLE` (T04, T12) | A | P0 |
| BK-22 | `decline` and staff `cancel` require `reason` (1–500) → 422 otherwise; customer `cancel` reason optional (T03, T22) | A | P0 |
| BK-23 | `notify-ready` sets `ready_notified_at`, is repeatable and sends `VEHICLE_READY` each time; `complete` by the customer or SA sets `completed_at` (O3, D27, D28, T21) | A | P0 |
| BK-24 | `start-repair` sets `repair_started_at` without changing status and writes an event; a second repair round overwrites it (O2, D25) | A | P0 |
| BK-25 | `reassign-technician` / `reassign-parts-person`: the new assignee must be eligible and different; the draft estimate is kept; the new assignee is notified (O4, O5) | A | P1 |
| BK-26 | Directory hides a shop without an active service (D64): a listed shop with no services, or with every service deactivated, is absent from `GET /api/v1/public/shops` and from the city list; its public detail still answers 200 with `services: []` and `is_bookable: false` (spec 03; D64 amended), whereas an **unlisted** shop's slug → 404 `NOT_FOUND` (D64); `POST /api/v1/bookings` for a listed shop without services → 404 `NOT_FOUND` (spec 08 T01, spec 03 order of checks); it reappears once a service is active again | A | P0 |
| BK-27 | Public routes use the shop slug (D68): `GET /api/v1/public/shops/{shop_slug}` and `…/availability?date=YYYY-MM-DD` answer by slug; an unknown slug, or a shop UUID in that position, → 404; every slot reports its free places as `remaining` (capacity − booked) and no slot object has an `available` key (glossary §1) | A | P0 |
| BK-28 | Mileage snapshot (D65): the wizard's mileage is stored on `bookings.mileage_km` (null when omitted); re-booking the same vehicle with a higher mileage updates the vehicle (D35) but leaves the earlier booking's `mileage_km` unchanged | A | P0 |
| BK-29 | Grid changes blocked by future bookings (D37): while the shop has a future non-cancelled booking, changing `slot_duration_minutes` or `timezone` → 409 `CONFLICT` (the bookings module vetoes `ShopGridChanging`) and nothing changes; once every future booking is cancelled the change succeeds, provided the working hours lie on the new grid (else 422, field code `hours_not_on_grid`, spec 03); capacity and working-hours changes are always allowed and keep existing bookings | A | P0 |
| BK-30 | Midnight-anchored grid (D37): slots start at local midnight + k × `slot_duration_minutes` in the shop's timezone. With 45-minute slots, 09:00 and 18:00 are on the grid (12 × 45 and 24 × 45 minutes) and 09:30 is not; working hours whose opening or closing time is off the grid → 422 `VALIDATION_ERROR` (field code `not_on_grid`, spec 03); the day's last slot ends by closing time | U + A | P0 |
| BK-31 | Timeline order without distinct timestamps (D79): with a frozen `SimulatedClock`, drive a booking through several actions so every event shares one `created_at`; the timeline (BK-19) and the event-chain invariant (§4.5) still follow insert order through `(created_at, seq)`, and `seq` strictly increases | A + I | P0 |
| BK-32 | Booking-creation limits (D69; spec 04 table): anonymous `POST /api/v1/bookings` over the per-IP limit, and a logged-in customer over the per-user limit → 429 `RATE_LIMITED` with `Retry-After`; nothing is created and the slot counter is unchanged | A | P0 |
| BK-33 | D83 `[bookings.md]`: a partial receipt for a `PARTS_ORDERED` booking writes no event and keeps `version`, but `booking.updated` reaches its viewers (server-side `TestClient` sockets) | A | P0; push half P1 (D88) |
| BK-34 | `allowed_actions` of a list item equals the detail's for the same caller, for every role and status reached by `drive_booking_to` `[bookings.md]` | A | P0 |
| BK-35 | `status_changed_at` ignores operations: after `start-repair`, `notify-ready` and an in-place estimate save it still equals the last status change `[bookings.md]` | A | P0 |
| BK-36 | Customer projection: `EDIT_ESTIMATE` and `REASSIGN_*` absent; notes only on `DECLINE`, `CANCEL`, `REJECT_ESTIMATE`; no actor, role or `metadata` keys (complements SEC-12) `[bookings.md]` | A | P0 |
| BK-37 | `GET …/parts`: QC inspector → 403 when the booking is in the queue, 404 when not visible; technician sees it only when assigned `[bookings.md]` | A | P0 |
| BK-38 | `PUT …/estimate` by an SA or the Owner with `inspection_notes` → 422 `not_allowed`; by the technician → saved, no event `[bookings.md]` | A | P0 |
| BK-39 | Concurrent `pick-qc` loser gets `ALREADY_PICKED` naming the picker; the picker's own repeated click gets the same 409 `[bookings.md]` | C | P0 |
| BK-40 | `can_view` and the SQL predicate agree for every role × status × assignment combination (unit + one DB round-trip per role) `[bookings.md]` | U + I | P0 |
| BK-41 | Grid veto counts only future non-cancelled bookings: a past booking or a cancelled future one does not block a duration change (complements BK-29) `[bookings.md]` | A | P0 |
| BK-42 | Generated routes: the staff family has exactly the 20 (22 with P1) slugs and the customer family exactly 4; `POST …/actions/edit-estimate` → 404 `[bookings.md]` | A | P0 |

### EST — estimates (brief §7.4, §7.5; D39–D41)

| ID | Test | Layer | Pri |
|---|---|---|---|
| EST-01 | `start-inspection` creates `DRAFT` v1 only when the booking has no estimate (T05) | A | P0 |
| EST-02 | Technician `PUT …/estimate` in `INSPECTING` replaces v1's lines in place: no new version, no booking event, `bookings.version` unchanged (O1, D30); `inspection_notes` sent with the draft are saved on the booking (D40) | A | P0 |
| EST-03 | An SA edit of a `SUBMITTED` v1 in `ESTIMATE_REVIEW` creates v2 `DRAFT` (author = SA), v1 → `SUPERSEDED`, exactly one event; further SA edits update v2 in place (D39, O1) | A | P0 |
| EST-04 | `send-estimate` marks the latest version `SENT` (`sent_at`, `sent_by_user_id`) and any other non-final version `SUPERSEDED`; with no SA edit, v1 is the one sent (T07) | A | P0 |
| EST-05 ★ | Totals are server-computed with `Decimal`; client-sent totals are ignored; worked example 16,600.00 → 16,100.00 (D40, D41) | U + A | P0 |
| EST-06 | Money serialized as 2-decimal strings (`"16100.00"`); part quantities integers, labour quantities decimals (glossary §9) | A | P0 |
| EST-07 | A `PART` line must reference an active part of the same shop: another shop's, inactive or unknown part → 422 `VALIDATION_ERROR` † (D40) | A | P0 |
| EST-08 | Lines: 1–50; `PART` quantity integer ≥ 1; `LABOUR` description required, quantity 0.01–999.99; `unit_price` a whole-rupee amount ≥ 0 (EST-20) → 422 otherwise (O1) | A | P0 |
| EST-09 | A `PART` line's unit price defaults to `parts.unit_cost` when omitted and can be overridden (D40) | A | P0 |
| EST-10 | Submit or send with zero lines → 422 `ESTIMATE_EMPTY` (T06, T07) | A | P0 |
| EST-11 | Editing outside `INSPECTING` (technician) / `ESTIMATE_REVIEW` (SA, Owner) → 409 `ESTIMATE_LOCKED`, including after send and after approval, and for an Owner or SA during `INSPECTING`: the domain answers `INVALID_TRANSITION` for `EDIT_ESTIMATE` outside the caller's own status, and the **bookings `edit_estimate` use case maps it to `ESTIMATE_LOCKED`** for `PUT …/estimate` (the estimates service also raises `ESTIMATE_LOCKED` itself, as a backstop, for a version that is no longer editable) — never 403 (O1, D39). The domain half exists (`test_state_machine.py`) | U + A | P0 |
| EST-12 | `SENT`, `APPROVED`, `REJECTED`, `SUPERSEDED` versions are immutable at the service layer: attempts raise; lines and totals unchanged (D39) | I | P0 |
| EST-13 | Approval stores `APPROVED`, `decided_at`, `decided_by_user_id`; the customer's view shows the timestamped acceptance (brief §3, T08) | A | P0 |
| EST-14 | Approve or reject with an `estimate_id` that is not the current `SENT` version (superseded, another booking's, unknown) → 409 `STALE_ESTIMATE` † (T08, T09) | A | P0 |
| EST-15 | `revise-estimate` and `return-to-technician` copy the rejected version's lines into a new `DRAFT` (`version + 1`, author = actor); the rejected version is unchanged; the reject reason is stored as `customer_note` (D39, T09–T11) | A | P0 |
| EST-16 | Invariant: at most one version per booking is `DRAFT`, `SUBMITTED` or `SENT` at any time (asserted by `assert_invariants`) | S | P0 |
| EST-17 | `cancel` turns `DRAFT`, `SUBMITTED` and `SENT` versions into `SUPERSEDED`; `APPROVED` / `REJECTED` stay (T22) | A | P0 |
| EST-18 | The estimate editor response shows live availability (on_hand − reserved) for each `PART` line and flags shortages (§7.6, D40) | A | P0 |
| EST-19 | Estimate events carry `{estimate_id, version, grand_total}` metadata (spec 08) | A | P1 |
| EST-20 | Whole rupees (D41): a `unit_price` or part `unit_cost` with paisa (`"900.50"`) → 422 `VALIDATION_ERROR` (field code `not_whole_rupees`, spec 03); each line total is quantity × unit price **rounded half-up** to whole rupees (`1.50 × 999` = 1,498.50 → `"1499.00"`, where banker's rounding would give 1,498); estimate totals are sums of the rounded lines; every money value serializes as `".00"`; the DB's `ck_<table>_whole_rupees` rejects paisa even when services are bypassed | U + A + I | P0 |
| EST-21 | Overflow guard: 9 999 × 9 999 999 999 → 422 `VALIDATION_ERROR`, never a 500; nothing written `[estimates.md]` | A | P0 |
| EST-22 | `estimate_revision_in_progress` truth table: nothing sent yet → false; after rejection + revise → true; after send → false; after cancellation → false `[estimates.md]` | A | P0 |
| EST-23 | A `PART` line's description comes from the catalogue at save time; renaming the part later leaves `SENT` / `APPROVED` versions unchanged, and the next draft save shows the new name `[estimates.md]` | A | P0 |
| EST-24 | One 422 lists every invalid line (`lines.0.part_id`, `lines.3.quantity`, …), not just the first `[estimates.md]` | A | P0 |
| EST-25 | `line_total` equals PostgreSQL `round(quantity * unit_price)` and `app.shared.money.round_rupees` for a sample including every `.5` tie `[estimates.md]` | U + I | P0 |
| EST-26 | The booking-status ↔ latest-version table of `modules/estimates.md` §7.1 holds after every scenario step (added to `assert_invariants`) | S | P0 |
| EST-27 | A `SENT` version superseded by a cancellation is absent from the customer detail, the customer estimates list (P1) and the agent view (P2) `[estimates.md]` | A | P0 |

### INV — inventory and procurement (brief §7.6; D42–D45)

| ID | Test | Layer | Pri |
|---|---|---|---|
| INV-01 ★ | Ledger: summing the signed deltas of `stock_movements` reproduces every part's `on_hand` and `reserved`; `booking_parts` quantities match the movements (checked after every scenario and seed test) (D42) | I + S | P0 |
| INV-02 | `order-parts` reserves `min(available, outstanding)` per part and creates a PO (`ORDERED`, `PO-XXXXXX`, linked to the booking) covering exactly the shortages; worked example → filter 10/1, oil 8/1, coil 0/0, PO for 1 coil (T13) | A | P0 |
| INV-03 | `order-parts` when nothing is short → 409 `CONFLICT`; nothing reserved or ordered (T13) | A | P0 |
| INV-04 | `order-parts` with an ordered quantity below a part's shortage → 422 `VALIDATION_ERROR` † (T13) | A | P0 |
| INV-05 | Partial receipt: PO → `PARTIALLY_RECEIVED`; booking stays `PARTS_ORDERED`; received units are reserved for the linked booking while it is `PARTS_ORDERED` (§5.3, D43, T15) | A | P0 |
| INV-06 | Final receipt: PO → `RECEIVED`; once every `booking_parts` row is fully reserved, the booking → `PARTS_READY` in the same transaction with a `RECEIVE_PARTS` event by the receiving Parts Person (T15) | A | P0 |
| INV-07 | Receiving more than a PO item's outstanding quantity, or receiving a `RECEIVED` PO → rejected (422 / 409 †); stock unchanged (D43) | A | P0 |
| INV-08 | General restock PO (no `booking_id`): receipt raises `on_hand` only; no reservation, no booking transition (D43) | A | P0 |
| INV-09 | Receipt on a PO whose booking was cancelled: stock arrives as general stock; the booking stays `CANCELLED` (D24) | A | P0 |
| INV-10 | `mark-parts-ready` reserves every outstanding quantity; any shortage → 409 `INSUFFICIENT_STOCK` with nothing reserved (atomic) (T14) | A | P0 |
| INV-11 | `allocate-parts` consumes: `on_hand −= q`, `reserved −= q`, `consumed_qty = required_qty`, `reserved_qty = 0`; worked example ends at 9/0, 7/0, 0/0 (T16) | A | P0 |
| INV-12 | `allocate-parts` while any row is not fully reserved → 409 `INSUFFICIENT_STOCK` (T16) | A | P0 |
| INV-13 | `cancel` releases every reservation with `RELEASE` movements; worked-example stock returns to 10/0, 8/0, 0/0 (§5.3, §7.6, T22) | A | P0 |
| INV-14 | DB `CHECK`s reject `on_hand < 0`, `reserved < 0` and `reserved > on_hand` even when services are bypassed (D42) | I | P0 |
| INV-15 | Low / out flags: available ≤ `reorder_level` → low; available = 0 → out; available is computed, never stored (D45, glossary §1) | U + A | P0 |
| INV-16 | "Jobs awaiting parts" lists the Parts Person's bookings in `PARTS_PENDING` / `PARTS_ORDERED` / `PARTS_READY` with required vs available per part (§7.4) | A | P0 |
| INV-17 | Parts catalogue: Parts Person and Owner create and edit parts; a duplicate SKU in the same shop → 409 `CONFLICT`; the same SKU in another shop is allowed (D44) | A | P0 |
| INV-18 | Stock operations (create PO, receive, adjust) are Parts Person only; Owner, SA, Technician, QC → 403 `FORBIDDEN` (D44, D16) | A | P0 |
| INV-19 | Two bookings reserve the last unit of a part concurrently → exactly one succeeds, the other gets 409 `INSUFFICIENT_STOCK`; `reserved ≤ on_hand` holds (D30) | C | P0 |
| INV-20 | PO numbers match `^PO-[0-9A-HJKMNP-TV-Z]{6}$` and are unique; a random PO number never starts with `SEED` (D43, glossary §14) | U + A | P0 |
| INV-21 | Stock adjustment (`POST /api/v1/shops/{shop_id}/parts/{part_id}/adjustments`, Parts Person only): opening stock and corrections write one `ADJUST` movement with a reason. P0 by D82: it is the only way to enter opening stock (D44) and to correct drift (D71) (going below `reserved`: INV-25) | A | P0 |
| INV-22 | Inventory table returns SKU, name, on hand, reserved, available, reorder level and cost (§7.4 Parts Person) | A | P0 |
| INV-23 | New parts start at zero (D44): a part created by the Owner or by the Parts Person has `on_hand = 0` and `reserved = 0` (a quantity in the create body → 422, SEC-17); its first stock arrives only through an `ADJUST` (INV-21) or a PO receipt by the Parts Person — the Owner can create the part but never stock it (INV-18) | A | P0 |
| INV-24 | A receipt never reserves for a booking that is not `PARTS_ORDERED` (D43): receive a booking-linked PO after the booking moved on (e.g. `mark-parts-ready` once stock arrived another way) or was cancelled (INV-09) → the stock arrives as general stock; the booking's `booking_parts`, status and events are unchanged and no `RECEIVE_PARTS` event is written | A | P0 |
| INV-25 | An `ADJUST` that would take `on_hand` below `reserved` (or below 0) → 409 `INSUFFICIENT_STOCK`; stock and ledger unchanged (D82) | A | P0 |
| INV-26 | Ledger order and order-free checks (D79): the movements of one action (e.g. `order-parts` reserving the filter and the oil) share one `created_at`; a part's stock history lists rows by `(created_at, seq)` with a running balance that ends at the part's `on_hand` / `reserved`; the INV-01 check gives the same verdict for every permutation of the rows inside one action (checker unit-tested on shuffled input) | U + I | P0 |
| INV-27 | `order-parts` item validation returns `missing_shortage`, `not_short` and `below_shortage` together in one 422; nothing reserved `[inventory.md]` | A | P0 |
| INV-28 | A receipt repeated with the same `expected_received_qty` → 409 `CONCURRENT_UPDATE` while the PO is still `PARTIALLY_RECEIVED`; stock unchanged `[inventory.md]` | A | P0 |
| INV-29 | General PO with an inactive or other-shop part → 422 `invalid_reference`; a `booking_id` in the body → 422 `extra_forbidden` `[inventory.md]` | A | P0 |
| INV-30 | Receipt rows: `RECEIVE` has `booking_id` NULL and the PO id; the following `RESERVE` carries both the booking and the PO id `[inventory.md]` | A + I | P0 |
| INV-31 | `on_order` and `stock_state` on `GET …/parts`, and the `stock_state` filter (`OUT` wins over `LOW`, reorder level 0) `[inventory.md]` | A | P0 |
| INV-32 | QC inspector: `GET …/parts` and `…/bookings/{id}/parts` → 403; estimate reads return `PartStockRef` with null stock fields `[inventory.md]` | A | P0 |
| INV-33 | PO-number collision: an injected generator returns a taken number first; the PO is created with the next one `[inventory.md]` | I | P0 |
| INV-34 | D83: a partial receipt reports its reservations (`ReceiptReservation.reserved`) and the booking's viewers get `booking.updated` (with bookings' `BookingPartsChanged` and notifications; = BK-33) `[inventory.md]` | A | P0; push half P1 (D88) |

### QC — quality check (brief §7.4, §5.3; D46, D47)

| ID | Test | Layer | Pri |
|---|---|---|---|
| QC-01 | `pass-qc` requires the default checklist with every item passed; missing checklist, a missing item or any failed item → 422 `VALIDATION_ERROR` † (D46, T19) | A | P0 |
| QC-02 | `fail-qc` requires `issue_title` (1–120) and `issue_description` (1–2000) → 422 otherwise (T20) | A | P0 |
| QC-03 | `fail-qc` records inspection `FAIL` + one `OPEN` issue, returns the booking to `IN_REPAIR` with the **same** `technician_user_id`, and clears `qc_inspector_user_id` (D47, T20) | A | P0 |
| QC-04 | Only the picker may pass or fail; another QC inspector → 403 `NOT_ASSIGNED` (spec 08 `QC_PICKER`) | A | P0 |
| QC-05 | `send-to-qc` resolves every `OPEN` issue of the booking (`resolved_at`, `resolved_by_user_id`) (D47, T17) | A | P0 |
| QC-06 | Each round creates its own `qc_inspections` row; the history lists every round in order (spec 08 QC loop) | A | P0 |
| QC-07 | The QC queue shows the shop's `QC_PENDING` jobs to every active QC inspector of that shop and to nobody else; another shop's QC inspector → 404 (§7.4) | A | P0 |
| QC-08 | Domain guard: the picker can never be the booking's technician → 403 `FORBIDDEN`. Unit-tested because one role per membership makes it unreachable through the API (D47) | U | P0 |
| QC-09 | The technician sees the QC issues sent back on the job detail (§7.4 Technician) | A | P0 |
| QC-10 | A re-test may be picked by a different QC inspector than the previous round (D47) | A | P0 |
| QC-11 | `pass-qc` keeps `qc_inspector_user_id` (it records who passed the job) and stores the checklist; `fail-qc` stores the checklist too when one is sent, and clears the picker (D46, D47) | A | P0 |
| QC-12 | `GET …/qc/checklist` returns the five items in D46 order with spec 03 labels for every role; non-member → 404 `[qc.md]` | A | P0 |
| QC-13 | Missing, repeated and unknown keys → 422 with `checklist_incomplete` / `enum`; a failed item on pass → `checklist_item_failed` listing every failed item `[qc.md]` | A | P0 |
| QC-14 | `qc_round` and `open_qc_issues_count` through a fail loop: 0 before QC, 1 at `QC_PENDING`, 1 after the fail, 2 at the re-test; open issues 1 → 0 on resend `[qc.md]` | A | P0 |
| QC-15 | `fail-qc` without a checklist stores NULL; with one, the stored JSON has labels in template order and item notes `[qc.md]` | A | P0 |
| QC-16 | After a booking leaves QC, the inspector who inspected it still sees it and its history; another QC inspector gets 404 (D21) `[qc.md]` | A | P0 |
| QC-17 | Repository: inserting a second open inspection for a booking → mapped to 409 `ALREADY_PICKED` (`uq_qc_inspections_one_open_per_booking`, spec 02 §7.5) `[qc.md]` | I | P0 |

### NOT — notifications (brief §5.4; D26)

| ID | Test | Layer | Pri |
|---|---|---|---|
| NOT-01 | Recipient matrix for the 11 "Minimum" types (glossary §6): each firing action creates notifications for exactly the listed recipients, no more and no fewer | A | P0 |
| NOT-02 | The same matrix for the 4 "Extra" types (`BOOKING_CONFIRMED`, `ESTIMATE_RETURNED`, `QC_PASSED`, `BOOKING_CANCELLED`), including the staff-cancel vs customer-cancel split | A | P1 |
| NOT-03 | "SAs of the shop" = all active Service Advisors; inactive SAs get nothing; with no active SA, the Owner receives instead (D26) | A | P0 |
| NOT-04 | Tenant safety: across the worked example, every recipient is the booking's customer or an active member of the booking's shop | S | P0 |
| NOT-05 | The unread count is the caller's own, and it drops after mark-read (§5.4 bell with unread count) | A | P0 |
| NOT-06 | Mark one and mark all as read; marking another user's notification → 404 | A | P0 |
| NOT-07 | Atomicity: a failed or rolled-back action leaves no notification rows (spec 08 step 13) | I | P0 |
| NOT-08 | After commit, `notification.created` reaches the recipient's socket and `booking.updated` reaches the booking's customer and the shop members who can see the booking (glossary §11; the negative cases are NOT-12) — also for parts changes without a status change, e.g. a partial PO receipt reserving stock for it (D83); nothing is pushed for rolled-back actions (D14) | A | P1 |
| NOT-09 | E-mail for `ESTIMATE_SENT` and `VEHICLE_READY` only when `EMAIL_PROVIDER` is `smtp` or `http`; `none` → no attempt; addresses at reserved/test TLDs (`.test`, `.example`, `.invalid`, `.localhost`) are never e-mailed; a provider failure never fails or rolls back the action (D26) | A | P1 |
| NOT-10 | The notification list returns the caller's notifications, newest first, paginated | A | P0 |
| NOT-11 | Every notification row stores `recipient_role` and a server-computed `link` for that recipient (D67): `BOOKING_CANCELLED` sent to the customer links into the customer portal, the same type sent to an SA links to that shop's POS booking page; every link opens for its recipient (no 403 / 404) | A | P0 |
| NOT-12 | `booking.updated` goes only to users who can see the booking (glossary §11, D21): an unassigned technician, another parts person, a QC inspector outside `QC_PENDING` / `QC_IN_PROGRESS` who never inspected it, members of other shops and deactivated members receive nothing. Asserted with server-side `TestClient` sockets (§4.2) | A | P1 (D88) |
| NOT-13 *(bonus)* | Bonus recipients (glossary §6): `CALL_MISSED` for a customer → shop call goes to the SAs of the shop (the Owner if none, D26); for a shop → customer call, to the customer; `AI_TASK_CREATED` goes to the SAs of the shop. Implemented by spec 05's CALL-04, CALL-08 and FD-07; indexed here so the recipient matrix is complete | A | P2 |
| NOT-14 | `link_for` for every `recipient_role` and `AI_TASK_CREATED` (unit); every link passes the `ck_notifications_link_relative` rule `[notifications.md]` | U + I | P0 |
| NOT-15 | Texts: placeholders filled from the event; a 2,000-character cancel reason is cut to the 1,000-character body `[notifications.md]` | U | P0 |
| NOT-16 | Ticket: exactly `sub`, `iat`, `exp = iat + 60`, `typ = "ws"`; used as a Bearer token → 401; no row or server state created `[notifications.md]` | A | P1 (D88) |
| NOT-17 | WebSocket: `ping` → `pong`; unknown frames and invalid JSON are ignored and the socket stays open `[notifications.md]` | A | P1 (D88) |
| NOT-18 | D83: `BookingPartsChanged` pushes `booking.updated` to the booking's viewers only and writes no row; a general-restock receipt pushes nothing (= BK-33 from the notifications side) `[notifications.md]` | A | P1 (D88) |
| NOT-19 | `http` adapter request (mocked transport): URL, Bearer key, JSON body, `Idempotency-Key`; reserved-TLD skip makes no request `[notifications.md]` | U | P1 (e-mail, D26) |
| NOT-20 | A socket whose send fails is removed; the action's HTTP response is unchanged `[notifications.md]` | A | P1 (D88) |
| NOT-21 | Mark-read twice → 204 both times, `read_at` unchanged by the second call `[notifications.md]` | A | P0 |

### RPT — owner overview (brief §7.4 Owner)

| ID | Test | Layer | Pri |
|---|---|---|---|
| RPT-01 | The owner overview for the selected shop returns bookings-by-status counts matching the bookings table, the team list and an inventory summary (low/out counts); no data from other shops | A | P0 |
| RPT-02 | Owner multi-shop summary aggregates only the shops the caller owns | A | P1 |
| RPT-03 | Non-owners cannot open the owner overview → 403 `FORBIDDEN` † | A | P0 |
| RPT-04 | `status_counts` lists all 17 statuses in glossary §3 order, zeros included, and sums to the shop's bookings `[reporting.md]` | A | P0 |
| RPT-05 | Today window in the shop's timezone with a frozen clock at `2026-10-15T19:30:00Z` (16 Oct 00:30 PKT): a booking at `2026-10-16T05:00:00Z` counts, one at `2026-10-15T18:00:00Z` does not; a cancelled one never counts; `completed` follows `completed_at` `[reporting.md]` | A | P0 |
| RPT-06 | Inventory: `stock_value` = Σ on hand × cost over active parts; an inactive part is excluded; `low_stock` order `OUT` first, then available, max 5; `low_stock_count` counts `LOW` + `OUT` `[reporting.md]` | A | P0 |
| RPT-07 | Team: inactive members and the `OWNER` row are listed; `open_jobs` counts technician, parts-person and current-picker roles and ignores `READY_FOR_PICKUP`, `COMPLETED`, `CANCELLED` `[reporting.md]` | A | P0 |
| RPT-08 | Setup flags on a brand-new shop (`has_services`, `has_team`, `has_parts` false; `is_listed` true), then each flips after the matching action `[reporting.md]` | A | P0 |
| RPT-09 | Owner summary (P1, with RPT-02): SA + in-progress + terminal groups partition all statuses (unit); the summary of an owner of two shops who is staff in a third has exactly two rows `[reporting.md]` | U + A | P1 |

### API — conventions, errors, health (brief §9.4; D48–D50)

| ID | Test | Layer | Pri |
|---|---|---|---|
| API-01 ★ | Every 4xx/5xx is `application/problem+json` with the RFC 9457 members of spec 03, `status` equal to the HTTP status, and a glossary §10 `code`. Checked for 401, 403, 404, 409, 422, 500, and 429 once rate limits exist (D49). The one exemption is `/health`'s 503, whose body is `HealthRead` (`{"status": "degraded", "database": "error"}`, D84, spec 03; API-08) | A | P0 |
| API-02 | 422 bodies list every invalid field (location + message) so the UI can show inline errors | A | P0 |
| API-03 | Framework errors are converted too: request-validation errors, unknown routes (404), wrong methods (405) and malformed JSON never return FastAPI's default `{"detail": …}` shape | A | P0 |
| API-04 | Unhandled exceptions → 500 `INTERNAL_ERROR` with a generic `detail`; no stack trace, SQL or exception class in the body; the error is logged | A | P0 |
| API-05 | Collections (lists that can grow without bound) use the pagination envelope `{items, total, limit, offset}`; default `limit` 20; `limit` outside 1–100 or a negative `offset` → 422 `VALIDATION_ERROR` † (glossary §9). Bounded lists — a booking's events, estimate versions, booking parts and QC rounds, the QC checklist, directory cities, a customer's vehicles — return `{items}` without pagination (spec 03) | A | P0 |
| API-06 | Every booking list item and detail, for every endpoint family, includes `allowed_actions` (array of slugs, possibly empty) (D48) | A | P0 |
| API-07 | Conventions on real responses: `snake_case` keys, UUID ids, UTC `Z` timestamps, money as decimal strings (a response walker over scenario responses; glossary §9) | S | P0 |
| API-08 | `GET /health` → 200 `{"status": "ok", "database": "ok"}` when `SELECT 1` succeeds within 2 s, 503 `{"status": "degraded", "database": "error"}` (`HealthRead`, not problem+json) when it does not; both `Cache-Control: no-store` (Railway health check, D13; D84; spec 03). As built: `tests/api/test_health.py` | A | P0 |
| API-09 | The OpenAPI schema is generated, `/docs` renders, and every operation in it declares its response model and documented errors — operations enumerated from the generated document, never `app.routes` (§3.4) (§9.1 optional API docs) | A | P1 |
| API-10 | An unknown action slug → 404 `NOT_FOUND`; any action on a terminal booking → 409 `INVALID_TRANSITION` (D48, spec 08) | A | P0 |
| API-11 | N+1 guard: list endpoints issue the same number of SQL statements for 1 and for 20 items (statement counter on the engine; §8 below) | A | P1 |
| API-12 ★ | Regression test for D62, the project `Email` type: `*@bayflow.test` demo addresses (incl. `smoke+<n>@bayflow.test`) and the brief's `ahmed@mail.com` are accepted on login, owner registration, member creation and the wizard, and stored lower-case (`Fatima.Owner@BayFlow.TEST` → `fatima.owner@bayflow.test`); malformed addresses and other special-use domains (`x@example.invalid`, `x@foo.localhost`) → 422 `VALIDATION_ERROR`; no DNS lookup is made (passes offline); Pydantic's `EmailStr` is never imported (Ruff TID251, §1.1) | U + A | P0 |
| API-13 | Every `/api/*` response — success and error, public and authenticated, including 401 / 404 / 422 / 429 problem responses — carries `Cache-Control: no-store` (D61); one call per operation of the generated OpenAPI document (§3.4) | A | P0 |
### SEED — demo data (brief §7.7; D51, D52)

| ID | Test | Layer | Pri |
|---|---|---|---|
| SEED-01 | The seed succeeds on an empty, migrated database and creates ≥ 6 listed shops, each with a full team (one member per `MembershipRole`), a service catalogue, inventory and working hours | D | P0 |
| SEED-02 ★ | Running the seed again, even with the clock advanced by one day, changes no row count in any table (D51 idempotent) | D | P0 |
| SEED-03 | Every seeded shop has bookable slots (`remaining` > 0, D68) in the next 7 days via the public availability endpoint (§7.7, D37) | D | P0 |
| SEED-04 | Worked-example stock at Lahore Auto Care: oil filter and engine oil 4 L available, ignition coil `on_hand = 0`; prices 900 / 5,200 / 6,500 (D51, glossary §14) | D | P0 |
| SEED-05 | `ahmed@mail.com` does not exist after seeding (D51) | D | P0 |
| SEED-06 | Ayesha's seeded bookings cover several statuses, and each passes `assert_invariants`: an event chain from `PENDING`, one open estimate version, a consistent ledger (D51 "through the service layer") | D | P0 |
| SEED-07 ★ | Every seeded glossary §14 demo account (everyone except Ahmed, who is created live) logs in with `BayFlow@2026` and gets the expected memberships (§7.7; guards D62: `.test` e-mails pass the project `Email` type) | D | P0 |
| SEED-08 | Fatima owns Lahore Auto Care and a second shop (shop-switcher demo, glossary §14) | D | P0 |
| SEED-09 | The pre-deploy entry point (`python -m app.scripts.seed`) seeds only when `SEED_ON_DEPLOY=true` and exits non-zero on failure (D13) | D | P0 |
| SEED-10 ★ | The full worked example (SM-18) passes on a freshly seeded database using the seeded Lahore Auto Care team and a fresh customer e-mail (§7.8) | D + S | P0 |
| SEED-11 | *(spec 11)* Exact snapshot of the seeded row counts listed in spec 11 "Verification" (users, memberships, hours, services, parts, vehicles, POs, sample bookings, booking events); `assert_invariants` holds for every sample booking; each sample booking carries its `mileage_km` (D65); no event has `actor_role` = `SYSTEM` (glossary §2.2); every event's `created_at` equals its scripted `SimulatedClock` time (D63) | D | P0 |
| SEED-12 | *(spec 11)* Lahore Auto Care stock equals spec 11's inventory table; PO statuses `RECEIVED`, `PARTIALLY_RECEIVED`, `ORDERED` present; in every shop each non-zero opening quantity is exactly one `ADJUST` movement by that shop's Parts Person, and no part received stock at creation (D44) | D | P0 |
| SEED-13 | *(spec 11)* Every seeded account (not only the glossary cast) logs in | D | P0 |
| SEED-14 | *(spec 11)* Judge data survives a re-run: an approved BF-SEED02, a consumed oil filter, an adjusted part, changed hours and capacity and a changed service price are all unchanged after seeding again (D60 never touches bookings, inventory, POs or shop settings). Demo-cast accounts and memberships are the exception — the seed repairs them (SEED-19) | D | P0 |
| SEED-15 | *(spec 11)* Resume after a mid-seed failure completes the interrupted booking with the exact event count | D | P1 |
| SEED-16 | *(spec 11)* `make db-reset` (local only) exits with code 2 before dropping anything when `APP_ENV=production` or the `DATABASE_URL` host is not local; the database is untouched (spec 07's guard) | D | P0 |
| SEED-17 | *(spec 11)* Future sample slots stay valid for any seed clock (on the grid, within 30 days, never the worked-example 10:00 slot) | D | P0 |
| SEED-18 | *(spec 11)* Unread counts per demo account match spec 11's first-login table | D | P1 |
| SEED-19 | *(spec 11)* **Demo-cast reconciliation (D60):** deactivate Hamza's membership, change Imran's role to `SERVICE_ADVISOR`, set Sara's `users.is_active` to false and give Usman another password hash; in the same test approve BF-SEED02, consume an oil filter and change Lahore Auto Care's capacity, and add a demo user to a non-seeded shop as a judge would → seed again → Hamza active, Imran `TECHNICIAN`, Sara active, Usman logs in with `BayFlow@2026`; the booking, stock, capacity and the judge's membership are unchanged; a further run writes no row (no `updated_at` changes) | D | P0 |

### WEB — web unit and contract tests

| ID | Test | Layer | Pri |
|---|---|---|---|
| WEB-01 | `formatPKR` (`src/lib/format.ts`) renders PKR in whole rupees with no decimals (D41: `Intl.NumberFormat('en-PK', { style: 'currency', currency: 'PKR' })`) from decimal-string input, with no float drift | W | P0 |
| WEB-02 | `formatDateTime` (and its alias `formatSlot`) renders UTC timestamps in the shop's timezone (`Asia/Karachi`) (D38) | W | P0 |
| WEB-03 | The status label map covers every `BookingStatus` in the generated types with the glossary §3 staff labels (POS), customer-facing labels (portal) and phases | W | P0 |
| WEB-04 | The booking action bar renders exactly the buttons in `allowed_actions`, with no client-side rule logic (D48) | W | P0 |
| WEB-05 | Problem responses map to user messages by `code` (e.g. `SLOT_FULL` → "pick another slot", `EMAIL_ALREADY_REGISTERED` → "log in") | W | P0 |
| WEB-06 | The wizard step schemas (Zod) enforce the same required fields and limits as the API | W | P0 |
| WEB-07 | Contract: the committed `apps/web/src/lib/api/openapi.json` and the generated `schema.d.ts` match the running API (`make gen-api` → no diff); CI fails on drift (D50, D76) | X | P0 |
| WEB-08 | Playwright smoke: book → approve → complete with seeded staff, labour-only, at the smoke-test shop `lyallpur-motors` (§3.8) | L | P1 |
| WEB-09 | Non-booking buttons and navigation entries (team, services, parts, stock, tasks) render only from the current membership's `capabilities`, booking buttons only from `allowed_actions`; no role-name checks in UI rule logic (D66) | W | P0 |
| WEB-10 | Realtime client (D70): fetches a fresh ticket from `GET /api/v1/realtime/ticket` before every connect and reconnect and never reuses one; treats any failed or dropped socket alike (a browser reports 1006, never the server's 1008) and reconnects with backoff; a 401 from the ticket endpoint is handled as an expired session | W | P1 |
| WEB-11 | Polling safety net (D14): the unread count and the current view are polled every 15 s whether or not the socket is connected (fake timers) | W | P0 |

### CON — further concurrency (D30)

| ID | Test | Layer | Pri |
|---|---|---|---|
| CON-01 | Double submit: the same action (`confirm`) sent twice concurrently → one 200, one 409 `INVALID_TRANSITION`; exactly one event; `version` incremented once | C | P0 |
| CON-02 | `cancel` racing `allocate-parts` on one booking → exactly one wins; stock and slot stay consistent (`assert_invariants`); no deadlock | C | P1 |
| CON-03 | Two bookings in one slot cancelled concurrently → `booked_count` drops by exactly 2 and never below 0 | C | P1 |
| CON-04 | A PO receipt racing `cancel` on its linked booking: the receipt locks the booking first (`PurchaseOrderReceiving`, D43; D30 order booking → PO → parts). Either the receipt reserves and the cancel then releases, or the cancel wins and the receipt reserves nothing (INV-24); `assert_invariants` holds; no deadlock | C | P1 |
| CON-05 | A grid change racing a booking creation (D37): the shops service locks the shop row `FOR UPDATE` and publishes `ShopGridChanging`, booking creation holds `FOR SHARE` on it. Either the booking commits first and the change → 409 `CONFLICT`, or the change commits first and the booking is checked against the new grid (422 `INVALID_SLOT` if its slot is off it); never a booking on a grid the shop no longer has | C | P1 |

### DEP — post-deploy checks (live URL; brief §9.1, §10 tip)

| ID | Check | How | Pri |
|---|---|---|---|
| DEP-01 | API `GET /health` → 200 on the Railway URL | scripted (`make smoke`, spec 07) | P0 |
| DEP-02 | The web landing page loads over HTTPS and lists ≥ 6 shops fetched through the `/api/*` rewrite (D7) | scripted (`make smoke`) | P0 |
| DEP-03 | Login on the web origin sets `bf_session` through the rewrite, and the current-user endpoint returns the user (D7 day-1 risk) | scripted (`make smoke`) | P0 |
| DEP-04 | WebSocket: ticket → `wss://<api-host>/api/v1/ws?ticket=…` → `ping` / `pong` (D7, D14, D70). Happy path only: over the network a rejected handshake surfaces as an HTTP 403 (scripts) or close code 1006 (browsers), so close-code checks stay in SEC-33 | scripted | P1 |
| DEP-05 | Production PostgreSQL major version (`SHOW server_version`) equals the local and CI image major (D12) | manual (day 1) | P0 |
| DEP-06 | Production migrations at head after the pre-deploy step (`alembic current` = `alembic heads`) (D13) | manual / deploy log | P0 |
| DEP-07 | Every README demo account (all 6 roles) logs in on the live URL (§9.1). If one fails during judging, re-running the seed (a redeploy) repairs the demo cast (D60) | scripted (`pytest -m live`) | P0 |
| DEP-08 | Worked-example readiness at Lahore Auto Care: ignition coil `on_hand = 0`, oil filter and oil in stock, Friday slots open (brief §6). It detects the accepted drift of D71 (§3.10); it never fixes it | scripted, read-only | P0 |
| DEP-09 | Judge path in two browsers (customer + staff): full worked example incl. the QC-fail loop and the estimate-rejected path, plus one cross-role and one cross-shop attempt (expect 403 / 404) (§7.8) | manual | P0 |
| DEP-10 | Scripted replay of the worked example over HTTP against the live URL, at the smoke-test shop `lyallpur-motors` (§3.6). Never at Lahore Auto Care: each run would consume one oil filter and one engine oil there (DEP-08) | scripted (`pytest -m live`) | P0 |
| DEP-11 | Playwright smoke (= WEB-08) against the live URL | scripted | P1 |
| DEP-12 | Mobile pass: landing, wizard and customer dashboard are usable at phone width (§7.3) | manual | P1 |
| DEP-13 | Swagger `/docs` reachable on the live API (§9.1 optional) | scripted | P1 |
| DEP-14 | Secrets: gitleaks full-history scan clean on the public repo; no `.env` tracked (§9.1) | CI | P0 |
| DEP-15 | No edge caching of API data (D61): through the `/api/*` rewrite, `GET /api/v1/me` for two different demo users returns each user's own data with `Cache-Control: no-store`, and no `/api/*` response reports a Vercel cache `HIT` (`x-vercel-cache`) | scripted (`pytest -m live`) | P0 |

### DEV — local developer scripts (D73)

| ID | Check | How | Pri |
|---|---|---|---|
| DEV-01 | `./start.sh` on a machine with Docker: PostgreSQL starts on host port 5434, migrations run, the seed runs (demo data on a fresh database: `.env.example` sets `SEED_ON_DEPLOY=true` locally; `--seed` forces it, D73), the API listens on 4000 and the web app on 3000 (logs in `logs/`, PIDs in `.run/`); `GET http://localhost:4000/health` → 200 and `http://localhost:3000` → 200 within a timeout. Then `./stop.sh`: both apps and the DB container stop (its volume is kept) and nothing listens on 3000, 4000 or 5434 any more. Windows: the same with `start.bat` / `stop.bat`. **Status:** passed by hand on Linux at the end of PH0 (2026-10-09: start → `/health` 200 and web 200 → stop frees 3000/4000; spec 14) | scripted on Linux/macOS (by hand before each checkpoint, or an optional CI job on `ubuntu-latest`); by hand on Windows | P1 |

### Bonus track index (owned by spec 05; P2, D36)

Listed so spec 15 can trace the bonus decisions to tests; spec 05 §14 holds the rows.

| Decision | Covered by (spec 05 unless noted) |
|---|---|
| D57 calling lifecycle; first accept wins | CALL-01…CALL-03, CALL-09, CALL-11 |
| D77 the AI is dispatched only after the full `AI_RING_TIMEOUT_SECONDS` — even when no SA is online — or once every rung SA declined | CALL-04 (timeout), CALL-06 (all declined), CALL-07 (caller hung up → no AI), CALL-15 (no SA online → still rings the full timeout) |
| D78 non-modal incoming-call panel (up to 3 stacked, Accept / Decline, ring sound, screen-reader announcement) | CALL-16 (vitest web test of spec 05 §9.3 behaviour), plus the scripted demo runs (§14.3) |
| D58 AI Front Desk guardrails | FD-01…FD-12, AG-01…AG-06, spec 04's SEC-36 |
| D69 call-start limit (5 per caller per 10 minutes) | CALL-12 |
| Glossary §6 bonus recipients (`CALL_MISSED` direction split, `AI_TASK_CREATED`) | NOT-13 (= CALL-04, CALL-08, FD-07) |

**Proposed by `modules/calls.md`, numbered here for spec 05 to adopt** (that module spec called them CALL-15…CALL-18; spec 05 already owns CALL-15 and CALL-16, so they become CALL-17…CALL-20; its later proposal keeps its number, CALL-21, which spec 05 §14.1 already lists; all P2):

| ID | Test | Layer | Pri |
|---|---|---|---|
| CALL-17 | D77: a customer → shop call with nobody online rings the full `AI_RING_TIMEOUT_SECONDS`, then dispatches the AI. Same subject as spec 05's CALL-15 — implement it once; this ID only records the module spec's proposal | A | P2 |
| CALL-18 | A socket that connects while a call is `RINGING` for that user receives `call.incoming` again | A | P2 |
| CALL-19 | Accept pushes `call.updated` to every rung user (their pop-ups close) and to the caller | A | P2 |
| CALL-20 | With `CALL_PROVIDER_*` blank: both start routes → 503, nothing stored; the OpenAPI document still lists the 14 call and task operations | A | P2 |
| CALL-21 | Eligibility (spec 05 §3.3): an active SA who was not rung can accept a ringing customer → shop call (200); the Owner of a shop that has an active SA gets 403 on accept and decline; with no active SA the Owner is the eligible callee and may accept | A | P2 |
| FD-13 | A repeated task kind for the same call updates the description and returns 200 `created: false` with no new `AI_TASK_CREATED` | A | P2 |
| FD-14 | An AI leg that ends with an `ai_error` creates exactly one `CALLBACK` task | A | P2 |
| FD-15 | Monthly-minutes formula (unit) and the 503 when it is reached | U + A | P2 |

---

## 6. CI quality gates (GitHub Actions)

The workflow `.github/workflows/ci.yml` is defined in spec 07 (§CI/CD). It runs jobs `api`, `web`, `contract` and `secrets` on every pull request and every push to `main`, with a PostgreSQL service container (`postgres:16`, the same major as Railway, D12). All four are required checks for merging into `main` (branch protection, §2.2 above). Merges to `main` auto-deploy, so `main` stays green and deployable.

This section defines what the gates must enforce. Spec 07 implements them; **as built (2026-10-09) every P0 gate below is in `.github/workflows/ci.yml`**, and the P1 rows are not yet.

| Gate | Job (spec 07) | Command | Blocks merge | Pri |
|---|---|---|---|---|
| Python lint | `api` | `uv run ruff check .` | ✅ | P0 |
| Python format | `api` | `uv run ruff format --check .` | ✅ | P0 |
| Python types | `api` | `uv run mypy app` (strict) | ✅ | P0 |
| Layering contracts | `api` | `uv run lint-imports` | ✅ | P0 |
| Backend tests (U, I, A, C, S, D) with PostgreSQL, coverage reported | `api` | `uv run pytest --cov=app --cov-report=term-missing` | ✅ | P0 |
| Migration round trip + single head | `api` (inside pytest) | `tests/db/test_migrations.py`: `alembic downgrade base` → `upgrade head` → `check` on `bayflow_test` | ✅ | P0 (as built) |
| Models ↔ migrations | `api` | `uv run alembic upgrade head` then `uv run alembic check` on the empty `bayflow` database | ✅ | P0 |
| Web lint (Next 16 no longer lints in `next build`) | `web` | `pnpm lint` = `eslint . --max-warnings 0` (D80) | ✅ | P0 |
| Web types | `web` | `pnpm typecheck` = `next typegen && tsc --noEmit` (D80) | ✅ | P0 |
| Web format | `web` | `pnpm format:check` = `prettier --check .` | ✅ | P0 |
| Web unit tests | `web` | `pnpm test` = `vitest run` | ✅ | P0 |
| Web build | `web` | `pnpm build` | ✅ | P0 |
| OpenAPI drift (WEB-07; D76) | `contract` | `make gen-api` + `git status --porcelain -- apps/web/src/lib/api` (any output fails) | ✅ | P0 |
| Secrets | `secrets` | gitleaks, full history (`pull-requests: read` for PR events) | ✅ | P0 |
| Domain coverage 100 % | `api` | `uv run pytest tests/unit/bookings --cov=app.modules.bookings.domain --cov-branch --cov-fail-under=100` | ✅ | P1 |
| Live smoke | `smoke` workflow | `scripts/smoke.sh` + Playwright against `WEB_URL` | manual trigger | P1 |

The `web` job runs its steps in this order: `pnpm install --frozen-lockfile` → `pnpm lint` → `pnpm typecheck` → `pnpm format:check` → `pnpm test` → `pnpm build`, so the cheapest failure is reported first.

Target: the whole `ci` workflow finishes in under 10 minutes (the jobs run in parallel).

**What spec 07's `ci.yml` must contain** (spec 07 implements it; listed here so the gates can be reviewed; items 1–3 ✅ present as built):
1. **`api` job:** `uv run alembic check` after `pytest` (the drift gate; Alembic ≥ 1.9), and `--cov=app --cov-report=term-missing` on `pytest` (report only). `astral-sh/setup-uv` is pinned to the commit SHA of v10.2.0 (no `@v10` tag exists, spec 07).
2. **`web` and `contract` jobs — pnpm setup.** pnpm is pinned to **10.34.6** by `"packageManager"` in `apps/web/package.json`; there is no root `package.json` (D1, D5, D11), and Vercel supports pnpm 6–10. CI installs it with the official `pnpm/action-setup`, pointed at that file, followed by `actions/setup-node`:

```yaml
      - uses: pnpm/action-setup@v6
        with:
          package_json_file: apps/web/package.json     # reads "packageManager": "pnpm@10.34.6" (no root package.json, D5)
      - uses: actions/setup-node@v7
        with:
          node-version: 24
          cache: pnpm
          cache-dependency-path: apps/web/pnpm-lock.yaml
      - run: pnpm install --frozen-lockfile
        working-directory: apps/web
```

   Do not also pass `version:` to `pnpm/action-setup`; the version comes from `packageManager` only, so the two can never disagree. pnpm's newer `pnpm/setup` action is not an option: it installs pnpm 11+ only (§9).
3. **`contract` job:** `make gen-api`, then `git status --porcelain -- apps/web/src/lib/api`, failing on any output (D76; WEB-07). `git status` also catches a generated file that was never committed, which `git diff --exit-code` would miss.
4. **(P1)** Add the domain coverage gate to `api` (the migration round trip already runs inside pytest, row above). Add a `smoke.yml` workflow:
   - triggered by `workflow_dispatch`, with inputs `web_url` and `api_url`;
   - runs spec 07's `scripts/smoke.sh`, then the Playwright smoke with `WEB_URL`;
   - optionally also triggered by Vercel's `repository_dispatch` event `vercel.deployment.success` (URL in `github.event.client_payload.url`), filtered to production deployments. If Deployment Protection is on, use Vercel's "Protection Bypass for Automation".

**Test database in CI.** The `api` job sets `DATABASE_URL` to the service's `bayflow` database. The test session derives `bayflow_test` from it and creates it (§4.1). The Postgres service syntax (health options, `5432:5432`, `localhost` from the runner) follows GitHub's documentation.

---

## 7. Definition of done (any feature)

A feature is done only when **all** of the following hold:

1. **Spec first.** The relevant spec reflects the behaviour: new decisions are recorded in spec 17, and new names are proposed under "Proposed glossary additions".
2. **Code** follows §1. Ruff, mypy, import-linter, ESLint, Prettier and `tsc` are all clean, with no new ignores without a reason.
3. **Tests.** The feature's catalogue IDs exist and pass, including negative paths (403 / 404 / 409 / 422). New behaviour adds new IDs to this spec's §5 in the same PR.
4. **Reviewed and merged** through a PR, using Conventional Commits, with the AI-assistance attestation filled in (§2.3).
5. **Deployed.** The live URL shows the feature after the auto-deploy, the pre-deploy migration ran, and DEP-01 to DEP-03 still pass.
6. **Demo data present.** The seed makes the feature demonstrable with seeded accounts (brief §7.7, D51), and the SEED tests still pass.
7. **Docs.** README is updated if commands, prerequisites, env vars or demo accounts changed. `.env.example` lists any new variable with a comment (§9.1–§9.3). Swagger shows descriptions for new routes.
8. **UX.** Loading, empty and error states are present, the screen is usable at phone width (§7.3), and buttons come from `allowed_actions`.
9. **Understood.** The author can explain the feature in the judges' review (brief FAQ).

The project-level done is the brief's §7.8 plus the submission checklist in spec 14.

---

## 8. Performance sanity

| Concern | Rule | Check |
|---|---|---|
| N+1 queries | Relationships default to `lazy="raise"`, so an accidental lazy load fails in tests instead of silently querying. Repositories load what each endpoint needs explicitly: `selectinload()` for collections (estimate lines, booking services), `joinedload()` for many-to-one (vehicle, customer) | API-11 (P1): statement counter on `engine.sync_engine` (`before_cursor_execute`) |
| Unbounded lists | Every collection is paginated (`limit` default 20, max 100, glossary §9); bounded lists return `{items}` (spec 03). List endpoints return summaries, not nested collections | API-05 |
| Indexes | Every filter and join used by a list or the availability query is backed by an index from spec 02 (e.g. bookings by `(shop_id, status)` and `(shop_id, slot_start)`, notifications by recipient + read state, `slot_counters` primary key `(shop_id, slot_start)`, the timeline by `(booking_id, created_at, seq)`) | `EXPLAIN` the five busiest queries once in PH7; sequential scans on tiny tables are fine |
| Availability | Slot grid computed in Python (≤ 30 days); **one** range query on `slot_counters` per request | Code review |
| `allowed_actions` | Pure in-memory function of the rule table: no extra queries | SM-19 |
| Polling fallback (D14) | Every 15 s, only the cheap unread-count and first-page queries, both indexed | Code review |
| Budgets (sanity, not gates) | ~10 or fewer SQL statements per request; seed under 60 s inside the pre-deploy step; CI under 10 minutes | Observed in logs and CI |

---

## 9. Tool facts verified (2026-10-09)

| Fact used above | Source |
|---|---|
| `AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`; AsyncClient doesn't trigger lifespan → use asgi-lifespan `LifespanManager` | https://fastapi.tiangolo.com/advanced/async-tests/ · https://github.com/florimondmanca/asgi-lifespan |
| pytest-asyncio options `asyncio_mode` (default `strict`), `asyncio_default_fixture_loop_scope`, `asyncio_default_test_loop_scope` | https://pytest-asyncio.readthedocs.io/en/latest/reference/configuration.html |
| The AnyIO pytest plugin runs all backends by default; override `anyio_backend` | https://anyio.readthedocs.io/en/stable/testing.html |
| `app.dependency_overrides` and reset; WebSocket testing with `TestClient.websocket_connect` | https://fastapi.tiangolo.com/advanced/testing-dependencies/ · https://fastapi.tiangolo.com/advanced/testing-websockets/ |
| AsyncSession not safe across concurrent tasks; `NullPool` across event loops; `expire_on_commit=False`; `lazy="raise"` / `selectinload` | https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html |
| `join_transaction_mode="create_savepoint"` test recipe (considered and rejected, §4.1) | https://docs.sqlalchemy.org/en/20/orm/session_transaction.html |
| SQLAlchemy mypy plugin deprecated, "will be removed in the SQLAlchemy 2.1 release", works only up to mypy 1.10.1, not needed with `Mapped[]` (its page is absent from the 2.1 docs) | https://docs.sqlalchemy.org/en/20/orm/extensions/mypy.html |
| SQLAlchemy 2.1: Python ≥ 3.11; `greenlet` only via the `[asyncio]` extra; 2.1.4 released 2026-10-07 | https://docs.sqlalchemy.org/en/21/changelog/migration_21.html · https://docs.sqlalchemy.org/en/21/changelog/changelog_21.html |
| Pydantic mypy plugin settings | https://pydantic.dev/docs/validation/latest/integrations/dev-tools/mypy/ |
| mypy `strict`, `[[tool.mypy.overrides]]` (mypy 2.4 docs) | https://mypy.readthedocs.io/en/stable/config_file.html |
| Ruff prefixes incl. `FAST001–003`, `PLR0912/0913/0915`, `TID251`; `banned-api` `"name".msg` syntax; mccabe/pylint settings. Config validated locally with ruff 0.16.10 | https://docs.astral.sh/ruff/rules/ · https://docs.astral.sh/ruff/settings/ |
| import-linter: forbidden (wildcards, indirect imports checked by default, external packages need `include_external_packages` and top-level names), protected, layers (`containers` with wildcards, optional `(layer)`), acyclic_siblings; CLI `lint-imports`. Spec 01's `module-internal-layers` and this spec's two proposals validated locally with import-linter 2.15 | https://import-linter.readthedocs.io/en/stable/ |
| GitHub Actions Postgres service (health options, `5432:5432`, `localhost` from the runner) | https://docs.github.com/en/actions/use-cases-and-examples/using-containerized-services/creating-postgresql-service-containers |
| uv in CI: `setup-uv` `enable-cache`, `uv python install`, `uv sync --locked --all-extras --dev` | https://docs.astral.sh/uv/guides/integration/github/ |
| `pnpm/action-setup@v6` reads `packageManager`, with `package_json_file` for subdirectories (here `apps/web/package.json`, D5); `actions/setup-node@v7` caches pnpm (`cache-dependency-path`). pnpm's newer `pnpm/setup` action installs pnpm 11+ only (its README points pnpm ≤ 10 users to `pnpm/action-setup`), so it cannot install the pinned 10.34.6 | https://github.com/pnpm/action-setup · https://github.com/actions/setup-node · https://github.com/pnpm/setup |
| Vercel builds support pnpm 6–10 (the lockfile version narrows it; `packageManager` picks the major without Corepack). `ENABLE_EXPERIMENTAL_COREPACK` needs a root `package.json` and breaks this layout (spec 07) | https://vercel.com/docs/package-managers |
| Next.js 16: `next lint` removed, `next build` no longer lints, `eslint` config option removed; flat config with `eslint-config-next/core-web-vitals`, `/typescript`, `eslint-config-prettier/flat`; ESLint 9 and 10 supported | https://nextjs.org/docs/app/guides/upgrading/version-16 · https://nextjs.org/docs/app/api-reference/config/eslint |
| `next build` fails on type errors; TypeScript 7 lacks the JS compiler API and Next uses the `tsc` CLI for it | https://nextjs.org/docs/app/api-reference/config/typescript |
| typescript-eslint supports TypeScript `>=4.8.4 <6.1.0`; `no-explicit-any` is in `recommended` | https://typescript-eslint.io/users/dependency-versions/ · https://typescript-eslint.io/rules/no-explicit-any/ |
| Vitest setup for Next.js; async Server Components unsupported → E2E | https://nextjs.org/docs/app/guides/testing/vitest |
| Playwright `baseURL` from env, `retries`, `trace: 'on-first-retry'`, projects | https://playwright.dev/docs/test-configuration |
| openapi-typescript CLI incl. `--check` | https://openapi-ts.dev/cli |
| `alembic check` (since 1.9); naming-convention recipe | https://alembic.sqlalchemy.org/en/latest/autogenerate.html · https://alembic.sqlalchemy.org/en/latest/naming.html |
| Alembic 1.20 + SQLAlchemy 2.1.4 autogenerate emits every non-native enum CHECK twice (SQLAlchemy 2.1 keeps the type-bound create rule as a `functools.partial`); the `alembic/env.py` `render_item` hook renders `String(32)` + one named CHECK, and `alembic check` is clean with it (D84; spec 02 §9) | Observed while generating the baseline `23165172278b` (2026-10-09); re-check on every Alembic or SQLAlchemy upgrade |
| RFC 9457 members (`type`, `status`, `title`, `detail`, `instance`), `application/problem+json`, extension members | https://www.rfc-editor.org/rfc/rfc9457.html |
| `pg_stat_activity.wait_event_type = 'Lock'` (`transactionid`, `tuple`); `lock_timeout` / `statement_timeout` settable per database | https://www.postgresql.org/docs/current/monitoring-stats.html · https://www.postgresql.org/docs/current/runtime-config-client.html |
| gitleaks-action v3 (`fetch-depth: 0`; license only for organizations); gitleaks CLI `git`/`dir`, `.gitleaksignore` | https://github.com/gitleaks/gitleaks-action · https://github.com/gitleaks/gitleaks |
| Push protection on by default, blocks secrets pushed to public repos | https://docs.github.com/en/code-security/secret-scanning/introduction/about-push-protection |
| Protected branches available for public repos on GitHub Free; required checks and reviews | https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches |
| PR template locations (`.github/pull_request_template.md`, default branch) | https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/creating-a-pull-request-template-for-your-repository |
| Conventional Commits 1.0.0 | https://www.conventionalcommits.org/en/v1.0.0/ |
| Vercel post-deploy E2E via `repository_dispatch` `vercel.deployment.success` (`client_payload.url`); Protection Bypass for Automation | https://vercel.com/guides/how-can-i-run-end-to-end-tests-after-my-vercel-preview-deployment |
| email-validator rejects special-use domains incl. `test` by default, so Pydantic's `EmailStr` fails on every demo account (reproduced with pydantic 2.14.0 + email-validator 2.3.0). D62's call `validate_email(v, check_deliverability=False, test_environment=True)` accepts `test` / `*.test` and skips DNS. **Reproduced 2026-10-09 with email-validator 2.3.0:** it accepts `fatima.owner@bayflow.test` and `smoke+1700000000@bayflow.test`; still rejects `x@example.invalid`, `x@foo.localhost`, `not-an-email` and `a@b`; and lower-cases only the domain (`Fatima.Owner@BayFlow.TEST` → `Fatima.Owner@bayflow.test`), hence D62's extra lower-casing | https://github.com/JoshData/python-email-validator |
| FastAPI 0.143's `include_router` adds a lazy internal `_IncludedRouter`, so walking `app.routes` misses included routes; enumerate operations from the OpenAPI document (§3.4) | Spec 04 "Verified facts" (executed with fastapi 0.143.0) |
| `TestClient.websocket_connect` raises `WebSocketDisconnect` carrying the app's close code (1008) when the app closes before `accept`; Starlette 1.7's `TestClient` emits a deprecation warning about its `httpx` usage, which the module-scoped filter of §4.2 silences; a browser sees a rejected handshake as close code 1006 (abnormal closure, no close frame) | Reproduced 2026-10-09 with the D11 versions from the local uv cache (FastAPI 0.143.0, Starlette 1.7.0, httpx 0.28.1, pytest 9.1.1; passes under `-W error` only with the filter); RFC 6455 §7.1.5 for 1006 |
| PyJWT's built-in `exp` / `iat` checks use the system time; `options={"verify_exp": False, "verify_iat": False}` keeps `require` and the signature check, so the app compares `iat` / `exp` with its own clock (D63) | Spec 04 "Verified facts" (executed with PyJWT 2.15) |
| Vercel caches external-rewrite responses that carry cache headers by default for projects created on or after 2026-04-06 — the reason for D61's `Cache-Control: no-store` (API-13, DEP-15) | Spec 04 "Verified facts" (Vercel rewrites docs) |
| pytest-cov `--cov`, `--cov-branch`, `--cov-report`, `--cov-fail-under` | https://pytest-cov.readthedocs.io/en/latest/config.html |
| Lock gate and D37 slot algorithm behaviour | Reproduced on `postgres:16-alpine` + asyncpg 0.32.0 in a throwaway container (§3.5) |
| Registry versions: pytest 9.1.1, pytest-asyncio 1.4.0, httpx 0.28.1, asgi-lifespan 2.1.0, import-linter 2.15, mypy 2.4.0, ruff 0.16.10, pytest-cov 7.1.0, sqlalchemy 2.1.4, alembic 1.20.0; vitest 5.0.3, @playwright/test 1.64.0, openapi-typescript 7.13.0, openapi-fetch 0.17.0, eslint 10.12.0 (latest; D11 pins 9.39.x), eslint-config-next 16.4.0, typescript 7.0.2 (latest) / 5.9.3 (D11), typescript-eslint 8.71.1, prettier 3.9.9, pnpm 12.10.1 (latest; Vercel supports ≤ 10; D11 pins 10.34.6); actions/checkout v7.0.1, actions/setup-node v7.1.0, astral-sh/setup-uv v10.2.0, pnpm/action-setup v6.1.0, gitleaks-action v3.0.0 | pypi.org, registry.npmjs.org and GitHub releases, queried 2026-10-09 |

**Not re-verified today, used with care:**
- httpx's cookie jar does not send `Secure` cookies over `http://` (§4.2).
- uvicorn answers a WebSocket handshake that the app closes before `accept` with HTTP 403, so non-browser scripts see a 403 rather than a close code (DEP-04).
- The existence of the TypeScript flags `noUncheckedIndexedAccess`, `noFallthroughCasesInSwitch` and `noImplicitOverride`.
- `[tool.pytest.ini_options]` and `--strict-markers` (long-standing pytest features).
- The ESLint `no-restricted-syntax` selector.
- The Tailwind v4 options of `prettier-plugin-tailwindcss` (configure from its README).

## Dependencies

- **Foundation:** [00-overview.md](00-overview.md), [18-glossary.md](18-glossary.md) (names, error codes §10, env vars §12, naming §13, demo cast §14), [17-decisions.md](17-decisions.md) (D3–D5, D7–D14, D16, D20–D21, D24–D47, D49–D54, D60–D88), [08-booking-state-machine.md](08-booking-state-machine.md) (SM-01…SM-20, check order, worked-example trace).
- **Module specs** whose proposed tests are numbered in §5: [identity](modules/identity.md) (IDN), [shops](modules/shops.md) (SHP), [scheduling](modules/scheduling.md) (SCH), [bookings](modules/bookings.md) (BK-33…42), [estimates](modules/estimates.md) (EST-21…27), [inventory](modules/inventory.md) (INV-27…34), [qc](modules/qc.md) (QC-12…17), [notifications](modules/notifications.md) (NOT-14…21), [reporting](modules/reporting.md) (RPT-04…09), [calls](modules/calls.md) (CALL-17…21, FD-13…15).
- **Sibling specs this one relies on:**
  - 01 — layer table, the import-linter contracts (§Dependency rules), `app.shared.clock` (`Clock`, `SystemClock`, `SimulatedClock`, D63), the test-folder layout.
  - 02 — constraints (incl. whole rupees), indexes, composite FKs, `NAMING_CONVENTION`, action times from the injected clock (D63) and the ledgers' `seq` column (D79).
  - 03 — problem+json members, validation limits, the † codes.
  - 04 — the SEC test catalogue (IDs and expected results), rate limits, security headers, WebSocket ticket rules, the FastAPI route-enumeration finding.
  - 05 — the bonus tests CALL-xx, FD-xx and AG-xx (D75), and the D77 / D78 behaviour.
  - 07 — `ci.yml` (incl. the pnpm steps of §6), Makefile targets (`gen-api`, `db-reset`), the root `start.sh` / `stop.sh` / `start.bat` / `stop.bat` (D73), `scripts/smoke.sh`, docker compose, test-database derivation, env setup.
  - 09 — web folder structure, the API client and the `api:types` script (D76).
  - 10 — screen IDs (QC Inspector screens are QI-xx, D75).
  - 11 — seed contents, the demo-cast reconciliation (D60) and SEED-11…SEED-19.
- **Used by:** [14-roadmap.md](14-roadmap.md) (phase exit criteria cite test IDs), 15 (requirement → spec → test), 16 (risks), the README "How to run tests" section.

## Open questions

1. ✅ Resolved by D62: **Demo e-mails at `.test`.** One project `Email` type (`app.shared.email`: `validate_email(value, check_deliverability=False, test_environment=True)`, then lower-cased) replaces Pydantic's `EmailStr`, whose default rejects the special-use `test` domain. API-12 is its regression test (behaviour reproduced again on 2026-10-09, §9), and Ruff bans the `EmailStr` import (§1.1).
2. ✅ Resolved by spec 03 (draft, its "spec 12 † codes" row): **† codes.** BK-15 404; BK-20 year 1900 … current year + 1; EST-07 422; EST-14 409 `STALE_ESTIMATE`; INV-04 422; INV-07 422 `exceeds_outstanding` and 409 `CONFLICT` (already `RECEIVED`); QC-01 422; RPT-03 403; API-05 422. The newer rows follow spec 03 too: BK-26 (public detail 200 with `is_bookable: false`; booking 404), BK-29 / BK-30 (`hours_not_on_grid`, `not_on_grid`), EST-20 (`not_whole_rupees`).
3. ✅ Resolved by D1, D5 and D11: **pnpm vs the CI action.** pnpm 10.34.6 is pinned by `packageManager` in `apps/web/package.json` (there is no root `package.json`); CI installs it with the official `pnpm/action-setup` + `actions/setup-node` (§6). Spec 07's `web` and `contract` jobs use the same steps.
4. **Scripted live checks use a non-demo shop.**
   - ✅ Resolved: spec 11 designates **Lyallpur Motors** (`lyallpur-motors`, Faisalabad) as the smoke-test shop; spec 07's smoke script, DEP-10 and WEB-08 book only there, so automation never touches Lahore Auto Care's worked-example stock.
   - ✅ Resolved by D71: the seed never restores stock or slots that rehearsals or judges used up (D51; D60 repairs accounts and memberships only). This is accepted drift, kept as a documented limitation (§3.10): DEP-08 detects it, and the judge notes say how to continue (pick another slot; Usman adjusts stock, INV-21). `make db-reset` stays local-only and refuses with exit code 2 when `APP_ENV=production` or the `DATABASE_URL` host is not local (SEED-16).
5. ✅ Resolved by D12: **CI Postgres image.** PostgreSQL 16 everywhere (Railway, local Docker, CI `postgres:16`); DEP-05 re-checks Railway's major on day 1.
6. **Rate limits in tests.** Spec 04 keeps the limits as constants in `app.core.security`, not env vars. Tests need one seam to raise them (a test-settings override) plus a reset of the in-memory storage after each test (§4.2); SEC-27 and SEC-49 use the real thresholds. D69 fixes which endpoints are limited and that per-account limits are primary; spec 04 should name the seam. *Half done as built:* the reset exists (`reset_rate_limits()`, autouse fixture); the raise seam is still open and is needed with the first rate-limited route (PH1).
7. ✅ Resolved by D75: **ID collisions across specs.** QC Inspector screens are QI-xx (QC-xx stays this spec's QC test prefix), AI Front Desk tests are FD-xx (AI-xx stays spec 13's backlog prefix), and roadmap phases are PH0…PH10 (P0–P3 stay D36 priorities).
8. ✅ Resolved by D76: **Type-generation naming.** The schema is exported to `apps/web/src/lib/api/openapi.json`, the web script `api:types` writes `schema.d.ts`, `make gen-api` runs both, and CI fails on drift (WEB-07, now P0).
9. ✅ Resolved by D11: **Toolchain pins.** TypeScript 5.9.3, ESLint 9.39.x and `sqlalchemy[asyncio]` are recorded in D11 (§1.1, §1.2).
10. **Proposals to merge.**
    - ✅ Spec 04 adopted SEC-44…SEC-47 and added SEC-48…SEC-50; SEC-32 now carries D61's `no-store` for every `/api/*` response and SEC-33 the glossary §11 fan-out rule. ✅ SEC-27 now also covers booking creation (cross-referencing BK-32).
    - ✅ Into spec 01: the `thin-routers` and `seed-through-services` contracts (now in spec 01 and `apps/api/pyproject.toml`, KEPT); `SimulatedClock`'s test-facing `step` / `set` / `advance` (§4.4) — as built in `app.shared.clock` (D84), with `use_clock()` / `set_clock()` to install it.
    - ✅ Module specs' proposed tests numbered in §5 (2026-10-09): IDN-01…06, SHP-01…10, SCH-01…07, BK-33…42, EST-21…27, INV-27…34, QC-12…17, NOT-14…21, RPT-04…09, CALL-17…21, FD-13…15. ✅ **For spec 05:** done — spec 05 §14.1 adopts CALL-17…20 and FD-13…15 and lists CALL-21; CALL-17 repeats CALL-15's subject (D77), so one implementation serves both.
    - ✅ Done in spec 05: CALL-15 (D77's empty rung set) and CALL-16 (D78's non-modal panel); the rest of the bonus index (§5) already maps to its rows.
    - ✅ Spec 11 proposed SEED-11…SEED-19; this spec adopted them with those numbers.

## Proposed glossary additions

| Kind | Name | Meaning |
|---|---|---|
| Clock classes | `Clock`, `SystemClock`, `SimulatedClock` | ✅ merged (glossary §1 "Clock", §7 `app.shared.clock`; D63). Tests use a frozen or stepping `SimulatedClock` (§4.4); no separate test clock classes |
| ID prefixes `PH`, `QI`, `FD` | Roadmap phases, QC Inspector screens, AI Front Desk tests | ✅ decided by D75 (glossary change log) |
| Database | `<db>_test` (e.g. `bayflow_test`) | Test database derived from `DATABASE_URL` (§4.1) — *pending* |
| Test ID prefixes | `SM` (spec 08), `SEC` (spec 04), `IDN`, `SHP`, `SCH` (new: module-spec proposals), `BK`, `EST`, `INV`, `QC`, `NOT`, `RPT`, `API`, `SEED` (shared with spec 11), `WEB`, `CON`, `DEP`, `DEV` (new: D73 local scripts); spec 05's `CALL`, `FD`, `AG` | Test catalogue groups (this spec §5) — *pending* |
| pytest markers | `db`, `concurrency`, `scenario`, `seed`, `slow`, `live` | §4.2 — *pending* |
| Test helpers | `SimulatedClock` test API (`step`, `set`, `advance`); fixtures `clock`, `as_user`; builders `make_*`, `drive_booking_to`; `assert_problem`, `assert_invariants`; `hold_row_lock`, `wait_for_lock_waiters` | §4 — *pending* |
| Workflow | `smoke` (`.github/workflows/smoke.yml`, P1) | §6 — *pending* |
| import-linter contract ids | `thin-routers`, `seed-through-services` (adopted by spec 01 and `pyproject.toml`) | §1.1 — glossary entry *pending* |
| Live-check inputs | `WEB_URL`, `API_URL` (spec 07's `scripts/smoke.sh` inputs; reused by Playwright and `pytest -m live`) | §3.10 — *pending* |
| Commit scopes | glossary §7 module names + `web`, `api`, `infra`, `ci`, `seed`, `specs`, `deps` | §1.4 — *pending* |
