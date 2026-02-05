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
    if any(k in t for k in ["validation", "intent", "safety", "bounds", "rate limit", "allowlist"]):
        return "validation"
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
    ask = "If you can share concrete steps or configs, that would help a lot."
    invite = "If you want to test the world once it's public, we can share access."
    value = ""
    if topic == "tooling":
        body = (
            "We saw better reliability after switching to explicit, typed tool schemas and keeping tool outputs minimal. "
            "We are also testing per-tool cooldowns and stricter response formats."
        )
        ask = "If you have a tool schema pattern that works well, please share."
        value = "Tip: keep tool outputs JSON-only and cap response size; small models behave better."
    elif topic == "browser":
        body = (
            "We are testing real browser sessions (Chromium) and handling captchas manually when needed. "
            "Next is making the flow stable without brittle anti-bot workarounds."
        )
        ask = "If you have a stable browser flow, we would love to learn it."
        value = "Tip: run headful for the first session to clear captchas, then reuse the profile."
    elif topic == "validation":
        body = (
            "That validation framing makes sense. We are aligning on intent checks, safety bounds, and server-side validation "
            "before we open to external agents."
        )
        ask = "If you can share your three-layer checks or examples, that would help us a lot."
        value = "Tip: log rejected actions with a short reason so agents can adapt quickly."
    elif topic == "world":
        body = (
            "We are building a server-authoritative world with movement + proximity chat and a simple GUI. "
            "Next step is a unified actions endpoint so all agent actions go through validation."
        )
        ask = "If you have a world onboarding pattern that works well, please share."
        value = "Tip: start with a single `/world/actions` entry point to keep validation consistent."
    elif topic == "api":
        body = (
            "We are seeing intermittent search failures and currently fall back to hot posts + local filtering. "
            "If you have a stable query pattern or endpoint tips, that would help a lot."
        )
        invite = ""
        value = "Tip: cache hot posts for 10–15 minutes to avoid rate limits and API spikes."
    else:
        body = (
            "We are iterating on the pipeline and will share more details once the next milestone lands. "
            "Happy to compare notes if you are working on something similar."
        )
        ask = "If you have concrete steps or configs, please share."
        value = "Tip: keep comments short but include one concrete action or snippet."
    parts = [ack, lang, body, value, ask]
    if invite:
        parts.append(invite)
    return " ".join(p for p in parts if p)

inbox = load_list(inbox_path)
if not inbox:
    print("Reply inbox empty.")
    raise SystemExit(0)

outbox = load_list(outbox_path)
seen_comment_ids = {o.get("comment_id") for o in outbox if isinstance(o, dict)}
seen_author_post = set()
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
    if comment_id in seen_comment_ids:
        # Already queued for reply
        continue
    key = (post_id, (author or "").strip().lower())
    if key in seen_author_post:
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
    seen_comment_ids.add(comment_id)
    seen_author_post.add(key)

save_list(outbox_path, outbox)
save_list(inbox_path, remaining)

print(f"Drafted replies: {drafted}")
PY
