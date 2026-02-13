#!/usr/bin/env bash
# Run MoltWorld narrator turn via the OpenClaw gateway (pull-and-wake).
# Usage: cd ~/ai_ai2ai && AGENT_ID=Sparky1Agent bash scripts/clawd/run_moltworld_openclaw_narrator_loop.sh
# Requires: ~/.moltworld.env (WORLD_AGENT_TOKEN, AGENT_ID, DISPLAY_NAME), OpenClaw gateway on 127.0.0.1:18789.
# Background: nohup bash run_moltworld_openclaw_narrator_loop.sh >> ~/.moltworld_openclaw_narrator.log 2>&1 </dev/null &
set -e
NARRATOR_INTERVAL_SEC="${NARRATOR_INTERVAL_SEC:-120}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WAKE_SCRIPT="${SCRIPT_DIR}/run_moltworld_pull_and_wake.sh"
export AGENT_ID="${AGENT_ID:-Sparky1Agent}"
export DISPLAY_NAME="${DISPLAY_NAME:-$AGENT_ID}"
if [[ ! -f "$WAKE_SCRIPT" ]]; then
  echo "ERROR: $WAKE_SCRIPT not found." >&2
  exit 1
fi
ENV_FILE="${HOME}/.moltworld.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  source <(tr -d '\r' < "$ENV_FILE") 2>/dev/null || true
  set +a
fi
cd "$REPO_ROOT"
while true; do
  echo "$(date '+%Y-%m-%dT%H:%M:%S') narrator (OpenClaw pull-and-wake)"
  out=""
  if out=$(bash "$WAKE_SCRIPT" 2>&1); then
    echo "  ok"
  else
    echo "  error"
  fi
  if [[ -n "${MOLTWORLD_DEBUG:-}" ]]; then
    echo "$out" | head -5
  fi
  sleep "$NARRATOR_INTERVAL_SEC" || true
done
