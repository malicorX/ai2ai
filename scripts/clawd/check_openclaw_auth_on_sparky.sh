#!/usr/bin/env bash
# Check OpenClaw agent auth (e.g. for the agent that serves /hooks/wake). Reports if auth-profiles.json
# exists and has ollama (local) or anthropic/openai so the model can run. We use Ollama locally; ollama is sufficient.
# Usage: bash check_openclaw_auth_on_sparky.sh   (run on sparky, or via ssh sparky2 'bash -s' < check_openclaw_auth_on_sparky.sh)
set -e

AGENT_DIR="${AGENT_DIR:-$HOME/.openclaw/agents/main/agent}"
AUTH_FILE="$AGENT_DIR/auth-profiles.json"

echo "Checking OpenClaw auth (agent dir: $AGENT_DIR)"
if [[ ! -d "$AGENT_DIR" ]]; then
  echo "  ERROR: Agent dir not found: $AGENT_DIR"
  echo "  Fix: Ensure OpenClaw is installed and the main (or wake-serving) agent exists."
  exit 1
fi

if [[ ! -f "$AUTH_FILE" ]]; then
  echo "  ERROR: auth-profiles.json not found: $AUTH_FILE"
  echo "  Fix: Run 'openclaw agents add main' (or your agent id) and add the Anthropic API key, or copy auth-profiles.json from a working agent into $AGENT_DIR"
  exit 1
fi

# Check for ollama (local), anthropic, or openai
HAS_OLLAMA=
HAS_ANTHROPIC=
HAS_OPENAI=
if grep -q '"ollama"' "$AUTH_FILE" 2>/dev/null; then
  HAS_OLLAMA=1
fi
if grep -q '"anthropic"' "$AUTH_FILE" 2>/dev/null; then
  if grep -q 'apiKey\|api_key\|ANTHROPIC' "$AUTH_FILE" 2>/dev/null; then
    HAS_ANTHROPIC=1
  fi
fi
if grep -q '"openai"' "$AUTH_FILE" 2>/dev/null; then
  if grep -q 'apiKey\|api_key\|OPENAI' "$AUTH_FILE" 2>/dev/null; then
    HAS_OPENAI=1
  fi
fi

if [[ -n "$HAS_OLLAMA" || -n "$HAS_ANTHROPIC" || -n "$HAS_OPENAI" ]]; then
  echo "  OK: auth-profiles.json exists and has provider key(s)."
  [[ -n "$HAS_OLLAMA" ]] && echo "    ollama: present (local)"
  [[ -n "$HAS_ANTHROPIC" ]] && echo "    anthropic: present"
  [[ -n "$HAS_OPENAI" ]] && echo "    openai: present"
  exit 0
fi

echo "  WARN: auth-profiles.json exists but no ollama/anthropic/openai detected."
echo "  Fix: For local Ollama run: .\scripts\clawd\run_fix_openclaw_ollama_on_sparky.ps1 -TargetHost sparky2"
echo "  Then restart the gateway: openclaw gateway stop; openclaw gateway start"
exit 1
