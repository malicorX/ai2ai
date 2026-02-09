#!/bin/bash
# Run ON the theebie server (e.g. ssh root@84.38.65.246) to issue MoltWorld tokens.
# Prereq: Backend must have ADMIN_TOKEN set (add to docker-compose env or .env, then restart backend).
# Usage: export ADMIN_TOKEN=your_secret; bash theebie_issue_tokens.sh
#   Or: ADMIN_TOKEN=xxx bash theebie_issue_tokens.sh
set -e
ADMIN_TOKEN="${ADMIN_TOKEN:?Set ADMIN_TOKEN}"
BASE="${BASE_URL:-http://127.0.0.1:8000}"

issue() {
  local agent_id="$1"
  local agent_name="${2:-$1}"
  echo "Issuing token for $agent_id..."
  out=$(curl -s -X POST "$BASE/admin/agent/issue_token" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"agent_id\":\"$agent_id\",\"agent_name\":\"$agent_name\"}")
  if echo "$out" | grep -q '"token"'; then
    token=$(echo "$out" | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))")
    echo "  $agent_id token: $token"
  else
    echo "  Failed: $out"
    return 1
  fi
}

issue "Sparky1Agent" "Sparky1Agent"
issue "MalicorSparky2" "MalicorSparky2"
echo "Done. Tokens are in /opt/ai_ai2ai/backend_data/agent_tokens.json (inside container: /app/data/agent_tokens.json)."
echo "From your machine run: .\scripts\get_moltworld_token_from_theebie.ps1 -AgentId MalicorSparky2 -WriteEnvAndPush"
