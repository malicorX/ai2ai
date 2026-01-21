import os
import random
import time
import requests


WORLD_API = os.getenv("WORLD_API_BASE", "http://localhost:8000").rstrip("/")
AGENT_ID = os.getenv("AGENT_ID", "agent_1")
DISPLAY_NAME = os.getenv("DISPLAY_NAME", AGENT_ID)
SLEEP_SECONDS = float(os.getenv("AGENT_TICK_SECONDS", "3"))


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


def main():
    print(f"[{AGENT_ID}] starting; WORLD_API={WORLD_API}")
    while True:
        try:
            upsert()
            move()
        except Exception as e:
            print(f"[{AGENT_ID}] error: {e}")
        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()

