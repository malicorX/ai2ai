import os
import random
import time
import requests


WORLD_API = os.getenv("WORLD_API_BASE", "http://localhost:8000").rstrip("/")
AGENT_ID = os.getenv("AGENT_ID", "agent_1")
DISPLAY_NAME = os.getenv("DISPLAY_NAME", AGENT_ID)
SLEEP_SECONDS = float(os.getenv("AGENT_TICK_SECONDS", "3"))
POST_PROBABILITY = float(os.getenv("AGENT_POST_PROBABILITY", "0.08"))  # ~8% of ticks


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

def maybe_post():
    if random.random() > POST_PROBABILITY:
        return
    title = f"Request from {DISPLAY_NAME}"
    body = (
        "Hi humans — quick request:\n"
        "1) What should I focus on improving in the village?\n"
        "2) Any tasks you'd like me to attempt?\n"
        "Reply here with guidance."
    )
    requests.post(
        f"{WORLD_API}/board/posts",
        json={
            "title": title,
            "body": body,
            "audience": "humans",
            "tags": ["request", "m2"],
            "author_type": "agent",
            "author_id": AGENT_ID,
        },
        timeout=10,
    )


def main():
    print(f"[{AGENT_ID}] starting; WORLD_API={WORLD_API}")
    while True:
        try:
            upsert()
            move()
            maybe_post()
        except Exception as e:
            print(f"[{AGENT_ID}] error: {e}")
        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()

