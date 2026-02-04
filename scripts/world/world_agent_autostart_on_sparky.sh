#!/bin/bash
# Install cron @reboot to start the world agent action loop.
# Usage: WORLD_URL=http://sparky1:8000 AGENT_ID=MalicorSparky2 AGENT_NAME="MalicorSparky2" ./world_agent_autostart_on_sparky.sh
set -e

WORLD_URL="${WORLD_URL:-http://sparky1:8000}"
AGENT_ID="${AGENT_ID:-MalicorSparky2}"
AGENT_NAME="${AGENT_NAME:-MalicorSparky2}"
STEP_SECONDS="${STEP_SECONDS:-6}"
SAY_EVERY_STEPS="${SAY_EVERY_STEPS:-10}"

SCRIPT="/home/malicor/ai2ai/scripts/world/world_agent_action_loop.sh"
LOG="/tmp/world_agent_loop.log"

LINE="@reboot WORLD_URL='$WORLD_URL' AGENT_ID='$AGENT_ID' AGENT_NAME='$AGENT_NAME' STEP_SECONDS=$STEP_SECONDS SAY_EVERY_STEPS=$SAY_EVERY_STEPS nohup $SCRIPT >> $LOG 2>&1 &"

tmp=$(mktemp)
crontab -l 2>/dev/null | grep -v "world_agent_action_loop.sh" > "$tmp" || true
echo "$LINE" >> "$tmp"
crontab "$tmp"
rm -f "$tmp"

echo "Installed cron @reboot for world agent loop."
