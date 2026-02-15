#!/usr/bin/env python3
"""Remove tools.allow from a config so full tool set (including web_fetch) is used."""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "/home/malicor/.clawdbot/clawdbot.json"
with open(path) as f:
    c = json.load(f)
if c.get("tools") and "allow" in c["tools"]:
    del c["tools"]["allow"]
    with open(path, "w") as f:
        json.dump(c, f, indent=2)
    print(f"Removed tools.allow from {path}")
else:
    print(f"No tools.allow in {path}")
