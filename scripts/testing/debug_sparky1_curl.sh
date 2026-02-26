#!/usr/bin/env bash
set -e
# Mimic test suite: get tokens, try v1/responses, then hooks/agent, then hooks/wake
for c in ~/.openclaw/openclaw.json ~/.clawdbot/clawdbot.json; do
  [ -f "$c" ] || continue
  tok=$(python3 -c "
import json,sys
with open(sys.argv[1]) as f: d=json.load(f)
gw=d.get('gateway',{}); auth=gw.get('auth') or {}
print(auth.get('token') or gw.get('token') or '')
" "$c" 2>/dev/null)
  [ -n "$tok" ] && GW_TOKEN="$tok" && break
done
for c in ~/.openclaw/openclaw.json ~/.clawdbot/clawdbot.json; do
  [ -f "$c" ] || continue
  tok=$(python3 -c "
import json,sys,os
with open(os.path.expanduser(sys.argv[1])) as f: d=json.load(f)
h=d.get('hooks',{}); token=h.get('token') if h.get('enabled') else None
if not token: gw=d.get('gateway',{}); auth=gw.get('auth') or {}; token=gw.get('token') or auth.get('token')
print(token or '')
" "$c" 2>/dev/null)
  [ -n "$tok" ] && WAKE_TOKEN="$tok" && break
done
[ -z "$WAKE_TOKEN" ] && WAKE_TOKEN="$GW_TOKEN"
echo "GW_TOKEN length: ${#GW_TOKEN} WAKE_TOKEN length: ${#WAKE_TOKEN}"
code=$(curl -s -S -X POST http://127.0.0.1:18789/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $GW_TOKEN" \
  -H "x-openclaw-agent-id: main" \
  -d '{"model":"openclaw:main","input":"Say hi."}' \
  -o /tmp/ot_suite_response.json -w "%{http_code}")
echo "v1/responses: $code"
if [[ "$code" = "405" || "$code" = "404" ]]; then
  [ ! -f /tmp/ot_suite_payload.json ] && echo '{"model":"openclaw:main","input":"Say hi."}' > /tmp/ot_suite_payload.json
  python3 -c "
import json
d=json.load(open('/tmp/ot_suite_payload.json'))
inp=d.get('input','Say hi.')
json.dump({'message':inp,'wakeMode':'now','name':'Test','model':'ollama/qwen2.5-coder:32b','deliver':False,'timeoutSeconds':120}, open('/tmp/ot_suite_hooks.json','w'))
json.dump({'text':inp,'mode':'now'}, open('/tmp/ot_suite_wake.json','w'))
" || echo "Python failed"
  echo "hooks.json exists: $([ -f /tmp/ot_suite_hooks.json ] && echo yes || echo no)"
  if [[ -f /tmp/ot_suite_hooks.json ]]; then
    code=$(curl -s -S -X POST http://127.0.0.1:18789/hooks/agent \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $WAKE_TOKEN" \
      --data-binary @/tmp/ot_suite_hooks.json \
      -o /tmp/ot_suite_response.json -w "%{http_code}")
    echo "hooks/agent: $code"
  fi
  if [[ "$code" = "405" || "$code" = "404" ]] && [[ -f /tmp/ot_suite_wake.json ]]; then
    code=$(curl -s -S -X POST http://127.0.0.1:18789/hooks/wake \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $WAKE_TOKEN" \
      --data-binary @/tmp/ot_suite_wake.json \
      -o /tmp/ot_suite_response.json -w "%{http_code}")
    echo "hooks/wake: $code"
  fi
fi
echo "final: $code"
