#!/usr/bin/env python3
"""Add compat.supportedParameters: ["tools", "tool_choice"] to all Ollama models.
Run after installing the jokelord-patched build.
Usage: python3 ~/ai2ai/scripts/clawd/clawd_add_supported_parameters.py
"""
import json
import os

paths = [
    os.path.expanduser("~/.openclaw/openclaw.json"),
    os.path.expanduser("~/.clawdbot/clawdbot.json"),
]
updated = []
for path in paths:
    if not os.path.isfile(path):
        continue
    with open(path) as f:
        d = json.load(f)
    ollama = d.get("models", {}).get("providers", {}).get("ollama", {})
    models = ollama.get("models", [])
    if not models:
        continue
    for m in models:
        if not isinstance(m, dict):
            continue
        if "compat" not in m:
            m["compat"] = {}
        if not isinstance(m["compat"], dict):
            m["compat"] = {}
        m["compat"].pop("supportsParameters", None)
        m["compat"]["supportedParameters"] = ["tools", "tool_choice"]
    with open(path, "w") as f:
        json.dump(d, f, indent=2)
    updated.append((path, len(models)))
if not updated:
    print("No config found or no Ollama models at:", ", ".join(paths))
    exit(1)
for path, n in updated:
    print("Added compat.supportedParameters to", n, "Ollama model(s) in", path)
print("Restart gateway so the change takes effect.")
