#!/bin/bash
# Register Moltbook agent FROM sparky2 (use when dev machine cannot reach Moltbook). Run on sparky2.
# Retries every 10 seconds until registration succeeds. Ctrl+C to stop.
# Usage: bash moltbook_register_on_sparky.sh [AgentName]
# Then: human must open the printed claim_url and tweet to verify.
NAME="${1:-MalicorSparky2}"
DESC="Clawd agent on sparky2; uses Ollama. Screens tasks, reports, and participates on Moltbook."
BODY="{\"name\": \"$NAME\", \"description\": \"$DESC\"}"

while true; do
  echo "Registering agent '$NAME' on Moltbook..."
  TMP=$(mktemp)
  STATUS=$(curl -s -w "%{http_code}" -o "$TMP" -X POST "https://www.moltbook.com/api/v1/agents/register" \
    -H "Content-Type: application/json" \
    -d "$BODY")
  RESP=$(cat "$TMP")
  rm -f "$TMP"

  if command -v jq >/dev/null 2>&1; then
    api_key=$(echo "$RESP" | jq -r '.agent.api_key // empty')
    claim_url=$(echo "$RESP" | jq -r '.agent.claim_url // empty')
    verification_code=$(echo "$RESP" | jq -r '.agent.verification_code // empty')
    err=$(echo "$RESP" | jq -r '.error // empty')
    hint=$(echo "$RESP" | jq -r '.hint // empty')
  else
    api_key=$(python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('agent',{}).get('api_key',''))" <<< "$RESP")
    claim_url=$(python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('agent',{}).get('claim_url',''))" <<< "$RESP")
    verification_code=$(python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('agent',{}).get('verification_code',''))" <<< "$RESP")
    err=$(python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error',''))" <<< "$RESP")
    hint=$(python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('hint',''))" <<< "$RESP")
  fi

  if [ -n "$api_key" ]; then
    break
  fi

  echo "Registration failed. HTTP $STATUS" >&2
  [ -n "$err" ] && echo "Error: $err" >&2
  [ -n "$hint" ] && echo "Hint: $hint" >&2
  echo "Retrying in 10 seconds... (Ctrl+C to stop)" >&2
  sleep 10
done
mkdir -p ~/.config/moltbook
if command -v jq >/dev/null 2>&1; then
  echo "{\"api_key\": \"$api_key\", \"agent_name\": \"$NAME\"}" > ~/.config/moltbook/credentials.json
else
  API_KEY="$api_key" python3 -c "import os,json; json.dump({'api_key':os.environ['API_KEY'],'agent_name':'$NAME'}, open(os.path.expanduser('~/.config/moltbook/credentials.json'),'w'))"
fi
echo ""
echo "Registered. Credentials saved to ~/.config/moltbook/credentials.json"
echo "Verification code (use in tweet if claim page asks): $verification_code"
echo "Claim URL (human must open and tweet to verify): $claim_url"
echo "Use the EXACT URL above — e.g. letter 'o' in Vqo, not digit '0'."
echo ""
