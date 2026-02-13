#!/usr/bin/env bash
# Test POST /chat/say from sparky2 using token from OpenClaw plugin config.
set -e
CONFIG="$HOME/.openclaw/openclaw.json"
TOKEN=$(python3 -c "
import json, os
path = os.path.expanduser('$CONFIG')
with open(path) as f:
    c = json.load(f)
cfg = c.get('plugins',{}).get('entries',{}).get('openclaw-moltworld',{}).get('config',{})
print(cfg.get('token',''))
")
if [[ -z "$TOKEN" ]]; then echo "No token in config"; exit 1; fi
echo "POST /chat/say (token ${#TOKEN} chars)"
curl -s -w "\nHTTP_CODE:%{http_code}\n" -X POST "https://www.theebie.de/chat/say" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"sender_id":"MalicorSparky2","sender_name":"MalicorSparky2","text":"Test from sparky2 script"}'
