#!/usr/bin/env bash
# Create auth-profiles.json for Clawdbot main agent so "No API key found for provider ollama" is fixed.
# Run on sparky1 so narrator/hook lanes can call Ollama.
# Usage: bash fix_clawdbot_ollama_on_sparky.sh   (or: ssh sparky1 'bash -s' < fix_clawdbot_ollama_on_sparky.sh)
set -e

AGENT_DIR="${HOME}/.clawdbot/agents/main/agent"
AUTH_FILE="${AGENT_DIR}/auth-profiles.json"

mkdir -p "$AGENT_DIR"
python3 - "$AUTH_FILE" << 'PY'
import json, os, sys
path = sys.argv[1]
data = {"ollama": {"apiKey": "ollama-local"}}
with open(path, "w") as f:
    json.dump(data, f, indent=2)
os.chmod(path, 0o600)
print("AUTH_UPDATED", path, "ollama apiKey=ollama-local")
PY
echo "Clawdbot main agent auth set for Ollama. Restart gateway to apply."
