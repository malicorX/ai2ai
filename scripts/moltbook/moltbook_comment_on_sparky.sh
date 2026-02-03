#!/bin/bash
# Post a comment on a Moltbook post.
# Usage: ./moltbook_comment_on_sparky.sh POST_ID "Content"
set -e

CREDS="$HOME/.config/moltbook/credentials.json"
if [ -z "$1" ] || [ -z "$2" ]; then
  echo "Usage: $0 POST_ID \"Content\"" >&2
  exit 1
fi
POST_ID="$1"
CONTENT="$2"

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
export POST_ID="$POST_ID"
export CONTENT="$CONTENT"

python3 - <<'PY'
import json, os, subprocess, sys
post_id = os.environ["POST_ID"]
content = os.environ["CONTENT"]
payload = json.dumps({"content": content})
api_key = os.environ["API_KEY"]
res = subprocess.run([
    "curl","-s","-w","\\n%{http_code}",
    "-H", f"Authorization: Bearer {api_key}",
    "-H","Content-Type: application/json",
    "-d", payload,
    f"https://www.moltbook.com/api/v1/posts/{post_id}/comments"
], capture_output=True, text=True)
print(res.stdout)
PY
