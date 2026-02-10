#!/usr/bin/env bash
# Run one wake request on this host (e.g. sparky1). Reads token from gateway config, POSTs payload to /hooks/wake.
# Usage: CLAW=clawdbot PAYLOAD_FILE=/tmp/moltworld_wake_payload.json bash run_moltworld_wake_once.sh
# Output: HTTP status code (e.g. 200) or NO_TOKEN.
set -e
CLAW="${CLAW:-clawdbot}"
CONFIG="$HOME/.clawdbot/clawdbot.json"
[[ "$CLAW" = "openclaw" ]] && CONFIG="$HOME/.openclaw/openclaw.json"
PAYLOAD_FILE="${PAYLOAD_FILE:-/tmp/moltworld_wake_payload.json}"
if [[ ! -f "$CONFIG" ]]; then
  echo "NO_TOKEN"
  exit 1
fi
if [[ ! -f "$PAYLOAD_FILE" ]]; then
  echo "NO_PAYLOAD"
  exit 1
fi
TOKEN=$(python3 -c "
import json, sys
with open('$CONFIG') as f:
    d = json.load(f)
h = d.get('hooks') or {}
g = d.get('gateway') or {}
t = h.get('token') or (g.get('auth') or {}).get('token') or g.get('token')
print(t or '')
")
if [[ -z "$TOKEN" ]]; then
  echo "NO_TOKEN"
  exit 1
fi
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:18789/hooks/wake \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d @"$PAYLOAD_FILE")
echo "$code"
