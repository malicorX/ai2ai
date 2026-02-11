#!/usr/bin/env bash
# Patch tools.allow to include MoltWorld plugin tools. Usage: CONFIG=~/.openclaw/openclaw.json bash patch_tools_allow_moltworld.sh
set -e
CONFIG="${CONFIG:-$HOME/.openclaw/openclaw.json}"
[[ -f "$CONFIG" ]] || CONFIG="$HOME/.clawdbot/clawdbot.json"
[[ -f "$CONFIG" ]] || { echo "No config at $CONFIG"; exit 1; }
tmp=$(mktemp)
jq '.tools.allow = ((.tools.allow // [] | if type == "string" then [.] else . end) + ["world_state","world_action","chat_say","web_fetch","fetch_url","openclaw-moltworld"] | unique)' "$CONFIG" > "$tmp"
mv "$tmp" "$CONFIG"
echo "Patched tools.allow in $CONFIG"
