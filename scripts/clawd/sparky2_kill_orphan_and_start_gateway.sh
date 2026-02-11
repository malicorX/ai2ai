#!/usr/bin/env bash
# Stop systemd gateway service, kill any process holding port 18789, start one openclaw gateway.
set -e
systemctl --user stop clawdbot-gateway.service 2>/dev/null || true
PID=$(ss -tlnp 2>/dev/null | grep 18789 | grep -oP 'pid=\K[0-9]+' | head -1)
if [ -n "$PID" ]; then
  kill "$PID" 2>/dev/null || true
  sleep 3
fi
source ~/.nvm/nvm.sh 2>/dev/null || true
source ~/.bashrc 2>/dev/null || true
nohup openclaw gateway >> ~/.openclaw/gateway.log 2>&1 &
sleep 4
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18789/ 2>/dev/null || echo "0"
