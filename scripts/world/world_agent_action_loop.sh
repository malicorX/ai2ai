#!/bin/bash
# Simple action loop using /world/actions (move + say).
# Usage: WORLD_URL=http://sparky1:8000 AGENT_ID=MalicorSparky2 AGENT_NAME="MalicorSparky2" ./world_agent_action_loop.sh
set -e

WORLD_URL="${WORLD_URL:-http://sparky1:8000}"
AGENT_ID="${AGENT_ID:-MalicorSparky2}"
AGENT_NAME="${AGENT_NAME:-MalicorSparky2}"
STEP_SECONDS="${STEP_SECONDS:-6}"
SAY_EVERY_STEPS="${SAY_EVERY_STEPS:-10}"
WORLD_TOKEN="${WORLD_TOKEN:-}"

echo "World URL: $WORLD_URL"
echo "Agent: $AGENT_ID ($AGENT_NAME)"
if [ -n "$WORLD_TOKEN" ]; then
  echo "Auth: bearer token enabled"
fi

step=0
messages=(
  "Checking in."
  "Exploring the map."
  "Looking for other agents."
  "Testing world actions."
)

while true; do
  dx=$(( (RANDOM % 3) - 1 ))
  dy=$(( (RANDOM % 3) - 1 ))
  if [ -n "$WORLD_TOKEN" ]; then
    authHeader="-H Authorization: Bearer $WORLD_TOKEN"
  else
    authHeader=""
  fi
  curl -s -X POST "$WORLD_URL/world/actions" $authHeader \
    -H "Content-Type: application/json" \
    -d "{\"agent_id\":\"$AGENT_ID\",\"agent_name\":\"$AGENT_NAME\",\"action\":\"move\",\"params\":{\"dx\":$dx,\"dy\":$dy}}" >/dev/null

  step=$((step + 1))
  if [ $((step % SAY_EVERY_STEPS)) -eq 0 ]; then
    idx=$((RANDOM % ${#messages[@]}))
    text="${messages[$idx]}"
    curl -s -X POST "$WORLD_URL/world/actions" $authHeader \
      -H "Content-Type: application/json" \
      -d "{\"agent_id\":\"$AGENT_ID\",\"agent_name\":\"$AGENT_NAME\",\"action\":\"say\",\"params\":{\"text\":\"$text\"}}" >/dev/null
  fi

  sleep "$STEP_SECONDS"
done
