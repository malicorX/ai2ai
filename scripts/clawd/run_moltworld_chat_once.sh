#!/usr/bin/env bash
# Run one MoltWorld chat cron job on this host. Usage: CLAW=clawdbot bash run_moltworld_chat_once.sh
# (or CLAW=openclaw). Called by run_moltworld_chat_now.ps1 after scp.
set -e
source ~/.nvm/nvm.sh 2>/dev/null || true
source ~/.bashrc 2>/dev/null || true
CLAW="${CLAW:-openclaw}"
id=$("$CLAW" cron list 2>/dev/null | awk '/MoltWorld chat turn/{print $1; exit}' || true)
if [[ -z "$id" ]]; then
  echo '{"ok":false,"error":"No MoltWorld cron job found"}'
  exit 1
fi
# Isolated runs can take 60-90s (LLM + tools). OpenClaw accepts --timeout; Clawdbot may ignore.
if [[ "$CLAW" = "openclaw" ]]; then
  "$CLAW" cron run "$id" --force --timeout 120000
else
  "$CLAW" cron run "$id" --force
fi
