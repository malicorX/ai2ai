#!/usr/bin/env bash
# Install MoltWorld plugin on a sparky using EXISTING identity from ~/.moltworld.env.
# Run on sparky: bash install_moltworld_plugin_on_sparky.sh
# Requires: ~/.moltworld.env with AGENT_ID, DISPLAY_NAME (or AGENT_NAME), WORLD_AGENT_TOKEN.
# Config: uses ~/.clawdbot/clawdbot.json or ~/.openclaw/openclaw.json (first found).
# See docs/OPENCLAW_MOLTWORLD_CHAT_PLAN.md and docs/MOLTWORLD_MANUAL_SETUP_SPARKIES.md.
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

CONFIG=""
for p in "$HOME/.clawdbot/clawdbot.json" "$HOME/.openclaw/openclaw.json"; do
  if [[ -f "$p" ]]; then CONFIG="$p"; break; fi
done
if [[ -z "$CONFIG" ]]; then
  echo "ERROR: No config found at ~/.clawdbot/clawdbot.json or ~/.openclaw/openclaw.json. Run OpenClaw/Clawd once first." >&2
  exit 1
fi

echo "Using config: $CONFIG"
echo "Agent: $AGENT_NAME ($AGENT_ID)"

# Ensure PATH has Node/npm and clawdbot/openclaw (non-interactive SSH often misses nvm)
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

CLAW=""
for cmd in clawdbot openclaw moltbot; do
  if command -v "$cmd" &>/dev/null; then CLAW="$cmd"; break; fi
done
if [[ -z "$CLAW" ]]; then
  echo "ERROR: clawdbot/openclaw/moltbot not in PATH (try: source ~/.bashrc; bash $0)" >&2
  exit 1
fi

# Remove plugin entry from BOTH config files so "plugins install" does not fail (sparky2 uses .openclaw/openclaw.json)
for cfg in "$HOME/.clawdbot/clawdbot.json" "$HOME/.openclaw/openclaw.json"; do
  if [[ -f "$cfg" ]]; then
    python3 - <<PY
import json, os, sys
p = os.path.expanduser("$cfg")
with open(p, "r", encoding="utf-8") as f:
    data = json.load(f)
data.setdefault("plugins", {}).setdefault("entries", {})
data["plugins"]["entries"].pop("openclaw-moltworld", None)
with open(p, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
print("CONFIG_CLEANED", p)
PY
  fi
done

# Remove existing plugin dirs so install succeeds (avoids "plugin already exists" on sparky2)
rm -rf "${HOME}/.clawdbot/extensions/openclaw-moltworld" "${HOME}/.openclaw/extensions/openclaw-moltworld" 2>/dev/null || true

echo "Installing plugin with: $CLAW plugins install @moltworld/openclaw-moltworld"
"$CLAW" plugins install @moltworld/openclaw-moltworld

# Clawd expects clawdbot.plugin.json; if missing (e.g. old npm package), copy from openclaw.plugin.json
for ext_dir in "$HOME/.clawdbot/extensions/openclaw-moltworld" "$HOME/.openclaw/extensions/openclaw-moltworld"; do
  if [[ -d "$ext_dir" && -f "$ext_dir/openclaw.plugin.json" && ! -f "$ext_dir/clawdbot.plugin.json" ]]; then
    cp -a "$ext_dir/openclaw.plugin.json" "$ext_dir/clawdbot.plugin.json"
    echo "Added clawdbot.plugin.json (from openclaw.plugin.json) in $ext_dir"
  fi
done

"$CLAW" plugins enable openclaw-moltworld 2>/dev/null || true

# Add plugin config to BOTH config files (so Clawd and OpenClaw both have it)
for cfg in "$HOME/.clawdbot/clawdbot.json" "$HOME/.openclaw/openclaw.json"; do
  if [[ -f "$cfg" ]]; then
    python3 - <<PY
import json, os
p = os.path.expanduser("$cfg")
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
    for name in ("world_state", "world_action", "chat_say", "web_fetch", "fetch_url", "openclaw-moltworld"):
        if name not in allow:
            allow.append(name)
    data["tools"]["allow"] = allow
with open(p, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
print("CONFIG_UPDATED", p)
PY
  fi
done

echo "Restarting gateway..."
"$CLAW" gateway stop 2>/dev/null || true
sleep 2
LOG_DIR="$(dirname "$CONFIG")"
nohup "$CLAW" gateway >> "${LOG_DIR}/gateway.log" 2>&1 &

echo "Done. Plugin installed and gateway restarted. Test in TUI/Control UI: use world_state, then chat_say."
