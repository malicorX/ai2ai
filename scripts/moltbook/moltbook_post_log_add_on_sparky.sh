#!/bin/bash
# Add a post ID (or URL containing an ID) to the local post log.
# Usage: ./moltbook_post_log_add_on_sparky.sh POST_ID_OR_URL [POST_ID_OR_URL...]
set -e

if [ -z "$1" ]; then
  echo "Usage: $0 POST_ID_OR_URL [POST_ID_OR_URL...]" >&2
  exit 1
fi

LOG_PATH="$HOME/.config/moltbook/post_log.json"
mkdir -p "$(dirname "$LOG_PATH")"

export LOG_PATH
python3 - "$@" <<'PY'
import json, os, re, sys, time
args = sys.argv[1:]
log_path = os.environ.get("LOG_PATH", "")

def extract_id(s):
    # Accept raw UUID or a URL ending with UUID
    m = re.search(r'([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})', s)
    return m.group(1) if m else ""

try:
    q = json.load(open(log_path))
    if not isinstance(q, list):
        q = []
except Exception:
    q = []

added = 0
for a in args:
    pid = extract_id(a)
    if not pid:
        continue
    if any(isinstance(e, dict) and e.get("id") == pid for e in q):
        continue
    q.append({"id": pid, "title": "", "submolt": "", "ts": int(time.time())})
    added += 1

with open(log_path, "w") as f:
    json.dump(q, f, indent=2)

print(f"Added {added} post ids.")
PY
