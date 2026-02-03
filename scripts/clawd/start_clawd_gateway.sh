#!/usr/bin/env bash
# Start Clawd gateway in background with OLLAMA_API_KEY so it can use local Ollama (no cost).
# Run on sparky1 or sparky2: bash scripts/clawd/start_clawd_gateway.sh
set -e
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[[ -s "$NVM_DIR/nvm.sh" ]] && . "$NVM_DIR/nvm.sh"
nvm use 22 2>/dev/null || true
export PATH="$HOME/.nvm/versions/node/v22.22.0/bin:$PATH"
export OLLAMA_API_KEY="${OLLAMA_API_KEY:-ollama-local}"
CLAWDBOT=$(command -v clawdbot || echo "$HOME/.nvm/versions/node/v22.22.0/bin/clawdbot")

# Stop systemd user service first so port is freed (otherwise "gateway already running")
if systemctl --user is-active clawdbot-gateway.service &>/dev/null; then
  systemctl --user stop clawdbot-gateway.service
  echo "Stopped systemd service: clawdbot-gateway.service"
fi
"$CLAWDBOT" gateway stop 2>/dev/null || true
sleep 2
# If port still in use (e.g. leftover nohup process), free it so this start succeeds
pids=$(command -v lsof &>/dev/null && lsof -t -i :18789 2>/dev/null)
if [[ -n "$pids" ]]; then
  echo "Port 18789 in use; stopping process(es): $pids"
  kill $pids 2>/dev/null || true
  sleep 2
fi
nohup "$CLAWDBOT" gateway >> ~/.clawdbot/gateway.log 2>&1 &
echo "Gateway started with OLLAMA_API_KEY=$OLLAMA_API_KEY (local Ollama). To chat: source ~/.bashrc; clawdbot tui"
