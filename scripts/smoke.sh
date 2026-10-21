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
