#!/usr/bin/env bash
# Create or fix auth-profiles.json for the OpenClaw agent that serves /hooks/wake (e.g. main).
# Reads API key from: (1) file at $ANTHROPIC_KEY_FILE, or (2) env ANTHROPIC_API_KEY.
# Usage on sparky2: export ANTHROPIC_API_KEY=sk-ant-...; bash fix_openclaw_auth_on_sparky.sh
#   Or: ANTHROPIC_KEY_FILE=/tmp/key.txt bash fix_openclaw_auth_on_sparky.sh   (key in file; file deleted after)
set -e

AGENT_DIR="${AGENT_DIR:-$HOME/.openclaw/agents/main/agent}"
AUTH_FILE="$AGENT_DIR/auth-profiles.json"

if [[ -n "${ANTHROPIC_KEY_FILE:-}" && -f "$ANTHROPIC_KEY_FILE" ]]; then
  KEY=$(cat "$ANTHROPIC_KEY_FILE")
  rm -f "$ANTHROPIC_KEY_FILE"
elif [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  KEY="$ANTHROPIC_API_KEY"
else
  echo "ERROR: Set ANTHROPIC_API_KEY or ANTHROPIC_KEY_FILE (path to file containing the key)."
  exit 1
fi

KEY=$(echo "$KEY" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
if [[ -z "$KEY" ]]; then
  echo "ERROR: Key is empty."
  exit 1
fi

mkdir -p "$AGENT_DIR"
KEY_TMP=$(mktemp)
echo -n "$KEY" > "$KEY_TMP"
trap 'rm -f "$KEY_TMP"' EXIT
python3 - "$KEY_TMP" "$AUTH_FILE" << 'PY'
import json, os, sys
key_path, auth_path = sys.argv[1], sys.argv[2]
with open(key_path) as f:
    key = f.read().strip().replace("\r", "").replace("\n", "")
with open(auth_path, "w") as f:
    json.dump({"anthropic": {"apiKey": key}}, f, indent=2)
os.chmod(auth_path, 0o600)
print("Created", auth_path, "with anthropic apiKey.")
PY
rm -f "$KEY_TMP"
trap - EXIT

# Restart gateway so it picks up auth
if command -v openclaw >/dev/null 2>&1; then
  openclaw gateway stop 2>/dev/null || true
  sleep 2
  openclaw gateway start &
  echo "Gateway restart triggered."
else
  echo "openclaw not in PATH; restart the gateway manually."
fi
exit 0
