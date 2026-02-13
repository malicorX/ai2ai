#!/usr/bin/env bash
# Add EnvironmentFile=~/.moltworld.env to the user's gateway service (openclaw-gateway or clawdbot-gateway) so the plugin gets WORLD_AGENT_TOKEN.
# Usage: ssh sparky2 'bash -s' < sparky2_systemd_moltworld_env.sh
set -e
UNIT="$HOME/.config/systemd/user/openclaw-gateway.service"
[[ ! -f "$UNIT" ]] && UNIT="$HOME/.config/systemd/user/clawdbot-gateway.service"
MOLTWORLD_ENV="$HOME/.moltworld.env"
if [[ ! -f "$UNIT" ]]; then
  echo "No $UNIT found. Skip."
  exit 0
fi
if [[ ! -f "$MOLTWORLD_ENV" ]]; then
  echo "No $MOLTWORLD_ENV. Skip."
  exit 0
fi
mkdir -p "$(dirname "$UNIT")"
# Add EnvironmentFile before ExecStart if not already present
if grep -q "EnvironmentFile.*moltworld" "$UNIT" 2>/dev/null; then
  echo "Already has EnvironmentFile for moltworld."
  exit 0
fi
# Insert line after [Service]
sed -i '/^\[Service\]/a EnvironmentFile='$MOLTWORLD_ENV'' "$UNIT"
systemctl --user daemon-reload
echo "Added EnvironmentFile=$MOLTWORLD_ENV to $UNIT. Restart gateway to apply."
exit 0
