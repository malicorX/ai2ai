#!/usr/bin/env bash
# Run on sparky1 or sparky2: stop Clawdbot, use OpenClaw only. Optional: archive ~/.clawdbot.
# Usage: bash migrate_sparky_to_openclaw_only.sh [--archive-clawdbot]
# After this, only ~/.openclaw and "openclaw gateway" are used.
set -e
ARCHIVE=0
[[ "${1:-}" = "--archive-clawdbot" ]] && ARCHIVE=1

echo "Stopping Clawdbot gateway and any service on 18789..."
clawdbot gateway stop 2>/dev/null || true
openclaw gateway stop 2>/dev/null || true
systemctl --user stop clawdbot-gateway.service 2>/dev/null || true
systemctl --user stop openclaw-gateway.service 2>/dev/null || true
PID=$(ss -tlnp 2>/dev/null | grep 18789 | grep -oP 'pid=\K[0-9]+' | head -1)
if [[ -n "$PID" ]]; then
  kill "$PID" 2>/dev/null || true
  sleep 3
fi

if [[ ! -f "$HOME/.openclaw/openclaw.json" ]]; then
  echo "ERROR: ~/.openclaw/openclaw.json not found. Run bootstrap_openclaw_on_sparky1.sh or run_setup_openclaw_on_sparky1.ps1 first." >&2
  exit 1
fi

if [[ "$ARCHIVE" -eq 1 && -d "$HOME/.clawdbot" ]]; then
  BACKUP="$HOME/.clawdbot.archived.$(date +%Y%m%d%H%M%S)"
  mv "$HOME/.clawdbot" "$BACKUP"
  echo "Archived ~/.clawdbot to $BACKUP"
fi

echo "Starting OpenClaw gateway..."
for f in "$HOME/.nvm/nvm.sh" "$HOME/.bashrc"; do [[ -f "$f" ]] && source "$f" 2>/dev/null || true; done
[[ -f "$HOME/.moltworld.env" ]] && source "$HOME/.moltworld.env" 2>/dev/null || true
nohup openclaw gateway >> ~/.openclaw/gateway.log 2>&1 &
sleep 4
code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 http://127.0.0.1:18789/ 2>/dev/null) || echo "0"
echo "Gateway check: $code"
echo "Done. This host now uses OpenClaw only."
