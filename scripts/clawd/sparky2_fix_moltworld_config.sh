#!/usr/bin/env bash
# On sparky2: set gateway.mode=local, set MoltWorld plugin token from ~/.moltworld.env, restart gateway.
# Usage: bash sparky2_fix_moltworld_config.sh (run on sparky2, or via: ssh sparky2 'bash -s' < sparky2_fix_moltworld_config.sh)
set -e
CONFIG="$HOME/.openclaw/openclaw.json"
ENV_FILE="$HOME/.moltworld.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found. Run get_moltworld_token_from_theebie.ps1 -WriteEnvAndPush first." >&2
  exit 1
fi
source "$ENV_FILE"
TOKEN="${WORLD_AGENT_TOKEN:-}"
if [[ -z "$TOKEN" ]]; then
  echo "ERROR: WORLD_AGENT_TOKEN not in $ENV_FILE" >&2
  exit 1
fi
if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: $CONFIG not found." >&2
  exit 1
fi
python3 - <<PY
import json, os
p = os.path.expanduser("$CONFIG")
with open(p, "r", encoding="utf-8") as f:
    data = json.load(f)
# Gateway: ensure mode=local and gateway.auth.token set so gateway can start
import secrets
gw = data.setdefault("gateway", {})
gw["mode"] = "local"
auth = gw.get("auth")
if not isinstance(auth, dict) or not auth.get("token"):
    gw["auth"] = {"mode": "token", "token": secrets.token_hex(16)}
# MoltWorld plugin token
data.setdefault("plugins", {}).setdefault("entries", {})
entry = data["plugins"]["entries"].setdefault("openclaw-moltworld", {"config": {}})
if isinstance(entry.get("config"), dict):
    entry["config"]["token"] = "$TOKEN"
    if not entry["config"].get("baseUrl"):
        entry["config"]["baseUrl"] = "https://www.theebie.de"
    if not entry["config"].get("agentId"):
        entry["config"]["agentId"] = "MalicorSparky2"
    if not entry["config"].get("agentName"):
        entry["config"]["agentName"] = "MalicorSparky2"
with open(p, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
print("CONFIG_UPDATED", p)
PY
# Restart gateway
source ~/.nvm/nvm.sh 2>/dev/null || true
source ~/.bashrc 2>/dev/null || true
openclaw gateway stop 2>/dev/null || true
sleep 2
nohup openclaw gateway >> ~/.openclaw/gateway.log 2>&1 &
sleep 3
curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 http://127.0.0.1:18789/ || echo "0"
echo " Done."
