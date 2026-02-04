#!/bin/bash
# Draft meaningful replies from inbox and enqueue to outbox.
# Usage: ./moltbook_reply_draft_on_sparky.sh
# Env:
#   MOLTBOOK_REPLY_INBOX="$HOME/.config/moltbook/reply_inbox.json"
#   MOLTBOOK_REPLY_OUTBOX="$HOME/.config/moltbook/reply_outbox.json"
#   MOLTBOOK_REPLY_DRAFT_MAX=5
set -e

INBOX_FILE="${MOLTBOOK_REPLY_INBOX:-$HOME/.config/moltbook/reply_inbox.json}"
OUTBOX_FILE="${MOLTBOOK_REPLY_OUTBOX:-$HOME/.config/moltbook/reply_outbox.json}"
MAX_DRAFTS="${MOLTBOOK_REPLY_DRAFT_MAX:-5}"

export INBOX_FILE OUTBOX_FILE MAX_DRAFTS
python3 - <<'PY'
import json, os, re, time

inbox_path = os.environ["INBOX_FILE"]
outbox_path = os.environ["OUTBOX_FILE"]
max_drafts = int(os.environ.get("MAX_DRAFTS", "5"))

def load_list(path):
    try:
        data = json.load(open(path))
        return data if isinstance(data, list) else []
    except Exception:
        return []

def save_list(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def classify(text):
    t = text.lower()
    if any(k in t for k in ["tool", "tools", "tool-calling", "schema", "ollama"]):
        return "tooling"
    if any(k in t for k in ["browser", "captcha", "chromium", "firefox", "playwright"]):
        return "browser"
    if any(k in t for k in ["world", "moltworld", "agents", "map", "movement", "chat"]):
        return "world"
    if any(k in t for k in ["search", "api", "endpoint", "500", "rate limit"]):
        return "api"
    return "general"

def build_reply(author, snippet):
    topic = classify(snippet)
    ack = f"Thanks {author} for the comment." if author else "Thanks for the comment."
    lang = "Replying in English for consistency."
    ask = "If you can share concrete steps or configs, we would love to learn from it."
    if topic == "tooling":
        body = (
            "We saw better reliability after switching to explicit, typed tool schemas and keeping tool outputs minimal. "
            "We are also testing per-tool cooldowns and stricter response formats."
        )
    elif topic == "browser":
        body = (
            "We are testing real browser sessions (Chromium) and handling captchas manually when needed. "
            "Next is making the flow stable without brittle anti-bot workarounds."
        )
    elif topic == "world":
        body = (
            "We are building a server-authoritative world with movement + proximity chat and a simple GUI. "
            "Next step is a unified actions endpoint so all agent actions go through validation."
        )
    elif topic == "api":
        body = (
            "We are seeing intermittent search failures and currently fall back to hot posts + local filtering. "
            "If you have a stable query pattern or endpoint tips, that would help a lot."
        )
    else:
        body = (
            "We are iterating on the pipeline and will share more details once the next milestone lands. "
            "Happy to compare notes if you are working on something similar."
        )
    return f"{ack} {lang} {body} {ask}"

inbox = load_list(inbox_path)
if not inbox:
    print("Reply inbox empty.")
    raise SystemExit(0)

outbox = load_list(outbox_path)
drafted = 0
remaining = []

for item in inbox:
    if drafted >= max_drafts:
        remaining.append(item)
        continue
    post_id = item.get("post_id")
    comment_id = item.get("comment_id")
    author = item.get("author", "")
    snippet = item.get("snippet", "")
    if not post_id or not comment_id:
        remaining.append(item)
        continue
    reply = build_reply(author or "there", snippet or "")
    outbox.append({
        "post_id": post_id,
        "comment_id": comment_id,
        "author": author,
        "snippet": snippet,
        "reply": reply,
        "drafted_at": int(time.time()),
    })
    drafted += 1

save_list(outbox_path, outbox)
save_list(inbox_path, remaining)

print(f"Drafted replies: {drafted}")
PY
