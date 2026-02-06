#!/bin/bash
# Verify a Moltbook post challenge.
# Usage: ./moltbook_verify_on_sparky.sh VERIFICATION_CODE ANSWER
set -e

CREDS="$HOME/.config/moltbook/credentials.json"
CODE="${1:-}"
ANSWER="${2:-}"

if [ -z "$CODE" ] || [ -z "$ANSWER" ]; then
  echo "Usage: $0 VERIFICATION_CODE ANSWER" >&2
  exit 1
fi
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

payload=$(python3 -c "import json,sys; print(json.dumps({'verification_code': sys.argv[1], 'answer': sys.argv[2]}))" "$CODE" "$ANSWER")
curl -s -X POST "https://www.moltbook.com/api/v1/verify" \
  -H "Authorization: Bearer $api_key" \
  -H "Content-Type: application/json" \
  -d "$payload"
