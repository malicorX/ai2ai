#!/bin/bash
# Create ~/.config/moltbook/credentials.json on sparky. Run via run_moltbook_save_credentials.ps1.
# Requires MOLTBOOK_API_KEY and MOLTBOOK_AGENT_NAME in environment.

set -e
if [ -z "$MOLTBOOK_API_KEY" ] || [ -z "$MOLTBOOK_AGENT_NAME" ]; then
  echo "ERROR: MOLTBOOK_API_KEY and MOLTBOOK_AGENT_NAME must be set" >&2
  exit 1
fi
mkdir -p ~/.config/moltbook
printf '%s\n' "{\"api_key\": \"$MOLTBOOK_API_KEY\", \"agent_name\": \"$MOLTBOOK_AGENT_NAME\"}" > ~/.config/moltbook/credentials.json
echo "Saved ~/.config/moltbook/credentials.json"
