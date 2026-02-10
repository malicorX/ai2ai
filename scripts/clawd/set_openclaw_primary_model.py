#!/usr/bin/env python3
"""Set agents.defaults.model.primary in OpenClaw config. Usage: python3 set_openclaw_primary_model.py <path-to-openclaw.json> <model-id>"""
import json, sys
p = sys.argv[1]
model = sys.argv[2]
with open(p, encoding="utf-8") as f:
    d = json.load(f)
if not isinstance(d.get("agents"), dict):
    d["agents"] = {}
agents = d["agents"]
if not isinstance(agents.get("defaults"), dict):
    agents["defaults"] = {}
defaults = agents["defaults"]
defaults["model"] = {"primary": model}
with open(p, "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2)
print("primary:", d["agents"]["defaults"]["model"]["primary"])
