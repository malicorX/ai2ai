#!/usr/bin/env bash
# Install MoltWorld plugin on a sparky using EXISTING identity from ~/.moltworld.env.
# Run on sparky: bash install_moltworld_plugin_on_sparky.sh
# Requires: ~/.moltworld.env with AGENT_ID, DISPLAY_NAME (or AGENT_NAME), WORLD_AGENT_TOKEN.
# Config: ~/.openclaw/openclaw.json only (OpenClaw).
set -e

ENV_FILE="${HOME}/.moltworld.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found. Create it with AGENT_ID, DISPLAY_NAME (or AGENT_NAME), WORLD_AGENT_TOKEN." >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$ENV_FILE"

AGENT_ID="${AGENT_ID:-}"
AGENT_NAME="${DISPLAY_NAME:-${AGENT_NAME:-}}"
TOKEN="${WORLD_AGENT_TOKEN:-}"
BASE_URL="${WORLD_API_BASE:-https://www.theebie.de}"

if [[ -z "$AGENT_ID" || -z "$TOKEN" ]]; then
  echo "ERROR: AGENT_ID and WORLD_AGENT_TOKEN must be set in $ENV_FILE" >&2
  exit 1
fi
if [[ -z "$AGENT_NAME" ]]; then
  AGENT_NAME="$AGENT_ID"
fi

CONFIG="$HOME/.openclaw/openclaw.json"
if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: No config at ~/.openclaw/openclaw.json. Run bootstrap_openclaw_on_sparky1.sh or openclaw once first." >&2
  exit 1
fi

echo "Using config: $CONFIG"
echo "Agent: $AGENT_NAME ($AGENT_ID)"

# Ensure PATH has Node/npm and openclaw (non-interactive SSH often misses nvm)
for f in "$HOME/.bashrc" "$HOME/.profile" "$HOME/.bash_profile" "$HOME/.nvm/nvm.sh"; do
  [[ -f "$f" ]] && source "$f" 2>/dev/null || true
done
if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
  source "$HOME/.nvm/nvm.sh" 2>/dev/null
  command -v nvm &>/dev/null && nvm use default 2>/dev/null || nvm use 22 2>/dev/null || true
fi
NODE_BIN="$(ls -d "${HOME}"/.nvm/versions/node/*/bin 2>/dev/null | sort -V | tail -n1)"
[[ -n "$NODE_BIN" ]] && export PATH="$NODE_BIN:$PATH"
[[ -d "$HOME/.local/bin" ]] && export PATH="$HOME/.local/bin:$PATH"
[[ -d /usr/local/bin ]] && export PATH="/usr/local/bin:$PATH"

if ! command -v openclaw &>/dev/null; then
  echo "ERROR: openclaw not in PATH (try: source ~/.bashrc; bash $0)" >&2
  exit 1
fi

# Remove plugin entry from config so "plugins install" does not fail
python3 - <<PY
import json, os
p = os.path.expanduser("$CONFIG")
with open(p, "r", encoding="utf-8") as f:
    data = json.load(f)
data.setdefault("plugins", {}).setdefault("entries", {})
data["plugins"]["entries"].pop("openclaw-moltworld", None)
with open(p, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
print("CONFIG_CLEANED", p)
PY

# Remove existing plugin dir so install succeeds
rm -rf "${HOME}/.openclaw/extensions/openclaw-moltworld" 2>/dev/null || true

echo "Installing plugin with: openclaw plugins install @moltworld/openclaw-moltworld"
openclaw plugins install @moltworld/openclaw-moltworld

# If package only has openclaw.plugin.json, copy to clawdbot.plugin.json for compat
if [[ -d "$HOME/.openclaw/extensions/openclaw-moltworld" && -f "$HOME/.openclaw/extensions/openclaw-moltworld/openclaw.plugin.json" && ! -f "$HOME/.openclaw/extensions/openclaw-moltworld/clawdbot.plugin.json" ]]; then
  cp -a "$HOME/.openclaw/extensions/openclaw-moltworld/openclaw.plugin.json" "$HOME/.openclaw/extensions/openclaw-moltworld/clawdbot.plugin.json"
  echo "Added clawdbot.plugin.json (from openclaw.plugin.json) for compat"
fi

openclaw plugins enable openclaw-moltworld 2>/dev/null || true

# Add plugin config to ~/.openclaw/openclaw.json
if [[ -f "$CONFIG" ]]; then
    python3 - <<PY
import json, os
p = os.path.expanduser("$CONFIG")
with open(p, "r", encoding="utf-8") as f:
    data = json.load(f)
data.setdefault("plugins", {}).setdefault("entries", {})
entry = data["plugins"]["entries"].setdefault("openclaw-moltworld", {})
entry["enabled"] = True
ecfg = entry.setdefault("config", {})
ecfg["baseUrl"] = "$BASE_URL"
ecfg["agentId"] = "$AGENT_ID"
ecfg["agentName"] = "$AGENT_NAME"
ecfg["token"] = "$TOKEN"
# Ensure MoltWorld plugin tools are explicitly allowed (append to existing allow if any)
data.setdefault("tools", {})
allow = data["tools"].get("allow")
if allow is not None:
    if isinstance(allow, str):
        allow = [allow]
    allow = list(allow)
    for name in ("world_state", "world_action", "go_to", "chat_say", "web_fetch", "fetch_url", "openclaw-moltworld"):
        if name not in allow:
            allow.append(name)
    data["tools"]["allow"] = allow
with open(p, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
print("CONFIG_UPDATED", p)
PY

echo "Restarting OpenClaw gateway..."
openclaw gateway stop 2>/dev/null || true
sleep 2
nohup openclaw gateway >> "${HOME}/.openclaw/gateway.log" 2>&1 &

echo "Done. Plugin installed and gateway restarted. Test in TUI/Control UI: use world_state, then chat_say."
