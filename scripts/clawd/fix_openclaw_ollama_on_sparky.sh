#!/usr/bin/env bash
# Ensure OpenClaw on this host uses Ollama locally (no cloud API key). Fixes "No API key for provider anthropic"
# when the wake/session should use Ollama. Adds models.providers.ollama to root config and agent auth.
# Usage: bash fix_openclaw_ollama_on_sparky.sh   (run on sparky2, or: ssh sparky2 'bash -s' < fix_openclaw_ollama_on_sparky.sh)
set -e

CONFIG="${HOME}/.openclaw/openclaw.json"
AGENT_DIR="${HOME}/.openclaw/agents/main/agent"
AUTH_FILE="${AGENT_DIR}/auth-profiles.json"
MODELS_JSON="${AGENT_DIR}/models.json"
OLLAMA_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434/v1}"
PRIMARY_MODEL="${PRIMARY_MODEL:-ollama/llama3.3:latest}"

if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: $CONFIG not found. OpenClaw not configured?" >&2
  exit 1
fi

mkdir -p "$AGENT_DIR"

# 1) Ensure root openclaw.json has models.providers.ollama (so wake/session can resolve ollama/*)
python3 - "$CONFIG" "$OLLAMA_URL" "$PRIMARY_MODEL" << 'PY'
import json, sys, os
cfg_path, base_url, primary = sys.argv[1], sys.argv[2], sys.argv[3]
with open(cfg_path) as f:
    d = json.load(f)
prov = d.setdefault("models", {}).setdefault("providers", {}).setdefault("ollama", {})
prov["baseUrl"] = base_url
prov["apiKey"] = prov.get("apiKey", "ollama-local")
prov["api"] = prov.get("api", "openai-completions")
if "models" not in prov or not prov["models"]:
    prov["models"] = [
        {"id": "llama3.3:latest", "name": "Llama 3.3", "reasoning": False, "input": ["text"], "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}, "contextWindow": 131072, "maxTokens": 8192},
        {"id": "qwen2.5-coder:32b", "name": "Qwen 2.5 Coder 32B", "reasoning": False, "input": ["text"], "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}, "contextWindow": 32768, "maxTokens": 8192},
    ]
defs = d.setdefault("agents", {}).setdefault("defaults", {})
defs.setdefault("model", {})["primary"] = primary
# Gateway: allow start without cloud (mode=local) and ensure auth token for hooks
gw = d.setdefault("gateway", {})
gw["mode"] = "local"
auth = gw.get("auth") or {}
if not auth.get("token"):
    import secrets
    gw["auth"] = {"mode": "token", "token": secrets.token_hex(16)}
# Hooks: enable so POST /hooks/wake is accepted (pull-and-wake uses hooks.token)
hooks = d.setdefault("hooks", {})
hooks["enabled"] = True
if not hooks.get("token"):
    import secrets as s
    hooks["token"] = s.token_hex(16)
# OpenResponses API: so pull-and-wake can run the main agent (with MoltWorld plugin) via POST /v1/responses
gw_http = gw.setdefault("http", {}).setdefault("endpoints", {}).setdefault("responses", {})
gw_http["enabled"] = True
with open(cfg_path, "w") as f:
    json.dump(d, f, indent=2)
print("CONFIG_UPDATED", cfg_path, "primary=", primary, "ollama baseUrl=", base_url)
PY

# 2) Fix agent dir models.json: ensure Ollama baseUrl is 11434 (standard), not 11435
if [[ -f "$MODELS_JSON" ]]; then
  python3 - "$MODELS_JSON" "$OLLAMA_URL" << 'PY'
import json, os, sys
path, base_url = sys.argv[1], sys.argv[2]
with open(path) as f:
    d = json.load(f)
ollama = d.get("providers", {}).get("ollama", {})
if ollama.get("baseUrl") and "11435" in ollama["baseUrl"]:
    ollama["baseUrl"] = base_url
    with open(path, "w") as f:
        json.dump(d, f, indent=2)
    print("AGENT_MODELS_FIXED", path, "baseUrl ->", base_url)
PY
fi

# 2b) MoltWorld plugin: inject token from ~/.moltworld.env so chat_say can post to theebie
ENV_FILE="${HOME}/.moltworld.env"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  PLUGIN_TOKEN="${WORLD_AGENT_TOKEN:-}"
  PLUGIN_BASE="${WORLD_API_BASE:-https://www.theebie.de}"
  PLUGIN_AGENT_ID="${AGENT_ID:-MalicorSparky2}"
  PLUGIN_AGENT_NAME="${DISPLAY_NAME:-${AGENT_NAME:-$PLUGIN_AGENT_ID}}"
  if [[ -n "$PLUGIN_TOKEN" ]]; then
    python3 - "$CONFIG" "$PLUGIN_TOKEN" "$PLUGIN_BASE" "$PLUGIN_AGENT_ID" "$PLUGIN_AGENT_NAME" << 'PYPLUGIN'
import json, sys
cfg_path, token, base_url, agent_id, agent_name = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
with open(cfg_path) as f:
    d = json.load(f)
entry = d.setdefault("plugins", {}).setdefault("entries", {}).setdefault("openclaw-moltworld", {"config": {}})
if not isinstance(entry.get("config"), dict):
    entry["config"] = {}
entry["config"]["token"] = token
entry["config"]["baseUrl"] = base_url
entry["config"]["agentId"] = agent_id
entry["config"]["agentName"] = agent_name
with open(cfg_path, "w") as f:
    json.dump(d, f, indent=2)
print("PLUGIN_TOKEN_SET", "openclaw-moltworld", "token from .moltworld.env")
PYPLUGIN
  fi
fi

# 3) Create auth-profiles.json with ollama so provider lookup finds it (no cloud key)
python3 - "$AUTH_FILE" << 'PY'
import json, os, sys
path = sys.argv[1]
data = {"ollama": {"apiKey": "ollama-local"}}
with open(path, "w") as f:
    json.dump(data, f, indent=2)
os.chmod(path, 0o600)
print("AUTH_UPDATED", path, "ollama apiKey=ollama-local")
PY

# 4) Restart gateway so it loads the new config (stop, wait for exit, then start)
source ~/.nvm/nvm.sh 2>/dev/null || true
source ~/.bashrc 2>/dev/null || true
OPENCLAW_CMD=$(command -v openclaw 2>/dev/null || true)
if [[ -z "$OPENCLAW_CMD" && -d "$HOME/.nvm" ]]; then
  for n in "$HOME/.nvm/versions/node"/*/bin/openclaw; do
    [[ -x "$n" ]] && OPENCLAW_CMD="$n" && break
  done
fi
if [[ -z "$OPENCLAW_CMD" ]]; then
  echo "WARN: openclaw not found in PATH or nvm. Start gateway manually: openclaw gateway" >&2
else
  openclaw gateway stop 2>/dev/null || true
  for i in 1 2 3 4 5; do
    sleep 2
    if ! curl -s -o /dev/null --connect-timeout 1 http://127.0.0.1:18789/ 2>/dev/null; then
      break
    fi
  done
  if curl -s -o /dev/null --connect-timeout 1 http://127.0.0.1:18789/ 2>/dev/null; then
    pid=$(lsof -ti :18789 2>/dev/null | head -1)
    if [[ -n "$pid" ]]; then
      kill "$pid" 2>/dev/null || true
      sleep 3
    fi
  fi
  nohup "$OPENCLAW_CMD" gateway >> ~/.openclaw/gateway.log 2>&1 &
  sleep 5
  echo "Gateway started with $OPENCLAW_CMD"
fi
echo "Gateway restart triggered. Wait a few seconds then run the test."
exit 0
