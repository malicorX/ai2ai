#!/usr/bin/env python3
"""Ensure ollama models in ~/.clawdbot/clawdbot.json include qwen2.5-coder:32b (for primary)."""
import json
import os

path = os.path.expanduser("~/.clawdbot/clawdbot.json")
with open(path) as f:
    d = json.load(f)

ollama = d.setdefault("models", {}).setdefault("providers", {}).setdefault("ollama", {})
models = ollama.setdefault("models", [])
ids = {m.get("id") for m in models if isinstance(m, dict)}

# 2026.2.x looks up by full ref "ollama/qwen2.5-coder:32b"
full_id = "ollama/qwen2.5-coder:32b"
short_id = "qwen2.5-coder:32b"
entry = {
    "id": full_id,
    "name": "Qwen 2.5 Coder 32B",
    "reasoning": False,
    "input": ["text"],
    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
    "contextWindow": 32768,
    "maxTokens": 8192,
    "compat": {"supportsParameters": ["tools", "tool_choice"]},
}
if full_id not in ids and short_id not in ids:
    models.append(entry)
    with open(path, "w") as f:
        json.dump(d, f, indent=2)
    print("Added %s to ollama models" % full_id)
elif full_id not in ids and short_id in ids:
    # Already have short id; add full id so lookup by "ollama/..." works
    models.append({**entry, "id": full_id})
    with open(path, "w") as f:
        json.dump(d, f, indent=2)
    print("Added %s to ollama models (lookup by full ref)" % full_id)
else:
    print("%s already in ollama models" % full_id)
