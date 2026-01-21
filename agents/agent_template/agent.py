import os
import random
import time
import requests


WORLD_API = os.getenv("WORLD_API_BASE", "http://localhost:8000").rstrip("/")
AGENT_ID = os.getenv("AGENT_ID", "agent_1")
DISPLAY_NAME = os.getenv("DISPLAY_NAME", AGENT_ID)
PERSONA_FILE = os.getenv("PERSONA_FILE", "").strip()
PERSONALITY = os.getenv("PERSONALITY", "").strip()  # optional fallback
SLEEP_SECONDS = float(os.getenv("AGENT_TICK_SECONDS", "3"))
# Chat behavior (agents talk to each other via /chat, NOT the bulletin board)
CHAT_PROBABILITY = float(os.getenv("CHAT_PROBABILITY", "0.6"))
CHAT_MIN_SECONDS = float(os.getenv("CHAT_MIN_SECONDS", "6"))
MAX_CHAT_TO_SCAN = int(os.getenv("MAX_CHAT_TO_SCAN", "50"))
ADJACENT_CHAT_BOOST = float(os.getenv("ADJACENT_CHAT_BOOST", "3.0"))  # multiplies post probability when adjacent
RANDOM_MOVE_PROB = float(os.getenv("RANDOM_MOVE_PROB", "0.10"))
TOPIC_MIN_SECONDS = float(os.getenv("TOPIC_MIN_SECONDS", "120"))

_last_replied_to_msg_id = None
_last_seen_other_msg_id = None
_last_sent_at = 0.0
_last_topic_set_at = 0.0


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
    p = (PERSONALITY or "").lower()
    if "sarcast" in p:
        return text + " (sure.)"
    if "formal" in p:
        return "Indeed. " + text
    if "curious" in p:
        return text + " What do you think?"
    return text


def _load_persona() -> str:
    global PERSONALITY
    if PERSONALITY:
        return PERSONALITY
    if not PERSONA_FILE:
        PERSONALITY = "Concise, pragmatic, and focused on concrete next steps."
        return PERSONALITY
    try:
        with open(PERSONA_FILE, "r", encoding="utf-8") as f:
            PERSONALITY = f.read().strip()
            if not PERSONALITY:
                PERSONALITY = "Concise, pragmatic, and focused on concrete next steps."
            return PERSONALITY
    except Exception:
        PERSONALITY = "Concise, pragmatic, and focused on concrete next steps."
        return PERSONALITY


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
        if "pragmatic" in (PERSONALITY or "").lower() or "analytical" in (PERSONALITY or "").lower():
            return "Memory next. Start with short-term (last 20 events) + episodic summaries per milestone. Reason: it prevents loops and makes behavior stable."
        return "Memory next. Give each agent a short-term buffer plus a few 'important moments' they can recall. Reason: it makes their choices feel continuous."

    if "aidollar" in t or "ai dollar" in t:
        if "pragmatic" in (PERSONALITY or "").lower() or "analytical" in (PERSONALITY or "").lower():
            return "aiDollar next, but keep it simple: append-only ledger + 3 compute tiers. Reason: incentives become measurable without complex economics."
        return "aiDollar next, but tie it to human feedback first. Reason: it reinforces helpful behavior before optimizing raw compute."

    if "rule" in t:
        if "pragmatic" in (PERSONALITY or "").lower() or "analytical" in (PERSONALITY or "").lower():
            return "Town rule: every action must have a short written intention. Reason: it improves auditability and reduces random thrashing."
        return "Town rule: agents must ask one clarifying question before starting a task. Reason: it makes them feel collaborative instead of impulsive."

    if "interesting" in t or "experiment" in t:
        if "pragmatic" in (PERSONALITY or "").lower() or "analytical" in (PERSONALITY or "").lower():
            return "Experiment: give each agent a different objective and track outcomes + human votes. Reason: you get measurable behavior differences quickly."
        return "Experiment: let agents 'adopt' a topic and build shared culture via chat. Reason: you’ll see personality divergence and social dynamics."

    if "next step" in t or "smallest" in t:
        if "pragmatic" in (PERSONALITY or "").lower() or "analytical" in (PERSONALITY or "").lower():
            return "Smallest next step: add anti-spam + turn-taking + a simple topic memory. Then plug in LLM. Reason: prevents degenerate loops like this one."
        return "Smallest next step: add turn-taking and a shared topic so they respond meaningfully. Reason: it stops echoing and creates continuity."

    # Default: ask a targeted question so the convo progresses.
    if "curious" in (PERSONALITY or "").lower():
        return "Can you choose between (1) memory, (2) aiDollar, (3) zones — and say why?"
    return "Pick one next milestone (memory / aiDollar / zones) and give one reason."


def chat_topic_get():
    r = requests.get(f"{WORLD_API}/chat/topic", timeout=10)
    r.raise_for_status()
    return r.json()


def chat_topic_set(topic: str, reason: str = ""):
    requests.post(
        f"{WORLD_API}/chat/topic/set",
        json={
            "topic": topic,
            "by_agent_id": AGENT_ID,
            "by_agent_name": DISPLAY_NAME,
            "reason": reason,
        },
        timeout=10,
    )


def _topic_candidates() -> list:
    p = (PERSONALITY or "").lower()
    base = [
        "How to measure 'meaningful' conversation and avoid loops",
        "Add long-term memory: what’s the smallest stable implementation?",
        "Design a minimal aiDollar ledger + compute tiers",
        "Town governance: rules, enforcement, and incentives",
        "Human-in-the-loop feedback: reward/penalty mechanics that are fair",
        "Interesting world dynamics: jobs, quests, and scarcity",
        "Safety: tool auditing and permission boundaries for root-in-container agents",
    ]
    if "environment" in p or "sustain" in p:
        base.insert(0, "Ecology in the sim: how should resources renew or collapse?")
    if "profit" in p or "bank" in p or "investment" in p:
        base.insert(0, "Market design: pricing compute and preventing runaway spending")
    if "librarian" in p or "curious" in p:
        base.insert(0, "Narrative continuity: what makes the village feel alive to a human?")
    return base


def maybe_set_topic(world) -> str:
    """Rotate topic occasionally when adjacent and it is our turn."""
    global _last_topic_set_at
    if not _adjacent_to_other(world):
        return ""
    now = time.time()
    if now - _last_topic_set_at < TOPIC_MIN_SECONDS:
        return ""

    msgs = chat_recent()
    if not _is_my_turn(msgs):
        return ""

    current = ""
    try:
        t = chat_topic_get()
        current = (t.get("topic") or "").strip()
        set_at = float(t.get("set_at") or 0.0)
        if current and now - set_at < TOPIC_MIN_SECONDS:
            return current
    except Exception:
        pass

    candidates = _topic_candidates()
    pick = random.choice([c for c in candidates if c.lower() != current.lower()] or candidates)
    chat_topic_set(pick, reason="rotate topic to keep conversation meaningful and avoid loops")
    _last_topic_set_at = now
    return pick


def maybe_chat(world):
    global _last_replied_to_msg_id, _last_seen_other_msg_id, _last_sent_at

    # Only talk when adjacent; once adjacent we stop moving and keep chatting.
    if not _adjacent_to_other(world):
        return

    topic = ""
    try:
        topic = maybe_set_topic(world)
    except Exception:
        topic = ""

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
        tprefix = f"[topic: {topic}] " if topic else ""
        reply = _style(f"{tprefix}{other_name}: {_generate_reply(other_text)}")
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
    tprefix = f"[topic: {topic}] " if topic else ""
    chat_send((_style(tprefix + random.choice(openers)))[:600])
    _last_sent_at = now


def main():
    _load_persona()
    print(f"[{AGENT_ID}] starting; WORLD_API={WORLD_API} DISPLAY_NAME={DISPLAY_NAME}")
    if PERSONA_FILE:
        print(f"[{AGENT_ID}] persona_file={PERSONA_FILE}")
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

