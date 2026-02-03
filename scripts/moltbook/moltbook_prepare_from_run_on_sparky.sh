#!/bin/bash
# Optional: if there is a test run log from today, create one meaningful queue entry from it.
# Run this before moltbook_maybe_post_on_sparky.sh in cron so that when a run happened today,
# we have something to post (real data, not generated filler).
#
# Usage: ./moltbook_prepare_from_run_on_sparky.sh [scripts_dir]
#   scripts_dir defaults to same dir as this script (for logs run_all_tests.*.log).
# Cron:  0 * * * * /path/moltbook_prepare_from_run_on_sparky.sh; /path/moltbook_maybe_post_on_sparky.sh
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGS_DIR="${1:-$SCRIPT_DIR}"
CONFIG_DIR="${HOME}/.config/moltbook"
MARKER_FILE="$CONFIG_DIR/last_queued_run"
today=$(date -u +%Y-%m-%d)

# Latest run_all_tests.YYYYMMDD-*.log from today (by filename date)
today_compact="${today//-/}"
pattern="run_all_tests.${today_compact}*.log"
latest=""
if [ -d "$LOGS_DIR" ]; then
  latest=$(ls -t "$LOGS_DIR"/$pattern 2>/dev/null | head -1)
fi
[ -z "$latest" ] && exit 0

# Already queued this run?
if [ -f "$MARKER_FILE" ]; then
  read -r queued_path < "$MARKER_FILE" || true
  if [ "$queued_path" = "$latest" ]; then
    exit 0
  fi
fi

# One-line summary from log
if grep -q "All tests passed" "$latest" 2>/dev/null; then
  summary="all passed"
elif grep -qi "failed\|FAIL" "$latest" 2>/dev/null; then
  summary="see log for details"
else
  summary="completed"
fi
title="Test run $today: $summary"
content="Latest run log: $(basename "$latest"). Summary: $summary."

mkdir -p "$CONFIG_DIR"
"$SCRIPT_DIR/moltbook_queue_on_sparky.sh" "$title" "$content" "general"
echo "$latest" > "$MARKER_FILE"
echo "Queued from run: $latest"
exit 0
