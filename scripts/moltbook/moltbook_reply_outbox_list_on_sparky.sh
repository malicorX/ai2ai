#!/bin/bash
# List queued replies that will be posted by cron.
# Usage: ./moltbook_reply_outbox_list_on_sparky.sh
# Env:
#   MOLTBOOK_REPLY_OUTBOX="$HOME/.config/moltbook/reply_outbox.json"
set -e

OUTBOX_FILE="${MOLTBOOK_REPLY_OUTBOX:-$HOME/.config/moltbook/reply_outbox.json}"

if [ ! -f "$OUTBOX_FILE" ]; then
  echo "Reply outbox empty (no file)."
  exit 0
fi

export OUTBOX_FILE="$OUTBOX_FILE"
python3 - <<'PY'
import json, os
path = os.environ.get("OUTBOX_FILE")
try:
    data = json.load(open(path))
    if not isinstance(data, list):
        data = []
except Exception:
    data = []

print(f"Reply outbox count: {len(data)}")
for i, item in enumerate(data, 1):
    post_id = item.get("post_id", "")
    comment_id = item.get("comment_id", "")
    author = item.get("author", "")
    snippet = item.get("snippet", "")
    reply = item.get("reply", "")
    print(f"{i}. {author} | post={post_id} comment={comment_id}")
    if snippet:
        print(f"   comment: {snippet}")
    if reply:
        print(f"   reply: {reply}")
PY
