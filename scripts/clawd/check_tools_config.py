#!/usr/bin/env python3
"""Print tools and ollama compat from openclaw/clawdbot config. Run on sparky."""
import json, os
for name in [".openclaw/openclaw.json", ".clawdbot/clawdbot.json"]:
    p = os.path.expanduser(os.path.join("~", name))
    if not os.path.isfile(p):
        continue
    with open(p) as f:
        d = json.load(f)
    t = d.get("tools", {})
    plug = d.get("plugins", {}).get("entries", {}).get("openclaw-moltworld", {})
    print("Config:", p)
    print("  plugins.entries.openclaw-moltworld.enabled:", plug.get("enabled"))
    print("  tools.profile:", t.get("profile"))
    print("  tools.allow:", t.get("allow"))
    o = d.get("models", {}).get("providers", {}).get("ollama", {})
    for i, m in enumerate(o.get("models", [])[:3]):
        if isinstance(m, dict):
            print("  ollama[%s].compat: %s" % (i, m.get("compat")))
    print()
