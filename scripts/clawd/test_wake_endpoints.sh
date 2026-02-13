#!/usr/bin/env bash
# Test which wake endpoint returns 200 on this host. Usage: bash test_wake_endpoints.sh
set -e
CONFIG="${HOME}/.openclaw/openclaw.json"
[[ -f "$CONFIG" ]] || CONFIG="${HOME}/.openclaw/openclaw.json"
TOK=$(python3 -c "
import json
with open('$CONFIG') as f:
    d = json.load(f)
print(d.get('gateway',{}).get('auth',{}).get('token') or d.get('gateway',{}).get('token') or d.get('hooks',{}).get('token') or '')
")
echo "v1/responses:"
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:18789/v1/responses \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOK" -H "x-openclaw-agent-id: main" \
  -d '{"model":"openclaw:main","input":"Say hello."}'
echo "hooks/agent:"
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:18789/hooks/agent \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOK" \
  -d '{"message":"Say hello.","wakeMode":"now","name":"MoltWorld","model":"ollama/qwen2.5-coder:32b","deliver":false,"timeoutSeconds":120}'
echo "hooks/wake:"
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:18789/hooks/wake \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOK" \
  -d '{"text":"Say hello.","mode":"now"}'
