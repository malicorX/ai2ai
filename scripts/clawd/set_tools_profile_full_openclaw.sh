#!/usr/bin/env bash
# Set tools.profile=full and remove tools.allow in OpenClaw config so Chat gets browser, web_fetch, etc.
# Usage: bash set_tools_profile_full_openclaw.sh
set -e
for CONFIG in "$HOME/.openclaw/openclaw.json" "$HOME/.clawdbot/clawdbot.json"; do
  [[ -f "$CONFIG" ]] || continue
  tmp=$(mktemp)
  jq '.tools = ((.tools // {}) | del(.allow) | . + {"profile": "full"})' "$CONFIG" > "$tmp"
  mv "$tmp" "$CONFIG"
  echo "Set tools.profile=full and removed tools.allow in $CONFIG"
done
