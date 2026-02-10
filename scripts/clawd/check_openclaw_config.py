#!/usr/bin/env python3
import json, sys
path = sys.argv[1] if len(sys.argv) > 1 else "/home/malicor/.openclaw/openclaw.json"
with open(path) as f:
    d = json.load(f)
h = d.get("hooks", {})
g = d.get("gateway", {})
print("hooks.enabled", h.get("enabled"))
print("hooks.token length", len(h.get("token") or ""))
print("gateway.auth.token length", len((g.get("auth") or {}).get("token") or ""))
plug = (d.get("plugins") or {}).get("entries") or {}
mw = plug.get("openclaw-moltworld", {}).get("config", {})
print("plugin.token length", len(mw.get("token") or ""))
