#!/bin/bash
# Simple movement loop: upsert agent, then random-walk on the world grid.
# Usage: WORLD_URL=http://sparky1:8000 AGENT_ID=openclaw_bot DISPLAY_NAME="OpenClaw Bot" ./world_agent_move_loop.sh
# Optional: STEP_SECONDS=5 (default)
set -e

WORLD_URL="${WORLD_URL:-http://sparky1:8000}"
AGENT_ID="${AGENT_ID:-openclaw_bot}"
DISPLAY_NAME="${DISPLAY_NAME:-OpenClaw Bot}"
STEP_SECONDS="${STEP_SECONDS:-5}"

echo "World URL: $WORLD_URL"
echo "Agent: $AGENT_ID ($DISPLAY_NAME)"
echo "Step seconds: $STEP_SECONDS"

# Upsert agent (creates if missing)
curl -s -X POST "$WORLD_URL/agents/upsert" \
  -H "Content-Type: application/json" \
  -d "{\"agent_id\":\"$AGENT_ID\",\"display_name\":\"$DISPLAY_NAME\"}" >/dev/null

while true; do
  dx=$(( (RANDOM % 3) - 1 ))
  dy=$(( (RANDOM % 3) - 1 ))
  curl -s -X POST "$WORLD_URL/agents/$AGENT_ID/move" \
    -H "Content-Type: application/json" \
    -d "{\"dx\":$dx,\"dy\":$dy}" >/dev/null
  sleep "$STEP_SECONDS"
done
