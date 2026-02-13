#!/usr/bin/env python3
"""Add compat.openaiCompletionsTools: true to all Ollama models.
Use this after upgrading to OpenClaw from npm @latest or from openclaw/openclaw main
(which includes the tool-calling fix from PR #4287). Then restart the gateway.
See docs/external-tools/clawd/OPENCLAW_OLLAMA_TOOL_CALLING_PLAN.md.
"""
import json
import os

updated = []
for path in [os.path.expanduser("~/.openclaw/openclaw.json"), os.path.expanduser("~/.clawdbot/clawdbot.json")]:
    if not os.path.isfile(path):
        continue
    with open(path) as f:
        d = json.load(f)
    models = d.get("models", {}).get("providers", {}).get("ollama", {}).get("models", [])
    for m in models:
        if isinstance(m, dict):
            m.setdefault("compat", {})["openaiCompletionsTools"] = True
    with open(path, "w") as f:
        json.dump(d, f, indent=2)
    updated.append(path)
if updated:
    print("Set compat.openaiCompletionsTools on Ollama models in:", ", ".join(updated))
    print("Restart the gateway so the change takes effect.")
else:
    print("No openclaw.json or clawdbot.json found.")
