#!/usr/bin/env bash
# Strip every openclaw-moltworld reference from OpenClaw/Clawdbot config so the gateway never loads it.
# Usage: bash strip_moltworld_from_config.sh
set -e
for CONFIG in "$HOME/.openclaw/openclaw.json" "$HOME/.clawdbot/clawdbot.json" "$HOME/.clawdbot/openclaw.json" "$HOME/.openclaw/clawdbot.json"; do
  [[ -f "$CONFIG" ]] || continue
  # jq: delete .plugins.entries["openclaw-moltworld"] and any top-level key that might list it
  if jq 'del(.plugins.entries["openclaw-moltworld"])' "$CONFIG" > "${CONFIG}.tmp"; then
    mv "${CONFIG}.tmp" "$CONFIG"
    echo "Stripped openclaw-moltworld from $CONFIG"
  fi
done
