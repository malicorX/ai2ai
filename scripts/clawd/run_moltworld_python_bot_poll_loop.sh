#!/usr/bin/env bash
# Poll chat every N s; when last message changed and not from us, run Python MoltWorld bot once. Run from repo root.
# Usage: cd ~/ai_ai2ai && AGENT_ID=MalicorSparky2 bash scripts/clawd/run_moltworld_python_bot_poll_loop.sh
#   Or:  POLL_INTERVAL_SEC=10 COOLDOWN_AFTER_WAKE_SEC=45 AGENT_ID=MalicorSparky2 bash ...
# Background: nohup bash run_moltworld_python_bot_poll_loop.sh >> ~/.moltworld_python_poll.log 2>&1 &
set -e
POLL_INTERVAL_SEC="${POLL_INTERVAL_SEC:-10}"
COOLDOWN_AFTER_WAKE_SEC="${COOLDOWN_AFTER_WAKE_SEC:-45}"
STALE_THRESHOLD_SEC="${STALE_THRESHOLD_SEC:-300}"
STALE_WAKE_INTERVAL_SEC="${STALE_WAKE_INTERVAL_SEC:-120}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BOT_SCRIPT="${SCRIPT_DIR}/run_moltworld_python_bot.sh"
STATE_FILE="${HOME}/.moltworld_python_last_chat"
ENV_FILE="${HOME}/.moltworld.env"
BASE_URL="${WORLD_API_BASE:-https://www.theebie.de}"
export AGENT_ID="${AGENT_ID:-MalicorSparky2}"
export DISPLAY_NAME="${DISPLAY_NAME:-$AGENT_ID}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  source <(tr -d '\r' < "$ENV_FILE") 2>/dev/null || true
  set +a
fi
if [[ ! -f "$BOT_SCRIPT" ]]; then
  echo "ERROR: $BOT_SCRIPT not found." >&2
  exit 1
fi
cd "$REPO_ROOT"
PREV=""
cooldown_until=0
while true; do
  now=$(date +%s)
  if [[ $now -lt $cooldown_until ]]; then
    sleep "$POLL_INTERVAL_SEC" || true
    continue
  fi
  RECENT_JSON=$(curl -s -S -H "Content-Type: application/json" "$BASE_URL/chat/recent?limit=1" 2>/dev/null) || true
  FINGERPRINT=""
  LAST_CREATED_AT=""
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
    LAST_CREATED_AT=$(python3 -c "
import json, sys
try:
    d = json.loads(sys.argv[1])
    msgs = d.get('messages') or []
    if msgs:
        print(float(msgs[-1].get('created_at') or 0))
except Exception:
    pass
" "$RECENT_JSON" 2>/dev/null) || true
  fi
  run_wake=0
  if [[ -n "$FINGERPRINT" && "$FINGERPRINT" != "$PREV" ]]; then
    last_sender="${FINGERPRINT#*|}"
    last_sender="${last_sender%%|*}"
    if [[ -n "$AGENT_ID" && "$last_sender" = "$AGENT_ID" ]]; then
      PREV="$FINGERPRINT"
    else
      run_wake=1
      echo "$(date '+%Y-%m-%dT%H:%M:%S') new message, running Python bot"
    fi
  fi
  if [[ $run_wake -eq 0 && -n "$LAST_CREATED_AT" ]]; then
    age_sec=$(python3 -c "import time; print(int(time.time() - $LAST_CREATED_AT))" 2>/dev/null) || age_sec=0
    if [[ $age_sec -gt $STALE_THRESHOLD_SEC && $now -ge $cooldown_until ]]; then
      run_wake=1
      echo "$(date '+%Y-%m-%dT%H:%M:%S') chat stale (${age_sec}s), running Python bot"
      cooldown_until=$((now + STALE_WAKE_INTERVAL_SEC))
    fi
  fi
  if [[ $run_wake -eq 1 ]]; then
    out=$(bash "$BOT_SCRIPT" 2>&1) || true
    echo "  ${out:-?}"
    if [[ "$out" = "sent" ]]; then
      cooldown_until=$((now + COOLDOWN_AFTER_WAKE_SEC))
    fi
    PREV="$FINGERPRINT"
  fi
  sleep "$POLL_INTERVAL_SEC" || true
done
