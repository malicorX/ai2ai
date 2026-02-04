#!/bin/bash
# List queued comment replies that need a meaningful response.
# Usage: ./moltbook_reply_inbox_list_on_sparky.sh
# Env:
#   MOLTBOOK_REPLY_INBOX="$HOME/.config/moltbook/reply_inbox.json"
set -e

INBOX_FILE="${MOLTBOOK_REPLY_INBOX:-$HOME/.config/moltbook/reply_inbox.json}"

if [ ! -f "$INBOX_FILE" ]; then
  echo "Reply inbox empty (no file)."
  exit 0
fi

export INBOX_FILE="$INBOX_FILE"
python3 - <<'PY'
import json, os
path = os.environ.get("INBOX_FILE")
try:
    data = json.load(open(path))
    if not isinstance(data, list):
        data = []
except Exception:
    data = []

print(f"Reply inbox count: {len(data)}")
for i, item in enumerate(data, 1):
    post_id = item.get("post_id", "")
    comment_id = item.get("comment_id", "")
    author = item.get("author", "")
    snippet = item.get("snippet", "")
    queued_at = item.get("queued_at", "")
    print(f"{i}. {author} | post={post_id} comment={comment_id} queued_at={queued_at}")
    print(f"   {snippet}")
PY
