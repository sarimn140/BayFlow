#!/usr/bin/env bash
# stop.sh — stop the BayFlow local dev stack (Linux/macOS) and free ports 3000 and 4000 (D73, spec 07).
# Windows: stop.bat. ./start.sh also calls this script (--keep-db --quiet) to free the ports first.
#
#   1. SIGTERM the process groups recorded by start.sh (.run/pids, .run/api.pid, .run/web.pid),
#      wait up to 10 s, SIGKILL stragglers
#   2. stop BayFlow's own Docker api/web containers if they run (`docker compose up` publishes 3000/4000)
#   3. port backstop: stop whatever still listens on 4000/3000 — never Docker/VM/SSH port forwarders.
#      With --bayflow-only only processes running inside this repository are stopped
#   4. pattern backstop: this repo's leftover uvicorn / next dev processes, matched by command line
#      AND working directory (no regex on the repo path, which may contain "(", ")" and the like)
#   5. remove Next.js dev lock state (apps/web/.next/dev, apps/web/.next/lock) and the PID files
#   6. `docker compose stop db` unless --keep-db — the data volume is never removed (make db-reset wipes data)
#   7. verify that ports 3000 and 4000 are free; otherwise name the holder and exit 1
#
# Deliberately no `set -e`: cleanup keeps going when a step fails. Safe to run twice. Works with
# macOS's bash 3.2.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$ROOT" || exit 1
WEB_DIR="$ROOT/apps/web"
RUN_DIR="$ROOT/.run"
PID_FILE="$RUN_DIR/pids"
PORTS="4000 3000"

KEEP_DB=0
QUIET=0
BAYFLOW_ONLY=0

usage() {
  cat <<'EOF'
Usage: ./stop.sh [--keep-db] [--quiet] [--bayflow-only] [--help]

Stops the BayFlow dev stack started by ./start.sh and frees ports 3000 and 4000.

  --keep-db       leave the PostgreSQL container running
  --quiet         print only problems
  --bayflow-only  stop only BayFlow's own processes; if another program holds 3000/4000,
                  name it and exit 1 instead of stopping it. Not used by ./start.sh, which
                  frees the ports from any program
  -h, --help      show this help

The database volume is always kept. To wipe the local data: make db-reset
EOF
}

while (($#)); do
  case "$1" in
    --keep-db) KEEP_DB=1 ;;
    --quiet) QUIET=1 ;;
    --bayflow-only) BAYFLOW_ONLY=1 ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      printf 'stop.sh: unknown option: %s\n\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

# -- output helpers (colour only on a terminal; NO_COLOR disables it) --------------------------
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  RED=$'\033[31m' GREEN=$'\033[32m' YELLOW=$'\033[33m' BOLD=$'\033[1m' RESET=$'\033[0m'
else
  RED='' GREEN='' YELLOW='' BOLD='' RESET=''
fi
say() { ((QUIET)) || printf '%s\n' "$*"; }
ok() { ((QUIET)) || printf '%s✓ %s%s\n' "$GREEN" "$*" "$RESET"; }
warn() { printf '%s⚠ %s%s\n' "$YELLOW" "$*" "$RESET"; }
err() { printf '%s✗ %s%s\n' "$RED" "$*" "$RESET" >&2; }

# -- process helpers ------------------------------------------------------------------------
alive() { kill -0 "$1" 2>/dev/null; }

# Working directory of a process ("" when unknown): /proc on Linux, lsof on macOS.
proc_cwd() {
  if [[ -L "/proc/$1/cwd" ]]; then
    readlink "/proc/$1/cwd" 2>/dev/null
  elif command -v lsof >/dev/null 2>&1; then
    lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1
  fi
  return 0
}

proc_args() { ps -o args= -p "$1" 2>/dev/null; }

proc_name() {
  local comm
  comm="$(ps -o comm= -p "$1" 2>/dev/null)"
  printf '%s' "${comm##*/}"
}

# True when the process runs inside this repository. Plain string comparison: the quoted
# "$ROOT" is matched literally, so "(" and ")" in the path are harmless.
in_repo() {
  local cwd
  cwd="$(proc_cwd "$1")"
  [[ -n "$cwd" ]] || return 1
  case "$cwd" in
    "$ROOT" | "$ROOT"/*) return 0 ;;
  esac
  return 1
}

# The recorded PID really is our api/web process (protects against PID reuse after a reboot).
looks_like_service() {
  local pid="$1" name="$2" args
  in_repo "$pid" || return 1
  args="$(proc_args "$pid")"
  case "$name:$args" in
    api:*uvicorn* | api:*uv* | api:*python*) return 0 ;;
    web:*pnpm* | web:*next* | web:*node*) return 0 ;;
  esac
  return 1
}

group_members() { ps -Ao pid=,pgid= 2>/dev/null | awk -v g="$1" '$2 == g { print $1 }'; }

service_running() {
  local pgid="$1" name="$2" pid
  if alive "$pgid" && looks_like_service "$pgid" "$name"; then
    return 0
  fi
  for pid in $(group_members "$pgid"); do
    looks_like_service "$pid" "$name" && return 0
  done
  return 1
}

# Signal a recorded service: its whole process group when the leader is ours, otherwise only
# those members of the group that are ours.
signal_service() {
  local sig="$1" pgid="$2" name="$3" pid
  if alive "$pgid" && looks_like_service "$pgid" "$name"; then
    kill -s "$sig" -- "-$pgid" 2>/dev/null || kill -s "$sig" "$pgid" 2>/dev/null
    return 0
  fi
  for pid in $(group_members "$pgid"); do
    looks_like_service "$pid" "$name" && kill -s "$sig" "$pid" 2>/dev/null
  done
  return 0
}

# "name pid port" lines from .run/pids plus .run/<name>.pid files, one line per PID.
recorded_services() {
  local f name pid
  {
    [[ -f "$PID_FILE" ]] && cat "$PID_FILE"
    for f in "$RUN_DIR"/*.pid; do
      [[ -f "$f" ]] || continue
      name="${f##*/}"
      pid="$(head -n 1 "$f" | tr -dc '0-9')"
      printf '%s %s ?\n' "${name%.pid}" "$pid"
    done
  } 2>/dev/null | awk 'NF >= 2 && !seen[$2]++'
  return 0
}

# PIDs listening on a TCP port. The answers of lsof, fuser and ss are merged: each one alone has
# been seen to miss listeners (e.g. lsof 4.95 skips a Next.js dev server on Linux with Docker).
pids_on_port() {
  {
    if command -v lsof >/dev/null 2>&1; then
      lsof -nP -t -iTCP:"$1" -sTCP:LISTEN 2>/dev/null
    fi
    if command -v fuser >/dev/null 2>&1; then
      fuser -n tcp "$1" 2>/dev/null | tr -s ' \t' '\n'
      echo # fuser ends its output without a newline
    fi
    if command -v ss >/dev/null 2>&1; then
      ss -ltnp "sport = :$1" 2>/dev/null | grep -oE 'pid=[0-9]+' | cut -d= -f2
    fi
  } | grep -E '^[0-9]+$' | sort -u
  return 0
}

# Is anything listening on the port? Also catches listeners owned by other users (root,
# docker-proxy) that lsof cannot see without sudo.
port_busy() {
  [[ -n "$(pids_on_port "$1")" ]] && return 0
  if command -v ss >/dev/null 2>&1; then
    [[ -n "$(ss -ltn "sport = :$1" 2>/dev/null | tail -n +2)" ]] && return 0
  fi
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && return 0
  return 1
}

docker_holder() {
  command -v docker >/dev/null 2>&1 || return 0
  docker ps --filter "publish=$1" --format '{{.Names}}' 2>/dev/null | head -n 1
  return 0
}

# Who holds a port, for error messages.
describe_port() {
  local holder pid text=""
  holder="$(docker_holder "$1")"
  if [[ -n "$holder" ]]; then
    printf "the Docker container '%s' (stop it: docker stop %s)" "$holder" "$holder"
    return 0
  fi
  for pid in $(pids_on_port "$1"); do
    text="$text$(proc_name "$pid") (pid $pid): $(proc_args "$pid" | cut -c1-150); "
  done
  if [[ -n "$text" ]]; then
    printf '%s' "${text%; }"
  else
    printf 'a process this user cannot see (check: sudo lsof -nP -iTCP:%s -sTCP:LISTEN)' "$1"
  fi
}

# Wait up to $2 seconds for the PIDs in $1 to exit, then SIGKILL the rest.
term_then_kill() {
  local pids="$1" seconds="$2" pid left i=0
  while ((i < seconds * 4)); do
    left=""
    for pid in $pids; do
      alive "$pid" && left="$left $pid"
    done
    [[ -z "$left" ]] && return 0
    pids="$left"
    sleep 0.25
    i=$((i + 1))
  done
  for pid in $pids; do
    kill -s KILL "$pid" 2>/dev/null
  done
  return 0
}

free_port() {
  local port="$1" pid name killed=""
  for pid in $(pids_on_port "$port"); do
    [[ "$pid" == "$$" ]] && continue
    name="$(proc_name "$pid")"
    case "$name" in
      docker* | com.docker* | Docker* | vpnkit* | rootlesskit* | slirp4netns* | gvproxy* | limactl* | qemu* | OrbStack* | ssh | sshd)
        warn "Port $port is forwarded by ${name} (pid $pid) — Docker/VM/SSH port forwarding, not stopping it"
        continue
        ;;
    esac
    # --bayflow-only: another program's listener is reported by the verification step instead
    if ((BAYFLOW_ONLY)) && ! in_repo "$pid"; then
      continue
    fi
    warn "Port $port is held by ${name:-an unknown process} (pid $pid) — stopping it"
    kill -s TERM "$pid" 2>/dev/null
    killed="$killed $pid"
  done
  [[ -n "$killed" ]] && term_then_kill "$killed" 3
  return 0
}

# PIDs of this script's ancestors (parent, grandparent, …). They are never signalled: the shell
# or terminal that ran ./stop.sh may well have "next dev" in its command line and the repo as its
# working directory.
ancestor_pids() {
  local pid=$$ ppid
  while [[ -n "$pid" && "$pid" != "0" && "$pid" != "1" ]]; do
    ppid="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')"
    [[ -n "$ppid" ]] || break
    printf '%s\n' "$ppid"
    pid="$ppid"
  done
  return 0
}
ANCESTORS=" $(ancestor_pids | tr '\n' ' ') "

# This repo's leftover dev servers: fixed-string match on the command line (awk index(), the
# pattern passed through the environment so awk never matches itself), then three filters —
# never this script or one of its ancestors, only real server executables (node, the Next.js
# `next-server` child, python/uvicorn, the `uv` wrapper; never a shell, editor or grep), and only
# processes whose working directory is inside this repository.
repo_dev_pids() {
  local pattern pid
  for pattern in 'uvicorn app.main:app' 'next dev' 'next-server'; do
    for pid in $(ps -Ao pid=,args= 2>/dev/null | PATTERN="$pattern" awk 'index($0, ENVIRON["PATTERN"]) { print $1 }'); do
      [[ "$pid" == "$$" ]] && continue
      [[ "$ANCESTORS" == *" $pid "* ]] && continue
      case "$(proc_name "$pid")" in
        node | next-server* | python* | uvicorn | uv) ;;
        *) continue ;;
      esac
      in_repo "$pid" && printf '%s\n' "$pid"
    done
  done | sort -u
  return 0
}

compose() { docker compose -f "$ROOT/docker-compose.yml" -p bayflow "$@"; }

# -----------------------------------------------------------------------------------------------
say ""
say "${BOLD}Stopping BayFlow…${RESET}"

# 1. Process groups recorded by start.sh -------------------------------------------------------
TERMED=""
while read -r name pid port _rest; do
  [[ -n "${name:-}" && "${name:0:1}" != "#" ]] || continue
  [[ "${pid:-}" =~ ^[0-9]+$ ]] || continue
  if service_running "$pid" "$name"; then
    say "  $name (pid $pid, port ${port:-?}): SIGTERM"
    signal_service TERM "$pid" "$name"
    TERMED="$TERMED $name:$pid"
  else
    say "  $name (pid $pid): already stopped"
  fi
done <<<"$(recorded_services)"

if [[ -n "$TERMED" ]]; then
  waited=0
  while ((waited < 40)); do # up to 10 s for a clean shutdown
    still=""
    for entry in $TERMED; do
      service_running "${entry#*:}" "${entry%%:*}" && still="$still $entry"
    done
    TERMED="$still"
    [[ -z "$TERMED" ]] && break
    sleep 0.25
    waited=$((waited + 1))
  done
  for entry in $TERMED; do
    warn "${entry%%:*} (pid ${entry#*:}) ignored SIGTERM — sending SIGKILL"
    signal_service KILL "${entry#*:}" "${entry%%:*}"
  done
  [[ -n "$TERMED" ]] && sleep 0.5
fi

# 2. Docker: BayFlow's own api/web containers publish 3000/4000 (docker compose up) ------------
DOCKER_UP=0
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  DOCKER_UP=1
  running_services="$(compose ps --status running --services 2>/dev/null)"
  app_services=""
  for service in api web; do
    printf '%s\n' "$running_services" | grep -qx "$service" && app_services="$app_services $service"
  done
  if [[ -n "$app_services" ]]; then
    warn "Stopping BayFlow's Docker containers:$app_services (they publish ports 3000/4000)"
    # shellcheck disable=SC2086 # word splitting of the service list is intended
    compose stop $app_services >/dev/null 2>&1 || warn "docker compose stop$app_services failed"
  fi
fi

# 3. Port backstop -----------------------------------------------------------------------------
for port in $PORTS; do
  free_port "$port"
done

# 4. Pattern backstop: this repo's uvicorn / next processes that hold no port any more --------
leftovers="$(repo_dev_pids | tr '\n' ' ')"
if [[ -n "${leftovers// /}" ]]; then
  warn "Stopping leftover BayFlow dev processes: ${leftovers% }"
  for pid in $leftovers; do
    kill -s TERM "$pid" 2>/dev/null
  done
  term_then_kill "$leftovers" 3
fi

# 5. Next.js dev lock state (a stale lock makes the next `next dev` refuse to start), PID files -
rm -rf "$WEB_DIR/.next/dev" "$WEB_DIR/.next/lock" 2>/dev/null
rm -f "$PID_FILE" "$RUN_DIR/api.pid" "$RUN_DIR/web.pid"

# 6. PostgreSQL container (the volume is kept) -------------------------------------------------
if ((!KEEP_DB)); then
  if ((DOCKER_UP)); then
    if compose ps --status running --services 2>/dev/null | grep -qx db; then
      say "  db container: stopping (the data volume is kept)"
      compose stop db >/dev/null 2>&1 || warn "docker compose stop db failed — check: docker compose ps"
    fi
  else
    warn "Docker is not running (or not installed) — the db container was not stopped"
  fi
fi

# 7. Verify -----------------------------------------------------------------------------------
busy=""
for port in $PORTS; do
  port_busy "$port" && busy="$busy $port"
done
if [[ -n "$busy" ]]; then
  for port in $busy; do
    err "Port $port is still in use by $(describe_port "$port")"
  done
  if ((BAYFLOW_ONLY)); then
    err "BayFlow needs ports 3000 and 4000. Stop that program, or run ./stop.sh, which stops whatever listens there."
  fi
  exit 1
fi

if ((KEEP_DB)); then
  ok "BayFlow stopped. Ports 3000 and 4000 are free (PostgreSQL left running)."
else
  ok "BayFlow stopped. Ports 3000 and 4000 are free. Data kept; wipe it with: make db-reset"
fi
exit 0
