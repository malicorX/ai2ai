#!/usr/bin/env bash
# Run on sparky to print Clawd summary (model, gateway, tools, ollama ids). Used by clawd_status.ps1.
set -e
CFG="${HOME}/.clawdbot/clawdbot.json"
MODEL="not set"
TOOLS=""
OLLAMA_IDS=""
if [[ -f "$CFG" ]]; then
  read MODEL TOOLS OLLAMA_IDS <<< $(python3 -c "
import json, os
try:
    with open(os.path.expanduser('$CFG')) as f:
        d = json.load(f)
    primary = d.get('agents', {}).get('defaults', {}).get('model', {}).get('primary', 'not set')
    tools = d.get('tools', {})
    tools_str = 'deny=' + str(tools.get('deny', [])) if tools else 'not set'
    ollama = d.get('models', {}).get('providers', {}).get('ollama', {})
    ids = [m.get('id', '') for m in ollama.get('models', []) if m.get('id')]
    ollama_str = ','.join(ids) if ids else 'none'
    print(primary, tools_str, ollama_str)
except Exception as e:
    print('not set', 'error', str(e)[:40])
" 2>/dev/null) || true
fi
GW=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18789/ 2>/dev/null) || true
[[ -z "$GW" || "$GW" = "000" ]] && GW="unreachable"
echo "---"
echo "Default model: $MODEL"
echo "Tools:         $TOOLS"
echo "Ollama model ids: $OLLAMA_IDS"
echo "Gateway:       $GW (200 = running)"
echo "---"
