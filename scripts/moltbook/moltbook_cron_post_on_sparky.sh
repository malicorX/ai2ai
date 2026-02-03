#!/bin/bash
# Cron-friendly: post one heartbeat to Moltbook (if 30+ min since last post).
# Usage: run by hand to test, or add to crontab (e.g. every 30 min or every hour).
#   ./moltbook_cron_post_on_sparky.sh
#   crontab: 0 * * * * /home/malicor/ai2ai/scripts/moltbook/moltbook_cron_post_on_sparky.sh
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
TITLE="MalicorSparky2 heartbeat"
CONTENT="Check-in from sparky2. $(date -u +%Y-%m-%dT%H:%MZ)."
exec ./moltbook_post_on_sparky.sh "$TITLE" "$CONTENT" general
