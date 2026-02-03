#!/bin/bash
# Fetch Moltbook feed or run semantic search to learn what other agents (e.g. Clawdbots earning money) are doing.
# Usage: ./moltbook_learn_on_sparky.sh [search query]
#   No args: fetch global hot posts (what agents are posting now).
#   With args: semantic search (e.g. ./moltbook_learn_on_sparky.sh "agents earning money" or "Fiverr gigs").
# Reads ~/.config/moltbook/credentials.json. Requires a valid API key (complete claim or re-register if 401).
set -e
CREDS="$HOME/.config/moltbook/credentials.json"
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

BASE="https://www.moltbook.com/api/v1"
if [ -n "$*" ]; then
  QUERY=$(echo "$*" | sed 's/ /+/g')
  URL="$BASE/search?q=$QUERY&limit=15"
  echo "Search: $*"
else
  URL="$BASE/posts?sort=hot&limit=15"
  echo "Global hot posts"
fi
echo ""

TMP=$(mktemp)
HTTP=$(curl -s -w "%{http_code}" -o "$TMP" -H "Authorization: Bearer $api_key" "$URL")
BODY=$(cat "$TMP")
rm -f "$TMP"

if [ "$HTTP" = "401" ]; then
  echo "Invalid API key. Complete the claim flow or re-register (after rate limit) to get a valid key." >&2
  exit 1
fi
if [ "$HTTP" != "200" ]; then
  echo "HTTP $HTTP — $BODY" >&2
  if [ "$HTTP" = "500" ] && [ -n "$*" ]; then
    echo "Search may be temporarily down; falling back to hot posts filter." >&2
    URL="$BASE/posts?sort=hot&limit=15"
    TMP=$(mktemp)
    # Use public feed as fallback (no auth) to avoid auth-related failures.
    HTTP=$(curl -s -w "%{http_code}" -o "$TMP" "$URL")
    BODY=$(cat "$TMP")
    rm -f "$TMP"
    if [ "$HTTP" != "200" ]; then
      echo "Fallback failed: HTTP $HTTP — $BODY" >&2
      exit 1
    fi
    if command -v jq >/dev/null 2>&1; then
      query="$*"
      echo "$BODY" | jq -r --arg q "$query" '
        def lc: ascii_downcase;
        (.posts // .data // [.] | if type == "array" then . else [.] end)[] |
        select((.title // "" | lc | contains($q | lc)) or (.content // "" | lc | contains($q | lc))) |
        "---\n\(.title // "no title")\n\(.content // "")[0:200]\(if (.content | length) > 200 then "..." else "" end)\nby \(.author.name // .author // "?")"
      '
    else
      echo "$BODY"
    fi
    exit 0
  fi
  exit 1
fi

# Pretty-print: for posts list or search results, show title, author, snippet
if [ -n "$*" ]; then
  # Search response: .results[] with .title, .content, .author.name, .type, .similarity
  if command -v jq >/dev/null 2>&1; then
    echo "$BODY" | jq -r '
      if .results then
        .results[] | "---\n\(.type): \(.title // .content[0:60])...\nby \(.author.name // "?")\(if .similarity then " (similarity: \(.similarity))" else "" end)\n"
      else
        "No results or unexpected format: \(. | tostring)[0:200]"
      end
    '
  else
    echo "$BODY"
  fi
else
  # Posts response: .posts[] or .data[] with .title, .content, .author
  if command -v jq >/dev/null 2>&1; then
    echo "$BODY" | jq -r '
      (.posts // .data // [.] | if type == "array" then . else [.] end)[] |
      "---\n\(.title // "no title")\n\(.content // "")[0:200]\(if (.content | length) > 200 then "..." else "" end)\nby \(.author.name // .author // "?")"
    ' 2>/dev/null || echo "$BODY"
  else
    echo "$BODY"
  fi
fi
