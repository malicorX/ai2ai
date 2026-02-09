#!/usr/bin/env bash
# Remove existing MoltWorld chat cron job. Usage: CLAW=clawdbot bash run_moltworld_cron_remove.sh
set -e
source ~/.nvm/nvm.sh 2>/dev/null || true
source ~/.bashrc 2>/dev/null || true
CLAW="${CLAW:-openclaw}"
id=$("$CLAW" cron list 2>/dev/null | awk '/MoltWorld chat turn/{print $1; exit}' || true)
if [[ -n "$id" ]]; then
  "$CLAW" cron remove "$id"
  echo "Removed MoltWorld cron job $id"
else
  echo "No MoltWorld cron job found"
fi
