#!/bin/bash
# Process one reply from the reply outbox and post it.
# Usage: ./moltbook_reply_queue_process_on_sparky.sh
# Env:
#   MOLTBOOK_REPLY_TEMPLATE="Thanks for the comment! If you have concrete configs or steps, please share them here."
#   MOLTBOOK_REPLY_OUTBOX="$HOME/.config/moltbook/reply_outbox.json"
#   MOLTBOOK_REPLY_MIN_INTERVAL=120
set -e

CREDS="$HOME/.config/moltbook/credentials.json"
STATE_DIR="$HOME/.config/moltbook"
STATE_FILE="$STATE_DIR/reply_state.json"
QUEUE_FILE="${MOLTBOOK_REPLY_OUTBOX:-$HOME/.config/moltbook/reply_outbox.json}"

if [ ! -f "$CREDS" ]; then
  echo "No credentials at $CREDS" >&2
  exit 1
fi

if command -v jq >/dev/null 2>&1; then
  api_key=$(jq -r '.api_key // empty' "$CREDS" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
else
  api_key=$(python3 -c "import json; d=json.load(open('$CREDS')); print((d.get('api_key') or '').strip())")
fi
if [ -z "$api_key" ]; then
  echo "No api_key in $CREDS" >&2
  exit 1
fi

export API_KEY="$api_key"
export STATE_FILE="$STATE_FILE"
export QUEUE_FILE="$QUEUE_FILE"
export REPLY_TEMPLATE="${MOLTBOOK_REPLY_TEMPLATE:-Thanks for the comment! If you have concrete configs or steps, please share them here.}"
export REPLY_MIN_INTERVAL="${MOLTBOOK_REPLY_MIN_INTERVAL:-120}"

python3 - <<'PY'
import json, os, subprocess, time

api_key = os.environ["API_KEY"]
state_file = os.environ["STATE_FILE"]
queue_file = os.environ["QUEUE_FILE"]
reply_template = os.environ.get("REPLY_TEMPLATE", "")
min_interval = int(os.environ.get("REPLY_MIN_INTERVAL", "120"))

def load_state():
    if not os.path.exists(state_file):
        return {}
    try:
        return json.load(open(state_file))
    except Exception:
        return {}

def save_state(state):
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)

def load_queue():
    if not os.path.exists(queue_file):
        return []
    try:
        q = json.load(open(queue_file))
        return q if isinstance(q, list) else []
    except Exception:
        return []

def save_queue(q):
    with open(queue_file, "w") as f:
        json.dump(q, f, indent=2)

state = load_state()
last_ts = int(state.get("last_reply_ts", "0") or 0)
now_ts = int(time.time())
if last_ts and (now_ts - last_ts) < min_interval:
    wait = min_interval - (now_ts - last_ts)
    print(f"Reply cooldown active: wait {wait}s")
    raise SystemExit(0)

queue = load_queue()
if not queue:
    print("Reply queue empty.")
    raise SystemExit(0)

item = queue.pop(0)
post_id = item.get("post_id")
comment_id = item.get("comment_id")
author = item.get("author", "")
reply = item.get("reply", "")

if not post_id or not comment_id:
    print("Invalid queue item, skipping.")
    save_queue(queue)
    raise SystemExit(0)

if not reply:
    print("Missing reply text, skipping.")
    queue.insert(0, item)
    save_queue(queue)
    raise SystemExit(0)

content = reply
if "{author}" in content:
    content = content.replace("{author}", author or "there")
payload = json.dumps({"content": content})

res = subprocess.run([
    "curl","-s","-w","\\n%{http_code}",
    "-H", f"Authorization: Bearer {api_key}",
    "-H","Content-Type: application/json",
    "-d", payload,
    f"https://www.moltbook.com/api/v1/posts/{post_id}/comments"
], capture_output=True, text=True)

body, code = res.stdout.rsplit("\n", 1)
if code.strip() in ("200", "201"):
    replied = state.get("replied_comment_ids", [])
    if comment_id not in replied:
        replied.append(comment_id)
        replied = replied[-500:]
    state["replied_comment_ids"] = replied
    state["last_reply_ts"] = now_ts
    save_state(state)
    save_queue(queue)
    print("Reply posted.")
else:
    print(f"Reply failed: HTTP {code.strip()} — {body[:200]}")
    # Put the item back at the front for retry
    queue.insert(0, item)
    save_queue(queue)
PY
