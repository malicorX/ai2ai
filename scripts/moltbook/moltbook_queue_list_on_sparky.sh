#!/bin/bash
# List queued Moltbook posts from ~/.config/moltbook/queue.json
# Usage: ./moltbook_queue_list_on_sparky.sh
set -e
QUEUE_FILE="$HOME/.config/moltbook/queue.json"
if [ ! -f "$QUEUE_FILE" ]; then
  echo "No queue file at $QUEUE_FILE"
  exit 0
fi

if command -v jq >/dev/null 2>&1; then
  len=$(jq 'length' "$QUEUE_FILE")
  echo "Queue length: $len"
  jq -r '
    to_entries[] |
    "\(.key+1). [\(.value.submolt // "general")] \(.value.title)\n    \(.value.content | gsub("\\n"; " "))"
  ' "$QUEUE_FILE"
else
  python3 - << 'PY'
import json, os
path=os.path.expanduser("~/.config/moltbook/queue.json")
with open(path) as f:
    q=json.load(f)
print(f"Queue length: {len(q)}")
for i, item in enumerate(q, start=1):
    title=item.get("title","")
    content=(item.get("content","") or "").replace("\n"," ")
    submolt=item.get("submolt","general")
    print(f"{i}. [{submolt}] {title}")
    print(f"    {content}")
PY
fi
