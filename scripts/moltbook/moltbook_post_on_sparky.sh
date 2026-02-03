#!/bin/bash
# Post once to Moltbook. Enforces 1 post per 30 minutes (Moltbook rate limit).
# Usage: ./moltbook_post_on_sparky.sh "Title" "Content" [submolt]
#   submolt defaults to "general". Example: ./moltbook_post_on_sparky.sh "Hello" "First post from MalicorSparky2."
set -e
CREDS="$HOME/.config/moltbook/credentials.json"
LAST_POST="$HOME/.config/moltbook/last_post_ts"
MIN_INTERVAL=1800   # 30 minutes in seconds

if [ -z "$1" ] || [ -z "$2" ]; then
  echo "Usage: $0 \"Title\" \"Content\" [submolt]" >&2
  echo "  submolt defaults to general." >&2
  exit 1
fi
TITLE="$1"
CONTENT="$2"
SUBMOLT="${3:-general}"

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

# Rate limit: 1 post per 30 min
mkdir -p "$(dirname "$LAST_POST")"
now=$(date +%s)
if [ -f "$LAST_POST" ]; then
  last=$(cat "$LAST_POST")
  elapsed=$((now - last))
  if [ "$elapsed" -lt "$MIN_INTERVAL" ]; then
    remaining=$((MIN_INTERVAL - elapsed))
    echo "Rate limit: wait $((remaining / 60)) more minutes before posting again (1 post per 30 min)." >&2
    exit 1
  fi
fi

# Build JSON payload (escape title and content).
if command -v jq >/dev/null 2>&1; then
  PAYLOAD=$(jq -n --arg submolt "$SUBMOLT" --arg title "$TITLE" --arg content "$CONTENT" '{submolt: $submolt, title: $title, content: $content}')
else
  PAYLOAD=$(python3 -c "
import json, os
t = os.environ.get('MB_TITLE', '')
c = os.environ.get('MB_CONTENT', '')
s = os.environ.get('MB_SUBMOLT', 'general')
print(json.dumps({'submolt': s, 'title': t, 'content': c}))
" MB_SUBMOLT="$SUBMOLT" MB_TITLE="$TITLE" MB_CONTENT="$CONTENT")
fi
# POST
TMP=$(mktemp)
HTTP=$(curl -s -w "%{http_code}" -o "$TMP" -X POST "https://www.moltbook.com/api/v1/posts" \
  -H "Authorization: Bearer $api_key" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")
BODY=$(cat "$TMP")
rm -f "$TMP"

if [ "$HTTP" = "200" ] || [ "$HTTP" = "201" ]; then
  echo "$now" > "$LAST_POST"
  echo "Posted to submolt '$SUBMOLT': $TITLE"
  if command -v jq >/dev/null 2>&1; then
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
  else
    echo "$BODY"
  fi
else
  echo "HTTP $HTTP — $BODY" >&2
  if [ "$HTTP" = "429" ]; then
    echo "Rate limit (429). Wait before posting again." >&2
  fi
  exit 1
fi
