#!/usr/bin/env bash
# Remove MoltWorld plugin entirely: delete from config and hide extension dir so the gateway cannot load it.
# Reversible: to restore, run install_moltworld_plugin_on_sparky.sh (or rename .disabled back and run set_moltworld_plugin_on_sparky.sh enable).
# Usage: bash remove_moltworld_plugin_on_sparky.sh
set -e

MOLTWORLD_TOOLS="world_state world_action go_to chat_say web_fetch fetch_url openclaw-moltworld"

# 1) Remove plugin entry from configs and strip MoltWorld tools from tools.allow
for CONFIG in "$HOME/.openclaw/openclaw.json" "$HOME/.clawdbot/clawdbot.json"; do
  [[ -f "$CONFIG" ]] || continue
  python3 - "$CONFIG" "$MOLTWORLD_TOOLS" << 'PY'
import json, sys, os
config_path = os.path.expanduser(sys.argv[1])
tool_names = set(sys.argv[2].split())

with open(config_path, "r", encoding="utf-8") as f:
    data = json.load(f)

data.setdefault("plugins", {}).setdefault("entries", {})
data["plugins"]["entries"].pop("openclaw-moltworld", None)

allow = data.get("tools", {}).get("allow")
if allow is not None:
    if isinstance(allow, str):
        allow = [allow]
    allow = [x for x in allow if x not in tool_names]
    data.setdefault("tools", {})["allow"] = allow if allow else None

with open(config_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
print("removed from config", config_path)
PY
done

# 2) Hide extension dir so gateway cannot load the plugin (reversible: mv back to openclaw-moltworld)
for EXT_BASE in "$HOME/.openclaw/extensions" "$HOME/.clawdbot/extensions"; do
  if [[ -d "$EXT_BASE/openclaw-moltworld" ]]; then
    mv "$EXT_BASE/openclaw-moltworld" "$EXT_BASE/openclaw-moltworld.disabled"
    echo "renamed $EXT_BASE/openclaw-moltworld -> openclaw-moltworld.disabled"
  fi
done

echo "MoltWorld plugin removed (config + extension hidden). Restart the gateway to apply."
