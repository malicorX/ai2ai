#!/usr/bin/env python3
"""
Issue MoltWorld agent tokens for Sparky1Agent and MalicorSparky2.
Requires: ADMIN_TOKEN, MOLTWORLD_BASE_URL (default https://www.theebie.de)
Usage: ADMIN_TOKEN=xxx python scripts/issue_moltworld_tokens.py
       Or set env and run; script prints tokens and writes deployment/*.moltworld.env
"""
import json
import os
import sys
import urllib.request
import urllib.error

BASE_URL = os.getenv("MOLTWORLD_BASE_URL", "https://www.theebie.de").rstrip("/")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()

AGENTS = [
    ("Sparky1Agent", "Sparky1Agent"),
    ("MalicorSparky2", "MalicorSparky2"),
]


def issue_token(agent_id: str, agent_name: str) -> str:
    payload = json.dumps({"agent_id": agent_id, "agent_name": agent_name}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/admin/agent/issue_token",
        data=payload,
        headers={
            "Authorization": f"Bearer {ADMIN_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            out = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise SystemExit(f"issue_token failed: HTTP {e.code} — {body}")
    token = (out.get("token") or "").strip()
    if not token:
        raise SystemExit(f"issue_token: no token in response — {out}")
    return token


def main():
    if not ADMIN_TOKEN:
        print("Set ADMIN_TOKEN (and optionally MOLTWORLD_BASE_URL).", file=sys.stderr)
        sys.exit(1)
    results = []
    for agent_id, agent_name in AGENTS:
        token = issue_token(agent_id, agent_name)
        results.append((agent_id, agent_name, token))
        print(f"{agent_id}: {token}")
    # Write env files next to deployment/ (sparky1 / sparky2)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    deployment_dir = os.path.join(os.path.dirname(script_dir), "deployment")
    # Sparky1Agent -> sparky1_moltworld.env, MalicorSparky2 -> sparky2_moltworld.env
    agent_to_file = {"Sparky1Agent": "sparky1_moltworld.env", "MalicorSparky2": "sparky2_moltworld.env"}
    for agent_id, agent_name, token in results:
        env_path = os.path.join(deployment_dir, agent_to_file.get(agent_id, f"{agent_id.lower()}_moltworld.env"))
        content = f"""# MoltWorld agent env for {agent_id} — source or pass to agent process
WORLD_API_BASE={BASE_URL}
AGENT_ID={agent_id}
DISPLAY_NAME={agent_name}
WORLD_AGENT_TOKEN={token}
"""
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Wrote {env_path}")
    return results


if __name__ == "__main__":
    main()
