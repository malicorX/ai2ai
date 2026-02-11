#!/usr/bin/env bash
# Remove tools.allow so the gateway sends the same full tool set to all requests (Chat and wake).
# Use on sparky2 (OpenClaw) so MoltWorld wake gets web_fetch, browser, etc. like the Dashboard Chat.
# Usage: CONFIG=~/.openclaw/openclaw.json bash patch_tools_same_as_chat.sh
set -e
CONFIG="${CONFIG:-$HOME/.openclaw/openclaw.json}"
[[ -f "$CONFIG" ]] || CONFIG="$HOME/.clawdbot/clawdbot.json"
[[ -f "$CONFIG" ]] || { echo "No config at $CONFIG"; exit 1; }
tmp=$(mktemp)
jq 'del(.tools.allow)' "$CONFIG" > "$tmp"
mv "$tmp" "$CONFIG"
echo "Removed tools.allow in $CONFIG (wake will get same tools as Chat)"
