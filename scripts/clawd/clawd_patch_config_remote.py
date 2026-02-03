#!/usr/bin/env python3
"""Patch ~/.clawdbot/clawdbot.json: tools.profile=full, browser.executablePath, tools.deny (message). Run on sparky.
Does not set compat.openaiCompletionsTools (stock Clawd rejects it); add manually when gateway has PR #4287.
Usage: python3 clawd_patch_config_remote.py [primary_model]
Example: python3 clawd_patch_config_remote.py ollama/qwen2.5-coder:32b
"""
import json
import os
import sys

p = os.path.expanduser("~/.clawdbot/clawdbot.json")
with open(p) as f:
    d = json.load(f)
if "tools" not in d:
    d["tools"] = {}
d["tools"]["profile"] = "full"
d["tools"].pop("allow", None)
if "deny" not in d["tools"]:
    d["tools"]["deny"] = []
for tool in ["sessions_send", "message"]:
    if tool not in d["tools"]["deny"]:
        d["tools"]["deny"].append(tool)
if "tools" in d and isinstance(d["tools"], dict):
    if "exec" not in d["tools"]:
        d["tools"]["exec"] = {}
    d["tools"]["exec"]["host"] = "gateway"
    d["tools"]["exec"]["ask"] = "off"
    d["tools"]["exec"]["security"] = "full"
if "browser" not in d:
    d["browser"] = {}
d["browser"]["enabled"] = True
d["browser"]["headless"] = True
d["browser"]["noSandbox"] = True
if os.path.isfile("/usr/bin/google-chrome-stable"):
    d["browser"]["executablePath"] = "/usr/bin/google-chrome-stable"
elif os.path.isfile("/usr/bin/google-chrome"):
    d["browser"]["executablePath"] = "/usr/bin/google-chrome"
elif os.path.isfile("/usr/bin/chromium-browser"):
    d["browser"]["executablePath"] = "/usr/bin/chromium-browser"  # fallback; Chrome .deb preferred on Ubuntu
# Ensure Ollama models list includes qwen2.5-coder:32b so primary=ollama/qwen2.5-coder:32b works (no empty response)
ollama_models = d.setdefault("models", {}).setdefault("providers", {}).setdefault("ollama", {}).setdefault("models", [])
existing_ids = {m.get("id") for m in ollama_models if isinstance(m, dict) and m.get("id")}
qwen_entry = {
    "id": "qwen2.5-coder:32b",
    "name": "Qwen 2.5 Coder 32B",
    "reasoning": False,
    "input": ["text"],
    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
    "contextWindow": 32768,
    "maxTokens": 8192,
}
if qwen_entry["id"] not in existing_ids:
    ollama_models.append(qwen_entry)
    print("Added %s to Ollama models list" % qwen_entry["id"])

# Remove compat.openaiCompletionsTools if present (stock Clawd rejects it)
for m in ollama_models:
    if isinstance(m, dict) and isinstance(m.get("compat"), dict):
        m["compat"].pop("openaiCompletionsTools", None)
        if not m["compat"]:
            m.pop("compat", None)

if len(sys.argv) > 1 and sys.argv[1].strip():
    primary = sys.argv[1].strip()
    if "agents" not in d:
        d["agents"] = {}
    if "defaults" not in d["agents"]:
        d["agents"]["defaults"] = {}
    if "model" not in d["agents"]["defaults"]:
        d["agents"]["defaults"]["model"] = {}
    d["agents"]["defaults"]["model"]["primary"] = primary
    print("Config patched: tools.profile=full, browser.executablePath, primary=%s" % primary)
else:
    print("Config patched: tools.profile=full, browser.executablePath set")
with open(p, "w") as f:
    json.dump(d, f, indent=2)
