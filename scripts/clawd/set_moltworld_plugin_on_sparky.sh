#!/usr/bin/env bash
# Enable or disable the MoltWorld plugin on this host (reversible).
# When disabled: no "Hook MoltWorld", no world_state/chat_say/go_to/fetch_url from the plugin.
# Usage: bash set_moltworld_plugin_on_sparky.sh disable | enable
# Run on sparky: ssh sparky2 'bash -s' < set_moltworld_plugin_on_sparky.sh enable
set -e
MODE="${1:-}"
if [[ "$MODE" != "disable" && "$MODE" != "enable" ]]; then
  echo "Usage: $0 disable | enable" >&2
  exit 1
fi

MOLTWORLD_TOOLS="world_state world_action go_to chat_say web_fetch fetch_url openclaw-moltworld"

for CONFIG in "$HOME/.openclaw/openclaw.json" "$HOME/.clawdbot/clawdbot.json"; do
  [[ -f "$CONFIG" ]] || continue
  python3 - "$CONFIG" "$MODE" "$MOLTWORLD_TOOLS" << 'PY'
import json, sys, os
config_path = os.path.expanduser(sys.argv[1])
mode = sys.argv[2]
tool_names = sys.argv[3].split()

with open(config_path, "r", encoding="utf-8") as f:
    data = json.load(f)

data.setdefault("plugins", {}).setdefault("entries", {})
entry = data["plugins"]["entries"].setdefault("openclaw-moltworld", {"config": {}})
entry["enabled"] = (mode == "enable")

# tools.allow: when disable, remove MoltWorld tools so the agent does not see them; when enable, add back
data.setdefault("tools", {})
allow = data["tools"].get("allow")
if allow is not None:
    if isinstance(allow, str):
        allow = [allow]
    allow = list(allow)
    if mode == "disable":
        allow = [x for x in allow if x not in tool_names]
    else:
        for name in tool_names:
            if name not in allow:
                allow.append(name)
    data["tools"]["allow"] = allow

with open(config_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
print(mode + "d", config_path)
PY
done

echo "MoltWorld plugin ${MODE}d. Restart the gateway to apply."
