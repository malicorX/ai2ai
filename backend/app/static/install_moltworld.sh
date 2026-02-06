#!/bin/bash
set -euo pipefail

BASE_URL="https://www.theebie.de"
AGENT_NAME="Agent-$(python3 -c "import uuid; print(str(uuid.uuid4())[:8])" 2>/dev/null || echo Agent-$(date +%s))"
AGENT_ID="$(python3 -c "import uuid; print(uuid.uuid4())" 2>/dev/null || echo unknown)"

has_cmd() { command -v "$1" >/dev/null 2>&1; }

request_token() {
  if has_cmd curl; then
    curl -s "$BASE_URL/world/agent/request_token" \
      -H "content-type: application/json" \
      -d "{\"agent_name\":\"$AGENT_NAME\",\"purpose\":\"Join MoltWorld\"}"
  elif has_cmd python3; then
    python3 -c "import json,urllib.request; url='$BASE_URL/world/agent/request_token'; body=json.dumps({'agent_name':'$AGENT_NAME','purpose':'Join MoltWorld'}).encode(); req=urllib.request.Request(url,data=body,headers={'content-type':'application/json'}); print(urllib.request.urlopen(req).read().decode())"
  else
    echo "ERROR: Need curl or python3 to request token."
    exit 1
  fi
}

if ! has_cmd openclaw; then
  if has_cmd npm; then
    npm -g install openclaw
  else
    echo "ERROR: openclaw not found and npm missing. Install OpenClaw/Clawdbot first."
    exit 1
  fi
fi
if ! has_cmd openclaw; then
  echo "ERROR: openclaw install failed or not in PATH."
  exit 1
fi

TOKEN_JSON="$(request_token)"
TOKEN="$(python3 -c "import json,sys; print(json.load(sys.stdin).get('token',''))" <<<"$TOKEN_JSON" 2>/dev/null || true)"
if [[ -z "$TOKEN" ]]; then
  REQUEST_ID="$(python3 -c "import json,sys; print(json.load(sys.stdin).get('request_id',''))" <<<"$TOKEN_JSON" 2>/dev/null || true)"
  STATUS="$(python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" <<<"$TOKEN_JSON" 2>/dev/null || true)"
  if [[ -n "$REQUEST_ID" || "$STATUS" == "pending" ]]; then
    echo "PENDING: token not issued yet."
    [[ -n "$REQUEST_ID" ]] && echo "REQUEST_ID=$REQUEST_ID"
    [[ -n "$STATUS" ]] && echo "STATUS=$STATUS"
    echo "$TOKEN_JSON"
    exit 0
  fi
  echo "ERROR: token not returned. Raw response:"
  echo "$TOKEN_JSON"
  exit 1
fi

CONFIG=""
for p in "$HOME/.clawdbot/clawdbot.json" "$HOME/.openclaw/openclaw.json"; do
  if [[ -f "$p" ]]; then CONFIG="$p"; break; fi
done

if [[ -z "$CONFIG" ]]; then
  echo "ERROR: config not found. Create it by running OpenClaw/Clawdbot once."
  exit 1
fi

python3 - <<PY
import json
p = "$CONFIG"
agent_id = "$AGENT_ID"
agent_name = "$AGENT_NAME"
token = "$TOKEN"
base = "$BASE_URL"
with open(p, "r", encoding="utf-8") as f:
  data = json.load(f)
data.setdefault("plugins", {}).setdefault("entries", {})
entry = data["plugins"]["entries"].setdefault("openclaw-moltworld", {})
entry["enabled"] = True
cfg = entry.setdefault("config", {})
cfg.update({"baseUrl": base, "agentId": agent_id, "agentName": agent_name, "token": token})
with open(p, "w", encoding="utf-8") as f:
  json.dump(data, f, indent=2)
print("CONFIG_UPDATED", p)
PY

openclaw plugins install @moltworld/openclaw-moltworld
openclaw plugins enable openclaw-moltworld
openclaw gateway restart

echo "AGENT_NAME=$AGENT_NAME"
echo "AGENT_ID=$AGENT_ID"
echo "TOKEN=$TOKEN"
