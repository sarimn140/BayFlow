# 07 — Deployment & Docs

**Status:** Draft

## Purpose

Step-by-step playbook for running BayFlow **live** (Vercel + Railway) and **locally** (Docker Compose or native uv + pnpm), plus everything the brief's submission rules ask for (§9): the CI/CD pipeline, the complete environment-variable inventory, the full root `.env.example`, the README outline, repository standards, a post-deploy smoke test and the day-1 verification checklist.

Brief §10 gives "Deployment and docs" 10 % ("Live URL works; README and .env.example let a stranger run it in minutes") and warns: "deploy early and keep deploying". Names follow [18-glossary.md](18-glossary.md); decisions D5–D14, D26, D60–D62, D68, D73, D76, D80, D81, D84 (the as-built backend), D85 (placeholder secrets) and D88 (realtime is P1) in [17-decisions.md](17-decisions.md) are binding; the system shape is in [01-architecture.md](01-architecture.md); endpoint paths and field names come from [03-api-contracts.md](03-api-contracts.md). Platform facts were checked against official documentation on 2026-10-09 (URL next to each claim); anything not verified is marked **(unverified)**.

## Hosts overview

| Component | Host | Plan / cost | Runs as | Public URL | Notes |
|---|---|---|---|---|---|
| Web — `apps/web` (Next.js 16) | Vercel | Hobby: free, personal / non-commercial use only ([Vercel Hobby](https://vercel.com/docs/plans/hobby)) | Vercel's Next.js build | `https://<project>.vercel.app` — **the live URL** in the README | `/api/*` is rewritten to the API (D7). Keep the repo **public**: Hobby cannot deploy private repositories owned by a GitHub organization ([Vercel community](https://community.vercel.com/t/why-cant-hobby-accounts-deploy-from-organizations/10015)) |
| API — `apps/api` (FastAPI) | Railway | Hobby: $5/month including $5 of usage ([Railway plans](https://docs.railway.com/pricing/plans)) | Dockerfile; uvicorn, **1 worker, 1 replica** (D14) | `https://<api>.up.railway.app` (`/docs`, `/health`, WebSocket — P1, D88) | Browsers reach it directly only for the WebSocket (D7) |
| PostgreSQL 16 | Railway (same project) | included in Hobby usage | Railway PostgreSQL template; its image is built from `railwayapp-templates/postgres-ssl`, whose `:latest` tag currently points to PostgreSQL 16 ([Railway PostgreSQL](https://docs.railway.com/guides/postgresql), [image README](https://github.com/railwayapp-templates/postgres-ssl)) | none | Private network only |
| AI agent — `apps/agent` *(bonus)* | Railway (same project) | included in Hobby usage | Dockerfile; LiveKit Agents worker | none | Outbound connections only |
| Calls + agent media *(bonus)* | LiveKit Cloud | Build plan, free (D57) | managed | `wss://<project>.livekit.cloud` | Spec 05 |

### Deploy flow at a glance

```
git push origin main
 ├─► GitHub Actions  .github/workflows/ci.yml   (api · web · contract · secrets)
 │      └─ all green ─► Railway "Wait for CI" releases the build:
 │                       docker build → pre-deploy (migrate + seed) → start → GET /health 2xx → traffic switch
 └─► Vercel Git integration (no CI gate): next build (rewrites baked with API_BASE_URL) → production alias
```

Railway's **Wait for CI** keeps a deployment `WAITING` until GitHub workflows finish, skips it if one fails, and requires a workflow triggered on `push` to `main` ([Railway GitHub autodeploys](https://docs.railway.com/deployments/github-autodeploys)). Vercel deploys every push (previews) and `main` (production) automatically ([Vercel for GitHub](https://vercel.com/docs/git/vercel-for-github)).

## Railway setup (API, PostgreSQL, bonus agent)

### 1. Project

1. Create a Railway project named `bayflow` on the Hobby plan.
2. Pick **one region for every service** (API, Postgres, agent) — the closest to Pakistan that your workspace offers (region list and latency **(unverified)**).
3. Railway services sleep only when **Serverless** is enabled ([app sleeping](https://docs.railway.com/reference/app-sleeping)); leave it **off** for every service so judges never hit a cold start and WebSockets stay up.

### 2. PostgreSQL service

1. **+ New → Database → PostgreSQL.** Keep the service name `Postgres` (the reference variable below uses it).
2. It exposes `DATABASE_URL`, `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`, and `DATABASE_PUBLIC_URL` only when public access is enabled ([Railway PostgreSQL](https://docs.railway.com/guides/postgresql)). Railway recommends wiring services with the private variables such as `DATABASE_URL` ([best practices](https://docs.railway.com/overview/best-practices)).
3. Do **not** enable the public TCP proxy except briefly for debugging.
4. Day 1: note the image tag under the service's source settings and keep `docker-compose.yml` and CI on the same major version (D12, checklist below).

### 3. API service

**+ New → GitHub Repo →** select the BayFlow repo, rename the service to **`api`** (its private hostname becomes `api.railway.internal`), then in *Settings*:

| Setting | Value | Why / source |
|---|---|---|
| Root Directory | `/apps/api` | Isolated monorepo: each service gets its own root directory ([monorepo guide](https://docs.railway.com/guides/monorepo)) |
| Builder | Dockerfile (auto) | Railway uses a file named exactly `Dockerfile` at the root of the source directory; `RAILWAY_DOCKERFILE_PATH` is only needed for another name or location ([Dockerfiles](https://docs.railway.com/guides/dockerfiles)) |
| Railway config file | `/apps/api/railway.json` | The config file does **not** follow the Root Directory; its absolute path must be given (monorepo guide) |
| Watch paths | `/apps/api/**` | Gitignore-style patterns evaluated from the repo root even when a Root Directory is set ([build configuration](https://docs.railway.com/builds/build-configuration)) |
| Branch / Wait for CI | `main` / **on** | See deploy flow above |
| Custom Start Command | **none** — use the Dockerfile `CMD` | With Dockerfile deploys Railway runs a start command in exec form, without variable expansion, unless wrapped in `/bin/sh -c` ([start command](https://docs.railway.com/deployments/start-command)); the `CMD` already handles `${PORT}` |
| Replicas | **1** | In-memory WebSocket hub (D14) |
| Serverless | off | Above |

**Build-time secrets:** Railway exposes service variables to a Dockerfile build only when the Dockerfile declares them with `ARG` (Dockerfiles guide). The API Dockerfile declares none, so no secret is baked into an image layer.

### 4. API variables

Set in *api → Variables* (use **sealed** variables for secrets: their values reach builds and deployments but are never shown in the UI or API — [variables](https://docs.railway.com/guides/variables)).

| Variable | Value on Railway |
|---|---|
| `APP_ENV` | `production` |
| `PORT` | `4000` — set explicitly so the health check, the public domain's target port and the private URL all agree; Railway uses `PORT` for health checks ([healthchecks](https://docs.railway.com/reference/healthchecks)) |
| `CLIENT_URL` | `https://<project>.vercel.app` (the production domain) |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` — reference-variable syntax `${{SERVICE_NAME.VAR}}` (variables guide) |
| `JWT_SECRET` | 48+ random characters, sealed — the API refuses to start in production with a value shorter than 32 bytes or **containing** a placeholder marker (`change-me`, `replace-me`, `dev-only`, `placeholder`; D85) |
| `JWT_EXPIRES_IN` | `7d` |
| `COOKIE_SECURE` | `true` — required: production refuses `false`, which is the code default for plain-HTTP localhost |
| `LOG_LEVEL` | `INFO` |
| `SEED_ON_DEPLOY` | `true` — every deploy re-runs the idempotent seed, which also repairs the demo cast (D13, D51, D60) |
| `EMAIL_PROVIDER` | `http` once an HTTPS e-mail API account exists (P1 extra), otherwise `none`. Never `smtp` here: SMTP is available only on Railway's Pro plan and above; Free, Trial and Hobby must use transactional e-mail services with HTTPS APIs ([outbound networking](https://docs.railway.com/networking/outbound-networking)) (D26) |
| `EMAIL_API_KEY` | the e-mail service's API key, sealed (only with `EMAIL_PROVIDER=http`) |
| `SMTP_FROM` | the sender for `http` too: an address on a domain the e-mail service has verified |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` | leave **blank** (unused on Railway) |
| Bonus: `CALL_PROVIDER_URL`, `CALL_PROVIDER_API_KEY`, `CALL_PROVIDER_API_SECRET`, `LLM_API_KEY`, `AGENT_SERVICE_TOKEN` | Railway **shared variables** referenced from both `api` and `agent`: `${{ shared.AGENT_SERVICE_TOKEN }}` etc. (variables guide) |
| Bonus: `AI_RING_TIMEOUT_SECONDS`, `AI_DAILY_CALL_CAP`, `CALL_MONTHLY_MINUTES_CAP` | `20`, `100`, `4000` (spec 05 defaults; caps stay below the provider's hard limits) |

### 5. Networking

- *Settings → Networking → Generate Domain.* When the app listens on one port Railway detects it as the domain's target port ([domains](https://docs.railway.com/networking/domains/working-with-domains)); confirm it shows `4000`.
- Private DNS: `<service>.railway.internal`; private networking works at runtime only, not during the build ([how private networking works](https://docs.railway.com/networking/private-networking/how-it-works)). Environments created after 2025-10-16 resolve private names to IPv4 **and** IPv6, so uvicorn's `--host 0.0.0.0` is reachable; a legacy IPv6-only environment would need `--host ::` (same page; uvicorn accepts IPv6 hosts — [uvicorn settings](https://github.com/encode/uvicorn/blob/master/docs/settings.md)).
- Railway's edge terminates TLS and adds `X-Real-IP`, `X-Forwarded-Proto` (always `https`) and `X-Forwarded-Host`; WebSockets are exempt from Railway's HTTP duration and idle limits ([specs & limits](https://docs.railway.com/networking/public-networking/specs-and-limits)). uvicorn trusts forwarded headers only from `--forwarded-allow-ips` (default `127.0.0.1`/`::1`, uvicorn settings), so the `CMD` passes `--forwarded-allow-ips='*'` — the container is reachable only through Railway's proxy and private network.

### 6. Pre-deploy: migrations and seed (D13)

*Settings → Deploy → Pre-deploy Command* (also in `railway.json` below):

```
/bin/sh -c "alembic upgrade head && python -m app.scripts.seed"
```

- **Why the wrapper (D13):** the command chains two commands with `&&`. For Dockerfile deployments Railway runs commands in **exec form**, which neither expands variables nor interprets shell operators, and its docs wrap such commands in `/bin/sh -c "…"` ([start command](https://docs.railway.com/deployments/start-command)). For `preDeployCommand` specifically, the accepted answer in a Railway Central Station thread (2026-04-28) gives the same fix for Dockerfile builds: wrap the chain in `/bin/sh -c` or call a script ([thread](https://station.railway.com/questions/pre-deploy-command-parsing-of-develop-71b60872)). The wrapper works whether Railway shell-evaluates the string or splits it into exec arguments. The command is exactly D13's — the dashboard field, `railway.json` and the Compose `migrate` service all use the same string.
- **Behaviour** ([pre-deploy command](https://docs.railway.com/deployments/pre-deploy-command)): runs between build and deploy, in a separate container from the app, inside the private network with the app's variables; volumes are not mounted and filesystem changes are not kept; a non-zero exit is not retried and the deployment does not proceed. There is no time limit by default; set *Pre-deploy Timeout* (1–3600 s) to **600** so a migration stuck on a lock fails the deploy instead of hanging (on expiry the container is removed and the deployment fails, same page).
- **Seed gating (D13):** `python -m app.scripts.seed` itself logs `seed skipped (SEED_ON_DEPLOY is not true)` and exits `0` **immediately** unless `SEED_ON_DEPLOY=true`; otherwise it runs the idempotent seed through the service layer (D51) and reconciles the demo cast — demo users and memberships active with their canonical roles, demo password hash valid for `BayFlow@2026` — without touching bookings, stock, POs or shop settings created by judges (D60). `--force` seeds regardless of the flag (used by `make seed` and by `./start.sh --seed` / `start.bat --seed`, D73). Production never relies on a default: Railway sets `SEED_ON_DEPLOY` explicitly on the `api` service (§4). As built (2026-10-09) the script implements the gate and `--force` and exits non-zero on any failure; with the gate open it logs `no seed data defined yet`, because the demo data is created through the module services, which arrive from PH1 (spec 11, spec 14).
- **Migrations must be backward compatible.** The pre-deploy step migrates the database while the **previous** deployment is still serving traffic (the switch happens only after the health check). Use expand → deploy → contract: add columns/tables first; drop or rename only in a later deploy, after no running code uses them.

### 7. Health check, restarts, single replica

- Health check path **`/health`** (unversioned, glossary §9). Railway calls it at deploy time until it returns any `2xx`; default timeout 300 s; it uses the `PORT` variable; requests come from host `healthcheck.railway.app`; it is **not** used for continuous monitoring; health checks give zero-downtime switches ([healthchecks](https://docs.railway.com/reference/healthchecks)).
- `/health` returns `200 {"status":"ok","database":"ok"}` after a `SELECT 1` with a 2 s timeout, `503 {"status":"degraded","database":"error"}` otherwise (its one exception to problem+json; D84, `app.core.health`). No auth, no host filtering (so `healthcheck.railway.app` is accepted). Like every response it sends `Cache-Control: no-store` and `X-Request-ID` (spec 03 §1.8, §4.2).
- Restart policy `ON_FAILURE`, max 10 retries.
- **One replica (D14).** A second replica would hold its own in-memory WebSocket hub (P1, D88) and its own in-memory rate-limit counters, so a push would only reach clients connected to the same replica. When a new deployment replaces the old one, open sockets drop; the web client reconnects with backoff and keeps polling every 15 s (D14) — the polling is the P0 path anyway (D88).

### 8. Config as code — `apps/api/railway.json`

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "watchPatterns": ["/apps/api/**"]
  },
  "deploy": {
    "preDeployCommand": "/bin/sh -c \"alembic upgrade head && python -m app.scripts.seed\"",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 300,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

Keys from the [config-as-code reference](https://docs.railway.com/reference/config-as-code) (`build.builder` `RAILPACK` | `DOCKERFILE`, `build.watchPatterns`, `deploy.preDeployCommand`, `deploy.healthcheckPath`, `deploy.healthcheckTimeout`, `deploy.restartPolicyType`, `deploy.restartPolicyMaxRetries`). Configuration in code always overrides the dashboard, and "the settings in the dashboard will not be updated with the settings defined in code"; settings that come from the file carry a file icon on the deployment details page (same page).

**`preDeployCommand` type.** The reference's only example is a one-element array (`["npm run db:migrate"]`), but the published JSON schema accepts **either a string or an array with at most one string** (`"maxItems": 1` — [railway.schema.json](https://railway.com/railway.schema.json), checked 2026-10-09). The array is therefore not an exec-style argv list; both forms carry the whole command as one string. We use the **string** form with the explicit `/bin/sh -c` wrapper — the form the Central Station thread above confirms for chained commands. Day 1: verify that **both** commands ran (checklist #4). `.toml` is equivalent; we use `.json` for its schema.

### 9. Agent service (bonus, spec 05)

- **+ New → GitHub Repo**, name **`agent`**, Root Directory `/apps/agent`, config file `/apps/agent/railway.json`, watch paths `/apps/agent/**`, **no** public domain.
- Variables: the shared `CALL_PROVIDER_URL`, `CALL_PROVIDER_API_KEY`, `CALL_PROVIDER_API_SECRET`, `LLM_API_KEY` (the key of the selected `AI_PROVIDER`), `AGENT_SERVICE_TOKEN`; `AI_PROVIDER` (`openai`, or `gemini` for the D58 fallback); `AI_REALTIME_MODEL` / `AI_SUMMARY_MODEL` only to override the code defaults; `STT_TTS_API_KEY` only if a separate speech provider is used; `PORT=8081`; `LOG_LEVEL=INFO`; `API_INTERNAL_URL=http://${{api.RAILWAY_PRIVATE_DOMAIN}}:${{api.PORT}}` ([private networking](https://docs.railway.com/private-networking)).
- LiveKit agent servers need no inbound ports and expose an optional health endpoint on `http://0.0.0.0:8081/` ([LiveKit deployment](https://docs.livekit.io/agents/ops/deployment/custom/)). `PORT=8081` plus `healthcheckPath: "/"` in `apps/agent/railway.json` lets Railway's deploy-time check hit it (spec 05).
- LiveKit's SDKs read `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` by default (same page); the agent must pass our `CALL_PROVIDER_*` values explicitly (spec 05).

### 10. Plan, cost and limits

- Hobby: $5/month including $5 of usage; memory $10/GB/month, CPU $20/vCPU/month, egress $0.05/GB, billed on actual use ([Railway plans](https://docs.railway.com/pricing/plans)). The API and PostgreSQL at demo load should stay near the included amount **(unverified estimate)**; the always-on agent adds memory — watch *Project → Usage* and stop the agent after judging if needed.
- Outbound SMTP is available only on Pro and above; Free, Trial and Hobby must use transactional e-mail services with HTTPS APIs — the page lists Resend, SendGrid, Mailgun and Postmark ([outbound networking](https://docs.railway.com/networking/outbound-networking)). Hence `EMAIL_PROVIDER=http` in production (D26).

## Vercel setup (web)

### Project settings

| Setting | Value | Source |
|---|---|---|
| Import | **Add New → Project →** the public GitHub repo | [Vercel monorepos](https://vercel.com/docs/monorepos) |
| Framework preset | Next.js (auto-detected) | [configure a build](https://vercel.com/docs/builds/configure-a-build) |
| Root Directory | `apps/web` — the build cannot read files outside it | configure a build |
| Install command | default `pnpm install` (detected from `apps/web/pnpm-lock.yaml`; there is no root `package.json` or workspace, D5) | [package managers](https://vercel.com/docs/package-managers) |
| Package manager version | **pnpm 10** (D1 pins 10.34.6 in `apps/web/package.json` → `"packageManager"`). Vercel reads that field without Corepack: with `lockfileVersion: 9.0` it puts its pnpm 10 first on the `PATH` and logs ``Detected `pnpm-lock.yaml` version 9 generated by pnpm@10.x from package.json#packageManager pnpm@10.34.6`` (day-1 check #12); pnpm 10 then switches itself to 10.34.6 (`manage-package-manager-versions`). **Never set `ENABLE_EXPERIMENTAL_COREPACK`** on this project. The Vercel CLI enables Corepack only from a `packageManager` in the *repository-root* `package.json`, which this repo does not have (D5), so it warns `Could not enable corepack because package.json is missing "packageManager" property`. The install step still finds `packageManager` in `apps/web`, assumes Corepack is in charge and skips its own pnpm selection. The build image's older default pnpm then runs: "Ignoring not compatible lockfile" followed by `ERR_PNPM_META_FETCH_FAIL … Value of "this" must be of type URLSearchParams` (`ERR_INVALID_THIS`) on Node 24. Source: `initCorepack` in the Vercel CLI 62.7.0 build command and `getPathOverrideForPackageManager` in `@vercel/build-utils` 14.20.1 | package managers; [Corepack](https://vercel.com/docs/builds/configure-a-build#corepack) |
| Build command | default (`pnpm build` → `next build`) | configure a build |
| Node.js | 24.x — the default for new projects; also pinned with `"engines": { "node": "24.x" }`, which overrides the dashboard | [Node.js versions](https://vercel.com/docs/functions/runtimes/node-js/node-js-versions) |
| Production branch | `main` | Vercel for GitHub |
| Ignored Build Step | `git diff --quiet "$VERCEL_GIT_PREVIOUS_SHA" HEAD -- .` (optional, below) | [Ignored Build Step](https://vercel.com/kb/guide/how-do-i-use-the-ignored-build-step-field-on-vercel) |

### Environment variables

| Variable | Environments | Value | Notes |
|---|---|---|---|
| `API_BASE_URL` | Production, Preview | `https://<api>.up.railway.app` | Server-only. Read by `next.config.ts` while **building**: rewrites are resolved at build time ([vercel/next.js discussion #33932](https://github.com/vercel/next.js/discussions/33932)), and Vercel applies env changes only to new deployments ([environment variables](https://vercel.com/docs/environment-variables)) — redeploy after changing it |
| `NEXT_PUBLIC_WS_URL` | Production, Preview | `wss://<api>.up.railway.app/api/v1/ws` | Inlined into the browser bundle at `next build` ([Next.js env vars](https://nextjs.org/docs/app/guides/environment-variables)) |
| `NEXT_PUBLIC_CALL_PROVIDER_URL` *(bonus)* | Production, Preview | `wss://<project>.livekit.cloud` | Same build-time rule |

All three are **fixed at build time** on Vercel: after a build the app no longer responds to changes of `NEXT_PUBLIC_*` values (Next.js env-vars guide), and the rewrite destination is baked in, so changing any of them means a redeploy (glossary §12).

### `apps/web/next.config.ts`

```ts
import type { NextConfig } from 'next'

// VERCEL=1 is a Vercel system variable (build and runtime). Rewrites and NEXT_PUBLIC_* values are
// fixed at build time, so a Vercel build without them would ship a broken app (spec 07).
const isVercelBuild = Boolean(process.env.VERCEL)
for (const name of ['API_BASE_URL', 'NEXT_PUBLIC_WS_URL'] as const) {
  if (isVercelBuild && !process.env[name]) {
    throw new Error(`${name} must be set in the Vercel project settings`)
  }
}

/** Where `/api/*` is proxied to (D7). Local dev and CI fall back to the local API on port 4000. */
const apiBaseUrl = (process.env.API_BASE_URL || 'http://localhost:4000').replace(/\/+$/, '')

/** Spec 04 "Security headers (Tier 1 values)" — every path, including the rewritten `/api/*`. */
export const securityHeaders = [
  { key: 'X-Frame-Options', value: 'DENY' },
  // Only directives that cannot break the app; the full CSP is spec 04 Tier 2.
  {
    key: 'Content-Security-Policy',
    value: "frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'",
  },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  // Bonus calling (P2) will need microphone=(self).
  { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
]

const nextConfig: NextConfig = {
  // Minimal Node server for the Docker Compose image only (the Dockerfile sets
  // NEXT_OUTPUT=standalone). Vercel and local `pnpm build` / `pnpm start` use the default output.
  output: process.env.NEXT_OUTPUT === 'standalone' ? 'standalone' : undefined,
  poweredByHeader: false,
  // Tailwind CSS 4 through its Turbopack loader (create-next-app 16.4 default; no PostCSS config).
  turbopack: {
    rules: {
      '*.css': {
        loaders: ['@tailwindcss/turbopack'],
        as: '*.css',
      },
    },
  },
  async headers() {
    return [{ source: '/(.*)', headers: securityHeaders }]
  },
  async rewrites() {
    // Array form = afterFiles: checked after app routes, so nothing may live under app/api/**.
    return [{ source: '/api/:path*', destination: `${apiBaseUrl}/api/:path*` }]
  },
}

export default nextConfig
```

- Syntax: [Next.js 16.4 rewrites](https://nextjs.org/docs/app/api-reference/config/next-config-js/rewrites) ("Rewriting to an external URL", `:path*` wildcard). An array return is applied after filesystem routes and before dynamic routes — the web app must not define `src/app/api/*` routes (spec 01).
- `VERCEL`: [system environment variables](https://vercel.com/docs/environment-variables/system-environment-variables). `output: 'standalone'`: [output option](https://nextjs.org/docs/app/api-reference/config/next-config-js/output) — used **only** when `NEXT_OUTPUT=standalone`, which the web Dockerfile sets; Vercel builds and local `pnpm build` / `pnpm start` keep the default output.
- As built the file also sends spec 04's Tier 1 security headers on every path (`securityHeaders`, unit-tested in `next.config.test.ts`), disables `X-Powered-By` (`poweredByHeader: false`) and loads Tailwind CSS 4 through `@tailwindcss/turbopack` (no PostCSS config). `API_BASE_URL` falls back to `http://localhost:4000` when unset **or empty** (`||`).
- Vercel executes the rewrite as a reverse proxy to an external origin, forwards visitor headers (`x-forwarded-for`, `x-real-ip`, `x-forwarded-host`, `x-forwarded-proto`) and honours upstream `cache-control`, `CDN-Cache-Control` and `Vercel-CDN-Cache-Control` headers: **responses that carry cache headers are cached by default for projects created on or after 2026-04-06** ([Vercel rewrites](https://vercel.com/docs/rewrites)). Our project is new, so the API sends `Cache-Control: no-store` on every `/api/*` response and on `/health`, errors and 500s included (D61, spec 01 middleware, spec 03 §1.8: Starlette's `ServerErrorMiddleware` sits outside user middleware, so the request-context middleware renders unhandled-exception 500s itself, with `no-store` and `X-Request-ID`) — the value Vercel's docs prescribe for content that must never be cached ([Cache-Control headers](https://vercel.com/docs/caching/cache-control-headers)). The smoke test and day-1 check #7 verify it; the fallback is an `apps/web/vercel.json` `headers` entry for `/api/:path*` with `x-vercel-enable-rewrite-caching: 0`, which restores "never cached" for external rewrites (rewrites page). A proxied request must start responding within 120 s ([Vercel changelog](https://vercel.com/changelog/cdn-origin-timeout-increased-to-two-minutes)).

### Preview deployments

- Every push to another branch and every pull request gets a preview URL (Vercel for GitHub). Previews use the **Preview** variables, i.e. the same production API and data: use them for UI review, not for test data.
- Deployment Protection's *Standard Protection* covers every deployment URL **except production domains** ([deployment protection](https://vercel.com/docs/deployment-protection)). Give judges only the production domain.
- The WebSocket `Origin` check accepts only `CLIENT_URL` (spec 04), so previews fall back to 15 s polling — the P0 path anyway (D88).

### Skipping web builds for API-only commits (optional)

Vercel's built-in "skip unaffected projects" needs JavaScript workspaces at the repo root ([monorepos](https://vercel.com/docs/monorepos)), which BayFlow does not use. Use the **Ignored Build Step**: exit code `0` skips, `1` or more builds; Vercel clones with `--depth=10` (Ignored Build Step guide). `VERCEL_GIT_PREVIOUS_SHA` (the last successful deployment of the branch) is exposed when an Ignored Build Step is configured (system env vars page). When that SHA is empty or outside the shallow clone, `git diff` errors and the build runs — the safe direction.

## Dockerfiles

### API — `apps/api/Dockerfile` (Railway and Docker Compose)

Follows the official uv multi-stage pattern: uv copied from its image, `uv sync --locked --no-install-project` for a cached dependency layer, then the project; final image without uv, same base image as the builder, non-root user ([uv Docker guide](https://docs.astral.sh/uv/guides/integration/docker/), [uv-docker-example multistage.Dockerfile](https://github.com/astral-sh/uv-docker-example/blob/main/multistage.Dockerfile)).

```dockerfile
# BayFlow API image (spec 07): Railway and Docker Compose.
# Official uv multi-stage pattern: dependencies in a cached layer, the project after it; the
# runtime image has no uv, uses the same base image as the builder and runs as a non-root user.

# ---- builder: resolve and install dependencies with uv ----
FROM python:3.12-slim-trixie AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.24 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app
# 1) dependencies only: this layer is reused while pyproject.toml / uv.lock are unchanged
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project
# 2) application code
COPY . .
RUN uv sync --locked

# ---- runtime: same base image (the venv's interpreter path must match), no uv, non-root ----
FROM python:3.12-slim-trixie AS runtime
RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot
COPY --from=builder --chown=nonroot:nonroot /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
WORKDIR /app
USER nonroot
EXPOSE 4000
# ONE worker on purpose: the WebSocket hub and the rate-limit counters live in process memory (D14).
# `sh -c` expands ${PORT} (Railway injects it); `exec` hands signals to uvicorn.
# --no-access-log: the API writes its own JSON access line; --no-server-header: spec 04 Tier 1.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-4000} --workers 1 --proxy-headers --forwarded-allow-ips='*' --no-access-log --no-server-header --timeout-graceful-shutdown 10"]
```

- `--workers` would otherwise default to `$WEB_CONCURRENCY` or 1; `--no-access-log` because the API writes its own JSON access log; `--no-server-header` drops uvicorn's `server: uvicorn` header (spec 04 Tier 1; D84); `--app-dir` defaults to the working directory, so `app.main` is importable from `/app` ([uvicorn settings](https://github.com/encode/uvicorn/blob/master/docs/settings.md)). The Alembic async template's `alembic.ini` sets `prepend_sys_path = .`, so `alembic upgrade head` finds `app` from `/app` too.
- **No BuildKit cache mounts:** Railway requires cache-mount IDs prefixed with the service ID (`id=s/<service id>-<target path>`) and forbids variables in them ([Dockerfiles](https://docs.railway.com/guides/dockerfiles)). Plain layers keep one Dockerfile valid for both Railway and Compose.
- The Railway pre-deploy step and the Compose `migrate` service run this same image with a different command.

`apps/api/.dockerignore`:

```
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.import_linter_cache/
.coverage
htmlcov/
tests/
.env
.env.*
```

### Web — `apps/web/Dockerfile` (Docker Compose only)

Vercel builds the web app itself; this image exists so `docker compose up` runs the whole product. Based on the official example ([with-docker](https://github.com/vercel/next.js/tree/canary/examples/with-docker): Node 24 slim, `corepack enable pnpm`, standalone output, user `node`, `node server.js`).

```dockerfile
# BayFlow web — image for `docker compose up` only. Vercel builds the web app itself (spec 07).
# Pattern: official Next.js with-docker example (Node 24 slim, Corepack pnpm, standalone output,
# non-root `node` user, `node server.js`).

FROM node:24-slim AS base
# Corepack installs the pnpm version pinned in package.json ("packageManager").
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    NEXT_TELEMETRY_DISABLED=1
RUN corepack enable pnpm
WORKDIR /app

FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Build-time values: the /api rewrite target and NEXT_PUBLIC_* are fixed during `next build` (D7).
ARG API_BASE_URL=http://api:4000
ARG NEXT_PUBLIC_WS_URL=ws://localhost:4000/api/v1/ws
ARG NEXT_PUBLIC_CALL_PROVIDER_URL=
ENV API_BASE_URL=$API_BASE_URL \
    NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL \
    NEXT_PUBLIC_CALL_PROVIDER_URL=$NEXT_PUBLIC_CALL_PROVIDER_URL \
    NEXT_OUTPUT=standalone
RUN pnpm build

FROM node:24-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    NEXT_TELEMETRY_DISABLED=1
RUN mkdir .next && chown node:node .next
# The standalone server does not copy public/ or .next/static; once copied next to server.js
# it serves them itself.
COPY --from=builder --chown=node:node /app/public ./public
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
```

The standalone server does not copy `public/` or `.next/static/` by default; once copied next to `server.js` it serves them, and `PORT` / `HOSTNAME` choose the bind address ([output option](https://nextjs.org/docs/app/api-reference/config/next-config-js/output)). The `deps` stage also copies `pnpm-workspace.yaml`: in pnpm 10 that file holds `apps/web`'s own settings (`ignoredBuiltDependencies`), not a monorepo workspace (D5). `apps/web/.dockerignore` excludes `node_modules/`, `.next/`, `out/`, `build/`, `coverage/`, `.env*`, `*.tsbuildinfo`, `next-env.d.ts`, debug logs, `.git`, `.vercel`, the Dockerfile and itself.

### Agent — `apps/agent/Dockerfile` (bonus)

Same uv multi-stage pattern as the API; `CMD` per spec 05; no exposed public port (health endpoint 8081 only).

## Local development

### Option A — everything in Docker (the README's one command)

```bash
cp .env.example .env
docker compose up --build
# web: http://localhost:3000    API docs: http://localhost:4000/docs
```

`docker-compose.yml` (repo root):

```yaml
# BayFlow local stack (spec 07 "Local development", D12, D73).
#
#   docker compose up -d --wait db                PostgreSQL only (used by ./start.sh, start.bat, make db-up)
#   docker compose up --build                     everything: db, one-shot migrate + seed, API :4000, web :3000
#   docker compose --profile mail up -d mailpit   optional local inbox: UI http://localhost:8025, SMTP :1025
#   docker compose --profile bonus up --build     adds the bonus AI Front Desk worker (apps/agent)
#
# Data lives in the named volume `pgdata`. `docker compose down`, ./stop.sh and stop.bat keep it;
# `make db-reset` wipes the schema; only `docker compose down -v` deletes the volume.
# The root .env is read automatically for ${...} interpolation (e.g. POSTGRES_HOST_PORT).
name: bayflow

# The root .env (a copy of .env.example) for the Python services. `required: false` (Compose 2.24+)
# keeps `docker compose config` and `docker compose up -d db` working before .env exists.
x-root-env-file: &root-env-file
  - path: .env
    required: false

services:
  db:
    image: postgres:16 # same major version as Railway and CI (D12); Debian-based like Railway's image
    environment:
      POSTGRES_USER: bayflow
      POSTGRES_PASSWORD: bayflow
      POSTGRES_DB: bayflow
    ports:
      - "${POSTGRES_HOST_PORT:-5434}:5432" # host 5434 by default (D73): 5432/5433 are often taken
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      # TCP check (-h 127.0.0.1): on the very first start the image initialises the database with a
      # temporary socket-only server, so a socket check could report "healthy" before the real server
      # accepts TCP connections (and the migrate step would then fail on a slow machine).
      test: ["CMD-SHELL", "pg_isready -h 127.0.0.1 -p 5432 -U bayflow -d bayflow"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 30s

  migrate: # one-shot: the same command as Railway's pre-deploy step (D13)
    build: ./apps/api
    env_file: *root-env-file
    environment:
      DATABASE_URL: postgresql://bayflow:bayflow@db:5432/bayflow
    command: ["/bin/sh", "-c", "alembic upgrade head && python -m app.scripts.seed"]
    depends_on:
      db:
        condition: service_healthy

  api:
    build: ./apps/api
    env_file: *root-env-file
    environment:
      DATABASE_URL: postgresql://bayflow:bayflow@db:5432/bayflow
      PORT: "4000"
    ports:
      - "4000:4000"
    depends_on:
      migrate:
        condition: service_completed_successfully
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:4000/health', timeout=2)"]
      interval: 10s
      timeout: 5s
      retries: 6

  web:
    # No env_file on purpose: the root .env sets PORT=4000 and the standalone server binds to PORT.
    build:
      context: ./apps/web
      args:
        API_BASE_URL: http://api:4000 # server-side rewrite target inside the Compose network
        NEXT_PUBLIC_WS_URL: ws://localhost:4000/api/v1/ws # the browser connects through the published port
        NEXT_PUBLIC_CALL_PROVIDER_URL: ${NEXT_PUBLIC_CALL_PROVIDER_URL:-}
    ports:
      - "3000:3000"
    depends_on:
      api:
        condition: service_healthy

  mailpit: # optional local inbox: EMAIL_PROVIDER=smtp, SMTP_PORT=1025, SMTP_HOST=mailpit (API in Docker) or localhost
    image: axllent/mailpit
    profiles: ["mail"]
    ports:
      - "8025:8025" # web UI
      - "1025:1025" # SMTP

  agent: # bonus AI Front Desk worker (spec 05): docker compose --profile bonus up
    build: ./apps/agent
    profiles: ["bonus"]
    env_file: *root-env-file
    environment:
      API_INTERNAL_URL: http://api:4000
    depends_on:
      api:
        condition: service_healthy

volumes:
  pgdata:
```

- `depends_on` conditions `service_healthy` and `service_completed_successfully` and the `pg_isready` health check follow [Docker's startup-order guide](https://docs.docker.com/compose/how-tos/startup-order/). The check runs over **TCP** (`-h 127.0.0.1`): on the very first start the image initialises the database with a temporary socket-only server, so a socket check could report healthy before the real server accepts TCP connections; `start_period: 30s` covers that initialisation.
- `env_file` uses the long form `- path: .env` with **`required: false`** (the `x-root-env-file` anchor), so `docker compose config` and `docker compose up -d db` work before `.env` exists. That form needs **Docker Compose 2.24 or newer** (README prerequisites); older Compose versions reject the file.
- Values under `environment:` override the same names from `env_file:` ([precedence](https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence/)); the root `.env` is also read automatically for `${…}` interpolation (same page).
- `web` deliberately gets no `env_file`: the root `.env` contains `PORT=4000`, and the standalone server binds to `PORT`.
- Host ports (D73): web `3000`, API `4000`, PostgreSQL `5434` (`POSTGRES_HOST_PORT`, read only by Compose for interpolation from the root `.env`), Mailpit UI `8025` / SMTP `1025`. Inside the Compose network the database is always `db:5432`; on the host it is `localhost:5434`, which is why the root `.env` has `DATABASE_URL=…@localhost:5434/bayflow`. Change both together if 5434 is taken.
- Mailpit: image `axllent/mailpit`, SMTP 1025, UI 8025 ([Mailpit Docker](https://mailpit.axllent.org/docs/install/docker/)). To see e-mails locally set `EMAIL_PROVIDER=smtp`, `SMTP_PORT=1025` and `SMTP_HOST=mailpit` (API in Docker) or `SMTP_HOST=localhost` (native API) (D26). Recipients on reserved TLDs — every demo `.test` address — are skipped even here (D26), so book a local test customer with a normal-looking address such as the brief's `ahmed@mail.com`: Mailpit catches every message and nothing leaves the machine. (Never do that on the live URL, README §2.)

### Option B — native API and web, PostgreSQL in Docker

```bash
cp .env.example .env
make setup        # uv sync (apps/api) + pnpm install (apps/web) + git hooks
./start.sh        # Windows: start.bat — PostgreSQL container → migrations → seed (SEED_ON_DEPLOY) → API :4000 + web :3000
                  # ./start.sh --seed (start.bat --seed) forces the seed whatever SEED_ON_DEPLOY says
./stop.sh         # Windows: stop.bat  — stop API + web, free ports 3000/4000, stop the DB container
```

`make dev` runs the same steps in the foreground (Ctrl+C stops both processes). Without GNU Make (plain Windows) install per app instead: `cd apps/api && uv sync`, `cd apps/web && pnpm install`.

**Root start/stop scripts (D73)** — the owner's conventions: preflight, port cleanup, PID files, Ctrl+C handling. `start.sh` / `stop.sh` are `bash` scripts for Linux and macOS (`*.sh text eol=lf`); `start.bat` / `stop.bat` are `cmd.exe` scripts for Windows (`*.bat text eol=crlf`, see `.gitattributes`). Both pairs do the same:

| Script | Steps |
|---|---|
| `start.sh` / `start.bat` | 1. **Preflight:** checks that `docker` (Compose v2, daemon running), `uv`, Node 24+, `pnpm` and `curl` are available and the checkout is complete; creates `.env` from `.env.example` if missing and loads it (`start.sh` also warns when `DATABASE_URL`'s port differs from `POSTGRES_HOST_PORT`); installs missing dependencies (`uv sync`, `pnpm install`) unless `--no-install`. 2. **Frees ports 3000 and 4000** by running `stop.sh --keep-db --quiet` (`stop.bat --keep-db --quiet`; owner request, D73 amended): stale BayFlow processes are stopped and **any other program listening on 3000/4000 is stopped too and named in the output**; Docker/VM/SSH port forwarders are never killed — then the port stays busy, the stop script names its holder and exits 1, and start stops with a message. 3. `docker compose up -d --wait --wait-timeout 90 db` (host port `POSTGRES_HOST_PORT`, default 5434). 4. In `apps/api`: `uv run alembic upgrade head`, then **always** `uv run python -m app.scripts.seed` (D73, amended) — the seed acts only when `SEED_ON_DEPLOY=true`, which `.env.example` sets for local development, so a fresh database gets the demo cast (D13, D60) and later runs only repair it; with `--seed` the script passes `--force`, which seeds whatever the flag says. 5. Starts the API (`uv run uvicorn app.main:app --host 0.0.0.0 --port 4000 --reload`) and the web app (`pnpm dev` with `PORT=3000`): `start.sh` runs each in its own process group (`setsid`, or `set -m` + `nohup` on macOS) with output in `logs/api.log` / `logs/web.log` and PIDs in **`.run/pids`** (`name pid port` lines) **plus `.run/api.pid` and `.run/web.pid`**; `start.bat` opens two minimized windows titled "BayFlow API" / "BayFlow Web" (output in `logs\*.log`). 6. Waits for `GET http://localhost:4000/health` → 2xx (90 s) and any answer from `http://localhost:3000` (180 s / 120 tries on Windows); on failure it shows the last log lines and runs the stop script. `start.bat` then records the **listening** PIDs in `.run\api.pid` / `.run\web.pid`. 7. Prints the URLs (web, Swagger `/docs`, `/health`, Mailpit when running, PostgreSQL, logs); unless `--detach`, `start.sh` streams both logs with `[api]` / `[web]` prefixes and **Ctrl+C** (or SIGTERM / a closed terminal) runs `./stop.sh`, while `start.bat` waits for a key press and then runs `stop.bat`. Flags: `--detach`, `--seed`, `--no-install`, `--help`. |
| `stop.sh` / `stop.bat` | 1. Sends SIGTERM to the process groups recorded in `.run/pids`, `.run/api.pid` and `.run/web.pid` — only when the PID still runs inside the repo and looks like the service (guarded against PID reuse; `stop.bat` checks for python, uv, uvicorn or node and also closes the "BayFlow API" / "BayFlow Web" windows) — waits up to 10 s, then SIGKILLs stragglers. 2. Stops BayFlow's own Docker `api`/`web` containers if they run (`docker compose up` publishes 3000/4000). 3. **Port backstop:** stops whatever still listens on 4000/3000 — never a Docker/VM/SSH port forwarder (`docker*`, `com.docker*`, `vpnkit`, `rootlesskit`, `slirp4netns`, `gvproxy`, `limactl`, `qemu*`, OrbStack, `ssh`, `sshd`; on Windows `com.docker*`, `wslrelay.exe`, `vpnkit.exe`, `dockerd.exe`, `docker-proxy.exe` and the System process). With `--bayflow-only` only processes running inside this repository are stopped here (`stop.bat`: whose command line contains this folder). 4. **Pattern backstop** (`stop.sh` only): leftover `uvicorn app.main:app`, `next dev` and `next-server` processes of this repo — matched by a fixed-string command line **and** a real server executable (`node`, `next-server*`, `python*`, `uvicorn`, `uv`; never a shell, editor or grep) **and** a working directory inside the repo — and **never** the script itself or one of its ancestors (so the shell or terminal that ran it is safe). 5. Removes the Next.js dev lock (`apps/web/.next/dev`, `apps/web/.next/lock`) and the PID files. 6. `docker compose stop db` unless `--keep-db` (the container stops; the `pgdata` volume and its data are kept). 7. Verifies that 3000 and 4000 are free; otherwise names the holder and exits 1. Flags: `--keep-db`, `--quiet`, `--bayflow-only`, `--help`. No `set -e`: cleanup continues when a step fails; safe to run twice. |

`logs/` and `.run/` are git-ignored. `docker compose down` (or `make down`) also removes the stopped containers; the data volume survives both.

### Makefile (repo root)

Recipes are indented with **tab** characters (GNU Make).

```make
# BayFlow developer commands (GNU Make; spec 07). Run `make` or `make help`.
# Windows without GNU Make: use start.bat / stop.bat, WSL2, or `docker compose up --build`.
SHELL := /bin/bash
.DEFAULT_GOAL := help
LOAD_ENV := set -a; [ -f .env ] && . ./.env; set +a;

.PHONY: help setup up down db-up migrate seed db-reset api web dev test lint fmt gen-api smoke

help: ## List all targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-9s %s\n", $$1, $$2}'

setup: ## First run: create .env, install API + web dependencies, install git hooks
	@[ -f .env ] || cp .env.example .env
	cd apps/api && uv sync
	cd apps/web && pnpm install
	@if [ -f .pre-commit-config.yaml ] && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
	  uvx pre-commit install; \
	else \
	  echo "setup: git hooks skipped (no .pre-commit-config.yaml or not a git repository)"; \
	fi

up: ## Everything in Docker: PostgreSQL, migrate + seed, API :4000, web :3000
	docker compose up --build

down: ## Stop the Docker stack (the database volume is kept)
	docker compose down

db-up: ## Start only PostgreSQL in Docker and wait until it is healthy
	docker compose up -d --wait db

migrate: ## Apply Alembic migrations to DATABASE_URL
	cd apps/api && uv run alembic upgrade head

seed: ## Load the demo data (idempotent; repairs the demo cast)
	cd apps/api && uv run python -m app.scripts.seed --force

db-reset: ## Wipe the LOCAL Docker database, then migrate and seed (refuses production / non-local URLs)
	@app_env="$${APP_ENV:-$$(sed -n 's/^APP_ENV=//p' .env 2>/dev/null | tail -n 1 | tr -d '"')}"; \
	db_url="$${DATABASE_URL:-$$(sed -n 's/^DATABASE_URL=//p' .env 2>/dev/null | tail -n 1 | tr -d '"')}"; \
	if [ "$$app_env" = production ]; then \
	  echo "db-reset refused: APP_ENV=production" >&2; exit 2; fi; \
	case "$$db_url" in \
	  *@localhost:*|*@localhost/*|*@127.0.0.1:*|*@127.0.0.1/*|*@\[::1\]:*|*@\[::1\]/*|*@db:*|*@db/*) ;; \
	  *) echo "db-reset refused: DATABASE_URL is not a local database (localhost, 127.0.0.1, ::1 or db)" >&2; exit 2 ;; \
	esac
	docker compose up -d --wait db
	docker compose exec -T db psql -U bayflow -d bayflow -v ON_ERROR_STOP=1 -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	$(MAKE) migrate seed

api: ## API with auto-reload on http://localhost:4000 (Swagger at /docs)
	cd apps/api && uv run uvicorn app.main:app --reload --port 4000

web: ## Web with hot reload on http://localhost:3000 (reads the root .env)
	$(LOAD_ENV) cd apps/web && PORT=3000 pnpm dev

dev: db-up migrate seed ## PostgreSQL in Docker + API and web locally (Ctrl+C stops both)
	$(MAKE) -j2 api web

test: db-up ## API tests (pytest on real PostgreSQL) + web unit tests (vitest)
	cd apps/api && uv run pytest
	cd apps/web && pnpm test

lint: ## Lint, format check, type check, architecture contracts
	cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run lint-imports
	cd apps/web && pnpm lint && pnpm format:check && pnpm typecheck

fmt: ## Auto-fix lint findings and format all code
	cd apps/api && uv run ruff check --fix . && uv run ruff format .
	cd apps/web && pnpm format

gen-api: ## Regenerate openapi.json (API export), then schema.d.ts (web script api:types) - D76
	cd apps/api && uv run python -m app.scripts.export_openapi ../web/src/lib/api/openapi.json
	cd apps/web && pnpm api:types

smoke: ## Post-deploy smoke test: make smoke WEB_URL=https://... API_URL=https://...
	WEB_URL="$(WEB_URL)" API_URL="$(API_URL)" ./scripts/smoke.sh
```

- `uv run` keeps the virtualenv in sync before running; `uvx` runs a tool such as `pre-commit` without installing it into the project ([uv CLI](https://docs.astral.sh/uv/reference/cli/)). `make setup` installs the git hooks only when `.pre-commit-config.yaml` exists and the folder is a git work tree (otherwise it says so and carries on).
- **`db-reset` guard:** before anything is dropped, the recipe resolves `APP_ENV` and `DATABASE_URL` the way the API does (a real environment variable wins over the root `.env`) and exits with code **2** when `APP_ENV=production` or when `DATABASE_URL` does not point at `localhost`, `127.0.0.1`, `[::1]` or `db` (a missing URL is refused too). The `DROP SCHEMA` itself always runs inside the local Compose `db` container, through `docker compose exec -T` (no TTY, so it also works from scripts) with `psql -v ON_ERROR_STOP=1`; the guard stops the follow-up `migrate` / `seed` from touching a remote database.
- **`gen-api` (D76):** `python -m app.scripts.export_openapi` writes `apps/web/src/lib/api/openapi.json` (its default path; the explicit argument above is the same file) as `app.openapi()` ([FastAPI](https://fastapi.tiangolo.com/how-to/extending-openapi/)) JSON with sorted keys and a trailing newline — `info.version` is a fixed string (never a Git SHA or a date), so the file only changes when the API contract changes. Then the web script `api:types` = `openapi-typescript src/lib/api/openapi.json -o src/lib/api/schema.d.ts` (CLI form `openapi-typescript <schema> -o <file>`, [openapi-ts.dev](https://openapi-ts.dev/introduction)). Both files are committed; CI fails if regenerating changes either (D50, D76).
- `apps/web/package.json` scripts used above: `dev` = `next dev --port 3000`, `build` = `next build`, `start` = `next start --port 3000`, `lint` = `eslint . --max-warnings 0` (D80: a warning fails `make lint` and CI like an error; Next.js 16 removed `next lint`, and `next build` no longer lints — [Next.js 16 upgrade guide](https://nextjs.org/docs/app/guides/upgrading/version-16)), `typecheck` = `next typegen && tsc --noEmit` (D80: route types are generated before type-checking, the form recommended in the [next CLI docs](https://nextjs.org/docs/app/api-reference/cli/next)), `format` / `format:check` = `prettier --write .` / `prettier --check .`, `test` = `vitest run`, `test:watch` = `vitest`, `api:types` (above). `"engines": {"node": "24.x"}` and `"packageManager": "pnpm@10.34.6"` pin the runtime and the package manager (D1, D5). Toolchain pins per D11: TypeScript **5.9.3** and ESLint **9.39.x**, not the npm `latest` majors (7.x / 10.x), because `openapi-typescript` 7.13 requires `typescript ^5.x`, `typescript-eslint` 8.71 requires `<6.1.0`, and the plugins pulled in by `eslint-config-next` 16.4 declare peer `eslint` up to `^9` only. Generated files under `src/lib/api/` are listed in `.prettierignore` and ignored by ESLint.

### How environment files are loaded

There is **one** local configuration file: the root `.env`, copied from `.env.example` (brief §9.2).

| Process | Reads its variables from | Mechanism |
|---|---|---|
| API, Alembic, seed, OpenAPI export (native) | root `.env` | pydantic-settings with `env_file` = the repo-root `.env` **resolved from `app/core/config.py`'s location**, never from the working directory (D84, spec 01), so it does not matter where the command is started; real environment variables win; a missing file is skipped |
| Docker Compose | root `.env` | automatic `${…}` interpolation (incl. the compose-only `POSTGRES_HOST_PORT`); `env_file` (`- path: .env`, `required: false`; Compose ≥ 2.24) for `migrate`, `api`, `agent`; `environment:` overrides (`DATABASE_URL` host `db`, `PORT`) win over `env_file` |
| `start.sh` / `start.bat` (D73) | root `.env` | the API reads it through pydantic-settings as above; both scripts also load it into their own environment, so the web process inherits it, with `PORT=3000` (`start.sh`: `set -a; . ./.env; set +a`, through a CR-free copy if the file has Windows line endings; `start.bat`: one `set` per `KEY=value` line) |
| Web via `make web` / `make dev` | root `.env` | the Makefile exports it into the process (`set -a; . ./.env; set +a`). Next.js looks up `process.env` **first**, then `.env.$(NODE_ENV).local`, `.env.local`, `.env.$(NODE_ENV)`, `.env` in `apps/web` ([Next.js env vars](https://nextjs.org/docs/app/guides/environment-variables)) |
| Web via `pnpm dev` inside `apps/web` | `apps/web/.env.local` (optional, git-ignored) | Next.js's own loading; without it the dev defaults in `next.config.ts` and the realtime client (`http://localhost:4000`, `ws://localhost:4000/api/v1/ws`) apply |
| Web on Vercel | Vercel project variables | build time (rewrites, `NEXT_PUBLIC_*`) and runtime |
| API / agent on Railway | Railway service and shared variables | no `.env` file exists in the images (`.dockerignore`) |

**Port collision:** the root `.env` sets `PORT=4000` for the API, and `next dev` also honours `PORT` ("Default: 3000, env: PORT" — next CLI docs). The `web` target and both start scripts therefore set `PORT=3000`, and the `dev` script passes `--port 3000`.

**`.env` format rules** (so make/shell, Docker Compose, python-dotenv and Next.js read it the same way): one `KEY=value` per line; comments only on their **own line** starting with `#` (no inline comments); quote values containing spaces with double quotes; no `$` or backticks in values; generate secrets with `python -c "import secrets; print(secrets.token_urlsafe(48))"` (URL-safe characters only).

## CI/CD (GitHub Actions)

`.github/workflows/ci.yml`:

```yaml
# BayFlow CI — the four required checks of spec 07 (§CI/CD) and spec 12 (§6): api, web, contract, secrets.
# Railway's "Wait for CI" needs a workflow triggered by `push` on main (spec 07).
#
# Action versions and inputs, verified on GitHub on 2026-10-09 (releases API + action.yml/README at the tag):
#   actions/checkout          v7.0.1  https://github.com/actions/checkout/releases/tag/v7.0.1
#                                     input fetch-depth (action.yml at v7.0.1)
#   actions/setup-node        v7.1.0  https://github.com/actions/setup-node/releases/tag/v7.1.0
#                                     inputs node-version, cache, cache-dependency-path (action.yml at v7.1.0)
#   pnpm/action-setup         v6.1.0  https://github.com/pnpm/action-setup/releases/tag/v6.1.0
#                                     input package_json_file: path relative to the repo root; without `version`
#                                     the action reads "packageManager" (pnpm@10.34.6 in apps/web/package.json, D1/D5).
#                                     pnpm/setup@v3 is not usable: it installs pnpm 11+ only (its README; spec 12 §6).
#   astral-sh/setup-uv        v10.2.0 https://github.com/astral-sh/setup-uv/releases/tag/v10.2.0
#                                     inputs version, python-version, enable-cache, working-directory (README at v10.2.0).
#                                     setup-uv publishes no moving major tags since v8 (`@v10` does not resolve), so it is
#                                     pinned to the commit of v10.2.0, the form its README uses.
#   gitleaks/gitleaks-action  v3.0.0  https://github.com/gitleaks/gitleaks-action/releases/tag/v3.0.0
#                                     env GITHUB_TOKEN, GITLEAKS_LICENSE (organisation-owned repos only), GITLEAKS_ENABLE_COMMENTS
#   uv 0.12.24 (latest release)       https://github.com/astral-sh/uv/releases/tag/0.12.24
name: ci

on:
  push:
    branches: [main] # Railway "Wait for CI" needs a push trigger on main
  pull_request:

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

env:
  UV_VERSION: "0.12.24"
  PYTHON_VERSION: "3.12"
  NODE_VERSION: "24"

jobs:
  api:
    name: api · lint, format, types, architecture, tests, migrations
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    defaults:
      run:
        working-directory: apps/api
    services:
      postgres:
        image: postgres:16 # same major as Railway and docker-compose.yml (D12)
        env:
          POSTGRES_USER: bayflow
          POSTGRES_PASSWORD: bayflow
          POSTGRES_DB: bayflow
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U bayflow -d bayflow"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    env:
      APP_ENV: development
      DATABASE_URL: postgresql://bayflow:bayflow@localhost:5432/bayflow # the CI service container (5434 is for developer machines, D73)
      JWT_SECRET: ci-placeholder-not-a-real-secret-value # letters and hyphens only: gitleaks allowlists it
      COOKIE_SECURE: "false"
      CLIENT_URL: http://localhost:3000
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
        with:
          version: ${{ env.UV_VERSION }}
          python-version: ${{ env.PYTHON_VERSION }}
          enable-cache: true
          working-directory: apps/api
      - run: uv sync --locked
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy app
      - run: uv run lint-imports
      - run: uv run pytest --cov=app --cov-report=term-missing # coverage is reported, not enforced (spec 12 §6)
      - run: uv run alembic upgrade head # migrations apply cleanly to the empty `bayflow` database (tests use bayflow_test)
      - run: uv run alembic check # models and migrations agree (spec 12 §6 gate; needs the database at head)
      # P1 gates from spec 12 §6, to add once the code exists: migration round-trip
      # (`alembic downgrade base && alembic upgrade head`) and 100 % branch coverage of the bookings domain.

  web:
    name: web · lint, types, format, unit tests, build
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    defaults:
      run:
        working-directory: apps/web
    env:
      API_BASE_URL: http://localhost:4000
      NEXT_PUBLIC_WS_URL: ws://localhost:4000/api/v1/ws
      NEXT_TELEMETRY_DISABLED: "1"
    steps:
      - uses: actions/checkout@v7
      - uses: pnpm/action-setup@v6 # no `version`: pnpm comes from "packageManager" only, so the two never disagree
        with:
          package_json_file: apps/web/package.json # relative to the repo root; there is no root package.json (D5)
      - uses: actions/setup-node@v7
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: pnpm # pnpm must already be installed (step above)
          cache-dependency-path: apps/web/pnpm-lock.yaml
      - run: pnpm install --frozen-lockfile
      - run: pnpm lint # eslint . --max-warnings 0 (D80)
      - run: pnpm typecheck # next typegen && tsc --noEmit (D80)
      - run: pnpm format:check
      - run: pnpm test
      - run: pnpm build

  contract:
    name: contract · OpenAPI ↔ generated TypeScript client
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    env:
      APP_ENV: development
      DATABASE_URL: postgresql://unused:unused@localhost:5432/unused # the export never connects
      JWT_SECRET: ci-placeholder-not-a-real-secret-value
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
        with:
          version: ${{ env.UV_VERSION }}
          python-version: ${{ env.PYTHON_VERSION }}
          enable-cache: true
          working-directory: apps/api
      - uses: pnpm/action-setup@v6
        with:
          package_json_file: apps/web/package.json
      - uses: actions/setup-node@v7
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: pnpm
          cache-dependency-path: apps/web/pnpm-lock.yaml
      - run: pnpm install --frozen-lockfile
        working-directory: apps/web
      - run: uv sync --locked
        working-directory: apps/api
      - run: make gen-api # export_openapi -> openapi.json, then pnpm api:types -> schema.d.ts (D76)
      - name: Both generated files are committed and current (D76, WEB-07)
        run: |
          changes="$(git status --porcelain -- apps/web/src/lib/api)"
          if [ -n "$changes" ]; then
            echo "$changes"
            git --no-pager diff --stat -- apps/web/src/lib/api
            echo "::error::apps/web/src/lib/api is stale: run 'make gen-api' and commit openapi.json and schema.d.ts"
            exit 1
          fi

  secrets:
    name: secrets · gitleaks
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    permissions:
      contents: read
      pull-requests: read # on pull_request events gitleaks-action lists the PR's commits through the API
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0 # full history: every commit is scanned
      - uses: gitleaks/gitleaks-action@v3
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITLEAKS_LICENSE: ${{ secrets.GITLEAKS_LICENSE }} # free key, needed only for organisation-owned repos
          GITLEAKS_ENABLE_COMMENTS: "false" # PR review comments would need pull-requests: write
```

Sources for the building blocks:

- Postgres service container with `pg_isready` health options, reached on `localhost` when the job runs on the runner ([GitHub docs](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers)).
- `astral-sh/setup-uv` with a pinned uv version, `python-version`, `enable-cache` ([uv GitHub integration](https://docs.astral.sh/uv/guides/integration/github/)); latest releases on 2026-10-09 (GitHub releases API): `actions/checkout` v7.0.1, `astral-sh/setup-uv` v10.2.0, `pnpm/action-setup` v6.1.0, `actions/setup-node` v7.1.0, `gitleaks/gitleaks-action` v3.0.0. **`setup-uv` is pinned to the commit SHA of v10.2.0** (`c18668ad3cf93ea998bef934396af7bb5c839dc7`): it has published no moving major tags since v8, so `@v10` does not resolve; the SHA form is the one its README uses. The other actions use their major tags.
- **`api` job as built:** `uv run pytest --cov=app --cov-report=term-missing` — coverage is reported, not enforced (the domain gate is P1, spec 12 §6); the pytest run already includes the migration round trip on `bayflow_test` (`tests/db/test_migrations.py`: `downgrade base` → `upgrade head` → `check`, spec 02 §9); then `alembic upgrade head` and `alembic check` on the empty `bayflow` database. Jobs have timeouts (api and web 20 min, contract 15, secrets 10).
- **`contract` drift check as built:** after `make gen-api` it runs `git status --porcelain -- apps/web/src/lib/api` and fails on any output — unlike `git diff --exit-code`, this also catches a generated file that is new and not yet committed — printing `git diff --stat` and an `::error::` that says to run `make gen-api` and commit both files.
- **`secrets` job permissions:** `contents: read` plus **`pull-requests: read`**, because on `pull_request` events gitleaks-action lists the PR's commits through the GitHub API; `GITLEAKS_ENABLE_COMMENTS: "false"`, since PR review comments would need `pull-requests: write`.
- **pnpm 10.34.6 in CI.** `pnpm/setup` is **not** used: it requires pnpm v11 or newer, while D1 pins pnpm 10 because Vercel builds support pnpm 6–10. The official `pnpm/action-setup@v6` supports pnpm v12 and earlier; when its `version` input is omitted it reads the version from `packageManager` (or `devEngines.packageManager`) in the file named by `package_json_file` — a path relative to the repository root, here `apps/web/package.json` because there is no root manifest (D5) ([pnpm/action-setup README and action.yml](https://github.com/pnpm/action-setup)). `actions/setup-node@v7` then installs Node 24 and caches the pnpm store: `cache: pnpm` needs pnpm installed first, and `cache-dependency-path` points at the app's lockfile because the default search is the repo root ([actions/setup-node](https://github.com/actions/setup-node)). `pnpm install --frozen-lockfile` fails when the lockfile is out of date ([pnpm CI docs](https://pnpm.io/continuous-integration)).
- `alembic check` (Alembic ≥ 1.9) fails when autogenerate would produce new operations, i.e. when models and migrations disagree; it needs a database at `head`, hence the `upgrade head` step before it (spec 12 §6).
- gitleaks-action needs a free `GITLEAKS_LICENSE` only for repositories owned by an organization ([gitleaks-action](https://github.com/gitleaks/gitleaks-action)).
- **Placeholder secrets stay scan-clean:** gitleaks's `generic-api-key` rule flags keyword-assigned values with entropy above 3.5 but allowlists values made only of letters, `_`, `.` and `-` (`^[a-zA-Z_.-]+$` — [gitleaks default config v8.30.1](https://github.com/gitleaks/gitleaks/blob/v8.30.1/config/gitleaks.toml)). Every placeholder in `.env.example`, CI and tests therefore uses letters and hyphens only (e.g. `local-dev-secret-replace-me-with-random-chars`, 45 characters, so it also passes the ≥ 32-byte rule in development); a digit-laden dummy such as `secret-0123abcd…` would fail our own `secrets` job. Production refuses every repository placeholder anyway (glossary §12): D85 rejects any `JWT_SECRET` **containing** `change-me`, `replace-me`, `dev-only` or `placeholder`, which covers `.env.example`'s value, CI's `ci-placeholder-not-a-real-secret-value` and the API's built-in development secret (`dev-only-…`), whatever their length.
- Test-database handling (a `<db>_test` database derived from `DATABASE_URL`, migrated with Alembic) and the full test list belong to spec 12. A Playwright smoke job is P1 (D54).

**Branch protection on `main`:** require the `api`, `web`, `contract` and `secrets` checks and one review; block force-pushes.

**Auto-deploy:** Vercel deploys previews for every push and production for `main` without waiting for CI; Railway deploys `main` only after CI passes. Consequences:

1. **API before web.** Vercel can go live minutes before Railway, so API changes must be backward compatible: add endpoints/fields first, ship the web change that needs them afterwards (or in the same PR when purely additive).
2. **Expand → contract migrations** (pre-deploy section above).
3. **Rollback.** Vercel keeps previous production deployments for instant rollback (Vercel for GitHub). On Railway, redeploy the previous deployment from the service's deployment list **(unverified UI path)**; migrations are not reverted automatically — prefer a forward fix.
4. Optional (P1): a `smoke.yml` workflow triggered by Vercel's `repository_dispatch` event `vercel.deployment.success` (payload `client_payload.url`, `client_payload.environment` — Vercel for GitHub) can run `scripts/smoke.sh` after every production deploy.

## Environment variable inventory

Exactly the variables of glossary §12 — no more, no fewer (33). "Prod" = where the production value is set. `API_BASE_URL` and every `NEXT_PUBLIC_*` value are **fixed at build time** on Vercel (change = redeploy).

| Variable | App | Required | Local example | Prod | Description |
|---|---|---|---|---|---|
| `APP_ENV` | api | yes (default `development`) | `development` | Railway `api`: `production` | Runtime mode; `production` enables the startup guards (strong `JWT_SECRET`, `COOKIE_SECURE=true`). Replaces the brief's `NODE_ENV` because the API is Python (README §9) |
| `PORT` | api, agent | yes (Railway injects one; we set it) | `4000` | Railway `api`: `4000`; `agent`: `8081` | Port the API (uvicorn) or the agent's health server binds; Railway health checks use it |
| `CLIENT_URL` | api | yes | `http://localhost:3000` | Railway `api`: `https://<project>.vercel.app` | Web origin: CORS, WebSocket `Origin` check, links in e-mails |
| `DATABASE_URL` | api | yes | `postgresql://bayflow:bayflow@localhost:5434/bayflow` | Railway `api`: `${{Postgres.DATABASE_URL}}` | PostgreSQL 16 URL; the API converts it to `postgresql+asyncpg://` |
| `POSTGRES_HOST_PORT` | docker compose only | no (default `5434`) | `5434` | — (not used on Railway) | Host port of the local PostgreSQL container (D73); keep `DATABASE_URL`'s port equal |
| `JWT_SECRET` | api | yes | `local-dev-secret-replace-me-with-random-chars` | Railway `api` (sealed): 48+ random characters | HS256 signing secret, at least 32 bytes; **production refuses to start** with a missing or shorter value or one containing a placeholder marker (`change-me`, `replace-me`, `dev-only`, `placeholder`; D85). Development without it falls back to a built-in `dev-only-…` secret and logs a warning |
| `JWT_EXPIRES_IN` | api | no (default `7d`) | `7d` | Railway `api` | Token lifetime: a number followed by `s`, `m`, `h` or `d` (a bare number = seconds), between 5 minutes and 30 days, else the API refuses to start |
| `COOKIE_SECURE` | api | no (default `false`, for plain-HTTP localhost) | `false` | Railway `api`: `true` (production refuses `false`) | `Secure` flag of `bf_session`; `false` only for plain-HTTP localhost |
| `LOG_LEVEL` | api, agent | no (default `INFO`) | `INFO` | Railway `api`, `agent` | Log level of the JSON logs |
| `SEED_ON_DEPLOY` | api | no (default `false`) | `true` | Railway `api`: `true` | `true` → `python -m app.scripts.seed` loads the idempotent demo data and repairs the demo cast after migrations (pre-deploy, Compose `migrate`, `start.*`); otherwise it exits 0 at once (D13, D60) |
| `EMAIL_PROVIDER` | api | no (default `none`) | `none` (`smtp` with Mailpit) | Railway `api`: `http` (P1; `none` until an e-mail API account exists) | E-mail channel (D26): `none`, `smtp` (local Mailpit) or `http` (HTTPS e-mail API — Railway Hobby blocks outbound SMTP) |
| `EMAIL_API_KEY` | api | with `EMAIL_PROVIDER=http` | blank | Railway `api` (sealed) | API key of the HTTPS e-mail service (vendor not fixed, e.g. Resend) |
| `SMTP_HOST` | api | with `EMAIL_PROVIDER=smtp` | blank (`localhost` or `mailpit` with Mailpit) | blank | SMTP server |
| `SMTP_PORT` | api | no (code default `587`; `.env.example` sets `1025`) | `1025` | blank | SMTP port (Mailpit 1025) |
| `SMTP_USER` | api | no | blank | blank | SMTP username |
| `SMTP_PASS` | api | no | blank | blank | SMTP password |
| `SMTP_FROM` | api | when e-mail is on | `no-reply@bayflow.test` | Railway `api`: an address on a domain the e-mail service has verified | Sender address for both `smtp` and `http` |
| `API_BASE_URL` | web | yes on Vercel (build time) | `http://localhost:4000` | Vercel: `https://<api>.up.railway.app` | Server-side rewrite target for `/api/*`; fixed at build time |
| `NEXT_PUBLIC_WS_URL` | web | yes on Vercel (build time) | `ws://localhost:4000/api/v1/ws` | Vercel: `wss://<api>.up.railway.app/api/v1/ws` | Browser WebSocket URL of the API; inlined at build time |
| `CALL_PROVIDER_URL` | api, agent | bonus | blank | Railway shared | LiveKit project URL (blank = calling off) |
| `CALL_PROVIDER_API_KEY` | api, agent | bonus | blank | Railway shared (sealed) | LiveKit API key |
| `CALL_PROVIDER_API_SECRET` | api, agent | bonus | blank | Railway shared (sealed) | LiveKit API secret |
| `NEXT_PUBLIC_CALL_PROVIDER_URL` | web | bonus | blank | Vercel (build time) | LiveKit URL for the browser SDK |
| `LLM_API_KEY` | api, agent | bonus | blank | Railway shared (sealed) | Key for the selected `AI_PROVIDER` (blank = AI off; the API only checks presence) |
| `AI_PROVIDER` | agent | bonus (default `openai`) | `openai` | Railway `agent` | `openai`, or `gemini` for the D58 fallback |
| `AI_REALTIME_MODEL` | agent | bonus, optional | blank | Railway `agent` (only to override) | Voice model override (code default `gpt-realtime-2.1-mini`) |
| `AI_SUMMARY_MODEL` | agent | bonus, optional | blank | Railway `agent` (only to override) | Post-call summary model override (code default, spec 05) |
| `STT_TTS_API_KEY` | agent | bonus, usually blank | blank | Railway `agent` (only if used) | Separate speech provider key |
| `AI_RING_TIMEOUT_SECONDS` | api | bonus (default `20`) | `20` | Railway `api` | Seconds before the AI answers an unanswered call |
| `AI_DAILY_CALL_CAP` | api | bonus (default `100`) | `100` | Railway `api` | AI-answered calls per day; above it the AI counts as disabled |
| `CALL_MONTHLY_MINUTES_CAP` | api | bonus (default `4000`) | `4000` | Railway `api` | Call participant-minutes per month; above it calling returns 503 `CALLING_DISABLED` |
| `AGENT_SERVICE_TOKEN` | api, agent | bonus | blank | Railway shared (sealed) | Shared secret for `/api/v1/internal/*` |
| `API_INTERNAL_URL` | agent | bonus | `http://localhost:4000` | Railway `agent`: `http://${{api.RAILWAY_PRIVATE_DOMAIN}}:${{api.PORT}}` | API base URL reachable from the agent |

Platform-provided variables we rely on but never set in `.env`: Railway `PORT` injection and `RAILWAY_PRIVATE_DOMAIN` ([Railway variables reference](https://docs.railway.com/reference/variables)); Vercel `VERCEL`, `VERCEL_GIT_PREVIOUS_SHA` (system env vars page). `ENABLE_EXPERIMENTAL_COREPACK` must **not** be set on the Vercel project: it breaks the install (Vercel project settings above). `NODE_ENV` is never set by us: Next.js assigns `development` for `next dev` and `production` for every other command ([Next.js env vars](https://nextjs.org/docs/app/guides/environment-variables)).

## Root `.env.example`

Brief §9.3 asks for every variable with a placeholder and a short comment; the grouping follows the brief's sample (App, Database, Auth, Email (optional), Bonus: calling / AI) plus a Web section. The file lists **exactly** the 33 variables of glossary §12 — the same set as the inventory above — each with one comment line. Secret placeholders use letters and hyphens only, so gitleaks does not flag them (§CI/CD), and the `JWT_SECRET` placeholder is long enough (45 characters) for local use while production still refuses it.

```dotenv
# =====================================================================
# BayFlow example environment. Copy it to `.env` in the repo root:
#     cp .env.example .env
# (./start.sh and start.bat create `.env` from this file on their first run.)
# Never commit `.env`. Comments sit on their own line (no inline
# comments). Quote values that contain spaces. Do not use `$` in values.
# Production values live in Railway (api, agent) and Vercel (web);
# API_BASE_URL and NEXT_PUBLIC_* are fixed at build time on Vercel.
# =====================================================================

# --- App ---
# Runtime mode of the API: development | production (replaces the brief's NODE_ENV; the API is Python)
APP_ENV=development
# HTTP port: the API locally (Railway injects its own); the bonus agent's health server uses 8081 on Railway
PORT=4000
# Origin of the web app: CORS, WebSocket Origin check and links in e-mails
CLIENT_URL=http://localhost:3000
# Log level of the API and the agent: DEBUG | INFO | WARNING | ERROR
LOG_LEVEL=INFO
# true = after migrations, load the idempotent demo data and repair the demo cast (pre-deploy, compose, start scripts)
SEED_ON_DEPLOY=true

# --- Database ---
# Host port of the local PostgreSQL container (read only by docker compose; keep DATABASE_URL's port the same)
POSTGRES_HOST_PORT=5434
# PostgreSQL 16 URL (the API adds the asyncpg driver itself; Docker Compose uses host `db` inside its network)
DATABASE_URL=postgresql://bayflow:bayflow@localhost:5434/bayflow

# --- Auth ---
# HS256 secret, at least 32 bytes; production refuses short or example values (new one: python -c "import secrets; print(secrets.token_urlsafe(48))")
JWT_SECRET=local-dev-secret-replace-me-with-random-chars
# Session lifetime: a number plus m, h or d
JWT_EXPIRES_IN=7d
# Secure flag on the bf_session cookie: false for plain-HTTP localhost, true in production
COOKIE_SECURE=false

# --- Email (optional) ---
# E-mail channel: none | smtp (local Mailpit: docker compose --profile mail up) | http (HTTPS e-mail API, production)
EMAIL_PROVIDER=none
# API key of the HTTPS e-mail service (only for EMAIL_PROVIDER=http; Railway Hobby blocks outbound SMTP)
EMAIL_API_KEY=
# SMTP server for EMAIL_PROVIDER=smtp: localhost (native API) or mailpit (API in Docker)
SMTP_HOST=
# SMTP port: 1025 for Mailpit
SMTP_PORT=1025
# SMTP username (blank for Mailpit)
SMTP_USER=
# SMTP password (blank for Mailpit)
SMTP_PASS=
# Sender address for smtp and http (production: an address on a domain your e-mail service has verified)
SMTP_FROM=no-reply@bayflow.test

# --- Web (Next.js, apps/web) ---
# Server-side only: where Next.js forwards /api/* (Vercel: the Railway API URL; fixed at build time)
API_BASE_URL=http://localhost:4000
# Browser WebSocket URL of the API (production: wss://<api-host>/api/v1/ws; inlined at build time)
NEXT_PUBLIC_WS_URL=ws://localhost:4000/api/v1/ws

# --- Bonus: calling / AI (leave blank if not used) ---
# LiveKit project URL for the API and the agent, e.g. wss://<project>.livekit.cloud (blank = calling off)
CALL_PROVIDER_URL=
# LiveKit API key (API and agent)
CALL_PROVIDER_API_KEY=
# LiveKit API secret (API and agent)
CALL_PROVIDER_API_SECRET=
# LiveKit URL for the browser SDK (web, build time), usually the same as CALL_PROVIDER_URL
NEXT_PUBLIC_CALL_PROVIDER_URL=
# Key for the selected AI_PROVIDER (API and agent; blank = AI Front Desk off)
LLM_API_KEY=
# AI provider of the agent: openai (default) | gemini (fallback)
AI_PROVIDER=openai
# Realtime voice model override (blank = code default gpt-realtime-2.1-mini)
AI_REALTIME_MODEL=
# Post-call summary model override (blank = code default)
AI_SUMMARY_MODEL=
# Separate speech-to-text / text-to-speech key; blank when using a realtime speech model
STT_TTS_API_KEY=
# Seconds a customer's call rings before the AI Front Desk answers
AI_RING_TIMEOUT_SECONDS=20
# Max AI-answered calls per day (app cap below the provider's hard limits)
AI_DAILY_CALL_CAP=100
# Max call participant-minutes per month (app cap below LiveKit's free allowance)
CALL_MONTHLY_MINUTES_CAP=4000
# Shared secret between API and agent for /api/v1/internal/* (32+ random characters)
AGENT_SERVICE_TOKEN=
# API base URL as seen by the agent (Railway: http://<api private domain>:<port>)
API_INTERNAL_URL=http://localhost:4000
```

## README outline

The README is written last but **planned now**, so each requirement has an owner. **As built (2026-10-09)** the root `README.md` follows this skeleton with sections 1–18 (the header is unnumbered; 17 Specs and 18 Troubleshooting are additions); sections that depend on unbuilt features carry "_to be completed_" and are filled as the features land (spec 14). Mapping to the brief:

| Brief requirement | README section |
|---|---|
| §9.1 project overview, tech stack | 1, 3 |
| §9.1 live URL; §9.1 optional demo video, architecture diagram, API docs | header, 4, 12, 13 |
| §9.2 prerequisites with exact versions | 6 |
| §9.2 install dependencies per app | 8 |
| §9.2 environment setup (copy `.env.example`, explain each variable) | 9 |
| §9.2 database: create, migrate, seed | 10 |
| §9.2 run: one command + `docker compose up` | 7, 8 |
| §9.1 how to run tests | 11 |
| §9.2 demo accounts for Owner, SA, Technician, QC, Parts, Customer | 2 |
| §9.1 deployment notes | 14 |
| §9.1 architecture summary; §9.2 project structure and design decisions | 4, 5, 15 |

**Skeleton:**

0. **Header** — name, one-line pitch, badges (CI), **Live URL** `https://<project>.vercel.app`, **API docs** `https://<api>.up.railway.app/docs`, **Demo video** `<link — 3–5 min, added before submission>`.
1. **Overview** — the problem (brief §2) in three lines; the three surfaces (customer portal, shop POS, API); one screenshot.
2. **Demo accounts** — all share the password **`BayFlow@2026`** (glossary §14; also shown on the login page, D52):

   | Role | Person | E-mail |
   |---|---|---|
   | Owner (Lahore Auto Care + a second shop) | Fatima Raza | `fatima.owner@bayflow.test` |
   | Service Advisor | Bilal | `bilal.sa@bayflow.test` |
   | Technician | Imran | `imran.tech@bayflow.test` |
   | QC Inspector | Sara | `sara.qc@bayflow.test` |
   | Parts Person | Usman | `usman.parts@bayflow.test` |
   | Customer (with sample bookings) | Ayesha Khan | `ayesha.customer@bayflow.test` |
   | Second Technician / second QC Inspector ("first pick wins") | Hamza / Hina | `hamza.tech@bayflow.test` / `hina.qc@bayflow.test` |

   **Notes for judges** (right under the table):
   - Ahmed from the worked example is **not** seeded — book through the wizard with a **fresh `.test` address (e.g. `ahmed1@bayflow.test`)** to replay §6. `.test` is a reserved domain: the API accepts it (D62) and never e-mails it (D26), whereas the brief's `ahmed@mail.com` is a real domain that the live e-mail channel would actually write to. Use a new address each time: an existing e-mail with a different password is refused with 409 `EMAIL_ALREADY_REGISTERED` (D32).
   - Passwords for new accounts need **12–128 characters** (D10), e.g. `Ahmed@2026-demo`.
   - **Shared demo data drifts** (D71): every replay consumes stock and fills a slot — the worked example's Friday 10:00 slot has capacity 2. If it is full, pick another slot; if the ignition coil is out, Usman can add stock (`ADJUST`) or order it.
   - **If a demo account stops working** (e.g. another judge deactivated Bilal), the seed repairs the demo cast — users and memberships active with their canonical roles, password `BayFlow@2026` — without touching anyone's bookings (D60). The team re-runs it by redeploying the Railway `api` service (the pre-deploy step runs the seed again).
   - **Lyallpur Motors is the smoke-test shop** (spec 11): automated post-deploy checks (`scripts/smoke.sh`, spec 12 DEP-10 and WEB-08) book there, and only there, with throw-away `smoke+<n>@bayflow.test` customers, so judges may see those bookings and notifications at Lyallpur Motors. Automation never writes at Lahore Auto Care.
   - A 10-step "try the full flow" list (spec 06).
3. **Tech stack** — table with versions from D11 (latest *compatible* versions): Next.js 16.4, React 19, TypeScript 5.9.3, Tailwind CSS 4.3, shadcn/ui (Radix), TanStack Query 5, React Hook Form + Zod, ESLint 9.39, FastAPI 0.143, Pydantic 2.14 + pydantic-settings 2, SQLAlchemy 2.1 (`sqlalchemy[asyncio]`, asyncpg), Alembic 1.20, pwdlib (`pwdlib[argon2]`, Argon2id), PostgreSQL 16, Python 3.12 + uv, Node.js 24 + pnpm 10.34.6, Vercel, Railway; bonus LiveKit + OpenAI `gpt-realtime-2.1-mini`. One line on why TypeScript and ESLint are not the npm `latest` majors (peer-dependency limits, D11).
4. **Architecture** — the topology diagram from spec 01, five sentences: modular monolith, `/api/*` rewrite + direct WebSocket, one transaction per action, in-process events, tenant isolation; link to `.claude/specs/01-architecture.md`.
5. **Project structure** — the root tree from spec 01 with one line per folder.
6. **Prerequisites** — exact versions:

   | Tool | Version | Needed for |
   |---|---|---|
   | Docker with Compose v2 (`docker compose`) | current Docker Desktop / Engine, **Compose 2.24 or newer** (the `env_file` `required: false` form) | Option A, and PostgreSQL in Option B |
   | Python | 3.12.x (`uv python install 3.12` installs it) | API (native) |
   | uv | 0.12.x (CI pins 0.12.24) | API (native) |
   | Node.js | 24 LTS | web (native) |
   | pnpm | 10.34.6 (pinned by `"packageManager"` in `apps/web/package.json`; `corepack enable` provides it) | web (native) |
   | PostgreSQL | 16 (Docker image `postgres:16`; a native 16 also works) | database |
   | GNU Make | any (macOS/Linux; on Windows use `start.bat` / `stop.bat`, WSL2 or Option A) | `make` shortcuts |
   | curl, jq | any | start scripts (curl); smoke test (curl + jq) |

   Free local ports: web **3000**, API **4000**, PostgreSQL **5434** (change with `POSTGRES_HOST_PORT` and `DATABASE_URL` together), Mailpit 8025/1025 (optional) — D73.
7. **Quick start (Docker)** — `cp .env.example .env` → `docker compose up --build` → open `http://localhost:3000`, log in with a demo account.
8. **Local development (native)** — per-app installs (`make setup` does the first two): `cd apps/api && uv sync`; `cd apps/web && pnpm install`; bonus `cd apps/agent && uv sync`; then **`./start.sh`** (Windows: `start.bat`) and **`./stop.sh`** (`stop.bat`) — what they do (the seed always runs after migrations and acts when `SEED_ON_DEPLOY=true`, as `.env.example` sets it; `--seed` forces it), where the logs (`logs/`) and PID files (`.run/`) are (D73). Alternatives: `make dev` in the foreground, or the manual commands (`docker compose up -d --wait db`, `uv run alembic upgrade head`, `uv run python -m app.scripts.seed --force`, `uv run uvicorn app.main:app --reload --port 4000`, `pnpm dev`). A `make help` table of all targets.
9. **Environment variables** — "copy `.env.example` to `.env`; defaults work locally"; the inventory table above, condensed (variable, purpose, local default). Two notes: (a) **`APP_ENV`, not `NODE_ENV`** — the brief's sample uses `NODE_ENV`, but the API is Python and reads `APP_ENV`; `NODE_ENV` belongs to Next.js, which sets it itself (`development` for `next dev`, `production` for every other command — [Next.js env vars](https://nextjs.org/docs/app/guides/environment-variables)), so never put it in `.env`. (b) On Vercel, `API_BASE_URL` and every `NEXT_PUBLIC_*` value are **fixed at build time** — change them, then redeploy.
10. **Database** — created by Compose (`POSTGRES_DB=bayflow`, host port 5434) or `createdb bayflow` for a native server; `make migrate`; `make seed` (what the seed contains, spec 11; re-running it repairs the demo cast, D60); `make db-reset` (local only: refuses `APP_ENV=production` or a non-local `DATABASE_URL` with exit code 2).
11. **Tests** — `make test` (pytest on PostgreSQL: state machine incl. every invalid transition, role and tenant isolation, concurrency — QC pick and last slot, the worked example end to end incl. QC-fail loop and estimate-rejected path; vitest for the web), `uv run pytest -m "not db"` for the DB-free tests (no PostgreSQL needed), `make lint`, what CI runs (spec 12 §4.7).
12. **API documentation** — Swagger UI at `/docs` (use **Authorize** with the `access_token` returned by `POST /api/v1/auth/login`, whose body is `{access_token, token_type, expires_in, user}`; memberships and capabilities come from `GET /api/v1/me`, D81), raw schema at `/openapi.json`, typed client generated with `make gen-api`.
13. **Demo video** — link placeholder.
14. **Deployment** — Vercel (web, root `apps/web`, build-time `API_BASE_URL` and `NEXT_PUBLIC_WS_URL`) + Railway (`api` with the pre-deploy command `/bin/sh -c "alembic upgrade head && python -m app.scripts.seed"` and `/health`, `Postgres` 16, bonus `agent`); production e-mail via `EMAIL_PROVIDER=http` because Railway Hobby has no outbound SMTP; every API response is `Cache-Control: no-store` (D61); `make smoke`; link to this spec.
15. **Design decisions** — modular monolith (ADR in spec 01); state machine as data with `allowed_actions`; tenant isolation enforced three times; row locks for QC pick and slots; money as `Decimal`/`numeric(12,2)`, time in UTC with shop timezone; realtime pushes after commit + polling fallback; typed client generated from OpenAPI.
16. **Contributing** — Conventional Commits, pre-commit hooks, PR checklist (below).
17. **Specs** — a table linking the `.claude/specs/` files (foundation first: 00, 18, 17, 08).
18. **Troubleshooting** — busy ports 3000/4000 (and what the start/stop scripts do about them), a taken port 5434, Docker not running, where the logs are, no demo accounts (`SEED_ON_DEPLOY`).

## Repository standards

- **Folder organisation:** the monorepo layout of spec 01 (D5); one folder per backend module; generated code only in `apps/web/src/lib/api/`; specs in `.claude/specs/` change **before** the code they describe.
- **Conventional Commits 1.0.0** ([conventionalcommits.org](https://www.conventionalcommits.org/en/v1.0.0/)), as glossary §13 requires: `<type>(<scope>): <summary>`. Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`, `build`, `perf`, `style`. Scopes: module names (`identity`, `shops`, `scheduling`, `bookings`, `estimates`, `inventory`, `qc`, `notifications`, `reporting`, `calls`) plus `web`, `api`, `agent`, `infra`, `specs`, `deps`. Examples: `feat(bookings): add approve-estimate customer action`, `fix(inventory): release reservations on cancel`, `docs(specs): draft 07 deployment`.
- **Small commits** (brief §9.4): one logical change that builds and passes its tests; the body explains *why*; no "wip"/"final" commits on `main`. AI-generated code is read and understood by a teammate before it is merged (brief §1, §9.4).
- **Branch / PR flow:** `main` is always deployable and protected (required checks, one review, no force-push). Short-lived branches `feat/<scope>-<topic>` and `fix/<scope>-<topic>`. Every PR uses `.github/pull_request_template.md` (spec updated? tests added? `make gen-api` run? no secrets? screenshots for UI). Merge with **rebase merge** so `main` keeps the small, meaningful commits the brief asks for ("not a single commit", §9.1); delete the branch after merging.
- **`.gitignore`** (root):

  ```gitignore
  # --- Secrets: never commit real values (brief §9.1) ---
  .env
  .env.*
  !.env.example

  # --- Local dev scripts (start.sh / start.bat) ---
  logs/
  .run/
  *.log

  # --- Python (apps/api, apps/agent) ---
  .venv/
  venv/
  __pycache__/
  *.py[cod]
  *.egg-info/
  .pytest_cache/
  .mypy_cache/
  .ruff_cache/
  .import_linter_cache/
  .coverage
  .coverage.*
  coverage.xml
  htmlcov/

  # --- Node / Next.js (apps/web) ---
  node_modules/
  .pnpm-store/
  .next/
  out/
  next-env.d.ts
  *.tsbuildinfo
  .eslintcache
  coverage/
  .vercel/
  playwright-report/
  test-results/
  blob-report/

  # --- OS and editors ---
  .DS_Store
  Thumbs.db
  ehthumbs.db
  Desktop.ini
  $RECYCLE.BIN/
  .idea/
  *.swp
  *~
  ```

  `.env.*` also covers `apps/web/.env.local`; Next.js recommends ignoring `next-env.d.ts` (next CLI docs); `.venv/` covers `apps/api/.venv` (D5); `logs/` and `.run/` are the start scripts' runtime folders (D73); the Playwright output folders are ignored ahead of the P1 smoke (WEB-08).
- **`.gitattributes`** (root, D5):

  ```gitattributes
  # Line endings (spec 01 root layout, spec 07 repository standards).
  # Text files are stored with LF and checked out with LF on every OS, so Prettier/Ruff
  # (end of line = lf) and the bash scripts behave the same after a Windows checkout.
  * text=auto eol=lf

  # Shell scripts must keep LF or bash fails with "$'\r': command not found".
  *.sh text eol=lf
  .env.example text eol=lf
  Makefile text eol=lf

  # Windows batch files need CRLF: cmd.exe mis-parses labels and blocks in LF-only files.
  *.bat text eol=crlf
  *.cmd text eol=crlf
  *.ps1 text eol=crlf

  # Binary assets: never normalise or diff as text.
  *.png binary
  *.jpg binary
  *.jpeg binary
  *.gif binary
  *.ico binary
  *.webp binary
  *.pdf binary
  *.woff binary
  *.woff2 binary
  ```

  Every text file is stored and checked out with LF (so Prettier and Ruff, which expect LF, agree on every OS); shell scripts, `.env.example` and the `Makefile` keep LF after a Windows checkout (otherwise `bash` fails on `\r`), and `cmd.exe` batch files keep CRLF. `.editorconfig` sets the same line endings (CRLF for `*.bat`), UTF-8, 2-space indentation (4 for Python, tabs for the `Makefile`).
- **Secret scanning:** the gitleaks pre-commit hook (`gitleaks` hook id, [gitleaks](https://github.com/gitleaks/gitleaks)) and the CI `secrets` job; GitHub **push protection** for users is on by default and blocks pushes of secrets to public repositories, and repository-level push protection can be enabled by an admin ([GitHub push protection](https://docs.github.com/en/code-security/secret-scanning/introduction/about-push-protection)) — enable it on day 1. If a secret ever lands in Git, **rotate it**; deleting the commit is not enough.
- **Pre-commit hooks** — `.pre-commit-config.yaml` (exists since PH0; installed by `make setup`, which skips it outside a git work tree):

  ```yaml
  repos:
    - repo: https://github.com/pre-commit/pre-commit-hooks
      rev: v6.0.0
      hooks:
        - id: check-added-large-files
        - id: check-merge-conflict
        - id: check-yaml
        - id: end-of-file-fixer
        - id: trailing-whitespace
        - id: detect-private-key
    - repo: https://github.com/astral-sh/ruff-pre-commit
      rev: v0.16.10
      hooks:
        - id: ruff-check
          args: [--fix]
          files: ^apps/(api|agent)/
        - id: ruff-format
          files: ^apps/(api|agent)/
    - repo: local
      hooks:
        - id: prettier
          name: prettier (apps/web)
          entry: apps/web/node_modules/.bin/prettier --write --ignore-unknown
          language: unsupported
          files: ^apps/web/
          exclude: ^apps/web/src/lib/api/(openapi\.json|schema\.d\.ts)$
    - repo: https://github.com/gitleaks/gitleaks
      rev: v8.30.1
      hooks:
        - id: gitleaks
  ```

  ruff hook ids `ruff-check` / `ruff-format`, lint before format when `--fix` is used ([ruff-pre-commit](https://github.com/astral-sh/ruff-pre-commit)). Prettier runs as a repository-local hook with the project's own Prettier (the old `mirrors-prettier` repository is archived — [prettier discussion #16227](https://github.com/prettier/prettier/discussions/16227)); `language: unsupported` is pre-commit's name since 4.4.0 for what used to be `language: system` ([pre-commit docs source](https://github.com/pre-commit/pre-commit.com/blob/main/sections/new-hooks.md)). ESLint and type checks run in `make lint` and CI, not on every commit.

## Post-deploy smoke test — `scripts/smoke.sh`

Run after every production deploy: `make smoke WEB_URL=https://<project>.vercel.app API_URL=https://<api>.up.railway.app`. Needs bash, curl and jq. Path prefixes follow glossary §9: public shop routes use the shop **slug** (`/api/v1/public/shops/{shop_slug}`, `/api/v1/public/shops/{shop_slug}/availability?date=YYYY-MM-DD`) and staff routes the shop UUID (D68); free places in a slot are `remaining` (D68), and full slots are omitted. Sub-paths and field names follow spec 03 (§4, §8.3): `/health` answers `{"status": "ok", "database": "ok"}` (D84); login returns `{access_token, token_type, expires_in, user}` and memberships come from `GET /api/v1/me` (D81); the public list is a page (`items`, `total`, `limit`); a shop detail has `id` and `services[].id`; availability `slots[].slot_start` and `slots[].remaining`; booking creation answers 201 with `account_created` and the booking under `booking` (`booking.id`, `booking.status`); a customer action answers 200 with the booking itself (`status`); the ticket is `ticket` / `expires_in` — update the script whenever spec 03 changes them. **Data is written only at the smoke-test shop, Lyallpur Motors (`lyallpur-motors`, spec 11)**, never at Lahore Auto Care, so judges' worked-example stock and slots stay untouched; if a step after the booking fails, an exit trap still cancels the smoke booking so it never keeps a slot place. Demo logins use the shared password `BayFlow@2026` (glossary §14); the throw-away customer's password has the required 12+ characters (D10). Coverage: DEP-01 (step 1), DEP-02 (step 2: the landing page answers 200 and the directory lists at least the 6 seeded shops, SEED-01) and DEP-03 (step 3: Bilal's login sets `bf_session` through the rewrite, and `GET /api/v1/me` with that cookie lists his `SERVICE_ADVISOR` membership). Every response that goes through the Vercel rewrite is checked for `Cache-Control: no-store`, and a repeated GET must never come back as `x-vercel-cache: HIT` (D61; header values per [Vercel response headers](https://vercel.com/docs/headers/response-headers)); `/health` must also carry `X-Request-ID` (spec 03 §1.8). Failures print the HTTP status and the problem's `code` and `detail`. The script passes ShellCheck 0.11 and was dry-run (2026-10-09) against a mock of these endpoints with the spec 03 shapes: it passes, skips the ticket on 404, and fails on a missing `no-store`, a ticket 500, a 409 `SLOT_FULL`, a cross-shop leak (cancelling the booking on exit) and the old `slots[].start` field.

**Realtime is P1 (D88).** Step 3's ticket check (`GET /api/v1/realtime/ticket`) needs the P1 realtime layer, which arrives with PH6 (spec 14). While that endpoint answers 404 the script prints a `SKIP` line and goes on, because the 15 s polling (D14) is the P0 path; any other non-200 answer fails. Once PH6 is deployed, run it with `SMOKE_REQUIRE_REALTIME=1` so that a missing ticket endpoint fails too.

**As-built status (2026-10-09).** The committed `scripts/smoke.sh` is the listing below, verbatim. This listing is the contract: change the script and the listing together.

```bash
#!/usr/bin/env bash
# BayFlow post-deploy smoke test (spec 07 "Post-deploy smoke test"; spec 12 DEP-01…DEP-03; D7, D61, D68,
# D70, D81, D84, D88).
#
#   make smoke WEB_URL=https://<project>.vercel.app API_URL=https://<api>.up.railway.app
#   WEB_URL=http://localhost:3000 API_URL=http://localhost:4000 scripts/smoke.sh     # local stack
#
# Needs bash, curl and jq. Side effects: creates one throw-away customer (smoke+<n>@bayflow.test, a
# reserved .test address that is never e-mailed, D26) and one booking at the smoke-test shop Lyallpur
# Motors (spec 11), then cancels it (that shop's Service Advisor gets two notifications). If a later
# step fails, the booking is still cancelled on the way out. Nothing is written at Lahore Auto Care.
# Every response that goes through the web origin's /api rewrite must carry Cache-Control: no-store and
# must never be a Vercel cache HIT (D61). Realtime is P1 (D88): while GET /api/v1/realtime/ticket
# answers 404 the ticket check is skipped; SMOKE_REQUIRE_REALTIME=1 makes it mandatory.
# Field names follow spec 03; update this script and spec 07's listing when spec 03 changes them.
set -euo pipefail

: "${WEB_URL:?set WEB_URL, e.g. WEB_URL=https://<project>.vercel.app}"
: "${API_URL:?set API_URL, e.g. API_URL=https://<api>.up.railway.app}"
WEB_URL="${WEB_URL%/}"
API_URL="${API_URL%/}"
for tool in curl jq; do
  command -v "$tool" >/dev/null 2>&1 || {
    printf 'FAIL: %s is required\n' "$tool" >&2
    exit 1
  }
done

DEMO_PASSWORD='BayFlow@2026'      # every demo account (glossary §14)
SMOKE_SHOP_SLUG='lyallpur-motors' # the designated smoke-test shop (spec 11); never lahore-auto-care
WORK="$(mktemp -d)"
JAR="$WORK/customer.jar" # cookie session of the throw-away customer
SA_JAR="$WORK/bilal.jar" # cookie session of Bilal (DEP-03)
BOOKING_ID=""
CANCELLED=0

step() { printf '\n== %s\n' "$*"; }
fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}
http() { curl --connect-timeout 15 --max-time 120 "$@"; } # Vercel allows a proxied request 120 s
status() { http -s -o /dev/null -w '%{http_code}' "$@"; }
call() { # usage: call <body-file> <curl args…>; prints the HTTP status, the body goes to <body-file>
  local out="$1"
  shift
  http -sS -o "$out" -w '%{http_code}' "$@"
}
problem() { # "<status> <code>: <detail>" of a problem+json body (spec 03 §2), else the body's start
  jq -r '"\(.status // "?") \(.code // "-"): \(.detail // .title // "")"' "$1" 2>/dev/null || head -c 300 "$1"
}
login() { # usage: login <email> [curl args…]; prints the access token (D81 body shape)
  local email="$1" out="$WORK/login.json" code
  shift
  code="$(call "$out" "$@" -X POST "$WEB_URL/api/v1/auth/login" -H 'Content-Type: application/json' \
    -d "$(jq -n --arg e "$email" --arg p "$DEMO_PASSWORD" '{email: $e, password: $p}')")" || return 1
  if [[ "$code" != 200 ]]; then
    printf 'login %s -> HTTP %s: %s\n' "$email" "$code" "$(problem "$out")" >&2
    return 1
  fi
  jq -er --arg e "$email" 'select(.token_type == "bearer" and (.expires_in | type) == "number"
      and (.user | type) == "object" and .user.email == $e
      and (.access_token | type) == "string" and (.access_token | length) > 0) | .access_token' "$out" || {
    printf 'login %s: the body is not {access_token, token_type: "bearer", expires_in, user} (D81)\n' "$email" >&2
    return 1
  }
}
no_store() { # usage: no_store <label> <curl args…>; D61, and through the rewrite never a Vercel cache HIT
  local what="$1" headers
  shift
  headers="$(http -fsS -o /dev/null -D - "$@")" || fail "$what: request failed"
  grep -qiE '^cache-control:.*no-store' <<<"$headers" || fail "$what: Cache-Control: no-store missing (D61)"
  if grep -qiE '^x-vercel-cache: *HIT' <<<"$headers"; then
    fail "$what: served from Vercel's CDN cache (D61)"
  fi
}
cleanup() { # a failure after step 4 must not leave the smoke booking holding a slot place
  if [[ -n "$BOOKING_ID" ]] && ((CANCELLED == 0)); then
    printf 'Cleaning up: cancelling the smoke booking %s\n' "$BOOKING_ID" >&2
    http -s -o /dev/null -b "$JAR" -X POST "$WEB_URL/api/v1/me/bookings/$BOOKING_ID/actions/cancel" \
      -H 'Content-Type: application/json' -d '{"reason": "smoke test (aborted)"}' || true
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

step "1. Health (direct to the API; no-store and X-Request-ID like every response, spec 03 §1.8)"
HEALTH_STATUS="$(call "$WORK/health.json" -D "$WORK/health.headers" "$API_URL/health")" ||
  fail "GET $API_URL/health: request failed"
[[ "$HEALTH_STATUS" == 200 ]] || fail "GET $API_URL/health -> HTTP $HEALTH_STATUS: $(head -c 300 "$WORK/health.json")"
jq -e '.status == "ok" and .database == "ok"' "$WORK/health.json" >/dev/null ||
  fail '/health body is not {"status": "ok", "database": "ok"} (D84)'
grep -qiE '^cache-control:.*no-store' "$WORK/health.headers" || fail "/health: Cache-Control: no-store missing (D61)"
grep -qi '^x-request-id:' "$WORK/health.headers" || fail "/health: X-Request-ID missing (spec 03 §1.8)"

step "2. Landing page and public shop directory through the web origin's /api rewrite (never cached; shops by slug, D68)"
[[ "$(status "$WEB_URL/")" == 200 ]] || fail "the landing page $WEB_URL/ does not answer 200 (DEP-02)"
SHOPS="$(http -fsS "$WEB_URL/api/v1/public/shops?limit=100")" || fail "GET /api/v1/public/shops"
jq -e '.total >= 6 and .limit == 100' <<<"$SHOPS" >/dev/null ||
  fail "expected >= 6 listed shops (spec 11 SEED-01, DEP-02) and limit=100"
no_store "public shop list (1st request)" "$WEB_URL/api/v1/public/shops?limit=1"
no_store "public shop list (repeat, must not be a cache HIT)" "$WEB_URL/api/v1/public/shops?limit=1"
SHOP_A_ID="$(http -fsS "$WEB_URL/api/v1/public/shops/lahore-auto-care" | jq -r '.id // empty')" ||
  fail "GET /api/v1/public/shops/lahore-auto-care (read only)"
SHOP_B="$(http -fsS "$WEB_URL/api/v1/public/shops/$SMOKE_SHOP_SLUG")" || fail "GET /api/v1/public/shops/$SMOKE_SHOP_SLUG"
SHOP_B_ID="$(jq -r '.id // empty' <<<"$SHOP_B")"
if [[ -z "$SHOP_A_ID" || -z "$SHOP_B_ID" ]]; then
  fail "lahore-auto-care or the smoke-test shop $SMOKE_SHOP_SLUG is not listed"
fi
printf 'Lahore Auto Care: %s   smoke-test shop %s: %s\n' "$SHOP_A_ID" "$SMOKE_SHOP_SLUG" "$SHOP_B_ID"

step "3. Every demo account logs in with $DEMO_PASSWORD; Bilal's cookie reaches /me through the rewrite (DEP-03, D81)"
for who in fatima.owner bilal.sa imran.tech hamza.tech sara.qc hina.qc usman.parts ayesha.customer; do
  login "$who@bayflow.test" >/dev/null || fail "login $who@bayflow.test"
done
SA_TOKEN="$(login bilal.sa@bayflow.test -c "$SA_JAR")" || fail "login bilal.sa@bayflow.test"
grep -q bf_session "$SA_JAR" || fail "login did not set the bf_session cookie through the rewrite (D7, DEP-03)"
http -fsS -b "$SA_JAR" "$WEB_URL/api/v1/me" |
  jq -e --arg a "$SHOP_A_ID" '.email == "bilal.sa@bayflow.test"
    and any(.memberships[]; .shop_id == $a and .role == "SERVICE_ADVISOR")' >/dev/null ||
  fail "GET /api/v1/me with the bf_session cookie does not list Bilal's SERVICE_ADVISOR membership (DEP-03, D81)"
[[ "$(status -H "Authorization: Bearer $SA_TOKEN" "$WEB_URL/api/v1/shops/$SHOP_A_ID/bookings?limit=1")" == 200 ]] ||
  fail "Bilal's Bearer token cannot list Lahore Auto Care bookings"
no_store "staff booking list" -H "Authorization: Bearer $SA_TOKEN" "$WEB_URL/api/v1/shops/$SHOP_A_ID/bookings?limit=1"
TICKET_STATUS="$(call "$WORK/ticket.json" -H "Authorization: Bearer $SA_TOKEN" "$WEB_URL/api/v1/realtime/ticket")" ||
  fail "GET /api/v1/realtime/ticket: request failed"
case "$TICKET_STATUS" in
  200)
    jq -e '.expires_in == 60 and (.ticket | type == "string" and length > 0)' "$WORK/ticket.json" >/dev/null ||
      fail "the WebSocket ticket is not {ticket, expires_in: 60} (D70)"
    ;;
  404)
    if [[ "${SMOKE_REQUIRE_REALTIME:-0}" == 1 ]]; then
      fail "GET /api/v1/realtime/ticket -> 404, but SMOKE_REQUIRE_REALTIME=1 (D88)"
    fi
    printf 'SKIP: the realtime ticket is not deployed yet (P1, D88); 15 s polling is the P0 path (D14)\n'
    ;;
  *) fail "GET /api/v1/realtime/ticket -> HTTP $TICKET_STATUS: $(problem "$WORK/ticket.json")" ;;
esac

step "4. A new customer books at the smoke-test shop through the wizard (public routes by slug, D68; cookie session)"
SERVICE_ID="$(jq -r '.services[0].id // empty' <<<"$SHOP_B")"
[[ -n "$SERVICE_ID" ]] || fail "the smoke-test shop shows no active service"
SLOT=""
for d in 1 2 3 4 5 6 7; do
  DAY="$(date -u -d "+$d day" +%F 2>/dev/null || date -u -v+"$d"d +%F)"
  SLOT="$(http -fsS "$WEB_URL/api/v1/public/shops/$SMOKE_SHOP_SLUG/availability?date=$DAY" |
    jq -r '[.slots[] | select(.remaining > 0)][0].slot_start // empty')" || fail "GET availability for $DAY"
  if [[ -n "$SLOT" ]]; then
    break
  fi
done
[[ -n "$SLOT" ]] || fail "no slot with remaining places at the smoke-test shop in the next 7 days"
EMAIL="smoke+$(date +%s)$RANDOM@bayflow.test"
BODY="$(jq -n --arg shop "$SHOP_B_ID" --arg svc "$SERVICE_ID" --arg slot "$SLOT" --arg email "$EMAIL" '{
    shop_id: $shop, service_ids: [$svc], slot_start: $slot, customer_notes: "smoke test",
    customer: {full_name: "Smoke Test", email: $email, password: "Smoke-Test@2026"},
    vehicle: {registration_number: "SMK-0001", make: "Toyota", model: "Corolla", year: 2018}}')"
CREATE_STATUS="$(call "$WORK/booking.json" -c "$JAR" -X POST "$WEB_URL/api/v1/bookings" \
  -H 'Content-Type: application/json' -d "$BODY")" || fail "POST /api/v1/bookings: request failed"
[[ "$CREATE_STATUS" == 201 ]] || fail "POST /api/v1/bookings -> HTTP $CREATE_STATUS: $(problem "$WORK/booking.json")"
BOOKING_ID="$(jq -r '.booking.id // empty' "$WORK/booking.json")" # BookingCreatedRead nests the booking (spec 03)
[[ -n "$BOOKING_ID" ]] || fail "the booking response has no booking.id (BookingCreatedRead, spec 03)"
jq -e '.booking.status == "PENDING" and .account_created == true and .token_type == "bearer"' \
  "$WORK/booking.json" >/dev/null ||
  fail "the new booking is not PENDING, or the response is not {access_token, token_type, expires_in, account_created, booking}"
grep -q bf_session "$JAR" || fail "Set-Cookie bf_session did not pass through the rewrite (D7)"
printf 'Booked %s (%s) at %s for %s\n' "$(jq -r '.booking.reference' "$WORK/booking.json")" "$BOOKING_ID" "$SLOT" "$EMAIL"

step "5. Tenant isolation: a Lahore Auto Care staff token on a smoke-test shop booking -> 404"
[[ "$(status -H "Authorization: Bearer $SA_TOKEN" "$WEB_URL/api/v1/shops/$SHOP_B_ID/bookings/$BOOKING_ID")" == 404 ]] ||
  fail "the smoke-test shop's route must be 404 for Lahore Auto Care staff"
[[ "$(status -H "Authorization: Bearer $SA_TOKEN" "$WEB_URL/api/v1/shops/$SHOP_A_ID/bookings/$BOOKING_ID")" == 404 ]] ||
  fail "Lahore Auto Care's route must not reveal a smoke-test shop booking"

step "6. Clean up: the customer cancels the smoke booking (frees the slot place)"
CANCEL_STATUS="$(call "$WORK/cancel.json" -b "$JAR" -X POST "$WEB_URL/api/v1/me/bookings/$BOOKING_ID/actions/cancel" \
  -H 'Content-Type: application/json' -d '{"reason": "smoke test"}')" || fail "cancel: request failed"
[[ "$CANCEL_STATUS" == 200 ]] || fail "cancel -> HTTP $CANCEL_STATUS: $(problem "$WORK/cancel.json")"
jq -e '.status == "CANCELLED"' "$WORK/cancel.json" >/dev/null || fail "the smoke booking is not CANCELLED after cancel"
CANCELLED=1

printf '\nSMOKE TEST PASSED\n'
```

## Day-1 verification checklist

Do these on the **first** day, with a "hello world" API and web deployed (brief §10 tip). Record results in spec 16.

| # | Check | How | If it fails |
|---|---|---|---|
| 1 | **`Set-Cookie` passes through the Vercel rewrite** (D7/D8 risk) | `curl -si -X POST https://<web>/api/v1/auth/login -H 'Content-Type: application/json' -d '{"email":"bilal.sa@bayflow.test","password":"BayFlow@2026"}' \| grep -i '^set-cookie'` shows `bf_session=…; HttpOnly; Path=/; SameSite=lax; Secure` and **no** `Domain=`; in a browser, DevTools → Application → Cookies lists `bf_session` for the Vercel domain and later `/api/v1/…` calls succeed. Third-party integrations report first-party cookies through Vercel rewrites ([Sesamy Next.js guide](https://developers.sesamy.com/integrations/frameworks/next-js.html)), but this must be confirmed for us | D7 fallback: keep the token from the login response in memory and send `Authorization: Bearer` (specs 04, 09) |
| 2 | **WebSocket connects directly** (D7, D70; the hub is P1, D88 — on day 1 a throwaway echo socket proves the network path, spec 14) | Browser DevTools → Network → WS: `wss://<api>.up.railway.app/api/v1/ws?ticket=…` returns 101; `ping` → `pong`; an action in a second browser produces `booking.updated` only for users who can see that booking (glossary §11). A ticket older than 60 s is refused before accept — the server closes with 1008, uvicorn answers the upgrade with HTTP 403, so DevTools reports close code **1006** (D70, spec 03 §6.2) — and the client reconnects with a fresh ticket; Railway's logs show `ticket=[redacted]`, never the token | Check `NEXT_PUBLIC_WS_URL` (rebuild after changing), `CLIENT_URL` (Origin check), the domain's target port 4000, the log filter (spec 01) |
| 3 | **PostgreSQL major version parity** (D12) | Railway → `Postgres` → source image tag (`postgres-ssl:<major>`) and the API's startup log line with the server version; must equal `postgres:16` in `docker-compose.yml` and CI | Change both tags to Railway's major on the same day |
| 4 | **Railway pre-deploy command form** (D13) | The deployment details page shows the pre-deploy command with the config-file icon and exactly `/bin/sh -c "alembic upgrade head && python -m app.scripts.seed"`; the deploy logs show Alembic's `Running upgrade … -> <head>` **and** the seed summary (or `seed skipped` when `SEED_ON_DEPLOY` is not `true`); a manual redeploy runs again without duplicates (D51) and repairs the demo cast (D60) | If only Alembic ran, `&&` was not interpreted: try the one-element array form, which the schema also accepts (`["/bin/sh -c \"alembic upgrade head && python -m app.scripts.seed\""]`); last resort, a script that runs both commands (needs a D13 update) |
| 5 | **Health check green** | Railway marks the deployment healthy; `curl -fsS https://<api>.up.railway.app/health` | Check `PORT=4000`, `DATABASE_URL` reference, logs |
| 6 | **Demo logins work** | `make smoke …` step 3 (every demo account with `BayFlow@2026`), then one manual login per role on the web login page | Check `SEED_ON_DEPLOY=true` and the seed logs |
| 7 | **Vercel rewrite caching: `no-store` honoured** (D61) | `curl -s -o /dev/null -D - "https://<web>/api/v1/public/shops?limit=1"` twice: both responses show `cache-control: no-store` and `x-vercel-cache` is never `HIT` (`MISS` or `BYPASS` are fine — values per [Vercel response headers](https://vercel.com/docs/headers/response-headers)); the same on a logged-in call (`/api/v1/me` with the cookie), on an error (an unknown path → 404) and on `/health`; 500s must carry `no-store` and `X-Request-ID` too (spec 03 §1.8); repeating a GET after a change returns fresh data. The smoke test automates the first part and the `/health` headers | Fix the API middleware (and the 500 handler, spec 01); additionally add `apps/web/vercel.json` with a `headers` entry for `/api/:path*` setting `x-vercel-enable-rewrite-caching: 0`, which makes Vercel ignore upstream cache headers on external rewrites ([Vercel rewrites](https://vercel.com/docs/rewrites)) |
| 8 | **Visitor IP header behind two proxies** | Log `x-forwarded-for` and `x-real-ip` for one request through Vercel and one direct; confirm which carries the visitor's IP | Tunes the per-IP ceilings only — the per-account limiter stays primary (D69, spec 04) |
| 9 | **The live URL is public** | Open the production domain in a private window, logged out of Vercel | Use the production domain, not a preview / deployment URL (Deployment Protection) |
| 10 | **No secrets in Git** | CI `secrets` job green; repository push protection enabled; `git ls-files \| grep -E '(^\|/)\.env$'` prints nothing | Rotate any leaked secret |
| 11 | **Outbound e-mail path** (D26) | With `EMAIL_PROVIDER=http`, `EMAIL_API_KEY` and a verified `SMTP_FROM` on Railway: run `notify-ready` on a booking whose customer is a team member's real inbox → the `VEHICLE_READY` e-mail arrives; the same for a `.test` customer → the API logs the reserved-TLD skip and sends nothing; the logs show no SMTP connection attempts (Railway Hobby has no outbound SMTP) | Check the key and the sender domain's verification with the e-mail service; fallback `EMAIL_PROVIDER=none` — in-app notifications are enough for core (brief §5.4) |
| 12 | **Vercel installs with pnpm 10** (D1) | The Vercel build log shows ``Detected `pnpm-lock.yaml` version 9 generated by pnpm@10.x from package.json#packageManager pnpm@10.34.6`` and no Corepack warning | Delete `ENABLE_EXPERIMENTAL_COREPACK` from the Vercel project (Settings → Environment Variables), then redeploy without the build cache. Its symptoms: "Could not enable corepack", "Ignoring not compatible lockfile", `ERR_INVALID_THIS` |

## Dependencies

- [00-overview.md](00-overview.md), [17-decisions.md](17-decisions.md) (D1, D2, D5–D14, D26, D32, D51–D54, D57–D58, D60–D62, D68–D71, D73, D76, D80, D81, D84, D85, D88), [18-glossary.md](18-glossary.md) (§9 paths, §11 realtime, §12 variables and local ports, §13 commits, §14 demo cast), [01-architecture.md](01-architecture.md) (topology, folder layout, middleware incl. `Cache-Control: no-store`, e-mail adapters, OpenAPI export), [03-api-contracts.md](03-api-contracts.md) (`/health`, headers incl. 500s, login, `/me`, booking and availability field names used by the smoke test), [11-seed-data.md](11-seed-data.md) (the smoke-test shop `lyallpur-motors`).
- Used by: [04-auth-and-security.md](04-auth-and-security.md) (cookie flags, Origin check, rate-limit IP), [05-calling-and-ai-front-desk.md](05-calling-and-ai-front-desk.md) (agent service), [09-frontend-and-ux.md](09-frontend-and-ux.md) (`package.json` scripts, client location), [11-seed-data.md](11-seed-data.md) (seed CLI, idempotency), [12-quality-and-testing.md](12-quality-and-testing.md) (CI jobs, test database), [14-roadmap.md](14-roadmap.md) (deploy on day 1), spec 16 — open questions and risks, not written yet (day-1 results).

## Open questions

1. ✅ Resolved by D26: **e-mail in production.** `EMAIL_PROVIDER=http` (HTTPS e-mail API, `EMAIL_API_KEY`) in production, `smtp` with Mailpit locally, `none` by default; reserved/test TLDs are never e-mailed. ✅ The provider is decided in [modules/notifications.md](modules/notifications.md): the `http` adapter targets Resend (`POST https://api.resend.com/emails`, Bearer `EMAIL_API_KEY`, an `Idempotency-Key` per notification; the endpoint is a code constant because the glossary has no URL variable). This spec keeps saying "e.g. Resend": another vendor means another adapter class, not a configuration change. Railway's page recommends Resend and also lists SendGrid, Mailgun and Postmark.
2. ✅ Resolved by D1/D11: **pnpm** is pinned to **10.34.6** (`packageManager` in `apps/web/package.json`); CI uses `pnpm/action-setup@v6` because `pnpm/setup` needs pnpm 11+. Revisit only if Vercel documents pnpm 11. On Vercel, `packageManager` selects the pnpm major and pnpm 10 switches to the exact version itself. Vercel's Corepack mode would need a root `package.json`, which D5 rules out (day-1 check #12).
3. ✅ Resolved by D13: **`preDeployCommand` form** — `/bin/sh -c "alembic upgrade head && python -m app.scripts.seed"`; the schema accepts a string or a one-element array, and we use the string. Day-1 check #4 still confirms that both commands ran.
4. **Rewrite-time `API_BASE_URL`.** Because rewrites are fixed at build time, a new Railway domain requires a Vercel redeploy. Acceptable (glossary §12 records it); noted for the runbook.
5. **Region** for Railway services (closest to Pakistan) and the resulting latency **(unverified)**.
6. **Agent cost and health check** (bonus): whether the always-on worker fits the $5 usage credit; the health endpoint is `/` on port 8081 (spec 05).
7. **Smoke-test field names.** Paths are fixed by glossary §9 and D68 (slug-based public routes, `remaining`); the request/response field names the script reads (`access_token`, `id`, `slug`, `services[].id`, `slots[].start`, `ticket`, `expires_in`, the wizard body shape) must still be confirmed by spec 03. ✅ Resolved by spec 03 (§4.3–§4.6, §8.3) and D81: availability `slots[].slot_start` / `slots[].remaining` (full slots omitted), the booking under `booking` (`booking.id`, `booking.status`) next to `access_token`, `token_type`, `expires_in` and `account_created`, the public shop by slug, and a login body of token + `user` with memberships from `GET /api/v1/me`. The script above uses these names (dry-run against a mock). ✅ Fixed in code (2026-10-09): the committed `scripts/smoke.sh` reads `slots[].slot_start`, books only at `lyallpur-motors` and is the listing verbatim ("As-built status" in §Post-deploy smoke test).
8. ✅ Resolved by D69: **visitor IP for rate limiting** — per-account (e-mail) limits are primary and per-IP limits only a generous ceiling, because many users can share Vercel's egress IPs. Day-1 check #8 still records which header carries the visitor IP so the ceilings can be tuned (spec 04).
9. **Keep `helping-folder/`** (the brief PDF) in the public repo, or replace it with a link if the organisers object.
10. **`start.*` and the seed.** D73 lists "start the DB container, run migrations, start API + web"; this spec also runs the `SEED_ON_DEPLOY`-gated seed in step 3 so a fresh local database has the demo accounts the README promises. Confirm, or drop step 3's seed and tell users to run `make seed` once. ✅ Resolved by D73 (amended 2026-10-09): the start scripts always run the seed script after migrations; it acts only when `SEED_ON_DEPLOY=true`, which `.env.example` sets for local development, and `--seed` forces it. Production keeps setting `SEED_ON_DEPLOY` explicitly on the Railway `api` service (§4).

## Proposed glossary additions

Apart from the generated `schema.d.ts` path (now in glossary §13), none of the items below is in the glossary yet (the 2026-10-09 consolidation merged `POSTGRES_HOST_PORT` and the local dev ports, which this spec never proposed); the rest remain pending. `api:types`, `make gen-api` and the two generated files are already fixed by D76, and the `start.*` scripts by D73, but not yet listed in the glossary.

| Name | Kind | Meaning |
|---|---|---|
| `--force` | CLI flag of `python -m app.scripts.seed` | Seed even when `SEED_ON_DEPLOY` is not `true` (used by `make seed` and `start.* --seed`) |
| `help`, `setup`, `up`, `down`, `db-up`, `migrate`, `seed`, `db-reset`, `api`, `web`, `dev`, `test`, `lint`, `fmt`, `gen-api`, `smoke` | Makefile targets | Developer commands (this spec) |
| `dev`, `build`, `start`, `lint`, `typecheck`, `format`, `format:check`, `test`, `api:types` | `apps/web/package.json` scripts | Called by the Makefile and CI (`api:types`: D76) |
| `start.sh`, `stop.sh`, `start.bat`, `stop.bat`; `logs/`, `.run/`; option `--seed` | Root scripts, their runtime folders and the start option | Native start/stop (D73); `--seed` forces the seed (`--force`) |
| `db`, `migrate`, `api`, `web`, `mailpit` (profile `mail`), `agent` (profile `bonus`); volume `pgdata` | Docker Compose services | Local stack |
| `api`, `Postgres`, `agent` | Railway service names | `api.railway.internal`, `${{Postgres.DATABASE_URL}}` depend on them |
| `apps/api/railway.json`, `apps/agent/railway.json` | Railway config-as-code files | Build/deploy settings |
| `api`, `web`, `contract`, `secrets` | CI job names (`.github/workflows/ci.yml`) | Required status checks |
| `apps/web/src/lib/api/openapi.json`, `apps/web/src/lib/api/schema.d.ts` | Generated files | OpenAPI snapshot and generated TypeScript types (drift-checked). `schema.d.ts` ✅ merged (glossary §13); `openapi.json` pending |
| `scripts/smoke.sh` with inputs `WEB_URL`, `API_URL` | Script + its parameters | Post-deploy smoke test (script inputs, not application configuration); writes only at the smoke-test shop `lyallpur-motors` (spec 11) |
