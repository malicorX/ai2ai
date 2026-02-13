#!/usr/bin/env bash
# On sparky1: ensure ~/.openclaw exists, set gateway.mode=local, set MoltWorld plugin for Sparky1Agent from ~/.moltworld.env, restart gateway.
# Usage: bash sparky1_fix_moltworld_config.sh (run on sparky1, or: ssh sparky1 'bash -s' < sparky1_fix_moltworld_config.sh)
# After this, run openclaw gateway on sparky1 (see sparky1_kill_orphan_and_start_gateway.sh).
set -e
CONFIG="$HOME/.openclaw/openclaw.json"
ENV_FILE="$HOME/.moltworld.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found. Create it with AGENT_ID=Sparky1Agent, DISPLAY_NAME=Sparky1Agent, WORLD_AGENT_TOKEN=..." >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$ENV_FILE"
TOKEN="${WORLD_AGENT_TOKEN:-}"
AGENT_ID="${AGENT_ID:-Sparky1Agent}"
AGENT_NAME="${DISPLAY_NAME:-${AGENT_NAME:-$AGENT_ID}}"
BASE_URL="${WORLD_API_BASE:-https://www.theebie.de}"
if [[ -z "$TOKEN" ]]; then
  echo "ERROR: WORLD_AGENT_TOKEN not in $ENV_FILE" >&2
  exit 1
fi
mkdir -p "$HOME/.openclaw"
if [[ ! -f "$CONFIG" ]]; then
  echo "Creating minimal $CONFIG..."
  python3 - <<PY
import json, secrets
data = {
  "gateway": {"mode": "local", "auth": {"mode": "token", "token": secrets.token_hex(16)}},
  "plugins": {"entries": {}},
  "tools": {"allow": ["world_state", "world_action", "go_to", "chat_say", "web_fetch", "fetch_url", "openclaw-moltworld"]}
}
with open("$CONFIG", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
print("CONFIG_CREATED", "$CONFIG")
PY
fi
python3 - <<PY
import json, os
p = os.path.expanduser("$CONFIG")
with open(p, "r", encoding="utf-8") as f:
    data = json.load(f)
gw = data.setdefault("gateway", {})
gw["mode"] = "local"
auth = gw.get("auth")
if not isinstance(auth, dict) or not auth.get("token"):
    import secrets
    gw["auth"] = {"mode": "token", "token": secrets.token_hex(16)}
data.setdefault("plugins", {}).setdefault("entries", {})
entry = data["plugins"]["entries"].setdefault("openclaw-moltworld", {"config": {}})
if isinstance(entry.get("config"), dict):
    entry["config"]["token"] = "$TOKEN"
    if not entry["config"].get("baseUrl"):
        entry["config"]["baseUrl"] = "$BASE_URL"
    if not entry["config"].get("agentId"):
        entry["config"]["agentId"] = "$AGENT_ID"
    if not entry["config"].get("agentName"):
        entry["config"]["agentName"] = "$AGENT_NAME"
data.setdefault("tools", {})
allow = data["tools"].get("allow")
if allow is None:
    data["tools"]["allow"] = ["world_state", "world_action", "go_to", "chat_say", "web_fetch", "fetch_url", "openclaw-moltworld"]
with open(p, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
print("CONFIG_UPDATED", p)
PY
# Restart gateway (openclaw)
for f in "$HOME/.nvm/nvm.sh" "$HOME/.bashrc"; do [[ -f "$f" ]] && source "$f" 2>/dev/null || true; done
openclaw gateway stop 2>/dev/null || true
sleep 2
nohup openclaw gateway >> ~/.openclaw/gateway.log 2>&1 &
sleep 3
curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 http://127.0.0.1:18789/ || echo "0"
echo " Done."
