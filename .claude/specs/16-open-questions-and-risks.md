# 16 — Open Questions & Risks

**Status:** Draft

## Purpose

An adversarial review of the whole spec set (00–18 and `modules/*.md`) as of 2026-10-09, after the final cross-spec consistency sweep. It lists what can still stop BayFlow from being judged well, what only the project owner can decide or do, every question the other specs still leave open, and every name still waiting to be merged into [18-glossary.md](18-glossary.md). Specs 07 and 14 record their day-1 results, kickoff decisions and cuts here (section F).

**How to read this.** Section A = prioritised **risks** (description, impact on judging, likelihood, mitigation, owner and phase, and the check or test that detects it). Section B = **decisions only the owner can take**. Section C = **every open question of every spec**, still open or resolved. Section D = **pending glossary additions**, grouped for one merge. Section E = the **"if you fix only five things"** list. Section F = the records other specs keep here.

**Severity** uses the D36 labels so they mean the same thing everywhere: a **P0** risk threatens a P0 deliverable (the core flow on the live URL, the submission rules of brief §9.1); **P1** would visibly cost points or force rework; **P2** touches the bonus track or an optional extra; **P3** is polish or post-hackathon. Phases are spec 14's PH0…PH10 and checkpoints CP1…CP5 (D75). "Day-1 #n" is check n of spec 07's day-1 verification checklist; test IDs are spec 12's.

> **Reviewer's summary.** The design is coherent: specs 03/04/05/06/09/10/11 and the module specs now agree with D1–D89 and the glossary, and the remaining conflicts are few and listed in C.3. D90 has since settled how the P1 realtime hub, the e-mail sender and the bonus call ports reach their handlers under D89's wiring convention (through `uow.app_state`), and D91 that notification recipients are literal; the one open design point left is how the calls router builds its conditional routes (C.1). The dangerous items are not in the design. They are: (1) **nothing is deployed yet**, while the brief says "deploy early" and the live URL carries the score; (2) the repository is **private and has one bulk commit**, while the brief demands a public repo with "meaningful commit history (not a single commit)"; (3) five **platform assumptions** (cookie through the Vercel rewrite, edge caching, Railway's pre-deploy form, PostgreSQL version, SMTP) are unverified until a real deploy exists; (4) **shared live data** will drift and can be vandalised during judging; (5) the deadline and team size are still unknown, so no schedule is fixed.

---

## A. Prioritised risks

### A0 — Day-1 platform checks at a glance

Every row is a spec 07 day-1 check (run with a "hello world" deploy, results in section F.1) and the risk it settles.

| Day-1 | What is verified | Risk | Fallback if it fails |
|---|---|---|---|
| #1 | `Set-Cookie: bf_session` survives the Vercel → Railway rewrite and is stored host-only | A3 | Bearer token kept in memory (D7, spec 09 §2.8 `AUTH_TRANSPORT`) |
| #2 | The browser opens `wss://<api>/api/v1/ws` directly (P1 layer, D88) | A20 | Polling only (D14); no bonus calling |
| #3 | Railway's PostgreSQL major equals `postgres:16` (local, CI) | A6 | Move local and CI images to Railway's major the same day |
| #4 | The pre-deploy command runs **both** `alembic upgrade head` and the seed (`/bin/sh -c "…"`) | A5 | One-element array form, then a script (needs a D13 update) |
| #5 | Railway health check green on `/health` | A1 | `PORT`, `DATABASE_URL` reference, logs |
| #6 | Every demo account logs in on the live URL | A5, A8 | `SEED_ON_DEPLOY=true`, seed logs |
| #7 | `Cache-Control: no-store` honoured through the rewrite; `x-vercel-cache` never `HIT` | A4 | Fix the middleware; add `x-vercel-enable-rewrite-caching: 0` for `/api/:path*` |
| #8 | Which header carries the visitor IP behind two proxies | A24 | Tune the per-IP ceilings only (the per-account limiter is primary, D69) |
| #9 | The production URL is public (no Deployment Protection) | A1 | Use the production domain, not a preview URL |
| #10 | No secrets in Git, push protection on | A2 | Rotate anything exposed |
| #11 | Outbound e-mail through the HTTPS API; no SMTP attempts (Railway Hobby blocks SMTP) | A7 | `EMAIL_PROVIDER=none` (in-app is enough for core) |
| #12 | Vercel installs with pnpm 10 | A1 | Delete `ENABLE_EXPERIMENTAL_COREPACK` from the Vercel project and redeploy without cache |

### A1 — Nothing is deployed yet (P0)

- **Description.** `README.md` still says "Live URL: *to be added after the first deploy*". The foundation code exists locally (API, web, migration, seed), but no Railway or Vercel project serves it. The brief: "Tip: deploy early and keep deploying. Teams that deploy at the last hour usually discover environment problems too late" and "A smaller, correct, deployed product beats a large broken one".
- **Impact on judging.** Without a live URL, "Core flow completeness" (35 %) and "Deployment and docs" (10 %) cannot be earned, and the bonus never counts (brief FAQ). Every risk A3–A7 stays unverified until a deploy exists.
- **Likelihood.** High if deployment waits for features; low once the walking skeleton is up.
- **Mitigation.** Deploy the walking skeleton now (spec 14 PH0, CP1): API `/health` + the empty web app + PostgreSQL, with CI and Railway's "Wait for CI". Every merge to `main` deploys afterwards (spec 14 §6). Use the production domain (day-1 #9). ✅ Fixed on 2026-10-09: `scripts/smoke.sh` now reads `slots[].slot_start`, books only at `lyallpur-motors`, checks DEP-02 and DEP-03, skips the realtime ticket check on 404 (D88) unless `SMOKE_REQUIRE_REALTIME=1`, and cancels its booking through an exit trap when a later step fails (C.3).
- **Owner / phase.** Platform person (spec 14 §4.5 role A); PH0, CP1. Needs the accounts of decision B2.
- **Detected by.** DEP-01, DEP-02, DEP-05, DEP-06; day-1 #5, #9, #12.

### A2 — The repository is private and holds one bulk commit (P0)

- **Description.** The owner ran `git init` on 2026-10-09 at 15:45: one commit (`59e1864`, "first commit", 271 files) pushed to `origin` `main` (`github.com/Haseebraza12/bayflow-loopverse-hackhathon-`). An anonymous request to the repository answers 404, so it is **private**. Brief §9.1 requires a "Public repo with meaningful commit history (not a single commit), organized folders, and no committed secrets", and §9.4 "Sensible commit messages and small commits". The first commit message is not a Conventional Commit (D53). `.env` is correctly untracked; `.claude/specs/` and `helping-folder/` are tracked.
- **Impact on judging.** A "must submit" item. A private link or a single squashed commit can fail the submission check and costs "Architecture and code quality" (20 %) credibility.
- **Likelihood.** Certain unless acted on; easy to fix.
- **Mitigation.** From now on, small Conventional Commits per feature from every member (never squash the history into one commit); branch protection with CI required. Before flipping to public: run the gitleaks full-history scan (DEP-14) and decide what stays public (decision B1). Make it public before the deadline and check the link while logged out (spec 14 §7).
- **Owner / phase.** The owner (B1) for visibility; every member for commits; PH0 onward, final check in PH10.
- **Detected by.** DEP-14; spec 14 §7 submission checklist; `git log --oneline | wc -l` at each checkpoint.

### A3 — `Set-Cookie` lost through the Vercel rewrite (P0)

- **Description.** The browser talks only to the Vercel origin, which rewrites `/api/*` to Railway (D7). The session lives in the httpOnly cookie `bf_session` set by the API (D8). That the `Set-Cookie` header passes through Vercel's external rewrite and is stored host-only is reported by third parties but unverified for us.
- **Impact on judging.** If it fails, every login silently loses its session: no role dashboard works, so the core flow (35 %) fails.
- **Likelihood.** Low to medium.
- **Mitigation.** Day-1 #1 settles it in minutes. Fallback already designed: `AUTH_TRANSPORT = 'bearer'` keeps the `access_token` from login, owner registration and booking responses in memory (never in storage) and sends `Authorization: Bearer` (D7, D32, spec 04, spec 09 §2.8).
- **Owner / phase.** Platform person; PH0 (CP1).
- **Detected by.** Day-1 #1; DEP-03 on every deploy.

### A4 — Vercel caches API responses at the edge (P0)

- **Description.** For projects created on or after 2026-04-06, Vercel caches external-rewrite responses that carry cache headers by default (D61). A cacheable `/api/v1/me` or booking response could be served to another visitor.
- **Impact on judging.** A cross-user data leak in front of judges ("Multi-tenancy and security", 10 %), and stale screens that look like broken state transitions.
- **Likelihood.** Low while every response sends `Cache-Control: no-store`; high for any path that misses it (e.g. a 500 rendered outside the middleware, spec 03 §1.8).
- **Mitigation.** `no-store` on every `/api/*` response and on `/health`, including errors and 500s (D61, spec 03 §1.8, spec 04 headers). Optionally `x-vercel-enable-rewrite-caching: 0` for `/api/:path*` (spec 04 open question 12), decided after day-1 #7.
- **Owner / phase.** API foundation (done in code per D84); verified in PH0.
- **Detected by.** Day-1 #7; API-13, DEP-15, SEC-32.

### A5 — Railway pre-deploy command or config file not applied (P0)

- **Description.** Migrations and the seed run in Railway's pre-deploy step as `/bin/sh -c "alembic upgrade head && python -m app.scripts.seed"` (D13), because Railway runs Dockerfile commands in exec form. `apps/api/railway.json` already uses this string. Two traps: if `&&` is not interpreted only Alembic runs, and Railway's config file does **not** follow the service's Root Directory, so its absolute path `/apps/api/railway.json` must be set in the service settings (spec 07).
- **Impact on judging.** No seed → no demo accounts → judges cannot log in (brief §7.7, §9.1: "seeded demo data and demo accounts for every role").
- **Likelihood.** Medium on the first deploy; nil once verified.
- **Mitigation.** Day-1 #4 (both commands in the deploy log), #6 (demo logins); keep the config-file path in spec 07's Railway table; the seed exits non-zero on failure, so a broken seed stops the deploy instead of shipping an empty site; `SEED_ON_DEPLOY=false` is the emergency switch.
- **Owner / phase.** Platform person; PH0, re-checked at CP1 and in PH10.
- **Detected by.** Day-1 #4, #6; DEP-06, DEP-07; SEED-09.

### A6 — PostgreSQL version drift between Railway, local and CI (P1)

- **Description.** D12 assumes Railway's managed PostgreSQL is 16, matching `postgres:16` in `docker-compose.yml` and CI. The baseline migration relies on identity columns, partial unique indexes and append-only triggers (spec 02).
- **Impact on judging.** A deploy that fails or behaves differently from the tested database, found late.
- **Likelihood.** Low.
- **Mitigation.** Day-1 #3 (`SHOW server_version`); if Railway's major differs, move local and CI to it the same day.
- **Owner / phase.** Platform person; PH0.
- **Detected by.** Day-1 #3; DEP-05.

### A7 — Railway Hobby blocks outbound SMTP (P2)

- **Description.** Railway's Hobby plan has no outbound SMTP (D26). E-mail is an optional P1 extra for `ESTIMATE_SENT` and `VEHICLE_READY`; production must use `EMAIL_PROVIDER=http` (the adapter targets Resend, `modules/notifications.md`) or `none`.
- **Impact on judging.** Small: in-app notifications are "enough for core" (brief §5.4). The risk is time lost debugging a silent SMTP failure.
- **Likelihood.** Certain for SMTP; avoided by design.
- **Mitigation.** Never configure `smtp` on Railway; `http` only with a verified sender domain and `EMAIL_API_KEY` (decision B5), else `none`. Reserved TLDs (`.test`) are never e-mailed, so demo accounts are never affected.
- **Owner / phase.** Notifications owner; P1, only after the core works.
- **Detected by.** Day-1 #11; NOT-09.

### A8 — Shared demo data drifts and can be vandalised during judging (P0)

- **Description.** All judges use the same live database. Each worked-example replay consumes one oil filter and one engine oil and fills a Friday 10:00 place (capacity 2); a cancelled replay can leave an orphan coil PO whose receipt puts a coil into stock (D71). One judge can deactivate Bilal or change Usman's password (D60). Seeded `BF-SEEDnn` bookings stay where judges leave them.
- **Impact on judging.** A judge who cannot finish the worked example scores the core flow (35 %) low, even though the product works.
- **Likelihood.** High once several judges test.
- **Mitigation.** Accepted drift (D71) with judge notes in the README and on the login page (pick another slot; Usman can **Adjust stock**, P0 by D82); automation books only at the smoke-test shop Lyallpur Motors (spec 11); every seed run — i.e. every redeploy — repairs the demo cast: users active, memberships active with canonical roles, password `BayFlow@2026` (D60); the README asks judges not to deactivate the shared cast and to use Hamza or Hina for that.
- **Owner / phase.** Seed owner and README owner; PH1 (reconciliation), PH7 (judge notes), PH10 (final check).
- **Detected by.** DEP-07, DEP-08 (read-only drift check), SEED-14, SEED-19.

### A9 — Deadline and team size are unknown (P1)

- **Description.** The brief states neither the hackathon duration nor the team size (spec 00). Spec 14 offers a 48-hour and a 7-day schedule and four team splits but cannot pick one. The submission mechanics (deadline time zone, repository state vs tagged commit, live demo slot) are also unknown (spec 14 open question 2).
- **Impact on judging.** Without a schedule, checkpoints CP1–CP5 have no dates, cuts happen too late, and the bonus may eat core time.
- **Likelihood.** Certain until the owner answers.
- **Mitigation.** Decision B3 at kickoff; record it in section F.2; then apply spec 14 §4.4/§4.5 and its cut list (§5).
- **Owner / phase.** The owner; kickoff.
- **Detected by.** Section F.2 still empty.

### A10 — One API replica holds all realtime and rate-limit state (P1)

- **Description.** The WebSocket hub, presence (who is online for call ringing) and the rate-limit counters live in memory in one API process (D14, D69). A second replica would split sockets and counters; every redeploy drops all sockets and resets the counters.
- **Impact on judging.** Missing live updates or calls that ring nobody, if someone scales the service out; brief windows of reconnection after each deploy.
- **Likelihood.** Low (nobody needs a second replica for hackathon load); redeploy resets are certain but harmless.
- **Mitigation.** Keep the Railway `api` service at one replica; polling every 15 s runs whatever the socket does (D14, D88); clients reconnect with a fresh ticket (D70); call deadlines live in the database and the sweeper uses `FOR UPDATE SKIP LOCKED` (spec 05 §3.5); the call-start limit is counted from `call_logs`, so it survives restarts. Scaling out means Redis (spec 04 Tier 3).
- **Owner / phase.** Platform person; PH0 (setting), PH6/PH8 (hub).
- **Detected by.** Railway service settings; NOT-08 and DEP-04 after a redeploy.

### A11 — Judges may read the brief's ambiguous points differently (P1)

- **Description.** Four interpretations are visible in the demo:
  - **D16 Owner powers:** the Owner manages everything and performs every Service Advisor action, but opens the Technician, Parts and QC views read-only and gets 403 on their actions (brief §4 "can do everything" vs §7.5/§7.8 "No role can perform another role's action").
  - **D23/D24 statuses without a row in §5.2:** from `ESTIMATE_REJECTED` the SA can revise, return to the technician or cancel; `CANCELLED` is terminal and releases parts and the slot.
  - **D25:** the Parts Person's `ALLOCATE_PARTS` moves `PARTS_READY → IN_REPAIR`; the technician's "start repair" only stamps `repair_started_at`.
  - **D31:** labour-only jobs still pass `mark-parts-ready` and `allocate-parts` with zero parts.
- **Impact on judging.** A judge expecting "the Owner can do everything" or a technician-driven `IN_REPAIR` may report a bug instead of a deliberate rule ("Core flow completeness", 35 %).
- **Likelihood.** Medium.
- **Mitigation.** A short "Design decisions" section in the README quoting the brief lines behind each choice (spec 07 README); the Owner's role views carry the read-only banner (spec 09 §4.11); the seeded BF-SEED04 shows a labour-only job; the demo video narrates the Owner's read-only views.
- **Owner / phase.** README owner; PH7.
- **Detected by.** DEP-09 judge-path rehearsal with someone outside the team.

### A12 — A QC pick held by a deactivated inspector leaves the booking stuck (P2)

- **Description.** If a QC inspector is deactivated while holding a `QC_IN_PROGRESS` pick, nobody can pass or fail the job: only the picker may, and spec 08 has no un-pick (D87). D87 plans `REASSIGN_QC_INSPECTOR` (P1, with the other reassign operations). Its implementation also needs a qc function that moves the open `qc_inspections` round to the new inspector, because qc treats "open round's inspector ≠ caller" as a data-integrity error (`modules/qc.md`).
- **Impact on judging.** A judge testing deactivation on Hina or Sara mid-inspection sees a stuck job.
- **Likelihood.** Low.
- **Mitigation.** Until D87 ships: the Owner reactivates the inspector, who finishes the round; every seed run reactivates demo memberships anyway (D60); the team view shows `open_jobs`, so the Owner is warned before deactivating; judge notes say "use Hamza or Hina, and reactivate afterwards".
- **Owner / phase.** Bookings + qc owners; P1 (D87), after PH6.
- **Detected by.** A P1 test to add with D87 (spec 12); SEED-19 for the reactivation path.

### A13 — `low_stock_count` counts `LOW` and `OUT` together (P2)

- **Description.** `OverviewRead.inventory.low_stock_count` and `OwnerShopSummary.low_stock_count` count active parts that are `LOW` **or** `OUT` (spec 03 §3.7); the web must show "Low" as `low_stock_count − out_of_stock_count` (`modules/reporting.md` open question 1).
- **Impact on judging.** An owner tile that double counts looks like wrong inventory data (brief §7.4 Owner "inventory summary").
- **Likelihood.** Medium (easy to misread the field name).
- **Mitigation.** Keep the definition, document the UI formula in spec 10 O-01, assert it in RPT-06 and against the seeded numbers (Lahore Auto Care: 3 OUT + 3 LOW = 6).
- **Owner / phase.** Reporting + owner-screen owners; PH6.
- **Detected by.** RPT-06; SEED-12/SEED-18 numbers on the overview.

### A14 — The Base-UI-free picker pattern can regress (P3)

- **Description.** shadcn switched its default base to Base UI in July 2026; we pin Radix (D1). shadcn's generated `combobox` uses Base UI's `Combobox` even on the Radix base, so it was removed with `@base-ui/react`; searchable pickers use `Popover` + `Command` (cmdk) (spec 09 §3.12, spec 10 PP-04). Today `apps/web/package.json` has `cmdk` and `radix-ui` and no `@base-ui/react`.
- **Impact on judging.** Mixed primitives (`asChild` vs `render`) cause focus and keyboard bugs in the estimate editor's part picker and the PO dialog, which are on the judge path.
- **Likelihood.** Medium: `shadcn add combobox`, a docs snippet or an AI suggestion brings it back.
- **Mitigation.** A CI check that fails when `@base-ui/react` appears in `apps/web/package.json` or any import; reviewers reject `combobox` additions.
- **Owner / phase.** Web foundation owner; PH0 (CI rule).
- **Detected by.** The proposed CI grep; WEB lint.

### A15 — The Windows scripts have never run on Windows (P2)

- **Description.** `start.bat` / `stop.bat` (D73) were written and reviewed but never executed on Windows; spec 12 DEV-01 is P1 and "by hand on Windows". Batch files are fragile (CRLF, labels, quoting; the repo path even contains parentheses).
- **Impact on judging.** "README and `.env.example` let a stranger run it in minutes" (10 %): a judge on Windows who follows the README and fails.
- **Likelihood.** Medium.
- **Mitigation.** Run DEV-01 on a real Windows machine before CP5; the README keeps the alternatives (Docker Compose "Option A", WSL2); `.gitattributes` forces CRLF for `.bat` files (spec 07).
- **Owner / phase.** Platform person; PH7.
- **Detected by.** DEV-01 on Windows.

### A16 — The macOS path of `start.sh` was only tested with bash 3.2 on Linux (P2)

- **Description.** `start.sh` / `stop.sh` claim macOS compatibility (bash 3.2, no `setsid`, `lsof` instead of `/proc`), but they were exercised only by running bash 3.2 on Linux, never on a Mac with BSD tools.
- **Impact on judging.** As A15, for judges on macOS — likely the most common judge laptop.
- **Likelihood.** Medium.
- **Mitigation.** One run on a real Mac before CP5, or a CI job on `macos-latest` that runs `shellcheck` and `./start.sh --help` plus the port-freeing helpers; README fallback `docker compose up`.
- **Owner / phase.** Platform person; PH7.
- **Detected by.** DEV-01 on macOS.

### A17 — LiveKit's free Build plan is a hard cap (P2, bonus)

- **Description.** The Build plan includes 5,000 WebRTC participant-minutes, 1,000 agent-session minutes (Cloud-deployed agents only) and 5 concurrent agent sessions per month; past the allowance "new requests fail", and free projects share allowances across all of a user's free projects (spec 05 §11.1, [P1]–[P3]). How a self-hosted agent is metered is not documented (spec 05 open question 6).
- **Impact on judging.** "Bonus features" (10 %): calling dies on demo day if another free project of the same account used the minutes.
- **Likelihood.** Low for hackathon traffic (≈ 790 three-minute calls per month); higher if the account is shared.
- **Mitigation.** A dedicated LiveKit account for the demo; the app cap `CALL_MONTHLY_MINUTES_CAP` (4,000) answers 503 `CALLING_DISABLED` before LiveKit's cap; calling degrades cleanly when disabled (spec 05 §12).
- **Owner / phase.** Bonus owner; B0 prep, PH8.
- **Detected by.** CALL-12 (cap → 503); LiveKit usage page before the demo.

### A18 — OpenAI cost on a public demo site (P2, bonus)

- **Description.** A typical three-minute AI call costs about $0.073 (≈ $0.024 per minute) with `gpt-realtime-2.1-mini`, up to about $0.13 at the five-minute cap (spec 05 §11.2). Anyone can create a customer account and call.
- **Impact on judging.** Budget exhaustion mid-judging makes the AI Front Desk fail ("Bonus features", 10 %).
- **Likelihood.** Low with the caps; the hard cap itself is unverified.
- **Mitigation.** Prepaid credit with auto-recharge off — whether this is a hard spending cap is unverified (spec 05 [P30]); `AI_DAILY_CALL_CAP` (100 AI legs per day); call starts limited to 5 per caller per 10 minutes (D69); a failed AI leg still leaves a `CALLBACK` task (spec 05 §12).
- **Owner / phase.** Owner (B2 account, B4 bonus); B0 prep, PH9.
- **Detected by.** CALL-12; FD-09/FD-11 (fallbacks); the OpenAI usage page before the demo.

### A19 — The start scripts free ports 3000 and 4000 from any program (P3)

- **Description.** At the owner's request, `start.*` (through `stop.* --keep-db --quiet`) and `stop.*` stop whatever listens on 3000 or 4000 (D73, amended), naming it in the output. The exceptions are other Docker containers, Docker/VM/SSH port forwarders and other users' processes; for those the script names the holder and exits.
- **Impact on judging.** A judge's own dev server on port 3000 would be stopped without asking.
- **Likelihood.** Low.
- **Mitigation.** ✅ Done on 2026-10-09: the README says so where it lists what the scripts do and in Troubleshooting, and the `stop.*` help texts no longer claim `--bayflow-only` is used by start; the output names the program it stopped.
- **Owner / phase.** README owner; done, re-checked in PH7.
- **Detected by.** DEV-01.

### A20 — The realtime layer is P1 but the bonus depends on it (P2)

- **Description.** D88 makes the WebSocket hub, `GET /api/v1/realtime/ticket` and `/api/v1/ws` P1; the P0 product runs on 15 s polling. In-app calling (P2) needs the hub for `call.incoming`, `call.updated`, presence and `task.created`. The socket connects straight to Railway (D7), which is verified only by day-1 #2.
- **Impact on judging.** If the realtime layer slips, calling cannot be built; core scores are unaffected.
- **Likelihood.** Low to medium.
- **Mitigation.** Day-1 #2 with a throwaway echo socket (spec 14 PH0); spec 05's B0 gate requires the P1 layer live before B1; spec 14's cut list cuts the socket with the other P1 extras while polling stays. ✅ How the hub and the e-mail sender reach the notifications handlers under D89 is settled by D90: one hub and one sender per app, created on first use by `get_realtime_hub(state)` / `get_email_sender(state)` and reached through `uow.app_state` (`modules/notifications.md` open question 7; the ports half of `modules/calls.md` open question 2).
- **Owner / phase.** Notifications owner (the D89 question is settled by D90); PH6 (P1), before PH8.
- **Detected by.** Day-1 #2; DEP-04; NOT-08, SEC-33.

### A21 — Specs and parallel implementation drift apart (P1)

- **Description.** Implementation started while the last specs were written (D72), several agents edited specs in parallel today, and D89 (module wiring by convention) arrived during this sweep. Known leftovers are listed in C.3, and the part of the D89 injection question that D90 left open (the calls router's conditional routes) in C.1.
- **Impact on judging.** Contract mismatches surface as UI bugs on the live URL or as failing CI late in the schedule.
- **Likelihood.** Medium.
- **Mitigation.** Spec 03 is the contract and WEB-07 fails CI when the generated types drift (D76); merge section D into the glossary in one pass; settle C.3 before the module phases that touch those files.
- **Owner / phase.** Coordinator; now, then at each checkpoint.
- **Detected by.** WEB-07; the C.3 list.

### A22 — Bonus work starts before the core is live (P1)

- **Description.** The bonus is tempting and visible, but brief §8 says "Do not start them until the core flow works end to end", and bonus points "only count if the core flow works" (FAQ).
- **Impact on judging.** A half-finished core loses far more (35 % + 15 %) than a bonus can add (10 %).
- **Likelihood.** Medium in a larger team.
- **Mitigation.** D36's hard gate (CP4); spec 14 keeps the stricter PH7-exit default; only zero-risk prep (accounts, keys) before B0 (spec 05 §16).
- **Owner / phase.** Owner and coordinator; CP3–CP4.
- **Detected by.** Spec 14 checkpoints; DEP-09 passing before any PH8 merge.

### A23 — Build-time web variables need a redeploy to change (P3)

- **Description.** `API_BASE_URL` (the rewrite destination) and every `NEXT_PUBLIC_*` value are fixed at build time on Vercel (glossary §12, spec 07 open question 4).
- **Impact on judging.** A changed Railway domain silently breaks the site until the web is redeployed.
- **Likelihood.** Low.
- **Mitigation.** The Vercel build fails without them (spec 09 §2.5); the runbook says "change → redeploy"; keep the Railway domain stable.
- **Owner / phase.** Platform person; PH0, PH10.
- **Detected by.** DEP-02, DEP-03 after every deploy.

### A24 — Shared egress IPs behind Vercel (P3)

- **Description.** Requests through the rewrite may reach Railway from Vercel's shared egress, so per-IP limits could group unrelated visitors (D69).
- **Impact on judging.** A judge hitting a 429 on login while another judge is active.
- **Likelihood.** Low: per-IP limits are generous ceilings; the per-account limiter is primary.
- **Mitigation.** Day-1 #8 tells which header carries the visitor IP; tune the ceilings, never lower them blindly.
- **Owner / phase.** Platform person; PH0.
- **Detected by.** Day-1 #8; SEC-27.

### A25 — The landing page ships GarageBox's own assets and claims (P1)

- **Description.** D101 takes GarageBox's fonts and palette as values only — never its name, logo, images or copy. The landing page and its footer predate D101 (commit `8559517`, "use Ibrahim's UI as-is") and still carry GarageBox material: 14 files in `apps/web/public/garagebox/` (the hero images, three feature illustrations, a phone mock-up, two app-store badges and six review-site logos; the hero's code comment says its image was taken from garagebox.io), the line "5-Star Rated based on 200+ reviews" beside those review-site logos, app-store badges for apps BayFlow does not have, and the footer's `support@garagebox.io`.
- **Impact on judging.** A judge who knows garagebox.io, or who writes to the footer address, sees copied material and claims BayFlow cannot back up; once the repository is public (B1) the copied images are also a copyright exposure. Product & UX is 15 % (brief §10).
- **Likelihood.** Medium: the hero and the footer are the first and last things a judge sees.
- **Mitigation.** Replace the `public/garagebox/` images with BayFlow's own screenshots or openly licensed images with their sources recorded (as the booking flow did for its shop photos in `apps/web/src/lib/shop-photos.ts`); drop the review count, the review-site logos and the app-store badges; use a BayFlow contact address. Keep the fonts and the palette (D101).
- **Owner / phase.** The owner (the landing was kept "as-is" on request, so changing it is the owner's call) and the web owner; before the repository goes public (B1) and before submission.
- **Detected by.** `apps/web/public/garagebox/` is gone; `grep -rni garagebox apps/web/src` finds code comments only.
- **Status (2026-10-10): OPEN — owner chose to keep the previous landing, 2026-10-10.** `ef510c5` had replaced this material; it was reverted, so the landing, its header and footer are the previous versions again and both checks above currently fail. Per `ef510c5`'s own commit message, the previous landing also carries the hero images' "4X / 60% / 40%" figures, testimonial photos of unknown provenance (`public/testimonials/`), features BayFlow lacks (invoicing, SMS/WhatsApp, payments, labour tracking, native apps, live chat, data migration), GarageBox's real e-mail and phone, legal links to pages that don't exist and a carousel with a missing image. It also has no link to the shop directory `/book` (spec 10 P-01, G1).

---

## B. Open decisions for the owner

### B1 — Make the repository public, keep a real commit history, and choose what is published

- **Why it matters.** Brief §9.1 (A2). The repository is private today and holds one bulk commit.
- **Options.** (a) Make it public now and grow the history with small Conventional Commits; (b) keep it private until the deadline and flip it at submission.
- **Recommendation.** (a) as soon as the gitleaks full-history scan is clean (DEP-14), so the history is visibly incremental. Keep `.claude/specs/` public (spec 14 open question 4: it shows the spec-driven process) and keep `helping-folder/` (the brief PDF) unless the organisers object (spec 07 open question 9).

### B2 — Create the hosting accounts and authorise the connectors

- **Why it matters.** Nothing can be deployed without them (A1), and day 1 depends on them.
- **What is needed.** Railway (Hobby, $5/month, D6) with the GitHub repository connected and "Wait for CI"; Vercel (Hobby) with root directory `apps/web`; the **claude.ai Vercel connector** must be authorised in the claude.ai connector settings before an agent can inspect deployments (it reported "needs authentication" in this session). For the bonus only, and only as B0 prep: a dedicated LiveKit Cloud account (A17) and an OpenAI key with prepaid credit and auto-recharge off (A18).
- **Recommendation.** Today, before any further feature work.

### B3 — Hackathon deadline, time zone, team size and submission mechanics

- **Why it matters.** A9: spec 14 cannot pick a schedule or a team split without them (specs 00, 01 open question 5, 14 open questions 1–2).
- **Recommendation.** Answer at kickoff and record the answers in section F.2; spec 14 §4.4/§4.5 then fixes the checkpoints.

### B4 — Build the bonus track or not

- **Why it matters.** 10 % of the score, judged separately and only if the core works (brief §8, FAQ).
- **Options.** (a) No bonus; (b) in-app calling only (PH8); (c) calling + AI Front Desk (PH8 + PH9).
- **Recommendation.** Decide at CP4 from the actual state: (b) when CP4 is met with time to spare, (c) only when PH7 exits early. Spec 05 B0 also requires the P1 realtime layer live first (D88).

### B5 — E-mail in production

- **Why it matters.** E-mail is an optional extra (brief §5.4); Railway Hobby blocks SMTP (A7).
- **Options.** (a) `EMAIL_PROVIDER=none` (in-app only); (b) `http` with Resend: an account, a verified sender domain for `SMTP_FROM`, and `EMAIL_API_KEY` (`modules/notifications.md`).
- **Recommendation.** (a) for the core; (b) only if a domain is available and P0 is done.

### B6 — Urdu for the AI Front Desk

- **Why it matters.** Pakistani customers; but untested speech quality could embarrass the demo (spec 05 open question 5, spec 13 open question 3).
- **Recommendation.** English for the demo; test Urdu / Roman Urdu only after B7 of spec 05 and enable it only if a native speaker approves the result.

### B7 — Railway region

- **Why it matters.** Latency from Pakistan and from the judges' location (spec 07 open question 5, unverified).
- **Recommendation.** The region closest to the judges if known, otherwise the one closest to Pakistan; measure once on day 1.

### B8 — Small product rules (defaults proposed; confirm or change)

| Question | Proposed default | Source |
|---|---|---|
| Cap active bookings per customer per shop? | No cap for the hackathon; rate limits suffice | spec 04 open question 9 |
| `Idempotency-Key` on booking creation? | Not in P0; P1 only if cheap (the wizard disables its button meanwhile) | spec 03 open question 2, spec 09 open question 8 |
| Quick-add common services on O-03? | ✅ Built 2026-10-10: kept — a new service's sheet suggests the brief's §5.1 examples the shop lacks; the owner sets the price | spec 10 open question 7 (resolved) |
| Fonts | ✅ Decided by D101: Fira Sans for all text, Edu NSW ACT Foundation for one handwritten accent word, JetBrains Mono for codes (garagebox.io's fonts, owner request 2026-10-10) | spec 09 open question 5 (resolved) |
| Purchase orders that will never arrive | Accept: no cancel/close status (brief statuses only) | `modules/inventory.md` open question 4 |
| Notify the actor when they are also the booking's customer | ✅ Decided by D91: glossary §6 is applied literally and the actor is not excluded | `modules/notifications.md` open question 3 (resolved) |
| Re-validate deactivated parts when the SA sends an estimate | Keep: the saved line is what the SA reviewed | `modules/estimates.md` open question 2 |
| Re-booking keeps stored `color` / `mileage_km` when omitted | Keep | `modules/bookings.md` open question 7 |
| "Within 30 days" for slots | Whole shop-local days (today + 30), matching the calendar | `modules/scheduling.md` open question 1 |

---

## C. Open questions collected from every spec

### C.1 Still open

| Spec · item | Question | Decides | Proposed answer / next step |
|---|---|---|---|
| 00 · single; 01 · 5; 14 · 1 | Hackathon duration and team size | Owner (B3) | Record in F.2 at kickoff |
| 14 · 2 | Submission mechanics: deadline time zone, repository state vs tagged commit, live demo slot | Owner (B3) | Ask the organisers; record in F.2 |
| 14 · 4; 07 · 9 | Keep `.claude/specs/` and `helping-folder/` in the public repository | Owner (B1) | Keep both unless the organisers object |
| 03 · 2; 09 · 8; bookings · 10 | `Idempotency-Key` on `POST /api/v1/bookings` | Owner (B8) | Not in P0 |
| 03 · 3; shops · 7 | Membership items carry no shop city or time zone | Coordinator | Keep the extra `GET /api/v1/shops/{shop_id}` in `ShopScope` |
| 04 · 9; bookings · 10 | Cap active bookings per customer per shop | Owner (B8) | No cap |
| 04 · 10 | Vercel preview origins vs the single `CLIENT_URL` | Coordinator | Accept; judging uses production |
| 04 · 11 | `__Host-` cookie prefix | Coordinator | Tier 3 |
| 04 · 12 | `x-vercel-enable-rewrite-caching: 0` for `/api/:path*` | Platform person | Decide after day-1 #7 (A4) |
| 05 · 3 | No reschedule action: a `RESCHEDULE_REQUEST` task ends in cancel + re-book | Coordinator | P3 operation in spec 08 later |
| 05 · 5 | Urdu / Roman Urdu for the demo | Owner (B6) | English only unless tested |
| 05 · 6 | Do self-hosted agents consume WebRTC participant-minutes? | Bonus owner | Assume yes (the cap is computed that way); check LiveKit usage at B4 |
| 05 · 7 | Transcript retention and deletion | Coordinator | P3 (spec 13 AI-41) |
| 05 · 9 | Gemini fallback: summary path untested | Bonus owner | Use OpenAI for the demo |
| 06 · 3 | Membership changes are not pushed | Coordinator | Accept (D9: the next request answers 404) |
| 07 · 4 | Build-time `API_BASE_URL` needs a redeploy to change | Platform person | Accept; runbook note (A23) |
| 07 · 5 | Railway region | Owner (B7) | Measure on day 1 |
| 07 · 6 | Does the always-on agent fit Railway's $5 credit; agent health check | Bonus owner | Check at B4 (PH9) |
| 10 · 7 | Quick-add common services (P1) | Owner (B8) | ✅ Built 2026-10-10 (kept; spec 10 O-03) |
| 12 · 6 | The test seam that raises spec 04's rate-limit constants | Coordinator | Spec 04 names a test-settings override |
| 13 · 1–8 | pgvector, WhatsApp, Urdu evaluation, data protection, data volume, pricing, production provider, fitment data | Post-hackathon | P3, revisit when each AI item is scheduled |
| bookings · 6; identity · 3 | Customer-name search through `identity.find_user_ids_by_name` (capped at 1,000 ids) | Coordinator | Accept the cap |
| bookings · 7; estimates · 2; inventory · 4; scheduling · 1 | Small product rules: re-booking keeps stored `color` / `mileage_km`; no re-validation of deactivated parts at send; no PO cancel or close; "within 30 days" in shop-local days (notifying the actor is decided by D91, C.2) | Owner (B8) | The B8 defaults |
| bookings · 8 | Event `metadata` shapes not fixed by spec 08 (e.g. `SEND_TO_QC {resolved_qc_issue_ids}`, `REASSIGN_* {…, previous_…}`) | Coordinator | Record in spec 08 at its next amendment, or keep module-level |
| calls · 2 (routers half) | **Conditional calls routers under D89.** ✅ The injection half is resolved by D90 (with notifications · 7, C.2): the P1 `RealtimeHub` and `EmailSender` and calls' `CallMediaGateway` and `Presence` are per-app objects on the app state, reached through `uow.app_state`. Still open: `wire_modules()` includes every router in `router.routers`, so how the calls router handles its conditional routes (webhook only when calling is enabled, `internal_router.py` only with `AGENT_SERVICE_TOKEN`) | Coordinator (spec 01, D89) | Always include the conditional routers and let a dependency refuse when the feature is off, as CALL-20 already expects for the start routes; decide before PH8. Then list both call ports in spec 01 and the glossary (D.2) |
| calls · 5 | `CALL_MISSED` also for a shop → customer call the customer declined | Coordinator | Keep literal; the web may skip the toast |
| calls · 6 | An AI leg ended by the caller before the agent joined creates no task | Spec 05 owner | Optionally add a `CALLBACK` task in A3 |
| notifications · 6 | E-mail vendor: the `http` adapter targets Resend; another vendor means another adapter class | Owner (B5) | Resend, only if a sender domain exists |
| qc · 4 | D87: move the open `qc_inspections` round to the new inspector | Coordinator | Confirm when D87 is implemented (A12) |
| 15 · 10 | Owner of the gap fixes G1–G8 (process checks, CI-gate IDs, README and `.env.example` checks, demo evidence) and whether DEP-12 / SEC-47 become P0 (G6) | Coordinator | Spec 15's proposal: spec 12's owner, in one pass before CP3 |
| 15 · 11 | May a test be lower priority than the requirement it proves (G6 lists three cases)? | Coordinator | Decide with 15 · 10 |
| reporting · 1 | `low_stock_count` counts `LOW` + `OUT` | Coordinator | Keep; UI subtracts `out_of_stock_count` (A13) |
| shops · 6 | `tasks.manage` appears when `Settings.calling_enabled` is true | Spec 05 owner | Confirm |
| 19 · retention; audit · 4 | **Audit log retention.** `audit_events` is append-only (D95): no API changes it and `trg_audit_events_append_only` rejects `UPDATE` and `DELETE`, so it grows forever (every booking action, sign-in and admin read adds a row) | Owner (post-hackathon) | Keep everything for the hackathon. Later: partition by month on `occurred_at` and archive or drop old partitions outside the app (partition drops are not row deletes), with a retention period the owner fixes |
| 19 · seed admin; admin · 4 | The seed has no data yet, so the demo platform admin Areeba Hashmi (`admin@bayflow.test`, spec 19 §8, spec 11) does not exist until the seed is built | Coordinator | Add her with the seed; until then `python -m app.scripts.create_platform_admin` creates an admin |

### C.2 Resolved (by which decision or spec)

| Spec | Resolved items |
|---|---|
| 01 | 1 (D30 + D43), 2 (D43, D24), 3 (D20 + glossary §7), 4 (glossary §10), 6 (D37), 7 (D70), 8 (D81), 9 (D80, D84), 10 (D86), 11 (spec 03 §4.11), 12 (`modules/notifications.md`, rule 6), 13 (`modules/calls.md`) |
| 02 | 1 (D30), 2 (D47), 3 (D37), 4 (D30), 5 (D65), 6 (D44), 7 (D64), 8 (spec 05, D58), 9 (spec 08 T07), 10 (glossary §9), 11 (glossary §13, §1), 12 (D63, D79), 13 (D37), 14 (D82), 15 (D84) |
| 03 | 1 (D81), 4 (spec 12 API-05), 5 (spec 12 API-01 exempts `/health`), 6 (D82), 7 (D83) |
| 04 | 1 (D10), 2 (glossary §11), 3 (D70), 4 (D69), 5 (D18), 6 (D85), 7 (D60), 8 (D19), 9 directory half (D64), 13 (glossary §10, D69), 14 (D63), 15 (glossary §10) |
| 05 | 1 (D77), 2 (D26, glossary §6), 4 (D36, D59), 8 (D21), 9 naming (D58, glossary §12) |
| 06 | 1 (D62), 2 (D71), 4 (D83) |
| 07 | 1 (D26; vendor Resend, `modules/notifications.md`), 2 (D1, D11), 3 (D13), 7 (spec 03, D81), 8 (D69), 10 (D73) |
| 09 | 1 (D41), 2 (D14), 3 (D1), 4 (D66), 5 (D101), 6 (D93), 7 (glossary §3) |
| 10 | 1 (D68), 2 (spec 03 §4.7), 3 (D40), 4 (D46), 5 (spec 03 §5.2), 6 (spec 03 §4.13), 8 (spec 03 §4.14, D78), 9 (spec 03 §4.8) |
| 11 | 1 (D62), 2 (D26), 3 (D63), 4 (D71), 5 (D51) |
| 12 | 1 (D62), 2 (spec 03), 3 (D1, D5, D11), 4 (spec 11, D71), 5 (D12), 7 (D75), 8 (D76), 9 (D11), 10 (specs 01, 04, 11, the §5 numbering, and spec 05 §14.1 for CALL-17 … CALL-20 and FD-13 … FD-15) |
| 14 | 3 (D36), 5 (D75) |
| 15 | 1 (spec 12 SCH-07), 2 (spec 00, D76), 3 (D75 amended: `DI-1` … `DI-7`), 4 (this spec), 5 (spec 12 status line), 8 (spec 11), 9 (spec 12 §5 numbers CALL-21) |
| `modules/bookings.md` | 1 (D83, spec 03 §6.4, spec 09 §2.7), 2 (D86), 3 (`modules/inventory.md`), 4 (spec 12 EST-11), 5 (spec 11), 9 (D87, planned) |
| `modules/calls.md` | 1 (spec 01), 2 ports half (D90), 3 (D84), 4 (specs 06, 10), 7 (spec 05 §3.3) |
| `modules/estimates.md` | 1 (spec 12 EST-11), 3 (spec 11) |
| `modules/identity.md` | 1 (specs 03, 04; the as-built internal `UserRecord`), 2 (proposal accepted by the coordinator, 2026-10-09: `last_login_at` on every successful password check or new session, incl. wizard case B) |
| `modules/inventory.md` | 1 (D86), 2 (D82), 3 (D83), 5 (as built: `identity.schemas.UserRef`) |
| `modules/notifications.md` | 1 (D88), 2 (D83), 3 (D91), 4 (spec 01), 5 (D70), 7 (D90) |
| `modules/qc.md` | 1 (spec 01), 2 (spec 03), 3 (D92) |
| `modules/reporting.md` | 2 (`modules/bookings.md` §5.3) |
| `modules/scheduling.md` | 2 (glossary §10), 3 (spec 02 §7.2) |
| `modules/shops.md` | 1 (D86), 2 (D64), 3 (spec 10), 4 (spec 04), 5 (D87, planned) |
| 08, 17, 18 | None open (changes go through spec 17) |

### C.3 Contradictions still present (in specs the sweep could not edit, and in code)

| Where | What it says | What wins | Fix |
|---|---|---|---|
| ✅ Spec 01: dependency rules 3 and 6, Event bus rule 7, the `main.py` line of the file tree, the wiring-functions row of "Still pending" | Said (before D89): `create_app()` called `register_event_handlers(bus)`, registered the D86 ports and called `register_call_handlers(bus, *, hub)` itself; the wiring functions were "called only by `create_app()`" | D89 and the code (`apps/api/app/main.py`): `wire_modules()` loads each module's `service.register_ports()`, `handlers.register(bus)` and `router.routers` in `MODULES` order | ✅ Fixed on 2026-10-09: reworded per D89 (bookings' `register_ports()` registers both D86 ports; notifications' `register(bus)` calls `register_call_handlers(bus)` only when the calls package exists); the hub comes from the app state (D90) |
| ✅ Glossary §7.1a; spec 14 PH1 and PH5 | The D86 ports are "registered by" / "wired in" `create_app()` | D89: `bookings.service.register_ports()`, which `app.main.wire_modules()` calls from `create_app()` | ✅ Fixed on 2026-10-09: all three now add "through `wire_modules()` (D89)" |
| ✅ Spec 12 §5 bonus index; spec 14 PH8 exit | Number CALL-17 … CALL-20 only | `modules/calls.md` also proposes CALL-21 (an active SA who was not rung accepts; the Owner of a shop with an active SA gets 403; spec 05 §3.3), now listed in spec 05 §14.1 | ✅ Fixed on 2026-10-09: spec 12 §5 numbers CALL-21 (P2), spec 14's PH8 exit list includes it, and spec 12 open question 10's "For spec 05" bullet is marked done |
| ✅ Spec 12 BK-20 | "colour and mileage optional" | The field is `color` (spec 03, glossary) | ✅ Fixed on 2026-10-09: BK-20 names the `VehicleWrite` fields (`color`, `mileage_km`) |
| Spec 12 | No test for D87's `reassign-qc-inspector` (planned P1) and no ID for D89's wiring | D87, D89; the code already has `apps/api/tests/unit/test_main_wiring.py` | Add a P1 row with D87 (A12); optionally record the wiring test |
| ✅ `scripts/smoke.sh` (code) vs specs 03, 07, 11 | Read `slots[].start`; by default booked at the first listed shop other than `lahore-auto-care` and `raza-auto-works` | `slots[].slot_start` (spec 03 `SlotRead`, §4.5); automation books only at `lyallpur-motors` (spec 11, spec 12 open question 4) | ✅ Fixed on 2026-10-09: the script reads `slots[].slot_start`, books only at `lyallpur-motors` and is spec 07's listing verbatim (spec 07 open question 7) |
| ✅ Spec 15, its list of conflicts (items 1–5 and 8) | Describes them as open | Fixed in this sweep on 2026-10-09: SCH-07 now says `off_grid` (spec 12); the OpenAPI drift check moved from P1 to the P0 row (spec 00, D76); spec 02's invariants renamed `DI-1` … `DI-7` (D75 amended) with every spec citation updated and the prefix in glossary §13; spec 16 exists; SM-20 removed from spec 12's status line; spec 11 marks SEED-11 … SEED-19 as adopted | ✅ Fixed on 2026-10-09: spec 15 marks them resolved (and item 9, now that spec 12 numbers CALL-21); items 6 and 7 are code state (next row; README) |
| `apps/web/src/lib/api/openapi.json` (code) vs D76 | A placeholder (version 0.1.0, no paths) from the first commit, while the API exports version 1.0.0 with `/health` | D76: both generated files come from `make gen-api` | Run `make gen-api` and commit `openapi.json` and `schema.d.ts`, or the CI `contract` job (WEB-07) fails (spec 15) |
| Code comments vs spec 02 §6 | `apps/api/app/modules/scheduling/service.py` cites `INV-4` (2 places); `inventory/domain/stock.py` and `tests/modules/estimates/test_lifecycle.py` already say `DI-…` | `DI-1` … `DI-7` (D75 amended, glossary §13) | Rename the citations to `DI-…` (code is outside this sweep) |
| `modules/identity.md` Dependencies | Lists D8–D81 only | It now cites D84 and D86 | Add D84, D86 (the edit was refused by the tool's permission classifier during the sweep) |

---

## D. Pending glossary additions (for one merge)

Already merged, so **not** to be proposed again: `BookingPartsChanged` (§7.1); the read ports `ShopActivityReader` / `BookingRefReader` with `register_activity_reader` / `register_booking_ref_reader` (§7.1a); the D89 wiring names `router.routers`, `handlers.register(bus)`, `service.register_ports()`, `app.main.wire_modules()` and `MODULES` (§7); the `DI` prefix of spec 02's data invariants `DI-1` … `DI-7` (§13, D75 amended); the `INVALID_SLOT` reason codes `off_grid`, `in_past`, `beyond_horizon`, `closed_day`, `outside_hours` (§10); `app.shared.phone.Phone` (§7); `shop_scoped_router()` (§7).

### D.1 Events, event payloads and actions

| Name | Proposed by | Note |
|---|---|---|
| `CallStateChanged` payload: `shop_id`, `call_id`, `booking_id`, `direction`, `previous_status`, `status`, `missed_reason`, `ai_status`, `caller_user_id`, `customer_user_id`, `answered_by_user_id`, `rung_user_ids` | `modules/calls.md` | Also published for AI-leg changes A1–A4 (spec 01) |
| `AiTaskCreated` payload: `shop_id`, `task_id`, `call_id`, `booking_id`, `booking_reference`, `kind`, `title`, `is_urgent` | `modules/calls.md` | — |
| `BookingPartsChanged` payload: `shop_id`, `booking_id`, `status`, `version`, `occurred_at` | `modules/bookings.md` §8 | Event name already merged |
| `REASSIGN_QC_INSPECTOR` / `reassign-qc-inspector` (operation O6, P1) | D87, `modules/bookings.md` | Only when implemented (glossary §4, spec 08) |
| identity events `LoginSucceeded`, `LoginFailed`, `LoginRateLimited`, `LoggedOut`, `OwnerRegistered`, `CustomerAccountCreated`, `UserActiveChanged`, `PlatformAdminChanged`; shops events `ShopCreated`, `ShopUpdated`, `WorkingHoursReplaced`, `ShopSuspensionChanged`, `MembershipAdded`, `MembershipRoleChanged`, `MembershipActiveChanged` | spec 19 §3.3, `modules/audit.md` | Published for the audit log (D95) |

### D.2 Ports, runtime objects and wiring

| Name | Proposed by | Note |
|---|---|---|
| `CallMediaGateway` (`create_room`, `delete_room`, `create_dispatch`, `delete_dispatch`, `issue_token`) | spec 05 §14.1, `modules/calls.md` | LiveKit adapter port; one per app at `app.state.call_media`, created on first use and reached through `uow.app_state` (D90) |
| `Presence` (`online_user_ids`, `is_online`) | `modules/notifications.md`, `modules/calls.md` | Implemented by the hub |
| `RealtimeHub`, `EmailSender` | `modules/notifications.md` | P1; one each per app, created on first use by `get_realtime_hub(state)` / `get_email_sender(state)`, stored at `state.realtime_hub` / `state.email_sender` and reached through `uow.app_state` (D90) |
| `register_call_handlers(bus)` as a wiring function, called by notifications' own `handlers.register(bus)` only when the calls package exists | spec 01 rule 6, `modules/notifications.md` | Spec 01 now says the same (D89) |
| `require_platform_admin` / `PlatformAdminDep`, `refuse_cross_site_requests` (`app.shared.auth`, D94, D98); identity ports `lock_acting_platform_admin`, `sign_in_for_booking` (D100), `change_user_active`, `change_platform_admin`, `bootstrap_platform_admin`; shops ports `get_shop_suspension`, `suspend_shop`, `reactivate_shop`; script `app.scripts.create_platform_admin` | spec 19, `modules/admin.md`, `modules/audit.md` | — |

### D.3 Schemas, wire enums and fields

| Name | Proposed by |
|---|---|
| Wire enums `BookingActionSlug` (25 slugs incl. `edit-estimate`), `StockState` (`OK`, `LOW`, `OUT`) | spec 03 §3.9, `modules/inventory.md` |
| Response schemas (`Problem` … `HealthRead`), request schemas (`SessionCreate` … `QcChecklistItemWrite`, the `<PascalCaseSlug>Request` bodies, `CustomerCancelRequest`), response fields, request fields and query parameters | spec 03 "Proposed glossary additions", spec 04 |
| Nested OpenAPI components `OverviewShop`, `OverviewToday`, `OverviewTeamMember`, `OverviewInventory`, `OverviewSetup`, `OwnerShopRef` | `modules/reporting.md` |
| `SessionToken`; internal `UserRecord` (as built) | `modules/identity.md` |
| Internal `MembershipRecord`, `ShopBrief`, `ServiceSnapshot`, `TeamMember`, `SetupFlags`; value objects `WorkingDay`, `ScheduleConfig`; `Capability`, `CAPABILITY_ROLES`, `capabilities_for()` | `modules/shops.md` |
| `EstimateSnapshot`, `EstimateEdit`, `CustomerEstimateView` | `modules/estimates.md` |
| `PartQty`, `ReceiptReservation`, `OrderPartsResult` | `modules/inventory.md` |
| `QcSummary`, `FailRecorded` | `modules/qc.md` |
| `DayActivity`, `BookingLabel` | `modules/bookings.md` |
| `GridSlot`, `SlotProblem` | `modules/scheduling.md` |
| Field-error codes of spec 03 §2.3 (`invalid_reference` … `unchanged`; `not_on_grid` for working hours only) | spec 03 |
| Problem members (`type` = `about:blank`, `title` = reason phrase, `instance` = path); OpenAPI tag and `operationId` conventions | spec 03 |
| Key column `users.tokens_valid_after` (only if spec 04 Tier 2 item 4 ships) | spec 04 |
| Response fields `MeRead.is_platform_admin`, `MembershipRead.shop_suspended`; internal `ShopBrief.is_suspended`; stored enums `AuditCategory`, `AuditActorRole`, `AuditTargetType`; admin wire enums `AdminShopStatus`, `AdminUserKind`, `AdminUserStatus`, `StatusPhase`; field-error code `inactive_account` (E-70) | spec 19, `modules/admin.md`, `modules/audit.md` |

### D.4 Constants and identifiers

| Name | Proposed by |
|---|---|
| `BOOKING_HORIZON_DAYS = 30` | `modules/scheduling.md` |
| `LOGOUT_IP_LIMIT = "30/minute"`; header `Sec-Fetch-Site` values `same-origin` / `none` accepted by the admin API (D98); trigger `trg_audit_events_append_only` | spec 04, spec 19 |
| `SA_ACTION_STATUSES`, `IN_PROGRESS_STATUSES` | `modules/reporting.md` |
| `REFERENCE_ALPHABET`, `QC_QUEUE_STATUSES`, `UNROUTED_SLUGS`, `CUSTOMER_HIDDEN_ACTIONS`, `CUSTOMER_NOTE_ACTIONS` | `modules/bookings.md` |
| `OPEN_STATUSES`, `CUSTOMER_VISIBLE_STATUSES`, `FINAL_STATUSES`, `MAX_AMOUNT`, `EditDecision` | `modules/estimates.md` |
| Calls constants: `AI_JOIN_TIMEOUT_SECONDS` (10), `AI_MAX_CALL_SECONDS` (300), `CALL_MAX_SECONDS` (900), `SUMMARY_GRACE_SECONDS` (180), start limit 5 per 600 s, token TTL 120 s, summary window 600 s, transcript ≤ 300 entries / 200 KB | spec 05, `modules/calls.md` |
| Human participant identity `u_<user_id>`; agent tool names `verify_caller`, `get_shop_info`, `get_my_bookings`, `get_booking_status`, `get_estimate`, `get_available_slots`, `request_reschedule`, `request_callback`, `escalate_to_human`, `end_call` | spec 05 |
| `RESEND_EMAILS_URL = "https://api.resend.com/emails"` | `modules/notifications.md` |
| Limiter keys `"failed-password", <email>`; `"booking-ip", <ip>`; `"booking-user", <user_id>`; `"shop-create", <user_id>`; `"member-create", <shop_id>` | `modules/identity.md`, `bookings.md`, `shops.md` |
| Seed advisory lock key `bayflow:seed`; smoke-test shop Lyallpur Motors (`lyallpur-motors`) as a §14.2 note | spec 11, spec 14 |
| Headers `WWW-Authenticate: Bearer` (401), `Retry-After` (429), `Allow` (405), `X-Agent-Call-Token` (bonus); server frame `{"type": "pong", "data": {}}`; body limits 64 KiB / 256 KiB → 413 | spec 03, spec 04, spec 05 |

### D.5 Test IDs and test vocabulary

The module specs' proposed tests are already numbered in spec 12 §5 and need no glossary entry: IDN-01 … 06, SHP-01 … 10, SCH-01 … 07, BK-33 … 42, EST-21 … 27, INV-27 … 34, QC-12 … 17, NOT-14 … 21, RPT-04 … 09, CALL-17 … 21 and FD-13 … 15 (the last two groups also listed in spec 05 §14.1).

| Name | Proposed by |
|---|---|
| ✅ CALL-21 (eligible callee accepts; Owner 403 when the shop has an active SA) — numbered in spec 12 §5 on 2026-10-09 (C.3); no glossary entry needed | `modules/calls.md`, spec 05 §14.1 |
| Test prefix list (`SM`, `SEC`, `IDN`, `SHP`, `SCH`, `BK`, `EST`, `INV`, `QC`, `NOT`, `RPT`, `API`, `SEED`, `WEB`, `CON`, `DEP`, `DEV`, `CALL`, `FD`, `AG`); pytest markers `db`, `concurrency`, `scenario`, `seed`, `slow`, `live`; test database `<db>_test`; helpers (`SimulatedClock` `step`/`set`/`advance`, `clock`, `as_user`, `make_*`, `drive_booking_to`, `assert_problem`, `assert_invariants`, `hold_row_lock`, `wait_for_lock_waiters`) | spec 12 |

### D.6 Files, modules and tooling names

| Name | Proposed by |
|---|---|
| `app.modules.notifications.realtime`, `app.modules.notifications.channels.email` | spec 01, `modules/notifications.md` |
| `app.scripts.export_openapi`; `app.core.http_headers`, `app.shared.orm`, `app.models_registry` (D84) | spec 01 |
| `app/scripts/seed_data.py`; the seed's `--force` flag | spec 11, spec 07 |
| Calls files `internal_router.py`, `timers.py`, `constants.py`, `providers/` | `modules/calls.md` |
| Domain files: bookings `vehicles.py`, `visibility.py`, `timeline.py`; estimates `totals.py`, `versions.py`; scheduling `slots.py`; shops `capabilities.py`, `grid.py`, `slugs.py`; qc `checklist.py` | module specs |
| Shared helpers already in code: `app.shared.auth.set_session_cookie`, `delete_session_cookie`, `session_cookie_clearing_headers` | `modules/identity.md` |
| `apps/web/src/lib/api/openapi.json`; `apps/api/railway.json`, `apps/agent/railway.json`; `scripts/smoke.sh` with `WEB_URL`, `API_URL`; `.github/workflows/smoke.yml` | spec 07, spec 12 |
| Makefile targets, `apps/web` package scripts, `start.*` / `stop.*` with `logs/`, `.run/` and `--seed`, Compose services and volume `pgdata`, Railway service names, CI job names, commit scopes, import-linter contract ids `thin-routers`, `seed-through-services` | spec 07, spec 12 |
| Web route table (`/`, `/shops/:slug`, `/book/:slug`, …, `/pos/shops/:shopId/{overview,…,calls}`) | spec 09, spec 10 |
| Process terms CP1 … CP5, walking skeleton, judge path, minimum proof set (★), feature freeze | spec 14 |

Service-function names proposed by the module specs (`get_bookable_shop`, `count_day_activity`, `get_booking_labels`, `password_matches`, `list_for_bookings`, …) extend spec 01's module catalogue rather than the glossary; spec 01 should adopt them from each module spec's last table.

---

## E. "If you fix only five things"

1. **Deploy the walking skeleton today and run day-1 checks #1–#12** (A1, A3–A6): the live URL carries the score, and the five platform assumptions are cheap to verify and expensive to discover late. Record the results in F.1.
2. **Make the repository public with a real history** (A2, B1): from now on small Conventional Commits from every member; run the full-history secret scan, then flip the visibility.
3. **Get the P0 worked example green on the live URL before anything P1 or P2** (A22, D36, D88): SM-18, SM-08 and SM-10 in CI plus the DEP-10 replay by CP3 — no realtime layer and no bonus first.
4. **Protect the judges' shared data** (A8): judge notes in the README and on the login page, the smoke-test shop for automation, and one rehearsed "redeploy repairs the demo cast" (D60) before judging starts.
5. **Close the last spec conflicts and merge the glossary in one pass** (A21): the calls router's conditional routes (C.1; D90 already settled the hub, the e-mail sender and the call ports, and spec 01's wiring text now follows D89), the rest of C.3, and section D — before the module phases that touch those files.

---

## F. Records kept in this spec

### F.1 Day-1 verification results (spec 07)

| Day-1 | Check | Result | Date | Notes |
|---|---|---|---|---|
| #1 | `Set-Cookie` through the rewrite | pending | — | — |
| #2 | WebSocket direct to Railway | pending | — | — |
| #3 | PostgreSQL major version | pending | — | — |
| #4 | Pre-deploy command form | pending | — | — |
| #5 | Health check green | pending | — | — |
| #6 | Demo logins | pending | — | — |
| #7 | `no-store` through the rewrite | pending | — | — |
| #8 | Visitor IP header | pending | — | — |
| #9 | Live URL public | pending | — | — |
| #10 | No secrets in Git | pending | — | — |
| #11 | Outbound e-mail path | pending | — | — |
| #12 | Vercel installs pnpm 10 | pending | — | — |

### F.2 Kickoff decisions (spec 14 open questions 1–2)

| Item | Answer |
|---|---|
| Deadline (date, time, time zone) | pending (B3) |
| Team size and split (spec 14 §4.5) | pending (B3) |
| Schedule (spec 14 §4.4) | pending |
| Submission mechanics | pending (B3) |
| Bonus track (B4) | pending; decided at CP4 |

### F.3 Cut log (spec 14 §5)

| Date | Checkpoint | Cut | Decision recorded in spec 17? |
|---|---|---|---|
| — | — | none yet | — |

---

## Dependencies

- Depends on every other spec: [00-overview.md](00-overview.md) to [18-glossary.md](18-glossary.md) and `modules/*.md`, in particular [17-decisions.md](17-decisions.md) (D1–D91), [15-requirements-traceability.md](15-requirements-traceability.md) (brief coverage), [07-deployment-and-docs.md](07-deployment-and-docs.md) (day-1 checklist), [12-quality-and-testing.md](12-quality-and-testing.md) (DEP, DEV and module tests), [14-roadmap.md](14-roadmap.md) (phases, checkpoints, cut list) and [05-calling-and-ai-front-desk.md](05-calling-and-ai-front-desk.md) (bonus costs and limits).
- Facts checked for this spec on 2026-10-09: the brief's §9.1 wording ("meaningful commit history (not a single commit)") and §10 tip ("deploy early and keep deploying") in `helping-folder/Web Dev - Virtual.pdf`; the repository state (`git log`: one commit; `git ls-files`: no `.env`; anonymous HTTPS request to the GitHub repository: 404); `apps/api/railway.json` (shell-wrapped pre-deploy command, `/health`); the Alembic baseline revision `23165172278b`; `apps/api/app/main.py` (`MODULES`, `wire_modules()`, D89); `scripts/smoke.sh` (`slots[].start`, default shop); `apps/web/package.json` (`cmdk`, `radix-ui`, no `@base-ui/react`); `README.md` (live URL not yet added).
- Used by: the owner and the coordinator; specs 07 and 14 record their results here (section F).

## Open questions

None of its own: sections B and C hold every open decision and question.

## Proposed glossary additions

None of its own; section D collects every other spec's pending additions.
