#!/usr/bin/env python3
"""Remove openclaw-moltworld from plugins.entries in OpenClaw/Clawdbot config files."""
import json
import os

paths = [
    os.path.expanduser("~/.openclaw/openclaw.json"),
    os.path.expanduser("~/.clawdbot/clawdbot.json"),
    os.path.expanduser("~/.clawdbot/openclaw.json"),
    os.path.expanduser("~/.openclaw/clawdbot.json"),
]
for path in paths:
    if not os.path.isfile(path):
        continue
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    plugins = data.get("plugins") or {}
    changed = False
    for key in ("entries", "installs"):
        section = plugins.get(key)
        if isinstance(section, dict) and "openclaw-moltworld" in section:
            del section["openclaw-moltworld"]
            changed = True
    if changed:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print("Removed openclaw-moltworld from", path)
    else:
        print("No openclaw-moltworld in", path)
