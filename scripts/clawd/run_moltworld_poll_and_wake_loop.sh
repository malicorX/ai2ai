#!/usr/bin/env bash
# Light poll every POLL_INTERVAL_SEC (default 5): GET /chat/recent?limit=1 only. When the last message
# changes, run full pull-and-wake once, then cooldown so we don't re-trigger during the same turn.
# Response time: ~5s to detect new message + ~60–90s for the turn (vs 2+ min with cron every 2 min).
#
# Usage: CLAW=openclaw bash run_moltworld_poll_and_wake_loop.sh
#   Or:  POLL_INTERVAL_SEC=5 COOLDOWN_AFTER_WAKE_SEC=60 CLAW=openclaw bash run_moltworld_poll_and_wake_loop.sh
# Run in background: nohup bash run_moltworld_poll_and_wake_loop.sh >> ~/.moltworld_poll.log 2>&1 &
# Requires: same as run_moltworld_pull_and_wake.sh (~/.moltworld.env, gateway, hooks). Script dir must contain run_moltworld_pull_and_wake.sh.
set -e

POLL_INTERVAL_SEC="${POLL_INTERVAL_SEC:-5}"
COOLDOWN_AFTER_WAKE_SEC="${COOLDOWN_AFTER_WAKE_SEC:-60}"
SCRIPT_DIR="${SCRIPT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
PULL_SCRIPT="${SCRIPT_DIR}/run_moltworld_pull_and_wake.sh"
STATE_FILE="${HOME}/.moltworld_last_chat"

ENV_FILE="${HOME}/.moltworld.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found." >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$ENV_FILE"
BASE_URL="${WORLD_API_BASE:-https://www.theebie.de}"
AGENT_ID="${AGENT_ID:-}"

if [[ ! -f "$PULL_SCRIPT" ]]; then
  echo "ERROR: $PULL_SCRIPT not found. Set SCRIPT_DIR or run from scripts/clawd." >&2
  exit 1
fi

cooldown_until=0
while true; do
  now=$(date +%s)
  if [[ $now -lt $cooldown_until ]]; then
    sleep "$POLL_INTERVAL_SEC"
    continue
  fi

  RECENT_JSON=$(curl -s -S -H "Content-Type: application/json" "$BASE_URL/chat/recent?limit=1" 2>/dev/null) || true
  FINGERPRINT=""
  if [[ -n "$RECENT_JSON" ]]; then
    FINGERPRINT=$(python3 -c "
import json, sys
try:
    d = json.loads(sys.argv[1])
    msgs = d.get('messages') or []
    if not msgs:
        sys.exit(0)
    m = msgs[-1]
    ts = m.get('created_at') or 0
    sid = (m.get('sender_id') or '').strip()
    txt = (m.get('text') or '').strip()[:500]
    print(f'{ts}|{sid}|{txt}')
except Exception:
    pass
" "$RECENT_JSON" 2>/dev/null) || true
  fi

  PREV=$(cat "$STATE_FILE" 2>/dev/null) || true
  if [[ -n "$FINGERPRINT" && "$FINGERPRINT" != "$PREV" ]]; then
    # If last message is from us, just update state (no need to wake to reply to ourselves)
    last_sender="${FINGERPRINT#*|}"
    last_sender="${last_sender%%|*}"
    if [[ -n "$AGENT_ID" && "$last_sender" = "$AGENT_ID" ]]; then
      echo "$FINGERPRINT" > "$STATE_FILE"
    else
      echo "$(date '+%Y-%m-%dT%H:%M:%S') new message, running pull-and-wake"
      if CLAW="${CLAW:-openclaw}" bash "$PULL_SCRIPT" >/dev/null 2>&1; then
        cooldown_until=$((now + COOLDOWN_AFTER_WAKE_SEC))
      fi
    fi
  fi

  sleep "$POLL_INTERVAL_SEC"
done
