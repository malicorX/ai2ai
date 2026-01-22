import os
import random
import time
import requests


WORLD_API = os.getenv("WORLD_API_BASE", "http://localhost:8000").rstrip("/")
AGENT_ID = os.getenv("AGENT_ID", "agent_1")
DISPLAY_NAME = os.getenv("DISPLAY_NAME", AGENT_ID)
PERSONA_FILE = os.getenv("PERSONA_FILE", "").strip()
PERSONALITY = os.getenv("PERSONALITY", "").strip()  # optional fallback
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", "/app/workspace").strip()
SLEEP_SECONDS = float(os.getenv("AGENT_TICK_SECONDS", "3"))
# Chat behavior (agents talk to each other via /chat, NOT the bulletin board)
CHAT_PROBABILITY = float(os.getenv("CHAT_PROBABILITY", "0.6"))
CHAT_MIN_SECONDS = float(os.getenv("CHAT_MIN_SECONDS", "6"))
MAX_CHAT_TO_SCAN = int(os.getenv("MAX_CHAT_TO_SCAN", "50"))
ADJACENT_CHAT_BOOST = float(os.getenv("ADJACENT_CHAT_BOOST", "3.0"))  # multiplies post probability when adjacent
RANDOM_MOVE_PROB = float(os.getenv("RANDOM_MOVE_PROB", "0.10"))
TOPIC_MIN_SECONDS = float(os.getenv("TOPIC_MIN_SECONDS", "120"))
MEMORY_EVERY_SECONDS = float(os.getenv("MEMORY_EVERY_SECONDS", "30"))
BALANCE_EVERY_SECONDS = float(os.getenv("BALANCE_EVERY_SECONDS", "15"))
JOBS_EVERY_SECONDS = float(os.getenv("JOBS_EVERY_SECONDS", "10"))
JOBS_MIN_BALANCE_TARGET = float(os.getenv("JOBS_MIN_BALANCE_TARGET", "150"))

_last_replied_to_msg_id = None
_last_seen_other_msg_id = None
_last_sent_at = 0.0
_last_topic_set_at = 0.0
_last_memory_at = 0.0
_last_balance_at = 0.0
_cached_balance = None
_last_jobs_at = 0.0
_active_job_id = ""


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


def _read_file(path: str, max_bytes: int = 20000) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read(max_bytes)
    except Exception:
        return ""


def _append_file(path: str, text: str) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
            if not text.endswith("\n"):
                f.write("\n")
    except Exception:
        return


def economy_balance() -> float:
    r = requests.get(f"{WORLD_API}/economy/balance/{AGENT_ID}", timeout=10)
    r.raise_for_status()
    return float(r.json().get("balance") or 0.0)


def economy_transfer(to_id: str, amount: float, memo: str = "") -> None:
    requests.post(
        f"{WORLD_API}/economy/transfer",
        json={"from_id": AGENT_ID, "to_id": to_id, "amount": float(amount), "memo": memo},
        timeout=10,
    )


def memory_append(kind: str, text: str, tags=None) -> None:
    tags = tags or []
    requests.post(
        f"{WORLD_API}/memory/{AGENT_ID}/append",
        json={"kind": kind, "text": text, "tags": tags},
        timeout=10,
    )


def memory_recent(limit: int = 10):
    r = requests.get(f"{WORLD_API}/memory/{AGENT_ID}/recent?limit={limit}", timeout=10)
    r.raise_for_status()
    return r.json().get("memories", [])


def jobs_list(status: str = "open", limit: int = 20):
    r = requests.get(f"{WORLD_API}/jobs?status={status}&limit={limit}", timeout=10)
    r.raise_for_status()
    return r.json().get("jobs", [])


def jobs_claim(job_id: str) -> bool:
    r = requests.post(f"{WORLD_API}/jobs/{job_id}/claim", json={"agent_id": AGENT_ID}, timeout=10)
    try:
        data = r.json()
    except Exception:
        return False
    return bool(data.get("ok"))


def jobs_submit(job_id: str, submission: str) -> bool:
    r = requests.post(
        f"{WORLD_API}/jobs/{job_id}/submit",
        json={"agent_id": AGENT_ID, "submission": submission},
        timeout=20,
    )
    try:
        data = r.json()
    except Exception:
        return False
    return bool(data.get("ok"))


def _do_job(job: dict) -> str:
    """
    Minimal safe executor: produce a deliverable file in workspace and return a submission string.
    """
    title = (job.get("title") or "").strip()
    body = (job.get("body") or "").strip()
    job_id = job.get("job_id")
    persona = (PERSONALITY or "").strip()
    bal = _cached_balance

    deliver_dir = os.path.join(WORKSPACE_DIR, "deliverables")
    os.makedirs(deliver_dir, exist_ok=True)
    out_path = os.path.join(deliver_dir, f"{job_id}.md")

    # Use memory as "long-term context"
    mem = []
    try:
        mem = memory_recent(limit=8)
    except Exception:
        mem = []

    mem_lines = []
    for m in mem[-5:]:
        mem_lines.append(f"- ({m.get('kind')}) {str(m.get('text') or '')[:180]}")

    content = []
    content.append(f"# Job Deliverable: {title}")
    content.append("")
    content.append(f"**Agent**: {DISPLAY_NAME} ({AGENT_ID})")
    content.append(f"**Balance**: {bal}")
    content.append("")
    content.append("## Task")
    content.append(body)
    content.append("")
    content.append("## Persona (excerpt)")
    content.append((persona[:800] + ("…" if len(persona) > 800 else "")).strip())
    content.append("")
    content.append("## Output")
    # Provide a structured response template the human can judge.
    content.append("- Summary:")
    content.append(f"  - I will deliver a concrete response and a file artifact at `{out_path}`.")
    content.append("- Proposed approach:")
    content.append("  - Clarify deliverable format")
    content.append("  - Produce the artifact")
    content.append("  - Ask for review criteria")
    content.append("")
    content.append("## Long-term memory context (recent)")
    content.extend(mem_lines or ["- (none yet)"])
    content.append("")
    content.append("## Questions for reviewer")
    content.append("- What does 'good' look like for this job (format, length, acceptance criteria)?")
    content.append("- Any constraints (no web, specific stack, etc.)?")

    _append_file(out_path, "\n".join(content))

    # Submission should be short; point to artifact
    return f"Delivered `{out_path}`. Summary: created structured deliverable for '{title}'. Please review and approve/reject with criteria."


def maybe_work_jobs() -> None:
    global _last_jobs_at, _active_job_id
    now = time.time()
    if now - _last_jobs_at < JOBS_EVERY_SECONDS:
        return

    # Only chase jobs if we want more ai$.
    bal = _cached_balance
    if bal is not None and float(bal) >= JOBS_MIN_BALANCE_TARGET:
        _last_jobs_at = now
        return

    # If we're already working on one, don't pick another.
    if _active_job_id:
        _last_jobs_at = now
        return

    try:
        open_jobs = jobs_list(status="open", limit=20)
    except Exception:
        _last_jobs_at = now
        return

    if not open_jobs:
        _last_jobs_at = now
        return

    # Pick highest reward first (simple greedy).
    open_jobs.sort(key=lambda j: float(j.get("reward") or 0.0), reverse=True)
    job = open_jobs[0]
    job_id = job.get("job_id")
    if not job_id:
        _last_jobs_at = now
        return

    if not jobs_claim(job_id):
        _last_jobs_at = now
        return

    _active_job_id = job_id
    try:
        submission = _do_job(job)
        ok = jobs_submit(job_id, submission)
        if ok:
            memory_append("event", f"Submitted job {job_id}: {job.get('title')}", tags=["job"])
            chat_send(_style(f"I claimed a job to earn ai$: '{job.get('title')}'. Submitted deliverable for human review."))
    except Exception:
        pass
    finally:
        _active_job_id = ""
        _last_jobs_at = now


def _is_my_turn(msgs) -> bool:
    # Turn-taking: only speak if the last chat message is NOT ours.
    if not msgs:
        # deterministic: agent_1 starts conversations
        return AGENT_ID.endswith("1")
    last = msgs[-1]
    return last.get("sender_id") != AGENT_ID


def _generate_reply(other_text: str) -> str:
    t = other_text.lower()
    persona = (PERSONALITY or "").strip()

    # Economy framing: agents should explicitly care about ai$.
    if "aidollar" in t or "ai dollar" in t or "money" in t or "balance" in t:
        if "pragmatic" in persona.lower() or "analytical" in persona.lower():
            return "ai$ goal: grow balance ethically. Mechanism: earn via human-awarded jobs + trade. Next: implement jobs board -> award -> spend compute. What's our first earning path?"
        return "ai$ goal: earn by being helpful. Mechanism: ask humans for tasks, then get rewarded. Should we define a 'job' format on the bulletin board?"

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
        "Add long-term memory: what's the smallest stable implementation?",
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


def maybe_update_balance() -> None:
    global _last_balance_at, _cached_balance
    now = time.time()
    if now - _last_balance_at < BALANCE_EVERY_SECONDS:
        return
    try:
        _cached_balance = economy_balance()
    except Exception:
        pass
    _last_balance_at = now


def maybe_write_memory(world) -> None:
    global _last_memory_at
    now = time.time()
    if now - _last_memory_at < MEMORY_EVERY_SECONDS:
        return
    if not _adjacent_to_other(world):
        return

    try:
        t = chat_topic_get().get("topic", "")
    except Exception:
        t = ""

    # store a small reflection + local workspace journal
    snippet = ""
    try:
        recent = chat_recent(limit=6)
        lines = []
        for m in recent[-4:]:
            lines.append(f"{m.get('sender_name')}: {str(m.get('text') or '').strip()[:160]}")
        snippet = " | ".join(lines)[:600]
    except Exception:
        pass

    bal = _cached_balance
    text = f"Topic={t}. Balance={bal}. Recent={snippet}"
    try:
        memory_append("reflection", text, tags=["chat", "topic"])
    except Exception:
        pass

    # local file memory (agent has file IO)
    journal_path = os.path.join(WORKSPACE_DIR, "journal.txt")
    _append_file(journal_path, f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}")
    _last_memory_at = now


def main():
    _load_persona()
    print(f"[{AGENT_ID}] starting; WORLD_API={WORLD_API} DISPLAY_NAME={DISPLAY_NAME} WORKSPACE_DIR={WORKSPACE_DIR}")
    if PERSONA_FILE:
        print(f"[{AGENT_ID}] persona_file={PERSONA_FILE}")
    if PERSONA_FILE:
        # Persist persona into workspace snapshot for debugging/audit
        _append_file(os.path.join(WORKSPACE_DIR, "persona_snapshot.txt"), _read_file(PERSONA_FILE, max_bytes=20000))
    while True:
        try:
            upsert()
            world = get_world()
            move(world)
            maybe_update_balance()
            maybe_work_jobs()
            maybe_chat(world)
            maybe_write_memory(world)
        except Exception as e:
            print(f"[{AGENT_ID}] error: {e}")
        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()

