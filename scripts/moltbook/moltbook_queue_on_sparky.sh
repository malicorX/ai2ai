#!/bin/bash
# Add one post to the Moltbook queue. Cron will post from the queue (respecting daily cap and 30 min rate limit).
# Usage: ./moltbook_queue_on_sparky.sh "Title" "Content" [submolt]
#   submolt defaults to "general".
# Other scripts (e.g. after test run, deploy) can call this to queue a meaningful post.
set -e
CONFIG_DIR="${HOME}/.config/moltbook"
QUEUE_FILE="$CONFIG_DIR/queue.json"

if [ -z "$1" ] || [ -z "$2" ]; then
  # Allow base64-encoded env inputs for remote queueing
  if [ -n "$MB_TITLE_B64" ] && [ -n "$MB_CONTENT_B64" ]; then
    TITLE="$(printf '%s' "$MB_TITLE_B64" | base64 -d)"
    CONTENT="$(printf '%s' "$MB_CONTENT_B64" | base64 -d)"
    SUBMOLT="${MB_SUBMOLT:-general}"
  else
    echo "Usage: $0 \"Title\" \"Content\" [submolt]" >&2
    echo "  Or set MB_TITLE_B64 and MB_CONTENT_B64 env vars." >&2
    exit 1
  fi
else
  TITLE="$1"
  CONTENT="$2"
  SUBMOLT="${3:-general}"
fi

mkdir -p "$CONFIG_DIR"

# Append one entry to queue (JSON array)
if command -v jq >/dev/null 2>&1; then
  if [ -f "$QUEUE_FILE" ]; then
    existing=$(cat "$QUEUE_FILE")
  else
    existing="[]"
  fi
  new_entry=$(jq -n --arg t "$TITLE" --arg c "$CONTENT" --arg s "$SUBMOLT" '{title: $t, content: $c, submolt: $s}')
  (echo "$existing" | jq --argjson e "$new_entry" '. + [$e]') > "${QUEUE_FILE}.tmp" && mv "${QUEUE_FILE}.tmp" "$QUEUE_FILE"
else
  # Python fallback
  python3 - "$QUEUE_FILE" "$TITLE" "$CONTENT" "$SUBMOLT" << 'PY'
import json, sys
path, title, content, submolt = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
try:
  with open(path) as f:
    q = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
  q = []
q.append({"title": title, "content": content, "submolt": submolt})
with open(path, "w") as f:
  json.dump(q, f, indent=0)
PY
fi

echo "Queued: $TITLE"
