#!/bin/bash
# Prune duplicate replies from outbox (by comment_id).
# Usage: ./moltbook_reply_outbox_prune_on_sparky.sh
# Env:
#   MOLTBOOK_REPLY_OUTBOX="$HOME/.config/moltbook/reply_outbox.json"
#   MOLTBOOK_REPLY_STATE="$HOME/.config/moltbook/reply_state.json"
set -e

OUTBOX_FILE="${MOLTBOOK_REPLY_OUTBOX:-$HOME/.config/moltbook/reply_outbox.json}"
STATE_FILE="${MOLTBOOK_REPLY_STATE:-$HOME/.config/moltbook/reply_state.json}"

export OUTBOX_FILE STATE_FILE
python3 - <<'PY'
import json, os
outbox_path = os.environ["OUTBOX_FILE"]
state_path = os.environ["STATE_FILE"]

def load(path):
    try:
        data = json.load(open(path))
        return data if isinstance(data, list) else []
    except Exception:
        return []

def load_state(path):
    try:
        return json.load(open(path))
    except Exception:
        return {}

outbox = load(outbox_path)
state = load_state(state_path)
replied = set(state.get("replied_comment_ids", []))

seen = set()
pruned = []
for item in outbox:
    cid = item.get("comment_id")
    if not cid:
        continue
    if cid in replied:
        continue
    if cid in seen:
        continue
    seen.add(cid)
    pruned.append(item)

with open(outbox_path, "w") as f:
    json.dump(pruned, f, indent=2)

print(f"Pruned outbox: {len(outbox)} -> {len(pruned)}")
PY
