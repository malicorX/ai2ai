#!/bin/bash
# Check if Moltbook agent is registered and claim status. Run on sparky2.
# Retries every 10 seconds until the API returns 200 (success). Ctrl+C to stop.
# Usage: ./moltbook_check_status_on_sparky.sh
# Reads ~/.config/moltbook/credentials.json for api_key, then calls Moltbook API.
CREDS="$HOME/.config/moltbook/credentials.json"
if [ ! -f "$CREDS" ]; then
  echo "No credentials found at $CREDS"
  echo "Run ./moltbook_register_on_sparky.sh first (and wait for Moltbook to accept)."
  exit 1
fi

if command -v jq >/dev/null 2>&1; then
  api_key=$(jq -r '.api_key // empty' "$CREDS" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  agent_name=$(jq -r '.agent_name // empty' "$CREDS")
else
  api_key=$(python3 -c "import json; d=json.load(open('$CREDS')); print((d.get('api_key') or '').strip())")
  agent_name=$(python3 -c "import json; d=json.load(open('$CREDS')); print(d.get('agent_name',''))")
fi

if [ -z "$api_key" ]; then
  echo "No api_key in $CREDS"
  exit 1
fi
if [[ "$api_key" != moltbook_* ]]; then
  echo "Warning: api_key in $CREDS does not start with 'moltbook_' — check file contents." >&2
fi

echo "Agent name in credentials: ${agent_name:-<none>}"
echo "Checking Moltbook status (retrying every 10s until success)..."
echo ""

while true; do
  TMP=$(mktemp)
  HTTP=$(curl -s -w "%{http_code}" -o "$TMP" -H "Authorization: Bearer $api_key" "https://www.moltbook.com/api/v1/agents/status")
  BODY=$(cat "$TMP")
  rm -f "$TMP"

  if [ "$HTTP" = "200" ]; then
    break
  fi

  echo "HTTP $HTTP — $BODY"
  echo "Retrying in 10 seconds... (Ctrl+C to stop)"
  sleep 10
done

if command -v jq >/dev/null 2>&1; then
  status=$(echo "$BODY" | jq -r '.status // empty')
else
  status=$(python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" <<< "$BODY")
fi

echo "Status: $status"
if [ "$status" = "pending_claim" ]; then
  echo "Human must open the claim URL (from when you registered) and tweet to verify."
elif [ "$status" = "claimed" ]; then
  echo "Agent is claimed and active."
fi

ME=$(curl -s -H "Authorization: Bearer $api_key" "https://www.moltbook.com/api/v1/agents/me")
echo ""
echo "Profile (agents/me):"
if command -v jq >/dev/null 2>&1; then echo "$ME" | jq '.'; else echo "$ME"; fi
