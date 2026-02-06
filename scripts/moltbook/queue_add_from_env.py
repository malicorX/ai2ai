#!/usr/bin/env python3
"""Append one post to the Moltbook queue (~/.config/moltbook/queue.json).
Reads MOLTBOOK_TITLE_B64, MOLTBOOK_BODY_B64 from environment; optional MOLTBOOK_SUBMOLT (default general)."""
import base64
import json
import os
import sys

def main():
    queue_path = os.path.expanduser("~/.config/moltbook/queue.json")
    title_b64 = os.environ.get("MOLTBOOK_TITLE_B64", "")
    body_b64 = os.environ.get("MOLTBOOK_BODY_B64", "")
    submolt = os.environ.get("MOLTBOOK_SUBMOLT", "general")
    if not title_b64 or not body_b64:
        print("Set MOLTBOOK_TITLE_B64 and MOLTBOOK_BODY_B64", file=sys.stderr)
        sys.exit(1)
    try:
        title = base64.b64decode(title_b64).decode("utf-8")
        content = base64.b64decode(body_b64).decode("utf-8")
    except Exception as e:
        print(f"Invalid base64: {e}", file=sys.stderr)
        sys.exit(1)
    os.makedirs(os.path.dirname(queue_path), exist_ok=True)
    try:
        with open(queue_path, "r", encoding="utf-8") as f:
            q = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        q = []
    q.append({"title": title, "content": content, "submolt": submolt})
    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump(q, f, indent=0)
    print(f"Queued: {title}")

if __name__ == "__main__":
    main()
