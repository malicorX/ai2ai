#!/usr/bin/env bash
# On sparky1: stop any gateway on 18789, start OpenClaw gateway.
# Usage: bash sparky1_kill_orphan_and_start_gateway.sh (run on sparky1)
set -e
systemctl --user stop clawdbot-gateway.service 2>/dev/null || true
systemctl --user stop openclaw-gateway.service 2>/dev/null || true
openclaw gateway stop 2>/dev/null || true
PID=$(ss -tlnp 2>/dev/null | grep 18789 | grep -oP 'pid=\K[0-9]+' | head -1)
if [ -n "$PID" ]; then
  kill "$PID" 2>/dev/null || true
  sleep 3
fi
for f in "$HOME/.nvm/nvm.sh" "$HOME/.bashrc"; do [[ -f "$f" ]] && source "$f" 2>/dev/null || true; done
# Source moltworld env so plugin gets token when gateway starts
[[ -f "$HOME/.moltworld.env" ]] && source "$HOME/.moltworld.env" 2>/dev/null || true
nohup openclaw gateway >> ~/.openclaw/gateway.log 2>&1 &
sleep 4
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18789/ 2>/dev/null || echo "0"
