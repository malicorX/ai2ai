#!/usr/bin/env bash
# Run one MoltWorld step with the Python bot (no gateway).
# Usage: AGENT_ID=Sparky1Agent bash run_moltworld_python_bot.sh
#        Or: source ~/.moltworld.env && AGENT_ID=Sparky1Agent bash run_moltworld_python_bot.sh
# Requires: WORLD_API_BASE, WORLD_AGENT_TOKEN, AGENT_ID; optional DISPLAY_NAME, LLM_BASE_URL, LLM_MODEL.
set -e
ENV_FILE="${HOME}/.moltworld.env"
# Source env file; strip CRLF to avoid "set: -" from Windows line endings
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source <(tr -d '\r' < "$ENV_FILE") 2>/dev/null || true
  set +a
fi
if [[ -z "$AGENT_ID" ]]; then
  echo "AGENT_ID not set. Set it or add to $ENV_FILE" >&2
  exit 1
fi
# Default DISPLAY_NAME from AGENT_ID
export DISPLAY_NAME="${DISPLAY_NAME:-$AGENT_ID}"
# LLM: point at local Ollama if not set
export LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:11434/v1}"
export LLM_MODEL="${LLM_MODEL:-qwen2.5-coder:32b}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"
export PYTHONPATH="${REPO_ROOT}/agents${PYTHONPATH:+:$PYTHONPATH}"
# Prefer venv if present (avoids externally-managed-environment on Debian/Ubuntu)
if [[ -x "${REPO_ROOT}/venv/bin/python3" ]]; then
  exec "${REPO_ROOT}/venv/bin/python3" -m agent_template.moltworld_bot
fi
exec python3 -m agent_template.moltworld_bot
