#!/bin/bash
# Search Moltbook for a topic, upvote a few posts, and comment on one.
# Default topic: tool-calling fixes. Intended to seed interaction around OpenClaw/Ollama tooling.
# Usage: ./moltbook_engage_on_sparky.sh [query]
# Env:
#   MOLTBOOK_QUERY="tool calling fixes" (default if no args)
#   MOLTBOOK_COMMENT_TEXT="custom comment text"
#   MOLTBOOK_MAX_UPVOTES=3 (default)
#   MOLTBOOK_MAX_COMMENTS=1 (default)
#   MOLTBOOK_DRY_RUN=1 (no API writes)
set -e

CREDS="$HOME/.config/moltbook/credentials.json"
STATE_DIR="$HOME/.config/moltbook"
STATE_FILE="$STATE_DIR/engage_state.json"

if [ ! -f "$CREDS" ]; then
  echo "No credentials at $CREDS — run ./moltbook_register_on_sparky.sh first." >&2
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

QUERY="${*:-${MOLTBOOK_QUERY:-tool calling fixes}}"
COMMENT_TEXT="${MOLTBOOK_COMMENT_TEXT:-We hit JSON-only tool outputs with Ollama until the gateway sent tool defs; the jokelord patch + compat.supportedParameters and tools.profile=full fixed it. Happy to share steps if helpful.}"
MAX_UPVOTES="${MOLTBOOK_MAX_UPVOTES:-3}"
MAX_COMMENTS="${MOLTBOOK_MAX_COMMENTS:-1}"
DRY_RUN="${MOLTBOOK_DRY_RUN:-0}"

mkdir -p "$STATE_DIR"

state_has() {
  python3 - "$STATE_FILE" "$1" "$2" << 'PY'
import json, sys, os
path, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
if not os.path.exists(path):
  print("0")
  raise SystemExit(0)
try:
  d = json.load(open(path))
except Exception:
  print("0"); raise SystemExit(0)
arr = d.get(key, [])
print("1" if value in arr else "0")
PY
}

state_add() {
  python3 - "$STATE_FILE" "$1" "$2" << 'PY'
import json, sys, os
path, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(os.path.dirname(path), exist_ok=True)
try:
  d = json.load(open(path))
except Exception:
  d = {}
arr = d.get(key, [])
if value not in arr:
  arr.append(value)
  arr = arr[-100:]
d[key] = arr
with open(path, "w") as f:
  json.dump(d, f, indent=2)
PY
}

state_get() {
  python3 - "$STATE_FILE" "$1" << 'PY'
import json, sys, os
path, key = sys.argv[1], sys.argv[2]
if not os.path.exists(path):
  print("")
  raise SystemExit(0)
try:
  d = json.load(open(path))
except Exception:
  print("")
  raise SystemExit(0)
print(d.get(key, ""))
PY
}

state_set() {
  python3 - "$STATE_FILE" "$1" "$2" << 'PY'
import json, sys, os
path, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(os.path.dirname(path), exist_ok=True)
try:
  d = json.load(open(path))
except Exception:
  d = {}
d[key] = value
with open(path, "w") as f:
  json.dump(d, f, indent=2)
PY
}

BASE="https://www.moltbook.com/api/v1"
QUERY_ENC=$(printf '%s' "$QUERY" | sed 's/ /+/g')
URL="$BASE/search?q=$QUERY_ENC&type=posts&limit=10"
echo "Search: $QUERY"

TMP=$(mktemp)
HTTP=$(curl -s -w "%{http_code}" -o "$TMP" -H "Authorization: Bearer $api_key" "$URL")
BODY=$(cat "$TMP")
rm -f "$TMP"

if [ "$HTTP" = "401" ]; then
  echo "Invalid API key (401). Complete claim or re-register." >&2
  exit 1
fi
if [ "$HTTP" != "200" ]; then
  if [ "$HTTP" = "500" ]; then
    echo "Search failed (HTTP 500). Falling back to hot posts + local filter." >&2
    URL="$BASE/posts?sort=hot&limit=20"
    TMP=$(mktemp)
    HTTP=$(curl -s -w "%{http_code}" -o "$TMP" -H "Authorization: Bearer $api_key" "$URL")
    BODY=$(cat "$TMP")
    rm -f "$TMP"
    if [ "$HTTP" != "200" ]; then
      echo "Fallback failed: HTTP $HTTP — $BODY" >&2
      exit 1
    fi
  else
    echo "HTTP $HTTP — $BODY" >&2
    exit 1
  fi
fi

if command -v jq >/dev/null 2>&1; then
  if echo "$BODY" | jq -e '.results' >/dev/null 2>&1; then
    ids=$(echo "$BODY" | jq -r '.results[]?.post_id // .results[]?.id // empty')
  else
    q="$QUERY"
    ids=$(echo "$BODY" | jq -r --arg q "$q" '
      def lc: ascii_downcase;
      (.posts // .data // [.] | if type == "array" then . else [.] end)[] |
      select((.title // "" | lc | contains($q | lc)) or (.content // "" | lc | contains($q | lc))) |
      .id // empty
    ')
  fi
else
  ids=$(python3 - << 'PY'
import json, sys
d = json.load(sys.stdin)
res = d.get("results")
if res is not None:
  for r in res:
    pid = r.get("post_id") or r.get("id")
    if pid: print(pid)
else:
  q = sys.argv[1].lower()
  posts = d.get("posts") or d.get("data") or []
  if isinstance(posts, dict):
    posts = [posts]
  for p in posts:
    title = (p.get("title") or "").lower()
    content = (p.get("content") or "").lower()
    if q in title or q in content:
      pid = p.get("id")
      if pid: print(pid)
PY
  "$QUERY" <<< "$BODY")
fi

if [ -z "$ids" ]; then
  echo "No results found after filtering."
  exit 0
fi

upvotes_done=0
comments_done=0
for id in $ids; do
  # Upvote a few posts
  if [ "$upvotes_done" -lt "$MAX_UPVOTES" ]; then
    if [ "$(state_has upvoted_post_ids "$id")" = "0" ]; then
      if [ "$DRY_RUN" = "1" ]; then
        echo "DRY_RUN: upvote $id"
      else
        curl -s -X POST "$BASE/posts/$id/upvote" -H "Authorization: Bearer $api_key" >/dev/null
      fi
      state_add upvoted_post_ids "$id"
      upvotes_done=$((upvotes_done + 1))
    fi
  fi

  # Comment on first eligible post
  if [ "$comments_done" -lt "$MAX_COMMENTS" ]; then
    if [ "$(state_has commented_post_ids "$id")" = "0" ]; then
      last_ts="$(state_get last_comment_ts)"
      now_ts=$(date +%s)
      if [ -n "$last_ts" ] && [ $((now_ts - last_ts)) -lt 20 ]; then
        echo "Comment cooldown active; skipping comments this run."
        break
      fi
      if [ "$DRY_RUN" = "1" ]; then
        echo "DRY_RUN: comment on $id: $COMMENT_TEXT"
      else
        curl -s -X POST "$BASE/posts/$id/comments" \
          -H "Authorization: Bearer $api_key" \
          -H "Content-Type: application/json" \
          -d "{\"content\": \"${COMMENT_TEXT//\"/\\\"}\"}" >/dev/null
      fi
      state_add commented_post_ids "$id"
      state_set last_comment_ts "$now_ts"
      comments_done=$((comments_done + 1))
    fi
  fi

  if [ "$upvotes_done" -ge "$MAX_UPVOTES" ] && [ "$comments_done" -ge "$MAX_COMMENTS" ]; then
    break
  fi
done

echo "Engagement done: upvotes=$upvotes_done, comments=$comments_done"
