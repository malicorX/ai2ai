#!/bin/bash
# Cron entry: check once per hour if there is something to post.
# (a) If we already posted too many times today (daily cap), skip.
# (b) If queue is empty, skip (no heartbeat — only post when there is meaningful content).
# (c) If 30 min have not passed since last post, skip.
# (d) Otherwise pop one item from queue, post it, update daily count and queue.
#
# Meaningful content is added to the queue by:
#   ./moltbook_queue_on_sparky.sh "Title" "Content" [submolt]
# or by other scripts (e.g. after test run / deploy) or by moltbook_prepare_from_run_on_sparky.sh.
#
# Usage: ./moltbook_maybe_post_on_sparky.sh
# Cron:  0 * * * * /path/moltbook_maybe_post_on_sparky.sh >> /tmp/moltbook_cron.log 2>&1
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

CONFIG_DIR="${HOME}/.config/moltbook"
QUEUE_FILE="$CONFIG_DIR/queue.json"
DAILY_POSTS_FILE="$CONFIG_DIR/daily_posts"
LAST_POST="$CONFIG_DIR/last_post_ts"
MIN_INTERVAL=1800   # 30 minutes
MAX_POSTS_PER_DAY="${MOLTBOOK_MAX_POSTS_PER_DAY:-5}"

today=$(date -u +%Y-%m-%d)
now=$(date +%s)

# (a) Daily cap: have we already posted MAX today?
if [ -f "$DAILY_POSTS_FILE" ]; then
  read -r file_date count < "$DAILY_POSTS_FILE" || true
  if [ "$file_date" = "$today" ] && [ -n "$count" ] && [ "$count" -ge "$MAX_POSTS_PER_DAY" ]; then
    echo "Daily cap reached ($count/$MAX_POSTS_PER_DAY). Skipping."
    exit 0
  fi
fi

# 30 min since last post
if [ -f "$LAST_POST" ]; then
  last=$(cat "$LAST_POST")
  elapsed=$((now - last))
  if [ "$elapsed" -lt "$MIN_INTERVAL" ]; then
    echo "Rate limit: wait $(( (MIN_INTERVAL - elapsed) / 60 )) min before next post. Skipping."
    exit 0
  fi
fi

# (b) Queue: is there something to post?
if [ ! -f "$QUEUE_FILE" ]; then
  echo "No queue file. Skipping."
  exit 0
fi

queue=$(cat "$QUEUE_FILE")
if command -v jq >/dev/null 2>&1; then
  len=$(echo "$queue" | jq 'length')
else
  len=$(python3 -c "import json; q=json.load(open('$QUEUE_FILE')); print(len(q))" 2>/dev/null || echo "0")
fi
if [ "$len" = "0" ] || [ -z "$len" ]; then
  echo "Queue empty. Skipping."
  exit 0
fi

# Pop first item (do not remove from queue until post succeeds)
if command -v jq >/dev/null 2>&1; then
  first=$(echo "$queue" | jq -c '.[0]')
  rest=$(echo "$queue" | jq '.[1:]')
  title=$(echo "$first" | jq -r '.title')
  content=$(echo "$first" | jq -r '.content')
  submolt=$(echo "$first" | jq -r '.submolt // "general"')
else
  first_json=$(python3 -c "
import json, sys
with open('$QUEUE_FILE') as f:
  q = json.load(f)
if not q:
  sys.exit(1)
e = q[0]
rest = q[1:]
with open('${QUEUE_FILE}.new', 'w') as f:
  json.dump(rest, f, indent=0)
print(json.dumps(e))
")
  title=$(echo "$first_json" | python3 -c "import json,sys; e=json.load(sys.stdin); print(e.get('title',''))")
  content=$(echo "$first_json" | python3 -c "import json,sys; e=json.load(sys.stdin); print(e.get('content',''))")
  submolt=$(echo "$first_json" | python3 -c "import json,sys; e=json.load(sys.stdin); print(e.get('submolt','general'))")
fi

# Post (this updates last_post_ts on success)
if ./moltbook_post_on_sparky.sh "$title" "$content" "$submolt"; then
  # Remove first item from queue only after successful post
  if command -v jq >/dev/null 2>&1; then
    echo "$rest" > "$QUEUE_FILE"
  else
    mv "${QUEUE_FILE}.new" "$QUEUE_FILE"
  fi
  # Update daily count
  if [ -f "$DAILY_POSTS_FILE" ]; then
    read -r file_date count < "$DAILY_POSTS_FILE" || true
  else
    file_date=""
    count="0"
  fi
  if [ "$file_date" = "$today" ]; then
    count=$((count + 1))
  else
    count=1
  fi
  echo "$today $count" > "$DAILY_POSTS_FILE"
  echo "Daily posts today: $count/$MAX_POSTS_PER_DAY"
else
  rm -f "${QUEUE_FILE}.new"
  exit 1
fi
