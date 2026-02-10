#!/usr/bin/env bash
# Run one isolated turn: call world_state, then chat_say RECEIVED if recent_chat contains ECHO_TOKEN, else NOT_RECEIVED.
# Verifies that the OpenClaw agent receives MoltWorld data (GET /world with recent_chat).
# Usage: ECHO_TOKEN="MOLTWORLD_ECHO_abc123" bash run_moltworld_echo_once.sh
set -e
source ~/.nvm/nvm.sh 2>/dev/null || true
source ~/.bashrc 2>/dev/null || true

ECHO_TOKEN="${ECHO_TOKEN:-MOLTWORLD_ECHO_TEST}"
# Message: only call tools; if recent_chat contains the token say RECEIVED else NOT_RECEIVED
MSG="Call world_state. Look at recent_chat (array of messages with text). If any message has text containing the exact string $ECHO_TOKEN, call chat_say with text RECEIVED. Otherwise call chat_say with text NOT_RECEIVED. Do not output any text; only call world_state and chat_say."

OUT=$(openclaw cron add --name "MoltWorld echo once" --at "2030-01-01T00:00:00Z" --session isolated --message "$MSG" --wake now --no-deliver 2>&1) || true
ID=$(echo "$OUT" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1)
if [[ -z "$ID" ]]; then
  echo "{\"ok\":false,\"error\":\"could not parse job id\"}"
  exit 1
fi
openclaw cron run "$ID" --force --timeout 120000
openclaw cron remove "$ID" 2>/dev/null || true
echo '{"ok":true,"ran":true}'
