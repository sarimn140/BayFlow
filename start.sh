#!/usr/bin/env bash
# start.sh — start the BayFlow local dev stack on Linux/macOS (D73, spec 07). Windows: start.bat.
#
#   a. preflight: docker with Compose v2 (daemon running), uv, node 24+, pnpm, curl
#   b. create .env from .env.example if missing (warning), then export it (set -a; . ./.env; set +a)
#   c. install dependencies if missing: uv sync (apps/api/.venv), pnpm install (apps/web/node_modules)
#   d. free the ports and clean up (./stop.sh --keep-db --quiet): stop stale BayFlow processes (.run/,
#      this repo's dev servers, BayFlow's Docker api/web), stop ANY other program listening on port
#      3000 or 4000 (named in the output; Docker/VM/SSH port forwarders are never killed — then this
#      script exits with a message) and clean the Next.js dev lock
#   e. docker compose up -d --wait db (host port POSTGRES_HOST_PORT, default 5434) with a timeout
#   f. uv run alembic upgrade head, then uv run python -m app.scripts.seed — the seed acts only when
#      SEED_ON_DEPLOY=true (.env.example sets it); --seed adds --force
#   g. start the API (uvicorn --reload, :4000) and the web app (pnpm dev, :3000), each in its own
#      process group; logs in logs/api.log and logs/web.log; PIDs in .run/pids ("name pid port")
#      and .run/api.pid / .run/web.pid
#   h. wait for http://localhost:4000/health and http://localhost:3000; on failure show the last
#      log lines and run ./stop.sh
#   i. print the URLs
#   j. unless --detach, stream both logs with [api]/[web] prefixes; Ctrl+C runs ./stop.sh
#
# Works with macOS's bash 3.2. Run ./start.sh --help for the flags.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$ROOT"
API_DIR="$ROOT/apps/api"
WEB_DIR="$ROOT/apps/web"
RUN_DIR="$ROOT/.run"
LOG_DIR="$ROOT/logs"
PID_FILE="$RUN_DIR/pids"
FIFO="$RUN_DIR/logstream.fifo"

API_PORT=4000
WEB_PORT=3000
DB_TIMEOUT=90   # seconds until PostgreSQL must be healthy
API_TIMEOUT=90  # seconds until GET /health must answer 2xx
WEB_TIMEOUT=180 # seconds until the web app answers (the first next dev compile can be slow)

DETACH=0
SEED=0
INSTALL=1

usage() {
  cat <<'EOF'
Usage: ./start.sh [--detach] [--seed] [--no-install] [--help]

Starts PostgreSQL 16 in Docker, applies the migrations, runs the seed script, then runs the API on
http://localhost:4000 and the web app on http://localhost:3000 and streams their logs until Ctrl+C.

  --detach      start everything and return instead of streaming the logs (stop with ./stop.sh)
  --seed        load the demo data even when SEED_ON_DEPLOY is not true (seed --force)
  --no-install  never install dependencies; fail if apps/api/.venv or apps/web/node_modules is missing
  -h, --help    show this help

The seed runs on every start and is idempotent: with SEED_ON_DEPLOY=true (the .env.example default)
a fresh database gets the demo accounts (password BayFlow@2026, see README.md).
Logs: logs/api.log, logs/web.log   PIDs: .run/   Stop: ./stop.sh (or Ctrl+C)
EOF
}

while (($#)); do
  case "$1" in
    --detach) DETACH=1 ;;
    --seed) SEED=1 ;;
    --no-install) INSTALL=0 ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      printf 'start.sh: unknown option: %s\n\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

# -- output helpers (colour only on a terminal; NO_COLOR disables it) --------------------------
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  RED=$'\033[31m' GREEN=$'\033[32m' YELLOW=$'\033[33m' CYAN=$'\033[36m' MAGENTA=$'\033[35m'
  BOLD=$'\033[1m' DIM=$'\033[2m' RESET=$'\033[0m'
else
  RED='' GREEN='' YELLOW='' CYAN='' MAGENTA='' BOLD='' DIM='' RESET=''
fi
ok() { printf '%s✓ %s%s\n' "$GREEN" "$*" "$RESET"; }
warn() { printf '%s⚠ %s%s\n' "$YELLOW" "$*" "$RESET"; }
err() { printf '%s✗ %s%s\n' "$RED" "$*" "$RESET" >&2; }
fail() {
  err "$*"
  exit 1
}
step() { printf '\n%s▸ %s%s\n' "$BOLD" "$*" "$RESET"; }
need() { command -v "$1" >/dev/null 2>&1; }
now() { date +%s; }

compose() { docker compose -f "$ROOT/docker-compose.yml" -p bayflow "$@"; }

# -- state shared with the traps -----------------------------------------------------------------
LAUNCHED=0 # 1 while API/web run under this script's responsibility (failure → stop them)
API_PID=""
WEB_PID=""
TAIL_PID=""
PREFIX_PID=""

stop_streamer() {
  if [[ -n "$TAIL_PID" ]]; then kill "$TAIL_PID" 2>/dev/null || true; fi
  if [[ -n "$PREFIX_PID" ]]; then kill "$PREFIX_PID" 2>/dev/null || true; fi
  TAIL_PID=""
  PREFIX_PID=""
  rm -f "$FIFO" 2>/dev/null || true
}

# Ctrl+C / SIGTERM / closed terminal: stop everything through stop.sh.
on_signal() {
  trap '' INT TERM HUP # a second Ctrl+C must not interrupt the cleanup
  printf '\n'
  warn "Stopping BayFlow…"
  stop_streamer
  local rc=0
  bash "$ROOT/stop.sh" || rc=$?
  LAUNCHED=0
  exit "$rc"
}

# Any other exit while the services are ours (a failed step, set -e): stop them too.
on_exit() {
  local rc=$?
  stop_streamer
  if ((LAUNCHED)); then
    LAUNCHED=0
    warn "start.sh did not finish (exit $rc) — stopping what it started"
    bash "$ROOT/stop.sh" || true
  fi
}
trap on_exit EXIT

# -- process helpers -----------------------------------------------------------------------------
group_alive() { kill -0 -- "-$1" 2>/dev/null; }

# Start "$@" in directory $3 in its own process group/session, output to logs/<name>.log.
# Linux: setsid (new session, no controlling terminal). macOS has no setsid(1): `set -m` gives
# every background job its own process group, and nohup keeps it alive when the terminal closes.
LAST_PID=""
launch() {
  local name="$1" port="$2" dir="$3" log="$LOG_DIR/$1.log"
  shift 3
  : >"$log"
  if need setsid && [[ -z "${BAYFLOW_NO_SETSID:-}" ]]; then
    (cd "$dir" && exec setsid "$@") >>"$log" 2>&1 </dev/null &
    LAST_PID=$!
  else
    set -m
    (cd "$dir" && exec nohup "$@") >>"$log" 2>&1 </dev/null &
    LAST_PID=$!
    set +m
  fi
  printf '%s %s %s\n' "$name" "$LAST_PID" "$port" >>"$PID_FILE"
  printf '%s\n' "$LAST_PID" >"$RUN_DIR/$name.pid"
  printf '  %s●%s %-4s pid %-7s port %-5s logs/%s.log\n' "$GREEN" "$RESET" "$name" "$LAST_PID" "$port" "$name"
}

# Poll an URL until it answers. $5 = process group that must stay alive, $6 = 2xx | any.
WAIT_REASON=""
wait_http() {
  local name="$1" url="$2" timeout="$3" max_time="$4" pgid="$5" accept="$6"
  local deadline code
  deadline=$(($(now) + timeout))
  while :; do
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time "$max_time" "$url" 2>/dev/null || true)"
    case "$accept:$code" in
      2xx:2?? | any:[1-5]??) return 0 ;;
    esac
    if ! group_alive "$pgid"; then
      WAIT_REASON="the $name process exited"
      return 1
    fi
    if (($(now) >= deadline)); then
      WAIT_REASON="no answer within ${timeout}s (last HTTP status: ${code:-none})"
      return 1
    fi
    sleep 1
  done
}

show_log_tail() {
  printf '\n%s── last 40 lines of logs/%s.log ──%s\n' "$BOLD" "$1" "$RESET" >&2
  tail -n 40 "$LOG_DIR/$1.log" >&2 2>/dev/null || true
  printf '%s── end of logs/%s.log ──%s\n\n' "$BOLD" "$1" "$RESET" >&2
}

# Prefix lines from `tail -F api.log web.log` with [api] / [web]. tail announces which file the
# next lines come from with "==> name <==" headers (preceded by a blank line, which is dropped).
prefix_logs() {
  local line prefix="" blank=0
  local api_tag="${CYAN}[api]${RESET} " web_tag="${MAGENTA}[web]${RESET} "
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      "==> api.log <==")
        prefix="$api_tag"
        blank=0
        continue
        ;;
      "==> web.log <==")
        prefix="$web_tag"
        blank=0
        continue
        ;;
    esac
    if ((blank)); then
      printf '%s\n' "$prefix"
      blank=0
    fi
    if [[ -z "$line" ]]; then
      blank=1
      continue
    fi
    printf '%s%s\n' "$prefix" "$line"
  done
}

# -----------------------------------------------------------------------------------------------
printf '\n%s  BayFlow · local dev stack%s\n' "$BOLD" "$RESET"
printf '  %s─────────────────────────%s\n' "$DIM" "$RESET"

# a. Preflight -----------------------------------------------------------------------------------
step "Checking prerequisites"
problems=0
if ! need docker; then
  err "docker not found — install Docker Desktop or Docker Engine: https://docs.docker.com/get-docker/"
  problems=1
elif ! docker compose version >/dev/null 2>&1; then
  err "Docker Compose v2 not found — the 'docker compose' plugin is required (not docker-compose v1): https://docs.docker.com/compose/install/"
  problems=1
elif ! docker info >/dev/null 2>&1; then
  err "Docker is installed but not running — start Docker Desktop (Linux: sudo systemctl start docker)"
  problems=1
fi
if ! need uv; then
  err "uv not found — install it: curl -LsSf https://astral.sh/uv/install.sh | sh"
  problems=1
fi
if need node; then
  node_major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
  [[ "$node_major" =~ ^[0-9]+$ ]] || node_major=0
  if ((node_major < 24)); then
    err "Node.js $(node --version 2>/dev/null || echo '?') found — Node.js 24 LTS or newer is required: https://nodejs.org/"
    problems=1
  fi
else
  err "node not found — install Node.js 24 LTS: https://nodejs.org/"
  problems=1
fi
if ! need pnpm; then
  err "pnpm not found — enable it with: corepack enable pnpm   (or: npm install -g pnpm@10.34.6)"
  problems=1
fi
if ! need curl; then
  err "curl not found — install it with your package manager"
  problems=1
fi
if [[ ! -f "$API_DIR/pyproject.toml" ]]; then
  err "apps/api/pyproject.toml is missing — is the checkout complete?"
  problems=1
fi
if [[ ! -f "$WEB_DIR/package.json" ]]; then
  err "apps/web/package.json is missing — is the checkout complete?"
  problems=1
fi
((problems == 0)) || fail "Fix the problems above, then run ./start.sh again."
ok "docker $(docker version --format '{{.Client.Version}}' 2>/dev/null || echo '?'), $(uv --version 2>/dev/null || echo 'uv ?'), node $(node --version), pnpm $(pnpm --version 2>/dev/null || echo '?')"

# b. .env -----------------------------------------------------------------------------------------
mkdir -p "$RUN_DIR" "$LOG_DIR"
if [[ ! -f "$ROOT/.env" ]]; then
  [[ -f "$ROOT/.env.example" ]] || fail ".env.example is missing — cannot create .env"
  cp "$ROOT/.env.example" "$ROOT/.env"
  warn "Created .env from .env.example (local defaults) — edit it if you need other values"
fi
env_file="$ROOT/.env"
if grep -q $'\r' "$env_file"; then
  warn ".env has Windows (CRLF) line endings — reading it without the CR characters"
  tr -d '\r' <"$ROOT/.env" >"$RUN_DIR/env.sh"
  env_file="$RUN_DIR/env.sh"
fi
set -a
# shellcheck source=/dev/null
if ! . "$env_file"; then
  set +a
  fail ".env could not be read by bash — see the format rules at the top of .env.example"
fi
set +a
ok "Loaded .env"
db_port="${POSTGRES_HOST_PORT:-5434}"
url_port_re='@(localhost|127\.0\.0\.1|\[::1\]):([0-9]+)/'
if [[ "${DATABASE_URL:-}" =~ $url_port_re ]] && [[ "${BASH_REMATCH[2]}" != "$db_port" ]]; then
  warn "DATABASE_URL uses port ${BASH_REMATCH[2]} but POSTGRES_HOST_PORT is $db_port — make them equal in .env"
fi

# c. Dependencies ---------------------------------------------------------------------------------
UV_RUN=(uv run)
if ((INSTALL)); then
  if [[ ! -d "$API_DIR/.venv" ]]; then
    step "Installing API dependencies (uv sync)"
    (cd "$API_DIR" && uv sync) || fail "uv sync failed in apps/api"
  fi
  if [[ ! -d "$WEB_DIR/node_modules" ]]; then
    step "Installing web dependencies (pnpm install)"
    (cd "$WEB_DIR" && pnpm install) || fail "pnpm install failed in apps/web"
  fi
  ok "Dependencies present"
else
  UV_RUN=(uv run --no-sync)
  [[ -d "$API_DIR/.venv" ]] || fail "apps/api/.venv is missing — run without --no-install, or: (cd apps/api && uv sync)"
  [[ -d "$WEB_DIR/node_modules" ]] || fail "apps/web/node_modules is missing — run without --no-install, or: (cd apps/web && pnpm install)"
  ok "Dependencies present (--no-install)"
fi

# d. Stale BayFlow processes, busy ports, Next.js dev lock ----------------------------------------
step "Stopping stale processes and freeing ports $WEB_PORT and $API_PORT"
bash "$ROOT/stop.sh" --keep-db --quiet || fail "Ports $WEB_PORT/$API_PORT are not free — see the messages above"
ok "Ports $WEB_PORT and $API_PORT are free"

# e. PostgreSQL ---------------------------------------------------------------------------------------
step "Starting PostgreSQL 16 in Docker on localhost:$db_port"
if ! compose up -d --wait --wait-timeout "$DB_TIMEOUT" db; then
  fail "PostgreSQL did not start or did not become healthy within ${DB_TIMEOUT}s. Details: docker compose logs db. If port $db_port is taken, set POSTGRES_HOST_PORT and the port in DATABASE_URL in .env"
fi
ok "PostgreSQL is healthy"

# f. Migrations, seed --------------------------------------------------------------------------------
step "Applying database migrations (alembic upgrade head)"
(cd "$API_DIR" && "${UV_RUN[@]}" alembic upgrade head) ||
  fail "Migrations failed — fix the error above and run ./start.sh again (PostgreSQL keeps running; ./stop.sh stops it)"
ok "Database schema is at head"
if ((SEED)); then
  step "Loading demo data (python -m app.scripts.seed --force)"
  (cd "$API_DIR" && "${UV_RUN[@]}" python -m app.scripts.seed --force) || fail "The seed failed — see the error above"
else
  step "Running the seed script (python -m app.scripts.seed; acts only when SEED_ON_DEPLOY=true)"
  (cd "$API_DIR" && "${UV_RUN[@]}" python -m app.scripts.seed) || fail "The seed failed — see the error above"
fi
ok "Seed script finished"

# g. API + web ----------------------------------------------------------------------------------------
step "Starting the API and the web app"
rm -f "$PID_FILE" "$RUN_DIR/api.pid" "$RUN_DIR/web.pid"
trap on_signal INT TERM HUP
LAUNCHED=1
export PYTHONUNBUFFERED=1
launch api "$API_PORT" "$API_DIR" "${UV_RUN[@]}" uvicorn app.main:app --host 0.0.0.0 --port "$API_PORT" --reload
API_PID="$LAST_PID"
# .env sets PORT=4000 for the API; next dev also honours PORT, so the web gets its own.
launch web "$WEB_PORT" "$WEB_DIR" env PORT="$WEB_PORT" pnpm dev
WEB_PID="$LAST_PID"

# h. Health -------------------------------------------------------------------------------------------
step "Waiting for the API (http://localhost:$API_PORT/health)"
started=$(now)
if ! wait_http api "http://127.0.0.1:$API_PORT/health" "$API_TIMEOUT" 5 "$API_PID" 2xx; then
  show_log_tail api
  fail "The API is not healthy: $WAIT_REASON"
fi
ok "API is healthy ($(($(now) - started))s)"

step "Waiting for the web app (http://localhost:$WEB_PORT) — the first compile can take a while"
started=$(now)
if ! wait_http web "http://127.0.0.1:$WEB_PORT/" "$WEB_TIMEOUT" 30 "$WEB_PID" any; then
  show_log_tail web
  fail "The web app is not answering: $WAIT_REASON"
fi
ok "Web app is up ($(($(now) - started))s)"

# i. URLs ---------------------------------------------------------------------------------------------
mailpit_up=""
if [[ -n "$(docker ps -q --filter label=com.docker.compose.project=bayflow --filter label=com.docker.compose.service=mailpit --filter status=running 2>/dev/null)" ]]; then
  mailpit_up=1
fi
printf '\n%s  BayFlow is running%s\n' "$BOLD" "$RESET"
printf '  %s──────────────────%s\n' "$DIM" "$RESET"
printf '  Web app ....... %shttp://localhost:%s%s\n' "$CYAN" "$WEB_PORT" "$RESET"
printf '  API docs ...... %shttp://localhost:%s/docs%s\n' "$CYAN" "$API_PORT" "$RESET"
printf '  API health .... %shttp://localhost:%s/health%s\n' "$CYAN" "$API_PORT" "$RESET"
if [[ -n "$mailpit_up" ]]; then
  printf '  Mailpit ....... %shttp://localhost:8025%s\n' "$CYAN" "$RESET"
fi
printf '  PostgreSQL .... localhost:%s  (database, user and password: bayflow)\n' "$db_port"
printf '  Logs .......... logs/api.log  logs/web.log\n'
stop_hint="./stop.sh"
((DETACH)) || stop_hint="./stop.sh  (or Ctrl+C here)"
printf '  Stop .......... %s\n' "$stop_hint"
if ((SEED)) || [[ "${SEED_ON_DEPLOY:-}" == "true" ]]; then
  printf '  Demo logins ... password BayFlow@2026, e.g. bilal.sa@bayflow.test (all accounts: README.md)\n'
else
  printf '  %sSEED_ON_DEPLOY is not true in .env, so no demo data was loaded: ./start.sh --seed (or make seed)%s\n' "$DIM" "$RESET"
fi

if ((DETACH)); then
  trap - INT TERM HUP
  LAUNCHED=0 # hand-off: the services keep running after this script exits
  printf '\n'
  ok "Started in the background (--detach). Stop with ./stop.sh"
  exit 0
fi

# j. Stream the logs until Ctrl+C -------------------------------------------------------------------------
printf '\n%s  Streaming logs — press Ctrl+C to stop everything%s\n\n' "$BOLD" "$RESET"
rm -f "$FIFO"
mkfifo "$FIFO"
tail_args=(-n +1 -F)
if tail --version 2>/dev/null | grep -q GNU; then
  tail_args=(--pid="$$" -n +1 -F) # GNU tail also exits if this script is killed with SIGKILL
fi
(cd "$LOG_DIR" && exec tail "${tail_args[@]}" api.log web.log) >"$FIFO" 2>/dev/null &
TAIL_PID=$!
prefix_logs <"$FIFO" &
PREFIX_PID=$!

# `wait` returns as soon as a trapped signal arrives, so Ctrl+C is handled immediately.
while :; do
  if ! group_alive "$API_PID" && ! group_alive "$WEB_PID"; then
    stop_streamer
    LAUNCHED=0
    printf '\n'
    warn "The API and the web app have stopped (was ./stop.sh run elsewhere?) — exiting"
    exit 0
  fi
  sleep 1 &
  wait "$!" || true
done
