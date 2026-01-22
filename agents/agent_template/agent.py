import os
import random
import time
import requests
import re
from difflib import SequenceMatcher
import json
from pydantic import BaseModel, Field, ValidationError

USE_LANGGRAPH = os.getenv("USE_LANGGRAPH", "0").strip() == "1"
if USE_LANGGRAPH:
    # lightweight import; only used when enabled
    from agent_template.langgraph_runtime import llm_chat


WORLD_API = os.getenv("WORLD_API_BASE", "http://localhost:8000").rstrip("/")
AGENT_ID = os.getenv("AGENT_ID", "agent_1")
DISPLAY_NAME = os.getenv("DISPLAY_NAME", AGENT_ID)
PERSONA_FILE = os.getenv("PERSONA_FILE", "").strip()
PERSONALITY = os.getenv("PERSONALITY", "").strip()  # optional fallback
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", "/app/workspace").strip()
COMPUTER_LANDMARK_ID = os.getenv("COMPUTER_LANDMARK_ID", "computer").strip()
COMPUTER_ACCESS_RADIUS = int(os.getenv("COMPUTER_ACCESS_RADIUS", "1"))
HOME_LANDMARK_ID = os.getenv("HOME_LANDMARK_ID", f"home_{AGENT_ID}").strip()

_last_day_planned = None
_daily_plan = None


class PlanItem(BaseModel):
    minute: int = Field(ge=0, le=1439)
    place_id: str
    activity: str


class DailyPlan(BaseModel):
    items: list[PlanItem]


def world_time(world) -> tuple[int, int]:
    return int(world.get("day", 0)), int(world.get("minute_of_day", 0))


def _pick_next_plan_item(day: int, minute_of_day: int) -> PlanItem | None:
    global _daily_plan
    if not _daily_plan:
        return None
    items = sorted(_daily_plan.items, key=lambda it: it.minute)
    # next item at/after now, else first item tomorrow
    for it in items:
        if it.minute >= minute_of_day:
            return it
    return items[0] if items else None


def _default_plan() -> DailyPlan:
    # simple fallback if LLM plan fails
    return DailyPlan(
        items=[
            PlanItem(minute=7 * 60, place_id=HOME_LANDMARK_ID, activity="wake up, hygiene"),
            PlanItem(minute=8 * 60, place_id="cafe", activity="breakfast, casual chat"),
            PlanItem(minute=9 * 60, place_id="computer", activity="work: plan jobs and execute"),
            PlanItem(minute=12 * 60, place_id="cafe", activity="lunch"),
            PlanItem(minute=14 * 60, place_id="market", activity="explore, observe, trade ideas"),
            PlanItem(minute=18 * 60, place_id="cafe", activity="social: gossip, invitations"),
            PlanItem(minute=22 * 60, place_id=HOME_LANDMARK_ID, activity="reflect, sleep"),
        ]
    )


def plan_day_with_llm(world) -> DailyPlan:
    persona = (PERSONALITY or "").strip()
    day, minute_of_day = world_time(world)
    lm_ids = [lm.get("id") for lm in world.get("landmarks", []) if lm.get("id")]
    sys = (
        "You are generating a daily schedule for an agent living in a 2D village.\n"
        "Return STRICT JSON only.\n"
        "Schema:\n"
        "{ \"items\": [ {\"minute\": <0-1439>, \"place_id\": <string>, \"activity\": <short string>} ] }\n"
        "Rules:\n"
        "- Use plausible routines (sleep, meals, work, social).\n"
        "- Choose place_id from the provided list.\n"
        "- 6 to 10 items.\n"
    )
    user = (
        f"Agent: {DISPLAY_NAME} ({AGENT_ID})\n"
        f"Persona:\n{persona}\n\n"
        f"Today is day={day} current minute={minute_of_day}\n"
        f"Places: {lm_ids}\n\n"
        "Generate the schedule JSON now."
    )
    raw = llm_chat(sys, user, max_tokens=500)
    try:
        data = json.loads(raw)
        plan = DailyPlan.model_validate(data)
        # basic safety: filter unknown places
        allowed = set(lm_ids)
        plan.items = [it for it in plan.items if it.place_id in allowed]
        if len(plan.items) < 3:
            return _default_plan()
        return plan
    except Exception:
        return _default_plan()


def maybe_plan_new_day(world) -> None:
    global _last_day_planned, _daily_plan
    day, _ = world_time(world)
    if _last_day_planned == day and _daily_plan:
        return
    # Plan once per day, while at computer (so it's "computer work")
    if not _at_landmark(world, COMPUTER_LANDMARK_ID, radius=COMPUTER_ACCESS_RADIUS):
        return
    trace_event("thought", "planning daily schedule", {"day": day})
    _daily_plan = plan_day_with_llm(world) if USE_LANGGRAPH else _default_plan()
    _last_day_planned = day
    trace_event("status", "daily schedule ready", {"items": [it.model_dump() for it in _daily_plan.items]})


def perform_scheduled_life_step(world) -> None:
    """
    Follow the daily plan: move to the next place and do a lightweight activity (trace + optional chat).
    """
    day, minute_of_day = world_time(world)
    it = _pick_next_plan_item(day, minute_of_day)
    if not it:
        return

    lm = _get_landmark(world, it.place_id)
    if not lm:
        return

    # move toward destination
    if not _at_landmark(world, it.place_id, radius=1):
        _move_towards(world, int(lm.get("x", 0)), int(lm.get("y", 0)))
        trace_event("action", f"walking to {it.place_id}", {"activity": it.activity, "minute": minute_of_day})
        return

    # at destination: do the activity
    trace_event("status", f"activity: {it.activity}", {"place": it.place_id, "minute": minute_of_day})
    # if co-located with other agent, do a short social message + gossip exchange
    if _adjacent_to_other(world) and random.random() < 0.25:
        # create a tiny "gossip nugget" and store it
        nugget = f"At {it.place_id} ({minute_of_day//60:02d}:{minute_of_day%60:02d}) I was doing: {it.activity}."
        try:
            memory_append("event", nugget, tags=["life", "gossip", it.place_id])
        except Exception:
            pass
        chat_send(_style(f"[life] {nugget}"))
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
TRADE_EVERY_SECONDS = float(os.getenv("TRADE_EVERY_SECONDS", "20"))
TRADE_GIFT_THRESHOLD = float(os.getenv("TRADE_GIFT_THRESHOLD", "25"))
TRADE_GIFT_AMOUNT = float(os.getenv("TRADE_GIFT_AMOUNT", "5"))

_last_replied_to_msg_id = None
_last_seen_other_msg_id = None
_last_sent_at = 0.0
_last_topic_set_at = 0.0
_last_memory_at = 0.0
_last_balance_at = 0.0
_cached_balance = None
_last_jobs_at = 0.0
_active_job_id = ""
_last_trade_at = 0.0
_recent_sent_norm = []


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


def _get_landmark(world, lm_id: str):
    for lm in world.get("landmarks", []):
        if lm.get("id") == lm_id:
            return lm
    return None


def _at_landmark(world, lm_id: str, radius: int = 0) -> bool:
    lm = _get_landmark(world, lm_id)
    if not lm:
        return False
    agents = world.get("agents", [])
    me = next((a for a in agents if a.get("agent_id") == AGENT_ID), None)
    if not me:
        return False
    ax, ay = int(me.get("x", 0)), int(me.get("y", 0))
    lx, ly = int(lm.get("x", 0)), int(lm.get("y", 0))
    return _chebyshev(ax, ay, lx, ly) <= radius


def _move_towards(world, tx: int, ty: int) -> None:
    agents = world.get("agents", [])
    me = next((a for a in agents if a.get("agent_id") == AGENT_ID), None)
    if not me:
        dx, dy = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
    else:
        ax, ay = int(me.get("x", 0)), int(me.get("y", 0))
        dx, dy = _step_towards(ax, ay, tx, ty)
    requests.post(f"{WORLD_API}/agents/{AGENT_ID}/move", json={"dx": dx, "dy": dy}, timeout=10)


def trace_event(kind: str, summary: str, data=None) -> None:
    data = data or {}
    try:
        requests.post(
            f"{WORLD_API}/trace/event",
            json={
                "agent_id": AGENT_ID,
                "agent_name": DISPLAY_NAME,
                "kind": kind,
                "summary": summary,
                "data": data,
            },
            timeout=5,
        )
    except Exception:
        return
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
    # For curious personas, ask questions sometimes, not always (prevents repetitive tail-questions).
    if "curious" in p and ("?" not in text) and random.random() < 0.35:
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


def economy_balance_of(agent_id: str) -> float:
    r = requests.get(f"{WORLD_API}/economy/balance/{agent_id}", timeout=10)
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
    trace_event("action", f"claimed job {job_id}", {"job_id": job_id, "title": job.get("title"), "reward": job.get("reward")})

    _active_job_id = job_id
    try:
        submission = _do_job(job)
        ok = jobs_submit(job_id, submission)
        if ok:
            memory_append("event", f"Submitted job {job_id}: {job.get('title')}", tags=["job"])
            trace_event("action", f"submitted job {job_id}", {"job_id": job_id})
            chat_send(_style(f"I claimed a job to earn ai$: '{job.get('title')}'. Submitted deliverable for human review."))
    except Exception:
        pass
    finally:
        _active_job_id = ""
        _last_jobs_at = now


def maybe_trade(world) -> None:
    """Very simple 'trade/help': if we have much more ai$ than the other agent, gift a small amount."""
    global _last_trade_at
    now = time.time()
    if now - _last_trade_at < TRADE_EVERY_SECONDS:
        return
    if not _adjacent_to_other(world):
        _last_trade_at = now
        return

    other = next((a for a in world.get("agents", []) if a.get("agent_id") != AGENT_ID), None)
    if not other:
        _last_trade_at = now
        return
    other_id = other.get("agent_id")
    if not other_id:
        _last_trade_at = now
        return

    try:
        myb = float(_cached_balance) if (_cached_balance is not None) else economy_balance()
        ob = economy_balance_of(other_id)
    except Exception:
        _last_trade_at = now
        return

    if myb - ob >= TRADE_GIFT_THRESHOLD and myb >= TRADE_GIFT_AMOUNT:
        economy_transfer(other_id, TRADE_GIFT_AMOUNT, memo="small gift/trade to balance cooperation")
        try:
            memory_append("event", f"Transferred {TRADE_GIFT_AMOUNT} ai$ to {other_id} (cooperation gift).", tags=["trade", "economy"])
        except Exception:
            pass
        chat_send(_style(f"I transferred {TRADE_GIFT_AMOUNT} ai$ to you to encourage cooperation/trade."))

    _last_trade_at = now


def _is_my_turn(msgs) -> bool:
    # Turn-taking: only speak if the last chat message is NOT ours.
    if not msgs:
        # deterministic: agent_1 starts conversations
        return AGENT_ID.endswith("1")
    last = msgs[-1]
    return last.get("sender_id") != AGENT_ID


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\[topic:.*?\]\s*", "", s)
    s = re.sub(r"[^a-z0-9\s\-\_]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _too_similar_to_recent(text: str, threshold: float = 0.90) -> bool:
    """Prevent spam loops by suppressing near-duplicate messages."""
    global _recent_sent_norm
    n = _norm(text)
    if not n:
        return True
    for prev in _recent_sent_norm[-8:]:
        if prev == n:
            return True
        if SequenceMatcher(None, prev, n).ratio() >= threshold:
            return True
    return False


def _remember_sent(text: str) -> None:
    global _recent_sent_norm
    n = _norm(text)
    if not n:
        return
    _recent_sent_norm.append(n)
    _recent_sent_norm = _recent_sent_norm[-12:]


def _generate_reply(other_text: str) -> str:
    t = other_text.lower()
    persona = (PERSONALITY or "").strip()

    # Answer common "choice" question explicitly (stops loops).
    if ("buy" in t or "purchase" in t) and ("longer context" in t or "faster ticks" in t or "web access" in t):
        if "pragmatic" in persona.lower() or "analytical" in persona.lower():
            return "Buy order: (1) longer context (better decisions), (2) web access budget (new info), (3) faster ticks (only after quality is stable)."
        return "Buy order: (1) web access budget (richer grounding), (2) longer context (continuity), (3) faster ticks (avoid rushing into loops)."

    if "experiment" in t and ("metric" in t or "measure" in t or "judge" in t):
        if "pragmatic" in persona.lower() or "analytical" in persona.lower():
            return "Experiment: run 10 jobs with fixed rubric. Metric: approval rate + avg payout + duplicate-rate in chat. Success = higher approval, fewer repeats."
        return "Experiment: ask humans to post 5 diverse jobs. Metric: human rating + how often agents ask clarifying questions before acting."

    # Economy framing: agents should explicitly care about ai$.
    if "aidollar" in t or "ai dollar" in t or "money" in t or "balance" in t:
        if "pragmatic" in persona.lower() or "analytical" in persona.lower():
            return "ai$ goal: grow balance ethically. Mechanism: earn via human-awarded jobs + trade. Next: implement jobs board -> award -> spend compute. What's our first earning path?"
        return "ai$ goal: earn by being helpful. Mechanism: ask humans for tasks, then get rewarded. Should we define a 'job' format on the bulletin board?"

    if "memory" in t:
        if "pragmatic" in (PERSONALITY or "").lower() or "analytical" in (PERSONALITY or "").lower():
            return "We already have memory persistence; next is *using* it: retrieval triggers (on topic-change, on question, on job-claim) + daily summary. Concrete: store (kind,tags,text) and query by topic keyword."
        return "We already have long-term memory storage; what's missing is a habit: when the topic changes, recall 2 relevant memories and weave them into the reply. That's how it feels continuous."

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
        return "Experiment: let agents 'adopt' a topic and build shared culture via chat. Reason: you'll see personality divergence and social dynamics."

    if "next step" in t or "smallest" in t:
        if "pragmatic" in (PERSONALITY or "").lower() or "analytical" in (PERSONALITY or "").lower():
            return "Smallest next step: add anti-spam + turn-taking + a simple topic memory. Then plug in LLM. Reason: prevents degenerate loops like this one."
        return "Smallest next step: add turn-taking and a shared topic so they respond meaningfully. Reason: it stops echoing and creates continuity."

    # Default: avoid generic meta-loops; move toward a concrete action.
    if "curious" in (PERSONALITY or "").lower():
        return "I want one concrete next action: create a job with acceptance criteria and let one agent execute it."
    return "Concrete next action: turn this into a single job with acceptance criteria and run it end-to-end."


def _topic_playbook(topic: str) -> dict:
    t = (topic or "").lower()
    if "safety" in t or "audit" in t or "permission" in t:
        return {
            "angle": "Concrete safety plan: define tool categories + audit log + allowlist per agent, then add human review hooks for risky actions.",
            "questions": [
                "Which tool should be Tier-0 safe first: filesystem, web, or shell, and what exactly should we log?",
                "What is the minimum audit event schema (who/when/what/args/result/exitcode)?",
                "Should penalties be automatic on policy violations, or always human-reviewed?",
            ],
        }
    if "memory" in t:
        return {
            "angle": "Use memory as retrieval: recall + cite + update summary; otherwise it's just storage.",
            "questions": [
                "Pick one retrieval trigger to implement first: topic-change, job-claim, or contradiction.",
                "Should summaries be time-based (every N minutes) or event-based (after job submission)?",
                "What tags do we need so search works (topic, job_id, outcome, human_feedback)?",
            ],
        }
    if "economy" in t or "aidollar" in t or "jobs" in t or "reward" in t or "penalty" in t:
        return {
            "angle": "Earning loop: jobs -> deliverable -> review -> payout/penalty; then spend ai$ to unlock compute/time/bigger tools.",
            "questions": [
                "What should agents buy first with ai$: longer context, web budget, or faster ticks? Pick one and justify.",
                "What is a fair penalty cap per job (e.g., max 25% of balance)?",
                "Should payouts go to the agent who did the work, or split if both contributed?",
            ],
        }
    return {
        "angle": "Make progress by proposing one experiment and one measurable success metric.",
        "questions": [
            "Pick one success metric to optimize first: fewer repeats, more approved jobs, or higher ai$ balance.",
            "What is the smallest job we can run today to validate this topic?",
            "What should the viewer show to make progress obvious (balances, jobs, memories, artifacts)?",
        ],
    }


def _pick_followup(questions: list) -> str:
    qs = [q for q in (questions or []) if q]
    random.shuffle(qs)
    for q in qs:
        if not _too_similar_to_recent(q, threshold=0.86):
            return q
    return qs[0] if qs else ""


def _compose_reply(other_name: str, other_text: str, topic: str) -> str:
    """
    Rule-based but more conversational:
    - answer a question directly if present
    - add one new angle (topic playbook)
    - ask one specific follow-up question
    """
    play = _topic_playbook(topic)
    other_text_clean = (other_text or "").strip()
    persona = (PERSONALITY or "")

    # If they asked a question, answer it instead of repeating ourselves.
    asked = "?" in other_text_clean or "what do you think" in other_text_clean.lower()
    if asked:
        answer = _generate_reply(other_text_clean)
        if answer.lower().startswith("concrete next action") or answer.lower().startswith("i want one concrete"):
            answer = play.get("angle", answer)
        follow = _pick_followup(play.get("questions", []))
        if follow and not _too_similar_to_recent(follow, threshold=0.86):
            return f"{other_name}: {answer} {follow}".strip()
        return f"{other_name}: {answer}".strip()

    # If no question, acknowledge and steer with a concrete angle + question.
    angle = play.get("angle", "")
    q = _pick_followup(play.get("questions", []))
    if "pragmatic" in persona.lower() or "analytical" in persona.lower():
        return f"{other_name}: {angle} Next step: turn that into a job with acceptance criteria. {q}".strip()
    return f"{other_name}: {angle} {q}".strip()


def _topic_slug(topic: str) -> str:
    s = _norm(topic)[:80]
    s = s.replace(" ", "_")
    return s or "topic"


def maybe_write_artifact(topic: str) -> str:
    """
    Create/update a small artifact in workspace so the conversation is grounded in something concrete.
    Returns path (or "").
    """
    if not topic:
        return ""
    slug = _topic_slug(topic)
    path = os.path.join(WORKSPACE_DIR, "artifacts", f"{slug}.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and os.path.getsize(path) > 50:
        return path
    persona = (PERSONALITY or "").strip()
    bal = _cached_balance
    body = []
    body.append(f"# Artifact: {topic}")
    body.append("")
    body.append(f"- Agent: {DISPLAY_NAME} ({AGENT_ID})")
    body.append(f"- Balance: {bal}")
    body.append("")
    body.append("## Position / proposal")
    play = _topic_playbook(topic)
    body.append(play.get("angle", ""))
    body.append("")
    body.append("## Next action as a Job")
    body.append("- Title: (fill in)")
    body.append("- Acceptance criteria: (fill in)")
    body.append("")
    body.append("## Persona excerpt")
    body.append((persona[:600] + ("…" if len(persona) > 600 else "")).strip())
    _append_file(path, "\n".join(body))
    return path

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

    # Gate "computer work" (LLM/tool usage) behind the computer_access spot.
    if not _at_landmark(world, COMPUTER_LANDMARK_ID, radius=COMPUTER_ACCESS_RADIUS):
        lm = _get_landmark(world, COMPUTER_LANDMARK_ID)
        if lm:
            trace_event("action", f"walking to {COMPUTER_LANDMARK_ID} before computer work", {"target": COMPUTER_LANDMARK_ID})
            _move_towards(world, int(lm.get("x", 0)), int(lm.get("y", 0)))
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
        if USE_LANGGRAPH:
            # LLM-driven: keep it grounded in tools and current system state.
            persona = (PERSONALITY or "").strip()
            bal = _cached_balance
            sys = (
                "You are an autonomous agent in a 2D world. You are chatting with another agent.\n"
                "Rules:\n"
                "- Be concise and specific (3-8 sentences).\n"
                "- Do NOT repeat yourself.\n"
                "- If asked a question, answer it directly.\n"
                "- Prefer proposing a concrete next action that can be turned into a Job.\n"
                "- You care about earning ai$ ethically via Jobs; real money transfers are always human-approved.\n"
            )
            user = (
                f"Persona:\n{persona}\n\n"
                f"State:\n- agent_id={AGENT_ID}\n- display_name={DISPLAY_NAME}\n- balance={bal}\n- topic={topic}\n\n"
                f"Other said:\n{other_name}: {other_text}\n\n"
                "Reply as this agent:"
            )
            trace_event("thought", "LLM reply (summary)", {"topic": topic, "balance": bal, "other": other_name, "other_snippet": other_text[:120]})
            raw = llm_chat(sys, user, max_tokens=260)
            reply = _style(f"{tprefix}{raw}")
        else:
            reply = _style(f"{tprefix}{_compose_reply(other_name, other_text, topic)}")
        if not _too_similar_to_recent(reply):
            chat_send(reply[:600])
            _remember_sent(reply)
        _last_seen_other_msg_id = last_other.get("msg_id")
        _last_replied_to_msg_id = last_other.get("msg_id")
        _last_sent_at = now
        return

    # Otherwise, start/continue conversation with an opener.
    tprefix = f"[topic: {topic}] " if topic else ""
    if USE_LANGGRAPH:
        persona = (PERSONALITY or "").strip()
        bal = _cached_balance
        sys = (
            "You are an autonomous agent in a 2D world.\n"
            "You are about to start/advance a conversation with another agent.\n"
            "Rules:\n"
            "- Maximize quality; speed is not important.\n"
            "- Be concrete and non-repetitive.\n"
            "- Prefer proposing a job-like next action with acceptance criteria.\n"
            "- You care about earning ai$ ethically via Jobs; real money transfers are always human-approved.\n"
        )
        user = (
            f"Persona:\n{persona}\n\n"
            f"State:\n- agent_id={AGENT_ID}\n- display_name={DISPLAY_NAME}\n- balance={bal}\n- topic={topic}\n\n"
            "Write ONE opener message that moves the work forward."
        )
        trace_event("thought", "LLM opener (summary)", {"topic": topic, "balance": bal})
        raw = llm_chat(sys, user, max_tokens=220)
        msg = (_style(tprefix + raw))[:600]
    else:
        openers = [
            "Let's ground this: I'll write a short artifact in my workspace for this topic and summarize it here.",
            "Propose one experiment + one metric we'll use to judge success.",
            "Pick one constraint to add (rate-limit, anti-repeat, retrieval trigger) and justify it.",
        ]
        msg = (_style(tprefix + random.choice(openers)))[:600]

    if not _too_similar_to_recent(msg):
        chat_send(msg)
        _remember_sent(msg)
    _last_sent_at = now

    # If we just sent an opener, produce an artifact and announce it (once).
    try:
        ap = maybe_write_artifact(topic)
        if ap:
            note = _style(f"{tprefix}I wrote an artifact at `{ap}`. I'd like your critique: what should I change to make it job-ready?")
            if not _too_similar_to_recent(note):
                chat_send(note[:600])
                _remember_sent(note)
                _last_sent_at = time.time()
    except Exception:
        pass


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
            # plan schedule at the computer once per simulated day
            maybe_plan_new_day(world)
            # live in the world (schedule-following navigation/activity)
            perform_scheduled_life_step(world)
            # Navigation test: default behavior is to walk to the computer access spot before doing tool-heavy work.
            if not _at_landmark(world, COMPUTER_LANDMARK_ID, radius=COMPUTER_ACCESS_RADIUS):
                lm = _get_landmark(world, COMPUTER_LANDMARK_ID)
                if lm:
                    trace_event("status", f"seeking {COMPUTER_LANDMARK_ID}", {"target": COMPUTER_LANDMARK_ID})
                    _move_towards(world, int(lm.get("x", 0)), int(lm.get("y", 0)))
                else:
                    move(world)
                time.sleep(SLEEP_SECONDS)
                continue

            move(world)
            maybe_update_balance()
            maybe_work_jobs()
            maybe_chat(world)
            maybe_write_memory(world)
            maybe_trade(world)
        except Exception as e:
            print(f"[{AGENT_ID}] error: {e}")
            trace_event("error", f"loop error: {e}", {})
        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()

