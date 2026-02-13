#!/usr/bin/env python3
"""Add compat.supportsParameters to Ollama models in ~/.clawdbot/clawdbot.json."""
import json
import os

path = os.path.expanduser("~/.clawdbot/clawdbot.json")
if not os.path.isfile(path):
    print("No clawdbot.json")
    exit(1)
with open(path) as f:
    d = json.load(f)
prov = d.get("models", {}).get("providers", {})
ollama = prov.get("ollama", {})
models = ollama.get("models", [])
if not models:
    print("No Ollama models in clawdbot.json")
    exit(0)
for m in models:
    if isinstance(m, dict):
        m.setdefault("compat", {})
        if isinstance(m["compat"], dict):
            m["compat"].pop("supportedParameters", None)
            m["compat"]["supportsParameters"] = ["tools", "tool_choice"]
with open(path, "w") as f:
    json.dump(d, f, indent=2)
print("Added compat to", len(models), "Ollama model(s) in clawdbot.json")
