#!/usr/bin/env bash
# Run sparky1 (narrator) turn every N minutes: pull world, wake gateway. Sparky1 opens or continues conversations;
# when sparky1 posts, sparky2's poll loop sees the new message and wakes to reply. Requires ~/.moltworld.env on sparky1 with AGENT_ID=Sparky1Agent.
#
# Usage: CLAW=clawdbot bash run_moltworld_narrator_loop.sh
#   Or:  NARRATOR_INTERVAL_SEC=300 CLAW=clawdbot bash run_moltworld_narrator_loop.sh   # every 5 min
# Run in background: nohup bash run_moltworld_narrator_loop.sh >> ~/.moltworld_narrator.log 2>&1 &
set -e

NARRATOR_INTERVAL_SEC="${NARRATOR_INTERVAL_SEC:-300}"
SCRIPT_DIR="${SCRIPT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
PULL_SCRIPT="${SCRIPT_DIR}/run_moltworld_pull_and_wake.sh"
CLAW="${CLAW:-clawdbot}"

if [[ ! -f "$PULL_SCRIPT" ]]; then
  echo "ERROR: $PULL_SCRIPT not found." >&2
  exit 1
fi

while true; do
  echo "$(date '+%Y-%m-%dT%H:%M:%S') narrator turn (sparky1)"
  if CLAW="$CLAW" MOLTWORLD_SKIP_IF_UNCHANGED=0 bash "$PULL_SCRIPT" >/dev/null 2>&1; then
    echo "  done"
  else
    echo "  run failed (check ~/.moltworld.env and gateway)"
  fi
  sleep "$NARRATOR_INTERVAL_SEC"
done
