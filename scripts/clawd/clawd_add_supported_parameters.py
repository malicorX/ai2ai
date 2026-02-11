#!/usr/bin/env python3
"""Add compat.supportsParameters: ["tools", "tool_choice"] to all Ollama models.
Schema key is supportsParameters (zod). Run after installing the jokelord-patched build.
Usage: python3 ~/ai2ai/scripts/clawd/clawd_add_supported_parameters.py
"""
import json
import os

paths = [
    os.path.expanduser("~/.openclaw/openclaw.json"),
    os.path.expanduser("~/.clawdbot/clawdbot.json"),
]
path = next((p for p in paths if os.path.isfile(p)), None)
if not path:
    print("No config found at:", ", ".join(paths))
    exit(1)

with open(path) as f:
    d = json.load(f)

ollama = d.get("models", {}).get("providers", {}).get("ollama", {})
models = ollama.get("models", [])
if not models:
    print("No Ollama models in config.")
    exit(0)

for m in models:
    if not isinstance(m, dict):
        continue
    if "compat" not in m:
        m["compat"] = {}
    if not isinstance(m["compat"], dict):
        m["compat"] = {}
    m["compat"].pop("supportedParameters", None)  # old wrong key name
    m["compat"]["supportsParameters"] = ["tools", "tool_choice"]

with open(path, "w") as f:
    json.dump(d, f, indent=2)

print("Added compat.supportsParameters to", len(models), "Ollama model(s).")
print("Config:", path)
print("Restart gateway: clawdbot gateway stop; sleep 2; nohup clawdbot gateway >> ~/.openclaw/gateway.log 2>&1 &")
