#!/bin/bash
# Install/update cron jobs to collect replies and post outbox replies.
# Usage: ./moltbook_cron_replies_on_sparky.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHECK_SCRIPT="$SCRIPT_DIR/moltbook_check_replies_on_sparky.sh"
POST_SCRIPT="$SCRIPT_DIR/moltbook_reply_queue_process_on_sparky.sh"

if [ ! -x "$CHECK_SCRIPT" ]; then
  echo "Missing or non-executable: $CHECK_SCRIPT" >&2
  exit 1
fi
if [ ! -x "$POST_SCRIPT" ]; then
  echo "Missing or non-executable: $POST_SCRIPT" >&2
  exit 1
fi

tmp=$(mktemp)
crontab -l 2>/dev/null > "$tmp" || true

cleaned=$(mktemp)
awk '
  BEGIN {skip=0}
  /# moltbook-replies-start/ {skip=1; next}
  /# moltbook-replies-end/ {skip=0; next}
  skip==0 {print}
' "$tmp" > "$cleaned"

cat >> "$cleaned" <<'CRON'
# moltbook-replies-start
*/10 * * * * MOLTBOOK_QUEUE_REPLIES=1 /home/malicor/ai2ai/scripts/moltbook/moltbook_check_replies_on_sparky.sh >> /tmp/moltbook_replies.log 2>&1
*/5 * * * * /home/malicor/ai2ai/scripts/moltbook/moltbook_reply_queue_process_on_sparky.sh >> /tmp/moltbook_replies.log 2>&1
# moltbook-replies-end
CRON

crontab "$cleaned"
rm -f "$tmp" "$cleaned"
echo "Installed moltbook replies cron."
