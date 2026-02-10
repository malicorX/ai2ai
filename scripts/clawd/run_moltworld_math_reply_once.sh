#!/usr/bin/env bash
# Run one isolated MoltWorld turn on OpenClaw using the SAME generic instruction as production cron.
# The agent must read the question FROM the world (world_state → recent_chat) and answer it itself.
# No hardwired "answer with the sum" or question text outside the bot.
# Usage: bash run_moltworld_math_reply_once.sh
# Requires: openclaw in PATH (source nvm/bashrc if needed).
set -e
source ~/.nvm/nvm.sh 2>/dev/null || true
source ~/.bashrc 2>/dev/null || true

# Same as add_moltworld_chat_cron.ps1 for sparky2: answer questions with number only; never Hi.
MSG='You are MalicorSparky2. Call world_state first. If the LAST message in recent_chat is a math question (e.g. "how much is 7+?" or "how much is 3+2?"), call chat_say with ONLY the number (e.g. "7" or "5")—never "Hi". Example: "how much is 3+2?" -> chat_say text "5". If not a question, call chat_say with one short greeting. Use only these tools; no plain-text output.'

# Add one-shot isolated job (far-future at so it only runs when we --force)
OUT=$(openclaw cron add --name "Math reply once" --at "2030-01-01T00:00:00Z" --session isolated --message "$MSG" --wake now --no-deliver 2>&1) || true
# Accept "id":"uuid" or "id": "uuid" (pretty-printed)
ID=$(echo "$OUT" | grep -oE '"id"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
if [[ -z "$ID" ]]; then
  echo "{\"ok\":false,\"error\":\"could not parse job id from: $OUT\"}"
  exit 1
fi
openclaw cron run "$ID" --force --timeout 120000
openclaw cron remove "$ID" 2>/dev/null || true
echo '{"ok":true,"ran":true}'
