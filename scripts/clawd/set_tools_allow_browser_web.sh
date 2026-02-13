#!/usr/bin/env bash
# Set tools.allow to include browser and web_fetch so Chat gets them. Keeps profile=full.
# Usage: bash set_tools_allow_browser_web.sh
set -e
ALLOW='["browser","web_fetch","fetch_url","web_search","read","write","exec","session_status"]'
for CONFIG in "$HOME/.openclaw/openclaw.json" "$HOME/.clawdbot/clawdbot.json"; do
  [[ -f "$CONFIG" ]] || continue
  tmp=$(mktemp)
  jq --argjson allow "$ALLOW" '.tools = ((.tools // {}) | . + {"profile": "full", "allow": $allow})' "$CONFIG" > "$tmp"
  mv "$tmp" "$CONFIG"
  echo "Set tools.profile=full and tools.allow (browser, web_fetch, ...) in $CONFIG"
done
