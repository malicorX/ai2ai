#!/usr/bin/env python3
"""Remove compat.supportedParameters, compat.supportsParameters, and compat.openaiCompletionsTools from Ollama models.
Use when the installed gateway rejects these keys (stock build)."""
import json
import os

for path in [os.path.expanduser("~/.openclaw/openclaw.json"), os.path.expanduser("~/.clawdbot/clawdbot.json")]:
    if not os.path.isfile(path):
        continue
    with open(path) as f:
        d = json.load(f)
    models = d.get("models", {}).get("providers", {}).get("ollama", {}).get("models", [])
    for m in models:
        if isinstance(m, dict) and "compat" in m:
            m["compat"].pop("supportedParameters", None)
            m["compat"].pop("supportsParameters", None)
            m["compat"].pop("openaiCompletionsTools", None)
            if not m["compat"]:
                m.pop("compat", None)
    with open(path, "w") as f:
        json.dump(d, f, indent=2)
    print("Removed compat keys from", path)
