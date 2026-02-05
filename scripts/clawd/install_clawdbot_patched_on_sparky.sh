#!/usr/bin/env bash
# Install patched Clawdbot using nvm Node path under sudo.
# Usage (on sparky2): bash /home/malicor/ai_ai2ai/scripts/clawd/install_clawdbot_patched_on_sparky.sh
set -euo pipefail

BUILD_DIR="${CLAWDBOT_BUILD_DIR:-$HOME/clawdbot-jokelord-build}"
CLAWDBOT_DIR="${BUILD_DIR}/clawdbot"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="${HOME}/.openclaw/openclaw.json"

if [[ ! -d "${CLAWDBOT_DIR}" ]]; then
  echo "ERROR: ${CLAWDBOT_DIR} not found. Run clawd_apply_jokelord_on_sparky.sh first." >&2
  exit 1
fi

NODE_BIN_DIR="$(ls -d "${HOME}"/.nvm/versions/node/*/bin 2>/dev/null | sort -V | tail -n 1 || true)"
if [[ -z "${NODE_BIN_DIR}" ]]; then
  echo "ERROR: nvm node bin not found under ~/.nvm/versions/node." >&2
  exit 1
fi

export PATH="${NODE_BIN_DIR}:${PATH}"

echo "Using NODE_BIN_DIR=${NODE_BIN_DIR}"
echo "Installing patched Clawdbot globally..."
cd "${CLAWDBOT_DIR}"
sudo env "PATH=${PATH}" "${NODE_BIN_DIR}/npm" install -g .

if [[ -f "${SCRIPT_DIR}/clawd_add_supported_parameters.py" ]]; then
  echo "Ensuring compat.supportedParameters in ${CONFIG_PATH}..."
  python3 "${SCRIPT_DIR}/clawd_add_supported_parameters.py"
fi

echo "Restarting gateway..."
clawdbot gateway stop 2>/dev/null || true
sleep 2
nohup clawdbot gateway >> "${HOME}/.openclaw/gateway.log" 2>&1 &

echo "Done. Test in Control UI or TUI."
