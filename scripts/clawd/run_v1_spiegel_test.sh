#!/usr/bin/env bash
# POST /v1/responses with fixed "what's on www.spiegel.de" payload. Run on sparky2.
set -e
CONFIG="${HOME}/.openclaw/openclaw.json"
[[ -f "$CONFIG" ]] || { echo "No $CONFIG"; exit 1; }
GW_TOKEN=$(python3 -c "
import json,sys,os
p=os.path.expanduser('$CONFIG')
with open(p) as f: d=json.load(f)
gw=d.get('gateway',{}); auth=gw.get('auth') or {}
print(auth.get('token') or gw.get('token') or '')
" 2>/dev/null)
# curl returns only the status code (from -w)
[[ -n "$GW_TOKEN" ]] || { echo "NO_GW_TOKEN"; exit 1; }
curl -s -S -X POST http://127.0.0.1:18789/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $GW_TOKEN" \
  -H "x-openclaw-agent-id: main" \
  --data-binary @/tmp/v1_spiegel_payload.json \
  -o /tmp/v1_response.json -w "%{http_code}"
