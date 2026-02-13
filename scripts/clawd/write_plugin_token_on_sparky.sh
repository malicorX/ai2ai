#!/usr/bin/env bash
# Write WORLD_AGENT_TOKEN from ~/.moltworld.env to ~/.openclaw/extensions/openclaw-moltworld/.token
# so the MoltWorld plugin can read it when the gateway doesn't pass config/env.
# Usage: bash write_plugin_token_on_sparky.sh   (run on sparky2, or: ssh sparky2 'bash -s' < write_plugin_token_on_sparky.sh)
set -e
ENV_FILE="${HOME}/.moltworld.env"
TOKEN_FILE="${HOME}/.openclaw/extensions/openclaw-moltworld/.token"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found" >&2
  exit 1
fi
source "$ENV_FILE"
if [[ -z "${WORLD_AGENT_TOKEN:-}" ]]; then
  echo "ERROR: WORLD_AGENT_TOKEN not set in $ENV_FILE" >&2
  exit 1
fi
mkdir -p "$(dirname "$TOKEN_FILE")"
echo -n "$WORLD_AGENT_TOKEN" > "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE"
echo "OK: token written to $TOKEN_FILE"
