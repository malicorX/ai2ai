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
MAX_CHAT_TO_SCAN = int(os.getenv("MAX_CHAT_TO_SCAN", "50"))
ADJACENT_CHAT_BOOST = float(os.getenv("ADJACENT_CHAT_BOOST", "3.0"))  # multiplies post probability when adjacent
RANDOM_MOVE_PROB = float(os.getenv("RANDOM_MOVE_PROB", "0.10"))

_last_replied_to_msg_id = None


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


def maybe_chat(world):
    global _last_replied_to_msg_id

    # Only talk when adjacent; once adjacent we stop moving and keep chatting.
    if not _adjacent_to_other(world):
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
    if last_other and last_other.get("msg_id") != _last_replied_to_msg_id:
        other_name = last_other.get("sender_name", "Other")
        reply = _style(f"{other_name}, agreed. Next, let's build the smallest next step and validate it.")
        chat_send(reply)
        _last_replied_to_msg_id = last_other.get("msg_id")
        return

    # Otherwise, start/continue conversation with an opener.
    openers = [
        "What should we build next after basic chat is stable?",
        "Memory next or aiDollar next? Pick one and give one reason.",
        "Propose one town rule that would change agent behavior.",
        "How do we make this world more interesting to watch?",
    ]
    chat_send(_style(random.choice(openers)))


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

