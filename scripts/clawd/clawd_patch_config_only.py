#!/usr/bin/env python3
"""Patch ~/.clawdbot/clawdbot.json only: tools.deny += message (no compat key; stock Clawd rejects it).
Run on sparky2 after syncing repo: python3 ~/ai2ai/scripts/clawd/clawd_patch_config_only.py
Then restart gateway: clawdbot gateway stop; sleep 2; nohup clawdbot gateway >> ~/.clawdbot/gateway.log 2>&1 &
"""
import json
import os

path = os.path.expanduser("~/.clawdbot/clawdbot.json")
os.makedirs(os.path.dirname(path), exist_ok=True)
if not os.path.isfile(path):
    open(path, "w").write("{}")

with open(path) as f:
    d = json.load(f)

# tools.deny must include "message" so /new doesn't show raw JSON
if "tools" not in d:
    d["tools"] = {}
if "deny" not in d["tools"]:
    d["tools"]["deny"] = []
for name in ["sessions_send", "message"]:
    if name not in d["tools"]["deny"]:
        d["tools"]["deny"].append(name)
d["tools"]["profile"] = "full"
d["tools"].pop("allow", None)

# Remove compat.openaiCompletionsTools if present (stock Clawd rejects it; add back when gateway has PR #4287)
ollama = d.get("models", {}).get("providers", {}).get("ollama", {})
for m in ollama.get("models", []):
    if isinstance(m, dict) and isinstance(m.get("compat"), dict):
        m["compat"].pop("openaiCompletionsTools", None)
        if not m["compat"]:
            m.pop("compat", None)

with open(path, "w") as f:
    json.dump(d, f, indent=2)

print("Patched:", path)
print("  tools.deny:", d["tools"]["deny"])
print("Restart gateway: clawdbot gateway stop; sleep 2; nohup clawdbot gateway >> ~/.clawdbot/gateway.log 2>&1 &")
