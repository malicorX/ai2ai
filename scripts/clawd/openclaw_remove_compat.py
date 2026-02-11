#!/usr/bin/env python3
"""Remove compat.supportedParameters from Ollama models so stock OpenClaw config is valid."""
import json
import os

path = os.path.expanduser("~/.openclaw/openclaw.json")
if not os.path.isfile(path):
    print("No", path)
    exit(1)
with open(path) as f:
    d = json.load(f)
models = d.get("models", {}).get("providers", {}).get("ollama", {}).get("models", [])
for m in models:
    if isinstance(m, dict) and "compat" in m:
        m["compat"].pop("supportedParameters", None)
        m["compat"].pop("supportsParameters", None)
        if not m["compat"]:
            m.pop("compat", None)
with open(path, "w") as f:
    json.dump(d, f, indent=2)
print("Removed compat.supportedParameters from", len(models), "model(s). Config valid.")
