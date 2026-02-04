#!/bin/bash
# Move a comment from inbox to outbox with a crafted reply.
# Usage: ./moltbook_reply_outbox_enqueue_on_sparky.sh POST_ID COMMENT_ID "Reply text"
# Env:
#   MOLTBOOK_REPLY_INBOX="$HOME/.config/moltbook/reply_inbox.json"
#   MOLTBOOK_REPLY_OUTBOX="$HOME/.config/moltbook/reply_outbox.json"
set -e

if [ -z "$1" ] || [ -z "$2" ] || [ -z "$3" ]; then
  echo "Usage: $0 POST_ID COMMENT_ID \"Reply text\"" >&2
  exit 1
fi

POST_ID="$1"
COMMENT_ID="$2"
REPLY_TEXT="$3"
INBOX_FILE="${MOLTBOOK_REPLY_INBOX:-$HOME/.config/moltbook/reply_inbox.json}"
OUTBOX_FILE="${MOLTBOOK_REPLY_OUTBOX:-$HOME/.config/moltbook/reply_outbox.json}"

export POST_ID COMMENT_ID REPLY_TEXT INBOX_FILE OUTBOX_FILE
python3 - <<'PY'
import json, os
post_id = os.environ["POST_ID"]
comment_id = os.environ["COMMENT_ID"]
reply_text = os.environ["REPLY_TEXT"]
inbox_path = os.environ["INBOX_FILE"]
outbox_path = os.environ["OUTBOX_FILE"]

def load_list(path):
    try:
        data = json.load(open(path))
        return data if isinstance(data, list) else []
    except Exception:
        return []

def save_list(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

inbox = load_list(inbox_path)
outbox = load_list(outbox_path)

match = None
remaining = []
for item in inbox:
    if item.get("post_id") == post_id and item.get("comment_id") == comment_id and match is None:
        match = item
        continue
    remaining.append(item)

outbox_item = {
    "post_id": post_id,
    "comment_id": comment_id,
    "reply": reply_text,
}
if match:
    outbox_item["author"] = match.get("author", "")
    outbox_item["snippet"] = match.get("snippet", "")

outbox.append(outbox_item)

save_list(outbox_path, outbox)
if match:
    save_list(inbox_path, remaining)

print("Queued reply in outbox.")
PY
