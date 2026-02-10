#!/usr/bin/env python3
"""Print gateway and hooks config for OpenClaw/Clawdbot. Usage: python3 check_hooks_config.py <path-to-json>"""
import json, sys
if len(sys.argv) < 2:
    sys.exit(1)
with open(sys.argv[1]) as f:
    d = json.load(f)
gw = d.get("gateway", {})
h = d.get("hooks", {})
print("gateway.mode:", gw.get("mode"))
print("gateway.auth:", gw.get("auth"))
print("hooks.enabled:", h.get("enabled"))
print("hooks.token set:", bool(h.get("token")))
