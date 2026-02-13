#!/usr/bin/env bash
# Run Python MoltWorld bot (narrator) every N minutes. Use from repo root so venv is used.
# Usage: cd ~/ai_ai2ai && AGENT_ID=Sparky1Agent bash scripts/clawd/run_moltworld_python_bot_loop.sh
#   Or:  NARRATOR_INTERVAL_SEC=180 AGENT_ID=Sparky1Agent bash scripts/clawd/run_moltworld_python_bot_loop.sh
# Background: nohup bash run_moltworld_python_bot_loop.sh >> ~/.moltworld_python_narrator.log 2>&1 </dev/null &
set -e
NARRATOR_INTERVAL_SEC="${NARRATOR_INTERVAL_SEC:-120}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BOT_SCRIPT="${SCRIPT_DIR}/run_moltworld_python_bot.sh"
export AGENT_ID="${AGENT_ID:-Sparky1Agent}"
export DISPLAY_NAME="${DISPLAY_NAME:-$AGENT_ID}"
if [[ ! -f "$BOT_SCRIPT" ]]; then
  echo "ERROR: $BOT_SCRIPT not found." >&2
  exit 1
fi
cd "$REPO_ROOT"
# Loop body: no set -e so one failure (e.g. sleep) doesn't kill the loop
while true; do
  echo "$(date '+%Y-%m-%dT%H:%M:%S') narrator (Python bot)"
  result="error"
  out=""
  if out=$(bash "$BOT_SCRIPT" 2>&1); then
    result="ok"
  fi
  echo "  ${out:-$result}"
  sleep "$NARRATOR_INTERVAL_SEC" || true
done
