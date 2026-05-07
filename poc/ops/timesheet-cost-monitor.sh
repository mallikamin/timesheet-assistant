#!/usr/bin/env bash
# Edge-side monitor for the Timesheet Assistant on Render.
# Two modes:
#   daily-summary   ??? called once daily (09:00 PKT). Always emails.
#   anomaly-check   ??? called every 30 min. Emails ONLY if a new anomaly is
#                       seen (one alert per type per day, like rsync-orbit.sh).
#
# Pulls everything via HTTPS:
#   GET /health                     ??? up/down + build marker
#   GET /api/admin/usage            ??? token-gated, returns live windows + history
# Auth via X-Admin-Token header from /home/loom-edge-01/.timesheet-monitor.env.
# That .env file is chmod 600, never committed, lives only on this box.

set -uo pipefail

# ---- Config ---------------------------------------------------------------

BASE_URL="https://timesheet-assistant-jclk.onrender.com"
ENV_FILE="/home/loom-edge-01/.timesheet-monitor.env"
LOCAL_DIR="/srv/timesheet-monitor"
STATE_FILE="$LOCAL_DIR/.state.json"
LOG_FILE="$LOCAL_DIR/monitor.log"
SUBJECT_PREFIX="[Timesheet]"

# Anomaly thresholds
ORG_HOURLY_PCT_WARN=50      # alert when org_hourly_tokens >= 50% of cap
USER_DAILY_PCT_WARN=80      # alert when any user_daily_tokens >= 80% of cap
HEALTH_TIMEOUT_SEC=15

# Haiku 4.5 rough list rates ($ / MTok). Used only for "estimated cost"
# rendering ??? not for any decision logic. Tune later from real invoice.
RATE_INPUT=1.00
RATE_CACHE_WRITE=1.25
RATE_CACHE_READ=0.10
RATE_OUTPUT=5.00

mkdir -p "$LOCAL_DIR"

if [ ! -r "$ENV_FILE" ]; then
  echo "[$(date -Iseconds)] FATAL: $ENV_FILE missing or unreadable" >> "$LOG_FILE"
  exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"
if [ -z "${ADMIN_API_TOKEN:-}" ]; then
  echo "[$(date -Iseconds)] FATAL: ADMIN_API_TOKEN not set in $ENV_FILE" >> "$LOG_FILE"
  exit 1
fi

TS=$(date -Iseconds)
TODAY=$(date +%F)
HOST=$(hostname)
MODE="${1:-anomaly-check}"

# ---- Helpers --------------------------------------------------------------

log() { echo "[$TS] $*" >> "$LOG_FILE"; }

send_email() {
  local subject=$1 body=$2
  printf "Subject: %s %s\nFrom: mallikamiin@gmail.com\nTo: mallikamiin@gmail.com, amin@sitaratech.info\n\n%s\n\n--\nSent: %s\nFrom host: %s\n" \
    "$SUBJECT_PREFIX" "$subject" "$body" "$TS" "$HOST" \
    | msmtp -a default mallikamiin@gmail.com amin@sitaratech.info
  log "EMAIL SENT: $subject"
}

# Read flag from state. Resets to "false" automatically if the state's
# `today` field doesn't match the current date.
get_flag() {
  local key=$1
  if [ ! -f "$STATE_FILE" ]; then echo false; return; fi
  local stored_today
  stored_today=$(jq -r '.today // ""' "$STATE_FILE" 2>/dev/null)
  if [ "$stored_today" != "$TODAY" ]; then echo false; return; fi
  jq -r --arg k "$key" '.[$k] // false' "$STATE_FILE" 2>/dev/null
}

set_flag() {
  local key=$1 value=$2
  local cur="{\"today\":\"$TODAY\"}"
  if [ -f "$STATE_FILE" ]; then
    local stored_today
    stored_today=$(jq -r '.today // ""' "$STATE_FILE" 2>/dev/null)
    if [ "$stored_today" = "$TODAY" ]; then
      cur=$(cat "$STATE_FILE")
    fi
  fi
  echo "$cur" | jq --arg k "$key" --argjson v "$value" '.[$k] = $v | .today = "'"$TODAY"'"' > "$STATE_FILE.tmp" \
    && mv "$STATE_FILE.tmp" "$STATE_FILE"
}

# Curl wrapper: returns body on 2xx, empty + nonzero exit on anything else.
curl_get() {
  local path=$1 extra=${2:-}
  curl -sS --max-time "$HEALTH_TIMEOUT_SEC" \
    -H "X-Admin-Token: $ADMIN_API_TOKEN" \
    $extra \
    -w "\n__HTTP_STATUS__%{http_code}" \
    "$BASE_URL$path" 2>/dev/null
}

# ---- Pull live data -------------------------------------------------------

HEALTH_RAW=$(curl_get "/health")
HEALTH_STATUS=$(echo "$HEALTH_RAW" | sed -n 's/.*__HTTP_STATUS__\([0-9]*\)$/\1/p')
HEALTH_BODY=$(echo "$HEALTH_RAW" | sed '$d')

USAGE_RAW=$(curl_get "/api/admin/usage")
USAGE_STATUS=$(echo "$USAGE_RAW" | sed -n 's/.*__HTTP_STATUS__\([0-9]*\)$/\1/p')
USAGE_BODY=$(echo "$USAGE_RAW" | sed '$d')

log "MODE=$MODE health_http=$HEALTH_STATUS usage_http=$USAGE_STATUS"

# ---- Build summary text ---------------------------------------------------

build_summary() {
  if [ "$USAGE_STATUS" != "200" ]; then
    echo "Could not fetch /api/admin/usage (HTTP $USAGE_STATUS)."
    return
  fi
  local org_now org_cap
  org_now=$(echo "$USAGE_BODY" | jq -r '.live_org.hourly_tokens // 0')
  org_cap=$(echo "$USAGE_BODY" | jq -r '.live_org.hourly_cap // 0')

  echo "Live windows (right now)"
  echo "  Org hourly:   $org_now / $org_cap tokens"
  echo
  echo "Per-user 24h tokens (live)"
  echo "$USAGE_BODY" | jq -r '
    .live_users // {}
    | to_entries
    | sort_by(-.value.daily_tokens)
    | .[]
    | "  \(.key): \(.value.daily_tokens) / \(.value.daily_cap)"
  '
  echo
  echo "History today (per-user totals from training_log)"
  echo "$USAGE_BODY" | jq -r --arg today "$TODAY" '
    .history_by_user_day // {}
    | to_entries
    | map({email: .key, day: $today, stats: (.value[$today] // null)})
    | map(select(.stats != null))
    | sort_by(-(.stats.input_tokens + .stats.output_tokens))
    | .[]
    | "  \(.email): \(.stats.calls) calls  in=\(.stats.input_tokens)  out=\(.stats.output_tokens)  cache_read=\(.stats.cache_read_input_tokens)"
  '
  echo
  # Cost estimate ??? rough, list-rate, not actual invoice
  local in_tok out_tok cw cr
  in_tok=$(echo "$USAGE_BODY" | jq -r --arg today "$TODAY" '
    [.history_by_user_day // {} | .[] | (.[$today].input_tokens // 0)] | add // 0
  ')
  out_tok=$(echo "$USAGE_BODY" | jq -r --arg today "$TODAY" '
    [.history_by_user_day // {} | .[] | (.[$today].output_tokens // 0)] | add // 0
  ')
  cw=$(echo "$USAGE_BODY" | jq -r --arg today "$TODAY" '
    [.history_by_user_day // {} | .[] | (.[$today].cache_creation_input_tokens // 0)] | add // 0
  ')
  cr=$(echo "$USAGE_BODY" | jq -r --arg today "$TODAY" '
    [.history_by_user_day // {} | .[] | (.[$today].cache_read_input_tokens // 0)] | add // 0
  ')
  local cost
  cost=$(awk -v ai="$in_tok" -v ao="$out_tok" -v cw="$cw" -v cr="$cr" \
    -v ri="$RATE_INPUT" -v rcw="$RATE_CACHE_WRITE" -v rcr="$RATE_CACHE_READ" -v ro="$RATE_OUTPUT" \
    'BEGIN { printf "%.4f", (ai*ri + cw*rcw + cr*rcr + ao*ro)/1000000 }')
  echo "Estimated cost today (Haiku 4.5 list rates): \$${cost}"
  echo "  in=$in_tok  out=$out_tok  cache_write=$cw  cache_read=$cr"
}

# ---- Anomaly detection ----------------------------------------------------

check_anomalies() {
  # 1. Service down ??? /health not 200
  if [ "$HEALTH_STATUS" != "200" ]; then
    if [ "$(get_flag alerted_health_down)" != "true" ]; then
      send_email "ALERT: service /health failed (HTTP $HEALTH_STATUS)" \
"The Render-hosted Timesheet Assistant returned HTTP $HEALTH_STATUS to /health.

Body (first 500 chars):
$(echo "$HEALTH_BODY" | head -c 500)

Source: $BASE_URL/health
Time: $TS"
      set_flag alerted_health_down true
    fi
    return
  else
    # Healthy ??? clear the down-flag so the next outage re-fires
    set_flag alerted_health_down false
  fi

  if [ "$USAGE_STATUS" != "200" ]; then
    if [ "$(get_flag alerted_admin_unauth)" != "true" ]; then
      send_email "ALERT: /api/admin/usage returned HTTP $USAGE_STATUS" \
"Edge cron could not pull cost data from $BASE_URL/api/admin/usage.
HTTP $USAGE_STATUS. Likely cause: ADMIN_API_TOKEN env var on Render
doesn't match $ENV_FILE on edge.

Body (first 500 chars):
$(echo "$USAGE_BODY" | head -c 500)

Time: $TS"
      set_flag alerted_admin_unauth true
    fi
    return
  fi

  # 2. Org hourly window over warn threshold
  local org_now org_cap pct
  org_now=$(echo "$USAGE_BODY" | jq -r '.live_org.hourly_tokens // 0')
  org_cap=$(echo "$USAGE_BODY" | jq -r '.live_org.hourly_cap // 0')
  if [ "$org_cap" -gt 0 ]; then
    pct=$(( org_now * 100 / org_cap ))
    if [ "$pct" -ge "$ORG_HOURLY_PCT_WARN" ] && [ "$(get_flag alerted_org_hourly)" != "true" ]; then
      send_email "WARN: org hourly token spend at ${pct}% of cap" \
"Combined Anthropic-token spend across all users in the last hour has
crossed ${ORG_HOURLY_PCT_WARN}% of HOURLY_BUDGET_CEILING.

  Now: $org_now tokens
  Cap: $org_cap tokens

If this stays elevated, the org-wide circuit breaker will fire and every
chat call will return a billing-pause 503 until the window rolls.

Time: $TS"
      set_flag alerted_org_hourly true
    fi
  fi

  # 3. Any user over 80% of their daily cap
  local hot_users
  hot_users=$(echo "$USAGE_BODY" | jq -r --arg pct "$USER_DAILY_PCT_WARN" '
    .live_users // {}
    | to_entries[]
    | select(.value.daily_cap > 0)
    | select((.value.daily_tokens * 100 / .value.daily_cap) >= ($pct | tonumber))
    | "\(.key): \(.value.daily_tokens) / \(.value.daily_cap)"
  ')
  if [ -n "$hot_users" ] && [ "$(get_flag alerted_user_daily)" != "true" ]; then
    send_email "WARN: user(s) approaching daily token cap" \
"One or more users have crossed ${USER_DAILY_PCT_WARN}% of their daily
DAILY_TOKEN_CAP. Once they hit 100%, they get a billing-pause message
on every chat call until their 24h window rolls.

$hot_users

Time: $TS"
    set_flag alerted_user_daily true
  fi

  # 4. Per-turn budget tripped today (sign of a runaway loop)
  local tripped_today
  tripped_today=$(echo "$USAGE_BODY" | jq -r --arg today "$TODAY" '
    [.history_by_user_day // {} | .[] | (.[$today].turn_budget_tripped_count // 0)] | add // 0
  ')
  if [ "$tripped_today" -gt 0 ] && [ "$(get_flag alerted_turn_budget)" != "true" ]; then
    send_email "ALERT: per-turn token budget tripped (count=$tripped_today)" \
"PER_TURN_TOKEN_BUDGET fired ${tripped_today} time(s) today. This means
a single chat turn ran past its token ceiling and was aborted mid-flight.
Most common cause: a runaway tool loop or pathological context bloat.

Pull /api/admin/usage from a logged-in admin browser to see which users
hit it, and grep training_log for turn_budget_tripped=true to find the
exact prompts.

Time: $TS"
    set_flag alerted_turn_budget true
  fi
}

# ---- Mode dispatch --------------------------------------------------------

case "$MODE" in
  daily-summary)
    summary=$(build_summary)
    build_marker=$(echo "$HEALTH_BODY" | jq -r '.build.marker // "?"' 2>/dev/null)
    send_email "Daily AI cost summary  $TODAY" \
"Daily Anthropic-spend summary for the Timesheet Assistant.

$summary

Service health: HTTP $HEALTH_STATUS
Build marker:   $build_marker
Source:         $BASE_URL/api/admin/usage

??? generated by ~/scripts/timesheet-cost-monitor.sh"
    ;;
  anomaly-check)
    check_anomalies
    ;;
  *)
    echo "Usage: $0 {daily-summary|anomaly-check}" >&2
    exit 2
    ;;
esac

log "MODE=$MODE done"
