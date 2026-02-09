#!/usr/bin/env python3
"""Issue MoltWorld tokens. Run on theebie with ADMIN_TOKEN in env."""
import os
import json
import urllib.request

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()
BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000")

if not ADMIN_TOKEN:
    raise SystemExit("Set ADMIN_TOKEN")

for agent_id, agent_name in [("Sparky1Agent", "Sparky1Agent"), ("MalicorSparky2", "MalicorSparky2")]:
    req = urllib.request.Request(
        f"{BASE}/admin/agent/issue_token",
        data=json.dumps({"agent_id": agent_id, "agent_name": agent_name}).encode(),
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        r = urllib.request.urlopen(req, timeout=10)
        out = json.loads(r.read().decode())
        print(out.get("token", ""))
    except Exception as e:
        raise SystemExit(f"Failed {agent_id}: {e}")
