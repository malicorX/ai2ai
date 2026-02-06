#!/usr/bin/env python3
"""Post to Moltbook using credentials from ~/.config/moltbook/credentials.json.
Reads from environment: MOLTBOOK_TITLE_B64 and MOLTBOOK_BODY_B64 (base64), or MOLTBOOK_TITLE + MOLTBOOK_BODY_B64."""
import base64
import json
import os
import sys
import urllib.request
import urllib.error

def b64_decode(env_name: str, b64_value: str) -> str:
    if not b64_value:
        return ""
    try:
        return base64.b64decode(b64_value).decode("utf-8")
    except Exception as e:
        print(f"Invalid {env_name}: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    creds_path = os.path.expanduser("~/.config/moltbook/credentials.json")
    if not os.path.exists(creds_path):
        print("No credentials at", creds_path, file=sys.stderr)
        sys.exit(1)
    with open(creds_path, "r", encoding="utf-8") as f:
        api_key = json.load(f).get("api_key", "").strip()
    if not api_key:
        print("No api_key in credentials", file=sys.stderr)
        sys.exit(1)

    title_b64 = os.environ.get("MOLTBOOK_TITLE_B64", "")
    title_plain = os.environ.get("MOLTBOOK_TITLE", "")
    body_b64 = os.environ.get("MOLTBOOK_BODY_B64", "")
    if title_b64:
        title = b64_decode("MOLTBOOK_TITLE_B64", title_b64)
    else:
        title = title_plain
    if not body_b64:
        print("Set MOLTBOOK_BODY_B64 (and MOLTBOOK_TITLE_B64 or MOLTBOOK_TITLE)", file=sys.stderr)
        sys.exit(1)
    body = b64_decode("MOLTBOOK_BODY_B64", body_b64)
    if not title:
        print("Set MOLTBOOK_TITLE or MOLTBOOK_TITLE_B64", file=sys.stderr)
        sys.exit(1)

    payload = json.dumps({"title": title, "content": body, "submolt": "general"}).encode("utf-8")
    req = urllib.request.Request(
        "https://www.moltbook.com/api/v1/posts",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req).read().decode()
    except urllib.error.HTTPError as e:
        resp = e.read().decode() if e.fp else "{}"
        print(json.dumps({"error": "HTTP " + str(e.code), "body": resp}))
        sys.exit(1)
    print(resp)

if __name__ == "__main__":
    main()
