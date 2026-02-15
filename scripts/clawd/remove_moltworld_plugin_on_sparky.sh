#!/usr/bin/env bash
# Remove MoltWorld plugin entirely: delete from config and hide extension dir so the gateway cannot load it.
# Reversible: to restore, run install_moltworld_plugin_on_sparky.sh (or rename .disabled back and run set_moltworld_plugin_on_sparky.sh enable).
# Usage: bash remove_moltworld_plugin_on_sparky.sh
set -e

MOLTWORLD_TOOLS="world_state world_action go_to chat_say web_fetch fetch_url openclaw-moltworld"

# 1) Remove plugin from plugins.entries AND plugins.installs in ALL configs (gateway loads from .installs)
for CONFIG in "$HOME/.openclaw/openclaw.json" "$HOME/.clawdbot/clawdbot.json" "$HOME/.clawdbot/openclaw.json" "$HOME/.openclaw/clawdbot.json"; do
  [[ -f "$CONFIG" ]] || continue
  python3 - "$CONFIG" "$MOLTWORLD_TOOLS" << 'PY'
import json, sys, os
config_path = os.path.expanduser(sys.argv[1])
tool_names = set(sys.argv[2].split())

with open(config_path, "r", encoding="utf-8") as f:
    data = json.load(f)

plugins = data.setdefault("plugins", {})
for key in ("entries", "installs"):
    section = plugins.get(key)
    if isinstance(section, dict):
        section.pop("openclaw-moltworld", None)

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

# 2) Remove extension dir entirely so gateway cannot load the plugin (no discovery by name)
for EXT_BASE in "$HOME/.openclaw/extensions" "$HOME/.clawdbot/extensions"; do
  for DIR in "$EXT_BASE/openclaw-moltworld" "$EXT_BASE/openclaw-moltworld.disabled"; do
    if [[ -d "$DIR" ]]; then
      rm -rf "$DIR"
      echo "removed $DIR"
    fi
  done
done

echo "MoltWorld plugin removed (config + extension deleted). Restart the gateway to apply."
