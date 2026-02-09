#!/bin/bash
# Post once to Moltbook. Enforces min interval between posts (default 2h; set MOLTBOOK_MIN_INTERVAL to override).
# Usage: ./moltbook_post_on_sparky.sh "Title" "Content" [submolt]
#   submolt defaults to "general". Example: ./moltbook_post_on_sparky.sh "Hello" "First post from MalicorSparky2."
set -e
CREDS="$HOME/.config/moltbook/credentials.json"
LAST_POST="$HOME/.config/moltbook/last_post_ts"
POST_LOG="$HOME/.config/moltbook/post_log.json"
MIN_INTERVAL="${MOLTBOOK_MIN_INTERVAL:-7200}"   # default 2 hours (best behavior: quality over quantity)

if [ -z "$1" ] || [ -z "$2" ]; then
  # Allow base64-encoded env inputs for safe remote posting
  if [ -n "$MB_TITLE_B64" ] && [ -n "$MB_CONTENT_B64" ]; then
    TITLE="$(printf '%s' "$MB_TITLE_B64" | base64 -d)"
    CONTENT="$(printf '%s' "$MB_CONTENT_B64" | base64 -d)"
    SUBMOLT="${MB_SUBMOLT:-general}"
  else
    echo "Usage: $0 \"Title\" \"Content\" [submolt]" >&2
    echo "  submolt defaults to general." >&2
    echo "  Or set MB_TITLE_B64 and MB_CONTENT_B64 env vars." >&2
    exit 1
  fi
else
  TITLE="$1"
  CONTENT="$2"
  SUBMOLT="${3:-general}"
fi

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

# Rate limit: 1 post per MIN_INTERVAL (default 2h)
mkdir -p "$(dirname "$LAST_POST")"
now=$(date +%s)
if [ -f "$LAST_POST" ]; then
  last=$(cat "$LAST_POST")
  elapsed=$((now - last))
  if [ "$elapsed" -lt "$MIN_INTERVAL" ]; then
    remaining=$((MIN_INTERVAL - elapsed))
    echo "Rate limit: wait $((remaining / 60)) more minutes before posting again." >&2
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
  # If Moltbook requires verification, solve challenge and verify so the post gets published
  SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
  if command -v jq >/dev/null 2>&1; then
    v_code=$(echo "$BODY" | jq -r '.verification.code // empty')
    v_challenge=$(echo "$BODY" | jq -r '.verification.challenge // empty')
  else
    _btmp=$(mktemp); printf '%s' "$BODY" > "$_btmp"
    v_code=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); v=d.get('verification',{}); print(v.get('code',''))" "$_btmp" 2>/dev/null || true)
    v_challenge=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); v=d.get('verification',{}); print(v.get('challenge',''))" "$_btmp" 2>/dev/null || true)
    rm -f "$_btmp"
  fi
  if [ -n "$v_code" ] && [ -n "$v_challenge" ] && [ -f "$SCRIPT_DIR/moltbook_solve_challenge.py" ]; then
    answer=$(echo "$v_challenge" | python3 "$SCRIPT_DIR/moltbook_solve_challenge.py" 2>/dev/null || true)
    if [ -n "$answer" ]; then
      verify_tmp=$(mktemp)
      curl -s -o "$verify_tmp" -X POST "https://www.moltbook.com/api/v1/verify" \
        -H "Authorization: Bearer $api_key" \
        -H "Content-Type: application/json" \
        -d "$(python3 -c "import json,sys; print(json.dumps({'verification_code': sys.argv[1], 'answer': sys.argv[2]}))" "$v_code" "$answer")"
      if grep -q '"success":\s*true' "$verify_tmp" 2>/dev/null; then
        echo "Verification succeeded; post is published."
      else
        echo "Verification failed or skipped; post may be pending. Response: $(cat "$verify_tmp")"
      fi
      rm -f "$verify_tmp"
    fi
  fi
  # Append to local post log for later reply tracking
  MB_BODY="$BODY" MB_TITLE="$TITLE" MB_SUBMOLT="$SUBMOLT" MB_POST_LOG="$POST_LOG" python3 - <<'PY'
import json, os, sys, time
body = os.environ.get("MB_BODY", "")
title = os.environ.get("MB_TITLE", "")
submolt = os.environ.get("MB_SUBMOLT", "")
log_path = os.environ.get("MB_POST_LOG", "")
def extract_id(data):
    if isinstance(data, dict):
        if "post" in data and isinstance(data["post"], dict) and data["post"].get("id"):
            return data["post"]["id"]
        if data.get("id"):
            return data.get("id")
    return ""
try:
    data = json.loads(body)
except Exception:
    data = {}
post_id = extract_id(data)
entry = {
    "id": post_id,
    "title": title,
    "submolt": submolt,
    "ts": int(time.time()),
}
try:
    q = json.load(open(log_path))
    if not isinstance(q, list):
        q = []
except Exception:
    q = []
q.append(entry)
q = q[-500:]
with open(log_path, "w") as f:
    json.dump(q, f, indent=2)
PY
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
