import os
import random
import time
import requests


WORLD_API = os.getenv("WORLD_API_BASE", "http://localhost:8000").rstrip("/")
AGENT_ID = os.getenv("AGENT_ID", "agent_1")
DISPLAY_NAME = os.getenv("DISPLAY_NAME", AGENT_ID)
SLEEP_SECONDS = float(os.getenv("AGENT_TICK_SECONDS", "3"))
POST_PROBABILITY = float(os.getenv("AGENT_POST_PROBABILITY", "0.08"))  # ~8% of ticks
POST_AUDIENCE = os.getenv("AGENT_POST_AUDIENCE", "agents")  # agents|humans|public
REPLY_PROBABILITY = float(os.getenv("AGENT_REPLY_PROBABILITY", "0.8"))  # reply most of the time
MAX_POSTS_TO_SCAN = int(os.getenv("AGENT_MAX_POSTS_TO_SCAN", "20"))


def upsert():
    requests.post(
        f"{WORLD_API}/agents/upsert",
        json={"agent_id": AGENT_ID, "display_name": DISPLAY_NAME},
        timeout=10,
    )


def move():
    dx, dy = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
    requests.post(
        f"{WORLD_API}/agents/{AGENT_ID}/move",
        json={"dx": dx, "dy": dy},
        timeout=10,
    )

def list_posts():
    r = requests.get(f"{WORLD_API}/board/posts?limit={MAX_POSTS_TO_SCAN}", timeout=10)
    r.raise_for_status()
    return r.json().get("posts", [])


def get_post(post_id: str):
    r = requests.get(f"{WORLD_API}/board/posts/{post_id}", timeout=10)
    r.raise_for_status()
    return r.json()


def maybe_post():
    if random.random() > POST_PROBABILITY:
        return
    title = f"Message from {DISPLAY_NAME}"
    prompts = [
        "What do you think our next milestone should be after movement + board?",
        "Can you propose a simple rule for how agents should behave in the town?",
        "If we add aiDollar next, what should agents spend it on first?",
        "What’s one interesting experiment we can run in this village world?",
        "How should we structure agent memory to stay coherent over time?",
    ]
    body = (
        f"Hi {POST_AUDIENCE} — quick question from {DISPLAY_NAME}:\n"
        f"- {random.choice(prompts)}\n\n"
        "Reply with a concrete suggestion and one reason."
    )
    requests.post(
        f"{WORLD_API}/board/posts",
        json={
            "title": title,
            "body": body,
            "audience": POST_AUDIENCE,
            "tags": ["agent_chat", "m2"],
            "author_type": "agent",
            "author_id": AGENT_ID,
        },
        timeout=10,
    )


def maybe_reply():
    if random.random() > REPLY_PROBABILITY:
        return

    posts = list_posts()
    # Find the most recent post addressed to agents (or public) that isn't ours.
    candidates = []
    for p in posts:
        if p.get("status") != "open":
            continue
        if p.get("author_type") != "agent":
            continue
        if p.get("author_id") == AGENT_ID:
            continue
        audience = (p.get("audience") or "").lower()
        if audience not in ("agents", "public"):
            continue
        candidates.append(p)

    if not candidates:
        return

    # Newest first
    candidates.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    target = candidates[0]
    post_id = target.get("post_id")
    if not post_id:
        return

    data = get_post(post_id)
    replies = data.get("replies", [])
    # If we've already replied, do nothing.
    for r in replies:
        if r.get("author_type") == "agent" and r.get("author_id") == AGENT_ID:
            return

    other = target.get("author_id", "other_agent")
    question = (target.get("body") or "").strip()

    # Deterministic-ish, but coherent: acknowledge + propose + ask follow-up.
    suggestions = [
        "Let’s add a simple aiDollar ledger next (append-only) and tie it to rate limits/model access. Reason: incentives become measurable immediately.",
        "We should add agent memory (short-term + episodic) before economy. Reason: without memory, incentives won’t shape long-term behavior.",
        "Add a ‘zones’ concept (cafe/market/board effects) next. Reason: it gives the world semantics beyond coordinates.",
        "Start logging every action/tool call to an audit trail next. Reason: you’ll need it for safety and later training/analysis.",
    ]
    reply_body = (
        f"Hey {other} — I read your post.\n\n"
        f"My take: {random.choice(suggestions)}\n\n"
        f"Follow-up: should we keep this as public board chatter or add direct agent DMs?\n"
    )

    requests.post(
        f"{WORLD_API}/board/posts/{post_id}/replies",
        json={"body": reply_body, "author_type": "agent", "author_id": AGENT_ID},
        timeout=10,
    )


def main():
    print(f"[{AGENT_ID}] starting; WORLD_API={WORLD_API}")
    while True:
        try:
            upsert()
            move()
            maybe_post()
            maybe_reply()
        except Exception as e:
            print(f"[{AGENT_ID}] error: {e}")
        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()

