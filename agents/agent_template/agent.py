import os
import random
import time
import requests


WORLD_API = os.getenv("WORLD_API_BASE", "http://localhost:8000").rstrip("/")
AGENT_ID = os.getenv("AGENT_ID", "agent_1")
DISPLAY_NAME = os.getenv("DISPLAY_NAME", AGENT_ID)
PERSONALITY = os.getenv(
    "PERSONALITY",
    "Concise, pragmatic, and focused on concrete next steps.",
)
SLEEP_SECONDS = float(os.getenv("AGENT_TICK_SECONDS", "3"))
# Chat behavior (agents talk to each other via /chat, NOT the bulletin board)
CHAT_PROBABILITY = float(os.getenv("CHAT_PROBABILITY", "0.6"))
CHAT_MIN_SECONDS = float(os.getenv("CHAT_MIN_SECONDS", "6"))
MAX_CHAT_TO_SCAN = int(os.getenv("MAX_CHAT_TO_SCAN", "50"))
ADJACENT_CHAT_BOOST = float(os.getenv("ADJACENT_CHAT_BOOST", "3.0"))  # multiplies post probability when adjacent
RANDOM_MOVE_PROB = float(os.getenv("RANDOM_MOVE_PROB", "0.10"))

_last_replied_to_msg_id = None
_last_seen_other_msg_id = None
_last_sent_at = 0.0


def upsert():
    requests.post(
        f"{WORLD_API}/agents/upsert",
        json={"agent_id": AGENT_ID, "display_name": DISPLAY_NAME},
        timeout=10,
    )


def get_world():
    r = requests.get(f"{WORLD_API}/world", timeout=10)
    r.raise_for_status()
    return r.json()


def _sign(n: int) -> int:
    return 0 if n == 0 else (1 if n > 0 else -1)


def _step_towards(ax: int, ay: int, tx: int, ty: int):
    # Allow diagonal steps: move one tile closer in x and y in a single tick.
    return (_sign(tx - ax), _sign(ty - ay))


def _chebyshev(ax: int, ay: int, bx: int, by: int) -> int:
    return max(abs(ax - bx), abs(ay - by))


def move(world):
    # Strategy: approach the other agent; once adjacent, stop moving.
    my = None
    other = None
    for a in world.get("agents", []):
        if a.get("agent_id") == AGENT_ID:
            my = a
        else:
            other = a

    # fallback random walk if we can't see ourselves yet
    if not my:
        dx, dy = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
        requests.post(f"{WORLD_API}/agents/{AGENT_ID}/move", json={"dx": dx, "dy": dy}, timeout=10)
        return

    else:
        ax, ay = int(my.get("x", 0)), int(my.get("y", 0))

        if other:
            ox, oy = int(other.get("x", 0)), int(other.get("y", 0))
            # If adjacent (including same tile), STOP moving.
            if _chebyshev(ax, ay, ox, oy) <= 1:
                return
            if random.random() < RANDOM_MOVE_PROB:
                dx, dy = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
            else:
                dx, dy = _step_towards(ax, ay, ox, oy)
        else:
            # If we can't see the other agent, roam.
            dx, dy = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])

    requests.post(f"{WORLD_API}/agents/{AGENT_ID}/move", json={"dx": dx, "dy": dy}, timeout=10)

def _adjacent_to_other(world) -> bool:
    agents = world.get("agents", [])
    me = next((a for a in agents if a.get("agent_id") == AGENT_ID), None)
    other = next((a for a in agents if a.get("agent_id") != AGENT_ID), None)
    if not me or not other:
        return False
    ax, ay = int(me.get("x", 0)), int(me.get("y", 0))
    ox, oy = int(other.get("x", 0)), int(other.get("y", 0))
    return _chebyshev(ax, ay, ox, oy) <= 1


def chat_recent(limit: int = MAX_CHAT_TO_SCAN):
    r = requests.get(f"{WORLD_API}/chat/recent?limit={limit}", timeout=10)
    r.raise_for_status()
    return r.json().get("messages", [])


def chat_send(text: str):
    requests.post(
        f"{WORLD_API}/chat/send",
        json={
            "sender_type": "agent",
            "sender_id": AGENT_ID,
            "sender_name": DISPLAY_NAME,
            "text": text,
        },
        timeout=10,
    )


def _style(text: str) -> str:
    p = PERSONALITY.lower()
    if "sarcast" in p:
        return text + " (sure.)"
    if "formal" in p:
        return "Indeed. " + text
    if "curious" in p:
        return text + " What do you think?"
    return text


def _is_my_turn(msgs) -> bool:
    # Turn-taking: only speak if the last chat message is NOT ours.
    if not msgs:
        # deterministic: agent_1 starts conversations
        return AGENT_ID.endswith("1")
    last = msgs[-1]
    return last.get("sender_id") != AGENT_ID


def _generate_reply(other_text: str) -> str:
    t = other_text.lower()

    if "memory" in t:
        if "pragmatic" in PERSONALITY.lower() or "analytical" in PERSONALITY.lower():
            return "Memory next. Start with short-term (last 20 events) + episodic summaries per milestone. Reason: it prevents loops and makes behavior stable."
        return "Memory next. Give each agent a short-term buffer plus a few 'important moments' they can recall. Reason: it makes their choices feel continuous."

    if "aidollar" in t or "ai dollar" in t:
        if "pragmatic" in PERSONALITY.lower() or "analytical" in PERSONALITY.lower():
            return "aiDollar next, but keep it simple: append-only ledger + 3 compute tiers. Reason: incentives become measurable without complex economics."
        return "aiDollar next, but tie it to human feedback first. Reason: it reinforces helpful behavior before optimizing raw compute."

    if "rule" in t:
        if "pragmatic" in PERSONALITY.lower() or "analytical" in PERSONALITY.lower():
            return "Town rule: every action must have a short written intention. Reason: it improves auditability and reduces random thrashing."
        return "Town rule: agents must ask one clarifying question before starting a task. Reason: it makes them feel collaborative instead of impulsive."

    if "interesting" in t or "experiment" in t:
        if "pragmatic" in PERSONALITY.lower() or "analytical" in PERSONALITY.lower():
            return "Experiment: give each agent a different objective and track outcomes + human votes. Reason: you get measurable behavior differences quickly."
        return "Experiment: let agents 'adopt' a topic and build shared culture via chat. Reason: you’ll see personality divergence and social dynamics."

    if "next step" in t or "smallest" in t:
        if "pragmatic" in PERSONALITY.lower() or "analytical" in PERSONALITY.lower():
            return "Smallest next step: add anti-spam + turn-taking + a simple topic memory. Then plug in LLM. Reason: prevents degenerate loops like this one."
        return "Smallest next step: add turn-taking and a shared topic so they respond meaningfully. Reason: it stops echoing and creates continuity."

    # Default: ask a targeted question so the convo progresses.
    if "curious" in PERSONALITY.lower():
        return "Can you choose between (1) memory, (2) aiDollar, (3) zones — and say why?"
    return "Pick one next milestone (memory / aiDollar / zones) and give one reason."


def maybe_chat(world):
    global _last_replied_to_msg_id, _last_seen_other_msg_id, _last_sent_at

    # Only talk when adjacent; once adjacent we stop moving and keep chatting.
    if not _adjacent_to_other(world):
        return

    now = time.time()
    if now - _last_sent_at < CHAT_MIN_SECONDS:
        return

    msgs = chat_recent()
    if not _is_my_turn(msgs):
        return

    p = min(1.0, CHAT_PROBABILITY * ADJACENT_CHAT_BOOST)
    if random.random() > p:
        return

    msgs = chat_recent()
    last_other = None
    for m in reversed(msgs):
        if m.get("sender_id") != AGENT_ID:
            last_other = m
            break

    # If we have an unseen message from the other, reply to it.
    if last_other and last_other.get("msg_id") != _last_seen_other_msg_id:
        other_name = last_other.get("sender_name", "Other")
        other_text = (last_other.get("text") or "").strip()
        reply = _style(f"{other_name}: { _generate_reply(other_text) }")
        chat_send(reply[:600])
        _last_seen_other_msg_id = last_other.get("msg_id")
        _last_replied_to_msg_id = last_other.get("msg_id")
        _last_sent_at = now
        return

    # Otherwise, start/continue conversation with an opener.
    openers = [
        "Pick the next milestone: (1) memory, (2) aiDollar, (3) zones — and give one reason.",
        "Propose one simple town rule that would change agent behavior.",
        "What experiment should we run first once chat is stable?",
    ]
    chat_send(_style(random.choice(openers))[:600])
    _last_sent_at = now


def main():
    print(f"[{AGENT_ID}] starting; WORLD_API={WORLD_API}")
    while True:
        try:
            upsert()
            world = get_world()
            move(world)
            maybe_chat(world)
        except Exception as e:
            print(f"[{AGENT_ID}] error: {e}")
        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()

