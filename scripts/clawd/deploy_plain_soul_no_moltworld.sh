#!/usr/bin/env bash
# Overwrite SOUL.md on this host with a plain one (no world_state / MoltWorld). Run on sparky.
set -e
PLAIN_SOUL="$1"
if [[ ! -f "$PLAIN_SOUL" ]]; then
  echo "Usage: $0 <path-to-soul_plain_no_moltworld.md>" >&2
  exit 1
fi
for D in ~/.openclaw ~/.clawdbot /home/malicor/clawd; do
  if [[ -d "$D" ]]; then
    cp "$PLAIN_SOUL" "$D/SOUL.md"
    echo "Deployed plain SOUL to $D/SOUL.md"
  fi
done
echo "Done. Restart gateway and start a new chat."
