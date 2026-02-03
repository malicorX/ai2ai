#!/usr/bin/env bash
# Run on sparky: merge tools.deny (sessions_send, message) into ~/.clawdbot/clawdbot.json, fix ~/bin/start_clawd_gateway.sh CRLF, restart gateway.
# Used by run_clawd_apply_config.ps1. Usage: bash clawd_apply_config_remote.sh
set -e
CFG="${HOME}/.clawdbot/clawdbot.json"
mkdir -p "$(dirname "$CFG")"
[[ -f "$CFG" ]] || { echo '{}' > "$CFG"; }

python3 -c "
import json, os
p = os.path.expanduser('~/.clawdbot/clawdbot.json')
with open(p) as f:
    d = json.load(f)
if 'tools' not in d:
    d['tools'] = {}
if 'deny' not in d['tools']:
    d['tools']['deny'] = []
for x in ['sessions_send', 'message']:
    if x not in d['tools']['deny']:
        d['tools']['deny'].append(x)
# Force full tool set so browser is never omitted (avoids "function definitions not suitable").
# Restrictive profile or allow-list can make the model say definitions don't fit the task.
d['tools']['profile'] = 'full'
d['tools'].pop('allow', None)  # no allow-list: full set except deny
if 'exec' not in d['tools']:
    d['tools']['exec'] = {}
d['tools']['exec']['host'] = 'gateway'
d['tools']['exec']['ask'] = 'off'
d['tools']['exec']['security'] = 'full'
# Browser: enable headless for Fiverr etc. (use Chrome .deb on Ubuntu, not snap Chromium)
if 'browser' not in d:
    d['browser'] = {}
d['browser']['enabled'] = True
d['browser']['headless'] = True
d['browser']['noSandbox'] = True
if os.path.isfile('/usr/bin/google-chrome-stable'):
    d['browser']['executablePath'] = '/usr/bin/google-chrome-stable'
elif os.path.isfile('/usr/bin/google-chrome'):
    d['browser']['executablePath'] = '/usr/bin/google-chrome'
elif os.path.isfile('/usr/bin/chromium-browser'):
    d['browser']['executablePath'] = '/usr/bin/chromium-browser'
# Remove compat.openaiCompletionsTools if present (stock Clawd rejects it; add back when gateway has PR #4287)
d.setdefault('models', {}).setdefault('providers', {}).setdefault('ollama', {}).setdefault('models', [])
ollama_models = d['models']['providers']['ollama']['models']
if not ollama_models:
    ollama_models.append({
        'id': 'qwen2.5-coder:32b', 'name': 'Qwen 2.5 Coder 32B', 'reasoning': False, 'input': ['text'],
        'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0},
        'contextWindow': 32768, 'maxTokens': 8192
    })
    print('Added qwen2.5-coder:32b to Ollama models')
for m in ollama_models:
    if isinstance(m, dict) and isinstance(m.get('compat'), dict):
        m['compat'].pop('openaiCompletionsTools', None)
        if not m['compat']:
            m.pop('compat', None)
with open(p, 'w') as f:
    json.dump(d, f, indent=2)
print('tools.deny + browser (compat.openaiCompletionsTools removed for stock Clawd)')
" || { echo "Config write failed"; exit 1; }

# Fix CRLF on gateway start script if present (avoids nohup "clawdbot$'\r'" error)
if [[ -f ~/bin/start_clawd_gateway.sh ]]; then
    sed -i 's/\r$//' ~/bin/start_clawd_gateway.sh && echo "Fixed CRLF in ~/bin/start_clawd_gateway.sh"
fi

# Restart gateway with OLLAMA_API_KEY (gateway may be managed by systemd; stop then start)
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[[ -s "$NVM_DIR/nvm.sh" ]] && . "$NVM_DIR/nvm.sh"
export OLLAMA_API_KEY="${OLLAMA_API_KEY:-ollama-local}"
CLAWDBOT=$(command -v clawdbot 2>/dev/null || command -v moltbot 2>/dev/null || true)
if [[ -z "$CLAWDBOT" ]]; then
    echo "clawdbot/moltbot not in PATH; config updated, restart gateway manually"
    exit 0
fi
"$CLAWDBOT" gateway stop 2>/dev/null || true
sleep 2
# If port still in use, suggest manual stop (e.g. systemd)
if command -v lsof &>/dev/null && lsof -i :18789 &>/dev/null; then
    echo "Port 18789 still in use. On sparky2 run: clawdbot gateway stop; sleep 2; nohup clawdbot gateway >> ~/.clawdbot/gateway.log 2>&1 &"
else
    nohup "$CLAWDBOT" gateway >> ~/.clawdbot/gateway.log 2>&1 &
    echo "Gateway restarted"
fi
