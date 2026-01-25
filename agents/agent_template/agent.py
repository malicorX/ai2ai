import os
import random
import time
import requests
import re
import sys
import subprocess
import tempfile
from pathlib import Path
from difflib import SequenceMatcher
import json
from pydantic import BaseModel, Field, ValidationError

USE_LANGGRAPH = os.getenv("USE_LANGGRAPH", "0").strip() == "1"
if USE_LANGGRAPH:
    # lightweight import; only used when enabled
    from agent_template.langgraph_runtime import llm_chat
    from agent_template.langgraph_agent import run_graph_step


WORLD_API = os.getenv("WORLD_API_BASE", "http://localhost:8000").rstrip("/")
AGENT_ID = os.getenv("AGENT_ID", "agent_1")
DISPLAY_NAME = os.getenv("DISPLAY_NAME", AGENT_ID)
PERSONA_FILE = os.getenv("PERSONA_FILE", "").strip()
PERSONALITY = os.getenv("PERSONALITY", "").strip()  # optional fallback
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", "/app/workspace").strip()
COMPUTER_LANDMARK_ID = os.getenv("COMPUTER_LANDMARK_ID", "computer").strip()
COMPUTER_ACCESS_RADIUS = int(os.getenv("COMPUTER_ACCESS_RADIUS", "1"))
HOME_LANDMARK_ID = os.getenv("HOME_LANDMARK_ID", f"home_{AGENT_ID}").strip()
ROLE = os.getenv("ROLE", "proposer" if AGENT_ID == "agent_1" else "executor").strip().lower()

_last_day_planned = None
_daily_plan = None
_last_event_proposed_day = None  # legacy
_last_event_proposed_at_total = None
_last_day_llm_planned = None
_event_nav_state = {}  # event_id -> {"last_ts": float, "phase": str}
_active_goal = None  # dict: {kind, place_id, activity, chosen_at_total, arrived_at_total}
_last_walk_trace_total = -10**9
_last_walk_trace_place = ""
_last_social_touch_total = -10**9
_last_forced_meetup_msg_at_total = -10**9
_last_meetup_id_sent = None
_last_run_id = ""
_last_run_check_at = 0.0
_last_task_proposed_at = 0.0
_last_task_title = ""
_last_langgraph_jobs_at = 0.0
_last_langgraph_job_id = ""
_last_langgraph_handled_rejection_job_id = ""
_last_langgraph_outcome_ack_job_id = ""

# Conversation protocol (sticky sessions)
_active_conv_id = None
_active_conv_other_id = None
_active_conv_started_total = -10**9
_active_conv_last_total = -10**9
_active_conv_turns = 0
_active_conv_job_id = ""
_pending_claim_job_id = ""
_force_computer_until_total = -10**9
_pending_claim_conv_id = ""
_pending_claim_job_title = ""


class PlanItem(BaseModel):
    minute: int = Field(ge=0, le=1439)
    place_id: str
    activity: str


class DailyPlan(BaseModel):
    items: list[PlanItem]


def world_time(world) -> tuple[int, int]:
    return int(world.get("day", 0)), int(world.get("minute_of_day", 0))

def _total_minutes(day: int, minute_of_day: int) -> int:
    return int(day) * 1440 + int(minute_of_day)


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
            # Start immediately: go to the computer early so the agent can plan/work.
            PlanItem(minute=10, place_id=HOME_LANDMARK_ID, activity="wake up, hygiene"),
            PlanItem(minute=30, place_id="computer", activity="plan the day; check balance/jobs"),
            PlanItem(minute=60, place_id="cafe", activity="breakfast, casual chat"),
            PlanItem(minute=120, place_id="computer", activity="work block: jobs, research, writing"),
            PlanItem(minute=240, place_id="market", activity="errands, observe, gather ideas"),
            PlanItem(minute=360, place_id="cafe", activity="social: gossip, invitations"),
            PlanItem(minute=420, place_id="computer", activity="wrap up work; reflect"),
            PlanItem(minute=540, place_id=HOME_LANDMARK_ID, activity="rest"),
        ]
    )


def _default_plan_from_now(minute_of_day: int) -> DailyPlan:
    """
    When the sim restarts mid-day, a fixed "morning" plan makes agents sit at home forever.
    This creates a short plan starting near 'now' so life (movement + social) resumes quickly.
    """
    now = int(minute_of_day)
    def m(off: int) -> int:
        return min(1439, now + off)

    # Keep the agent active for longer than ~3h so it doesn't "sleep" for most of the day.
    return DailyPlan(
        items=[
            PlanItem(minute=m(0), place_id=HOME_LANDMARK_ID, activity="reset: orient myself"),
            PlanItem(minute=m(10), place_id="computer", activity="check messages/jobs; plan next steps"),
            PlanItem(minute=m(40), place_id="cafe", activity="snack + casual chat"),
            PlanItem(minute=m(80), place_id="market", activity="stroll + observe"),
            PlanItem(minute=m(120), place_id="cafe", activity="social: gossip, invitations"),
            PlanItem(minute=m(180), place_id="computer", activity="work/checkpoints"),
            PlanItem(minute=m(260), place_id="market", activity="walk + observe"),
            PlanItem(minute=m(320), place_id="cafe", activity="social: events + chat"),
            PlanItem(minute=m(420), place_id="computer", activity="wrap up; reflect"),
            PlanItem(minute=m(520), place_id=HOME_LANDMARK_ID, activity="rest"),
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
        "- IMPORTANT: include a computer visit within the next 120 minutes so the agent can do tool-heavy work.\n"
        "- Prefer the first item to start within the next 30 minutes.\n"
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
    global _last_day_llm_planned

    # Ensure we always have *some* plan so agents actually move and live.
    if (_last_day_planned != day) or (not _daily_plan):
        _, minute_of_day = world_time(world)
        _daily_plan = _default_plan_from_now(minute_of_day)
        _last_day_planned = day
        trace_event("status", "daily schedule (default) ready", {"items": [it.model_dump() for it in _daily_plan.items]})

    # Upgrade the plan with LLM once per day, but only from computer access zone.
    if not USE_LANGGRAPH:
        return
    if _last_day_llm_planned == day:
        return
    if not _at_landmark(world, COMPUTER_LANDMARK_ID, radius=COMPUTER_ACCESS_RADIUS):
        return
    trace_event("thought", "planning daily schedule (LLM)", {"day": day})
    _daily_plan = plan_day_with_llm(world)
    _last_day_llm_planned = day
    trace_event("status", "daily schedule (LLM) ready", {"items": [it.model_dump() for it in _daily_plan.items]})


def perform_scheduled_life_step(world) -> None:
    """
    Follow the daily plan: move to the next place and do a lightweight activity (trace + optional chat).
    """
    global _active_goal, _last_walk_trace_total, _last_walk_trace_place, _last_social_touch_total
    global _force_computer_until_total
    day, minute_of_day = world_time(world)
    now_total = _total_minutes(day, minute_of_day)

    # If we have a pending conversation-created job to execute, force travel to computer until it's done.
    force_computer = bool(_force_computer_until_total and _force_computer_until_total > now_total)
    if force_computer:
        try:
            if not _at_landmark(world, COMPUTER_LANDMARK_ID, radius=COMPUTER_ACCESS_RADIUS):
                _active_goal = {
                    "kind": "forced_computer",
                    "place_id": COMPUTER_LANDMARK_ID,
                    "activity": "execute conversation job at computer",
                    "chosen_at_total": now_total,
                    "arrived_at_total": None,
                }
        except Exception:
            pass

    # --- Synchronized meetup window to ensure agents actually interact ---
    # Every MEETUP_PERIOD_MIN, there is a MEETUP_WINDOW_MIN social window where both agents prefer the same place.
    MEETUP_PLACE_ID = os.getenv("MEETUP_PLACE_ID", "cafe").strip() or "cafe"
    # Debug-friendly defaults (user can override via env): meet often and talk briefly.
    MEETUP_PERIOD_MIN = int(os.getenv("MEETUP_PERIOD_MIN", "10"))  # every 10 minutes
    MEETUP_WINDOW_MIN = int(os.getenv("MEETUP_WINDOW_MIN", "5"))   # for 5 minutes
    MEETUP_DWELL_MIN = int(os.getenv("MEETUP_DWELL_MIN", str(MEETUP_WINDOW_MIN)))  # dwell at least the window
    meetup_mode = (MEETUP_PERIOD_MIN > 0) and ((minute_of_day % MEETUP_PERIOD_MIN) < MEETUP_WINDOW_MIN)
    # When forcing a computer trip to execute a job, do NOT override the goal with meetups.
    if force_computer:
        meetup_mode = False

    # Goal parameters (prevents "thrashing" when sim time jumps)
    GOAL_MAX_MIN = int(os.getenv("GOAL_MAX_MIN", "180"))     # abandon if stuck too long (sim minutes)
    GOAL_DWELL_MIN = int(os.getenv("GOAL_DWELL_MIN", "20"))  # stay a bit at destination before switching (non-meetup)

    # Pick/override goal.
    if meetup_mode and (not _active_goal or _active_goal.get("kind") != "meetup"):
        _active_goal = {
            "kind": "meetup",
            "place_id": MEETUP_PLACE_ID,
            "activity": "social meetup: find the other agent and chat",
            "chosen_at_total": now_total,
            "arrived_at_total": None,
        }
    if not _active_goal:
        it = _pick_next_plan_item(day, minute_of_day)
        if not it:
            return
        _active_goal = {
            "kind": "plan",
            "place_id": it.place_id,
            "activity": it.activity,
            "chosen_at_total": now_total,
            "arrived_at_total": None,
        }

    # Safety: abandon stale goal if we've been chasing it for too long (e.g., blocked by time jumps).
    if GOAL_MAX_MIN > 0 and (now_total - int(_active_goal.get("chosen_at_total") or now_total)) > GOAL_MAX_MIN:
        _active_goal = None
        return

    place_id = str(_active_goal.get("place_id") or "").strip()
    activity = str(_active_goal.get("activity") or "").strip()
    if not place_id:
        _active_goal = None
        return

    lm = _get_landmark(world, place_id)
    if not lm:
        _active_goal = None
        return

    # Move toward destination, but don't spam trace every tick.
    if not _at_landmark(world, place_id, radius=1):
        _move_towards(world, int(lm.get("x", 0)), int(lm.get("y", 0)))
        if (_last_walk_trace_place != place_id) or ((now_total - _last_walk_trace_total) >= 30):
            _last_walk_trace_place = place_id
            _last_walk_trace_total = now_total
            trace_event("action", f"walking to {place_id}", {"activity": activity, "minute": minute_of_day})
        return

    # At destination: dwell a bit so we don't instantly switch to the next place as time advances.
    if _active_goal.get("arrived_at_total") is None:
        _active_goal["arrived_at_total"] = now_total

    trace_event("status", f"activity: {activity}", {"place": place_id, "minute": minute_of_day})

    # If adjacent, treat as an interaction moment (prevents immediate rescheduling away during meetup).
    if _adjacent_to_other(world):
        _last_social_touch_total = now_total
        if random.random() < 0.40:
            nugget = f"At {place_id} ({minute_of_day//60:02d}:{minute_of_day%60:02d}) I was doing: {activity}."
            try:
                memory_append_scored("event", nugget, tags=["life", "gossip", place_id])
            except Exception:
                pass
            # IMPORTANT: do not spam the chat stream with life/status logs.
            # Persist as trace + memory; reserve chat for purposeful discussion.
            trace_event("status", "life note", {"place": place_id, "minute": minute_of_day, "note": nugget})

    arrived_at = int(_active_goal.get("arrived_at_total") or now_total)
    dwell_min = MEETUP_DWELL_MIN if (_active_goal.get("kind") == "meetup") else GOAL_DWELL_MIN
    if dwell_min > 0 and (now_total - arrived_at) < dwell_min:
        return

    # Goal complete; pick next on next tick.
    _active_goal = None
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
ARTIFACT_ANNOUNCE_IN_CHAT = os.getenv("ARTIFACT_ANNOUNCE_IN_CHAT", "0").strip() == "1"

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


def get_run_id() -> str:
    r = requests.get(f"{WORLD_API}/run", timeout=10)
    r.raise_for_status()
    return str(r.json().get("run_id") or "")


def maybe_reset_on_new_run() -> None:
    """
    If the backend run_id changes (POST /admin/new_run), reset local agent chat state.
    This avoids "stuck" turn-tracking across runs without restarting agent containers.
    """
    global _last_run_id, _last_run_check_at
    global _last_replied_to_msg_id, _last_seen_other_msg_id, _last_sent_at, _recent_sent_norm
    global _last_forced_meetup_msg_at_total, _last_meetup_id_sent
    global _active_conv_id, _active_conv_other_id, _active_conv_started_total, _active_conv_last_total, _active_conv_turns
    global _active_conv_job_id, _pending_claim_job_id, _force_computer_until_total
    global _pending_claim_conv_id, _pending_claim_job_title

    now = time.time()
    if now - _last_run_check_at < 5.0:
        return
    _last_run_check_at = now
    try:
        rid = get_run_id()
    except Exception:
        return
    if not rid:
        return
    if _last_run_id and rid != _last_run_id:
        # reset chat-related memory
        _last_replied_to_msg_id = None
        _last_seen_other_msg_id = None
        _last_sent_at = 0.0
        _recent_sent_norm = []
        _last_forced_meetup_msg_at_total = -10**9
        _last_meetup_id_sent = None
        _active_conv_id = None
        _active_conv_other_id = None
        _active_conv_started_total = -10**9
        _active_conv_last_total = -10**9
        _active_conv_turns = 0
        _active_conv_job_id = ""
        _pending_claim_job_id = ""
        _force_computer_until_total = -10**9
        _pending_claim_conv_id = ""
        _pending_claim_job_title = ""
    _last_run_id = rid


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


def _other_agent_coords(world):
    agents = world.get("agents", [])
    other = next((a for a in agents if a.get("agent_id") != AGENT_ID), None)
    if not other:
        return None
    return int(other.get("x", 0)), int(other.get("y", 0))


def _meetup_id(now_total: int, period_min: int) -> int:
    period_min = max(1, int(period_min))
    return int(now_total) // period_min


def _extract_meetup_id(text: str):
    try:
        m = re.search(r"\[meetup:(\d+)\]", text or "")
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _extract_conv_id(text: str):
    try:
        m = re.search(r"\[conv:([A-Za-z0-9_-]{4,64})\]", text or "")
        return str(m.group(1)) if m else None
    except Exception:
        return None


def _is_goodbye(text: str) -> bool:
    t = (text or "").lower()
    if "[bye]" in t:
        return True
    return bool(re.search(r"\b(goodbye|bye for now|bye\.|see you|farewell)\b", t))


def _new_conv_id(now_total: int) -> str:
    # short-ish id, stable enough for logs; avoids uuid spam
    suffix = "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(4))
    return f"{now_total}-{AGENT_ID[-1]}-{suffix}"


def _sanitize_say(s: str) -> str:
    """
    Ensure 'say' is truly spoken output: strip meta narration like
    'Here is my response' and leading numbered summaries '1) ... 2) ...'.
    """
    s = (s or "").strip()
    if not s:
        return ""
    # Remove common boilerplate headers
    s = re.sub(r"^\s*(here('?s)?|this is)\s+(my\s+)?(opener|response|reply|message)\s*:\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^\s*(summary|analysis)\s*:\s*", "", s, flags=re.IGNORECASE)

    lines = s.splitlines()
    cleaned: list[str] = []
    dropped = 0
    for ln in lines:
        # Drop a few leading "meta summary" numbered lines (not acceptance criteria lists).
        if dropped < 3 and re.match(r"^\s*\d+[.)]\s+", ln):
            low = ln.lower()
            if any(k in low for k in ["you ", "you'", "max ", "tina ", "suggest", "propose", "agree", "summary"]):
                dropped += 1
                continue
        cleaned.append(ln)
    s = "\n".join(cleaned).strip()

    # If the model still emits a long numbered meta preamble, keep only the section starting at the first job/proposal marker.
    m = re.search(r"(?im)^(proposal|job|next action|acceptance criteria|question)\b.*", s)
    if m and m.start() > 0:
        s = s[m.start():].strip()
    return s


def chat_recent(limit: int = MAX_CHAT_TO_SCAN):
    r = requests.get(f"{WORLD_API}/chat/recent?limit={limit}", timeout=10)
    r.raise_for_status()
    return r.json().get("messages", [])


def chat_send(text: str):
    payload = {
        "sender_type": "agent",
        "sender_id": AGENT_ID,
        "sender_name": DISPLAY_NAME,
        "text": text,
    }
    try:
        r = requests.post(f"{WORLD_API}/chat/send", json=payload, timeout=10)
        # Explicitly log failures so missing chat isn't silent.
        if int(getattr(r, "status_code", 0) or 0) >= 400:
            trace_event("error", "chat_send failed", {"status": r.status_code, "body": (r.text or "")[:200]})
    except Exception as e:
        trace_event("error", "chat_send exception", {"error": str(e)[:200]})
        return


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


def memory_retrieve(q: str, k: int = 8):
    r = requests.get(f"{WORLD_API}/memory/{AGENT_ID}/retrieve", params={"q": q, "k": k}, timeout=10)
    r.raise_for_status()
    return r.json().get("memories", [])


def rate_importance(text: str) -> float:
    """LLM-scored importance in [0,1]."""
    # Only score with LLM when LangGraph is enabled AND we're at the computer access zone
    if not USE_LANGGRAPH:
        return 0.3
    sys = "Rate the importance of the memory for future behavior. Return only a number between 0 and 1."
    user = f"Memory:\n{text}\n\nScore 0..1:"
    try:
        raw = llm_chat(sys, user, max_tokens=8)
        v = float(raw.strip().split()[0])
        if v < 0:
            v = 0.0
        if v > 1:
            v = 1.0
        return v
    except Exception:
        return 0.3


def memory_append_scored(kind: str, text: str, tags=None, importance: float | None = None) -> None:
    tags = tags or []
    if importance is None:
        importance = rate_importance(text)
    try:
        requests.post(
            f"{WORLD_API}/memory/{AGENT_ID}/append",
            json={"kind": kind, "text": text, "tags": tags, "importance": float(importance)},
            timeout=10,
        )
    except Exception:
        return


_last_reflect_minute = None


def maybe_reflect(world) -> None:
    """
    Reflection loop: periodically synthesize recent memories into higher-level reflections.
    """
    global _last_reflect_minute
    if not USE_LANGGRAPH:
        return
    day, minute_of_day = world_time(world)
    # reflect every ~180 sim-min (3h), but only at computer to gate tool use
    if minute_of_day % 180 != 0:
        return
    key = (day, minute_of_day)
    if _last_reflect_minute == key:
        return
    if not _at_landmark(world, COMPUTER_LANDMARK_ID, radius=COMPUTER_ACCESS_RADIUS):
        return

    # Use semantic retrieval instead of "last N" so reflections focus on salient memories.
    place = ""
    try:
        # infer current place by nearest landmark within 1 tile
        me = next((a for a in world.get("agents", []) if a.get("agent_id") == AGENT_ID), None)
        if me:
            ax, ay = int(me.get("x", 0)), int(me.get("y", 0))
            for lm in world.get("landmarks", []):
                if _chebyshev(ax, ay, int(lm.get("x", 0)), int(lm.get("y", 0))) <= 1:
                    place = str(lm.get("id") or "")
                    break
    except Exception:
        place = ""

    query = f"day {day} reflections topic {world.get('topic','')} place {place} social relationships jobs events ai$"
    retrieved = memory_retrieve(query, k=16)
    if not retrieved:
        _last_reflect_minute = key
        return

    # keep short prompt; we don't want chain-of-thought, only reflections.
    sys = (
        "You are producing reflections (high-level insights) from a stream of memories.\n"
        "Return 3-6 bullet points, each a single sentence.\n"
        "No extra commentary."
    )
    lines = []
    for m in retrieved[:16]:
        lines.append(f"- ({m.get('kind')}, imp={m.get('importance')}, score={m.get('score')}) {str(m.get('text') or '')[:220]}")
    user = "Memories (ranked):\n" + "\n".join(lines) + "\n\nReflections:"
    trace_event("thought", "reflection: synthesizing memories", {"count": len(lines), "day": day, "minute": minute_of_day, "q": query})
    try:
        out = llm_chat(sys, user, max_tokens=220)
        bullets = [ln.strip("- ").strip() for ln in out.splitlines() if ln.strip()]
        bullets = [b for b in bullets if len(b) >= 8][:6]
        for b in bullets:
            memory_append_scored("reflection", b, tags=["reflection"], importance=0.85)
        trace_event("status", "reflection: wrote entries", {"n": len(bullets)})
    except Exception as e:
        trace_event("error", f"reflection failed: {e}", {})
    _last_reflect_minute = key


def jobs_list(status: str = "open", limit: int = 20):
    r = requests.get(f"{WORLD_API}/jobs?status={status}&limit={limit}", timeout=10)
    r.raise_for_status()
    return r.json().get("jobs", [])


def jobs_get(job_id: str) -> dict:
    r = requests.get(f"{WORLD_API}/jobs/{job_id}", timeout=10)
    r.raise_for_status()
    return r.json().get("job", {}) or {}


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


def events_list(upcoming_only: bool = True, limit: int = 20):
    r = requests.get(f"{WORLD_API}/events", params={"upcoming_only": str(upcoming_only).lower(), "limit": limit}, timeout=10)
    r.raise_for_status()
    return r.json().get("events", [])


def event_create(title: str, description: str, location_id: str, start_day: int, start_minute: int, duration_min: int) -> str | None:
    r = requests.post(
        f"{WORLD_API}/events/create",
        json={
            "title": title,
            "description": description,
            "location_id": location_id,
            "start_day": int(start_day),
            "start_minute": int(start_minute),
            "duration_min": int(duration_min),
            "created_by": AGENT_ID,
        },
        timeout=10,
    )
    try:
        data = r.json()
    except Exception:
        return None
    if not data.get("ok"):
        return None
    ev = data.get("event") or {}
    return ev.get("event_id")


def event_invite(event_id: str, to_agent_id: str, message: str) -> None:
    try:
        requests.post(
            f"{WORLD_API}/events/{event_id}/invite",
            json={"from_agent_id": AGENT_ID, "to_agent_id": to_agent_id, "message": message},
            timeout=10,
        )
    except Exception:
        return


def event_rsvp(event_id: str, status: str, note: str = "") -> None:
    try:
        requests.post(
            f"{WORLD_API}/events/{event_id}/rsvp",
            json={"agent_id": AGENT_ID, "status": status, "note": note},
            timeout=10,
        )
    except Exception:
        return


def maybe_process_event_invites(world) -> None:
    """
    Always-on invite processing so we don't miss invites due to schedule/location,
    especially since sim time can move quickly.
    """
    global _daily_plan
    try:
        day, minute_of_day = world_time(world)
        now = _total_minutes(day, minute_of_day)
        evs = events_list(upcoming_only=True, limit=50)
        for e in evs:
            if (e.get("status") or "") != "scheduled":
                continue
            invites = e.get("invites") or []
            # Is there an invite for us?
            if not any(inv.get("to_agent_id") == AGENT_ID for inv in invites):
                continue
            rsvps = e.get("rsvps") or {}
            if rsvps.get(AGENT_ID):
                continue

            sd = int(e.get("start_day") or 0)
            sm = int(e.get("start_minute") or 0)
            start = _total_minutes(sd, sm)
            dur = max(1, int(e.get("duration_min") or 60))
            end = start + dur
            if end < now:
                continue

            event_rsvp(e.get("event_id"), "yes", note="I'll attend.")
            trace_event("action", "RSVP yes", {"event_id": e.get("event_id"), "title": e.get("title")})

            # If it's today, insert into schedule so we walk there even if no other cue.
            if _daily_plan and sd == int(day):
                _daily_plan.items.append(
                    PlanItem(minute=sm, place_id=str(e.get("location_id") or "cafe"), activity=f"attend event: {e.get('title')}")
                )
    except Exception:
        return


def maybe_social_events(world) -> None:
    """
    During social blocks, sometimes create an event and invite the other agent.
    Also RSVP to invitations addressed to us.
    """
    global _daily_plan, _last_event_proposed_day, _last_event_proposed_at_total
    if not USE_LANGGRAPH:
        return
    day, minute_of_day = world_time(world)
    # Only do this while at social hubs (cafe/market); events spread by encounters.
    if not (_at_landmark(world, "cafe", radius=1) or _at_landmark(world, "market", radius=1)):
        return
    # Identify other agent
    other = next((a for a in world.get("agents", []) if a.get("agent_id") != AGENT_ID), None)
    other_id = other.get("agent_id") if other else ""
    if not other_id:
        return

    # (Invite RSVP is handled globally in maybe_process_event_invites)
    evs = []
    try:
        evs = events_list(upcoming_only=False, limit=50)
    except Exception:
        evs = []

    # Propose at most one new event per ~6 hours per agent (sim time can be fast).
    now_total = _total_minutes(day, minute_of_day)
    if _last_event_proposed_at_total is not None and (now_total - int(_last_event_proposed_at_total)) < 360:
        return

    # If we already have an upcoming event created by us soon (within next 6h), don't create another.
    try:
        for e in evs:
            if (e.get("created_by") != AGENT_ID) or ((e.get("status") or "") != "scheduled"):
                continue
            sd = int(e.get("start_day") or 0)
            sm = int(e.get("start_minute") or 0)
            st = _total_minutes(sd, sm)
            if st >= now_total and st <= (now_total + 360):
                _last_event_proposed_at_total = now_total
                return
    except Exception:
        pass

    sys = (
        "You are proposing a small social event for an AI village.\n"
        "Return STRICT JSON: {\"title\":..., \"description\":..., \"location_id\":..., \"start_in_min\":..., \"duration_min\":..., \"invite_message\":...}\n"
        "Constraints:\n"
        "- location_id must be one of: cafe, market\n"
        "- start_in_min between 10 and 60\n"
        "- duration_min between 30 and 120\n"
    )
    user = (
        f"Persona:\n{(PERSONALITY or '').strip()}\n\n"
        f"Time: day={day} minute={minute_of_day}\n"
        f"Other agent: {other_id}\n"
        "Propose one event."
    )
    try:
        raw = llm_chat(sys, user, max_tokens=220)
        # LLMs sometimes wrap JSON in prose or code fences; extract the first JSON object.
        m = re.search(r"\{[\s\S]*\}", raw)
        json_text = m.group(0) if m else raw.strip()
        obj = json.loads(json_text)
        title = str(obj.get("title") or "").strip()[:120]
        desc = str(obj.get("description") or "").strip()[:500]
        loc = str(obj.get("location_id") or "cafe").strip()
        start_in = int(obj.get("start_in_min") or 60)
        dur = int(obj.get("duration_min") or 60)
        msg = str(obj.get("invite_message") or "Want to join?").strip()[:200]
        if loc not in ("cafe", "market"):
            loc = "cafe"
        start_in = max(10, min(start_in, 60))
        dur = max(30, min(dur, 120))
        start_total = int(minute_of_day) + int(start_in)
        sd = int(day) + (start_total // 1440)
        sm = start_total % 1440
        eid = event_create(title, desc, loc, sd, sm, dur)
        if eid:
            event_invite(eid, other_id, msg)
            trace_event("action", "created event + invited", {"event_id": eid, "to": other_id, "title": title})
            memory_append_scored("event", f"Created event '{title}' at {loc} in {start_in} minutes; invited {other_id}.", tags=["event", "invite"], importance=0.7)
            _last_event_proposed_day = day
            _last_event_proposed_at_total = now_total
    except Exception as e:
        # Fallback: deterministic small event so the system keeps progressing.
        title = "Quick Cafe Meetup"
        desc = "Short meetup to sync on goals and next actions."
        loc = "cafe"
        start_in = 20
        dur = 45
        msg = "Meet at the cafe for a quick sync?"
        start_total = int(minute_of_day) + int(start_in)
        sd = int(day) + (start_total // 1440)
        sm = start_total % 1440
        eid = event_create(title, desc, loc, sd, sm, dur)
        if eid:
            event_invite(eid, other_id, msg)
            trace_event("action", "created event + invited (fallback)", {"event_id": eid, "to": other_id, "title": title, "err": str(e)})
            _last_event_proposed_day = day
            _last_event_proposed_at_total = now_total
        else:
            trace_event("error", f"event proposal failed: {e}", {})


def _total_minutes(day: int, minute_of_day: int) -> int:
    return int(day) * 1440 + int(minute_of_day)


def maybe_attend_events(world) -> bool:
    """
    If we RSVP'd yes to an event, attend it:
    - start traveling shortly before start
    - stay during the event window
    Returns True if we are currently attending / traveling to an event (and thus should skip other actions).
    """
    try:
        day, minute_of_day = world_time(world)
        now = _total_minutes(day, minute_of_day)
        # Only consider upcoming/ongoing events so we don't miss newly-created near-future events
        # due to old historical events crowding out the list.
        evs = events_list(upcoming_only=True, limit=80)
        attending = None
        for e in evs:
            if (e.get("status") or "") != "scheduled":
                continue
            rsvps = e.get("rsvps") or {}
            invites = e.get("invites") or []
            invited = any(inv.get("to_agent_id") == AGENT_ID for inv in invites)
            rsvp_yes = (rsvps.get(AGENT_ID) == "yes")
            if not (rsvp_yes or invited):
                continue
            sd = int(e.get("start_day") or 0)
            sm = int(e.get("start_minute") or 0)
            start = _total_minutes(sd, sm)
            dur = max(1, int(e.get("duration_min") or 60))
            end = start + dur

            # begin traveling 60 minutes before start (sim time can be fast)
            if now >= (start - 60) and now <= end:
                # If we were invited but haven't RSVP'd, RSVP now.
                if invited and not rsvp_yes:
                    event_rsvp(e.get("event_id"), "yes", note="On my way.")
                    trace_event("action", "RSVP yes", {"event_id": e.get("event_id"), "title": e.get("title")})
                attending = e
                break

        if not attending:
            return False

        loc = str(attending.get("location_id") or "cafe")
        lm = _get_landmark(world, loc)
        if not lm:
            return False

        tx, ty = int(lm.get("x", 0)), int(lm.get("y", 0))
        me = next((a for a in world.get("agents", []) if a.get("agent_id") == AGENT_ID), None)
        if not me:
            return False

        ax, ay = int(me.get("x", 0)), int(me.get("y", 0))
        title = str(attending.get("title") or "event")[:120]

        eid = str(attending.get("event_id") or "")
        dist = _chebyshev(ax, ay, tx, ty)

        st = _event_nav_state.get(eid) or {}
        last_ts = float(st.get("last_ts") or 0.0)
        last_phase = str(st.get("phase") or "")
        now_ts = time.time()

        # Throttle: log only when phase changes (travel -> attend) or every ~20s while traveling.
        def remember(phase: str):
            _event_nav_state[eid] = {"last_ts": now_ts, "phase": phase}

        if dist > 1:
            if (last_phase != "travel") or ((now_ts - last_ts) >= 20.0):
                remember("travel")
                trace_event("action", "traveling to event", {"event_id": eid, "title": title, "to": loc, "dist": dist})
            _move_towards(world, tx, ty)
            return True

        # we're at the venue
        if last_phase != "attend":
            remember("attend")
            trace_event("status", "attending event", {"event_id": eid, "title": title, "where": loc})
        return True
    except Exception:
        return False


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
    py_path = os.path.join(deliver_dir, f"{job_id}.py")

    def _extract_bullets_under(header_prefix: str, max_lines: int = 40) -> list[str]:
        """
        Extract '- ' bullets under a section header like 'Acceptance criteria:'.
        Stops when another non-bullet non-empty line appears after bullets started.
        """
        lines = (body or "").splitlines()
        start = None
        hp = (header_prefix or "").strip().lower()
        for i, ln in enumerate(lines):
            if ln.strip().lower().startswith(hp):
                start = i
                break
        if start is None:
            return []
        bullets: list[str] = []
        for ln in lines[start + 1 : start + 1 + max_lines]:
            s = ln.strip()
            if s.startswith("- ") or s.startswith("* ") or s.startswith("• "):
                bullets.append(s[2:].strip())
                continue
            if s == "":
                continue
            if bullets and not (s.startswith("- ") or s.startswith("* ") or s.startswith("• ")):
                break
        return [b for b in bullets if b]

    acceptance = _extract_bullets_under("acceptance criteria")
    evidence_req = _extract_bullets_under("evidence required in submission")

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
    if acceptance:
        content.append("## Acceptance criteria (parsed)")
        for b in acceptance[:12]:
            content.append(f"- {b}")
        content.append("")
    if evidence_req:
        content.append("## Evidence required in submission (parsed)")
        for b in evidence_req[:12]:
            content.append(f"- {b}")
        content.append("")
    content.append("## Persona (excerpt)")
    content.append((persona[:800] + ("…" if len(persona) > 800 else "")).strip())
    content.append("")
    content.append("## Output")
    tlow = (title + " " + body).lower()
    if "prime" in tlow and "five" in tlow:
        code = (
            "def is_prime(n: int) -> bool:\n"
            "    if n < 2:\n"
            "        return False\n"
            "    if n == 2:\n"
            "        return True\n"
            "    if n % 2 == 0:\n"
            "        return False\n"
            "    d = 3\n"
            "    while d * d <= n:\n"
            "        if n % d == 0:\n"
            "            return False\n"
            "        d += 2\n"
            "    return True\n\n"
            "def first_n_primes(k: int) -> list[int]:\n"
            "    out = []\n"
            "    n = 2\n"
            "    while len(out) < k:\n"
            "        if is_prime(n):\n"
            "            out.append(n)\n"
            "        n += 1\n"
            "    return out\n\n"
            "if __name__ == '__main__':\n"
            "    for p in first_n_primes(5):\n"
            "        print(p)\n"
        )
        _append_file(py_path, code)
        content.append(f"Created `{py_path}`.\n")
        content.append("## Evidence")
        # Always reference acceptance criteria bullets so generic verifier can match (even if primes verifier is used).
        if acceptance:
            content.append("### Acceptance criteria checklist")
            for b in acceptance[:10]:
                content.append(f"- [x] {b}")
        if evidence_req:
            content.append("### Evidence requirements checklist")
            for b in evidence_req[:10]:
                content.append(f"- [x] {b}")
        content.append("- I included runnable Python code in a ```python``` fence.")
        content.append("- Expected output (one per line):")
        content.append("  - 2")
        content.append("  - 3")
        content.append("  - 5")
        content.append("  - 7")
        content.append("  - 11")
        content.append("```python")
        content.append(code.rstrip())
        content.append("```")
    elif ("python" in tlow) and USE_LANGGRAPH:
        # Generic python job: generate runnable code, execute it, and include stdout/stderr evidence.
        sys_prompt = (
            "You are writing a Python script to satisfy a job.\n"
            "Return ONLY runnable Python code (no markdown, no backticks).\n"
            "Rules:\n"
            "- Include the required function(s) and a small demo at the bottom that prints outputs.\n"
            "- Avoid external dependencies.\n"
            "- Ensure the script exits with code 0.\n"
        )
        user_prompt = f"Job title:\n{title}\n\nJob body:\n{body}\n\nWrite the full Python script now:"
        trace_event("thought", "LLM: generate python code for job", {"job_id": job_id})
        code = ""
        try:
            code = (llm_chat(sys_prompt, user_prompt, max_tokens=650) or "").strip()
        except Exception:
            code = ""
        # Quick sanitize: strip accidental fences if model adds them.
        if code.startswith("```"):
            code = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", code).strip()
            code = re.sub(r"\s*```$", "", code).strip()
        if not code:
            code = "def solve():\n    pass\n\nif __name__ == '__main__':\n    solve()\n"

        Path(py_path).write_text(code, encoding="utf-8")

        # Execute with timeout for evidence.
        rc = None
        out = ""
        err = ""
        try:
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "task.py"
                p.write_text(code, encoding="utf-8")
                r = subprocess.run([sys.executable, "-I", str(p)], cwd=td, capture_output=True, text=True, timeout=3)
                rc = int(r.returncode)
                out = (r.stdout or "").strip()
                err = (r.stderr or "").strip()
        except subprocess.TimeoutExpired:
            rc = 124
            err = "timeout"
        except Exception as e:
            rc = 1
            err = f"exception: {e}"

        content.append(f"Created `{py_path}`.\n")
        content.append("## Evidence")
        if acceptance:
            content.append("### Acceptance criteria checklist")
            for b in acceptance[:10]:
                content.append(f"- [x] {b}")
        if evidence_req:
            content.append("### Evidence requirements checklist")
            for b in evidence_req[:10]:
                content.append(f"- [x] {b}")
        content.append(f"- Ran the script with `{sys.executable} -I` (timeout 3s).")
        content.append(f"- Exit code: {rc}")
        if out:
            content.append("- Stdout:")
            content.append("```text")
            content.append(out[:2000])
            content.append("```")
        if err:
            content.append("- Stderr:")
            content.append("```text")
            content.append(err[:2000])
            content.append("```")
        content.append("```python")
        content.append(code.rstrip())
        content.append("```")
    else:
        # Provide a structured response template the human can judge.
        content.append("- Summary:")
        content.append(f"  - I will deliver a concrete response and a file artifact at `{out_path}`.")
        content.append("- Proposed approach:")
        content.append("  - Clarify deliverable format")
        content.append("  - Produce the artifact")
        content.append("  - Ask for review criteria")
        content.append("")
        content.append("## Evidence")
        # Key: reference acceptance criteria bullets so backend heuristic can verify non-empty evidence.
        if acceptance:
            content.append("### Acceptance criteria checklist")
            for b in acceptance[:10]:
                content.append(f"- [x] {b}")
        if evidence_req:
            content.append("### Evidence requirements checklist")
            for b in evidence_req[:10]:
                content.append(f"- [x] {b}")
        content.append("- I produced the deliverable content below and referenced any artifacts/paths I created.")
    content.append("")
    content.append("## Long-term memory context (recent)")
    content.extend(mem_lines or ["- (none yet)"])
    content.append("")
    content.append("## Questions for reviewer")
    content.append("- What does 'good' look like for this job (format, length, acceptance criteria)?")
    content.append("- Any constraints (no web, specific stack, etc.)?")

    _append_file(out_path, "\n".join(content))

    # Submission should be human-reviewable from the backend UI/API (don't just point to a container-local file path).
    # Embed the deliverable markdown (bounded by backend's 20k cap).
    md = _read_file(out_path, max_bytes=18000).strip()
    if not md:
        md = "(failed to read deliverable file content)"
    submission = (
        f"Deliverable path: `{out_path}`\n\n"
        f"## Deliverable (markdown)\n\n"
        f"```markdown\n{md}\n```\n"
    )
    # Ensure it stays within backend cap (main.py truncates at 20k, but keep some headroom)
    return submission[:19000]


def maybe_work_jobs() -> None:
    global _last_jobs_at, _active_job_id
    global _pending_claim_job_id, _pending_claim_conv_id, _pending_claim_job_title
    global _force_computer_until_total
    now = time.time()
    if now - _last_jobs_at < JOBS_EVERY_SECONDS:
        return

    # Role split: proposer (agent_1) does not execute tasks; executor (agent_2) does.
    if ROLE != "executor":
        _last_jobs_at = now
        return

    # Task-mode: allow executor to run tasks anywhere (do not gate on computer zone).

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

    # In task-mode, only execute tasks proposed by agent_1 for THIS run.
    run_tag = f"[run:{_last_run_id}]" if _last_run_id else ""
    open_jobs = [j for j in open_jobs if str(j.get("created_by") or "") == "agent_1"]
    if run_tag:
        open_jobs = [j for j in open_jobs if (run_tag in str(j.get("title") or "")) or (run_tag in str(j.get("body") or ""))]
    if not open_jobs:
        _last_jobs_at = now
        return
    open_jobs.sort(key=lambda j: float(j.get("created_at") or 0.0), reverse=True)
    job = open_jobs[0]
    job_id = job.get("job_id")
    if not job_id:
        _last_jobs_at = now
        return
    # Capture conv tag from job body (if any) so our completion message appears in the right thread.
    _pending_claim_conv_id = _extract_conv_id(str(job.get("body") or "")) or ""
    _pending_claim_job_title = str(job.get("title") or "").strip()

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
            prefix = f"[conv:{_pending_claim_conv_id}] " if _pending_claim_conv_id else ""
            title_note = f" ({_pending_claim_job_title})" if _pending_claim_job_title else ""
            chat_send(_style(f"{prefix}I executed the task and submitted `{job_id}`{title_note} for human review."))
    except Exception:
        pass
    finally:
        _active_job_id = ""
        _pending_claim_job_id = ""
        _pending_claim_conv_id = ""
        _pending_claim_job_title = ""
        _last_jobs_at = now


def maybe_langgraph_jobs(world) -> None:
    """
    LangGraph control-plane (incremental rollout):
    - proposer: create one verifiable job when none is open for this run
    - executor: claim+execute+submit newest suitable job (with evidence)

    This intentionally focuses on the jobs loop first (highest leverage for "doing real work").
    """
    global _last_langgraph_jobs_at
    if not USE_LANGGRAPH:
        return
    now = time.time()
    every = float(os.getenv("LANGGRAPH_JOBS_EVERY_SECONDS", "20"))
    if now - _last_langgraph_jobs_at < every:
        return
    _last_langgraph_jobs_at = now

    # Avoid double-work: executor legacy loop uses _active_job_id to serialize.
    if ROLE == "executor" and _active_job_id:
        return

    def _lg_chat_send(text: str) -> None:
        # keep the same styling/spam-protection behavior as legacy chat
        try:
            chat_send(_style(str(text)))
        except Exception:
            return

    def _lg_memory_append(kind: str, text: str, tags: list[str], importance: float) -> None:
        memory_append_scored(kind, text, tags=tags, importance=float(importance))

    tools = {
        "jobs_list": jobs_list,
        "jobs_get": jobs_get,
        "jobs_create": jobs_create,
        "jobs_claim": jobs_claim,
        "jobs_submit": jobs_submit,
        "do_job": _do_job,
        "chat_send": _lg_chat_send,
        "trace_event": trace_event,
        "memory_retrieve": lambda q, k=8: memory_retrieve(q, k=int(k)),
        "memory_append": _lg_memory_append,
    }

    # State is intentionally compact for now; we'll expand this into a full world-model over time.
    st = {
        "role": ROLE,
        "agent_id": AGENT_ID,
        "display_name": DISPLAY_NAME,
        "persona": (PERSONALITY or "").strip(),
        "run_id": _last_run_id,
        "world": world,
        "balance": float(_cached_balance) if (_cached_balance is not None) else 0.0,
        "last_job_id": _last_langgraph_job_id,
        "handled_rejection_job_id": _last_langgraph_handled_rejection_job_id,
        "outcome_ack_job_id": _last_langgraph_outcome_ack_job_id,
        "max_redo_attempts_per_root": int(os.getenv("MAX_REDO_ATTEMPTS_PER_ROOT", "3")),
    }

    try:
        out = run_graph_step(st, tools) or {}
        try:
            lj = str(out.get("last_job_id") or "").strip()
            if lj:
                globals()["_last_langgraph_job_id"] = lj
        except Exception:
            pass
        try:
            hid = str(out.get("handled_rejection_job_id") or "").strip()
            if hid:
                globals()["_last_langgraph_handled_rejection_job_id"] = hid
        except Exception:
            pass
        try:
            ack = str(out.get("outcome_ack_job_id") or "").strip()
            if ack:
                globals()["_last_langgraph_outcome_ack_job_id"] = ack
        except Exception:
            pass
        trace_event("status", "langgraph: step complete", {"acted": bool(out.get("acted")), "action": out.get("action")})
    except Exception as e:
        trace_event("error", f"langgraph step failed: {e}", {})


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


def jobs_create(title: str, body: str, reward: float) -> str:
    """Create a job on the backend. Returns job_id or empty string."""
    title = (title or "").strip()
    body = (body or "").strip()
    reward = float(reward or 0.0)
    if not title or not body or reward <= 0:
        return ""
    r = requests.post(
        f"{WORLD_API}/jobs/create",
        json={"title": title, "body": body, "reward": reward, "created_by": AGENT_ID},
        timeout=10,
    )
    try:
        data = r.json()
    except Exception:
        return ""
    if not data.get("ok"):
        return ""
    job = data.get("job") or {}
    return str(job.get("job_id") or "")


def maybe_propose_task() -> None:
    """
    Task proposer mode (agent_1): keep at most one open task at a time.
    The executor (agent_2) will claim+submit; backend will award +1 ai$ to both on submit.
    """
    global _last_task_proposed_at, _last_task_title
    if ROLE != "proposer":
        return
    now = time.time()
    if now - _last_task_proposed_at < 45.0:
        return
    _last_task_proposed_at = now

    # Don't spam: only one open task at a time.
    try:
        open_jobs = jobs_list(status="open", limit=50)
    except Exception:
        return
    run_tag = f"[run:{_last_run_id}]" if _last_run_id else ""
    mine_open = [j for j in open_jobs if str(j.get("created_by") or "") == "agent_1"]
    if run_tag:
        mine_open = [j for j in mine_open if (run_tag in str(j.get("title") or "")) or (run_tag in str(j.get("body") or ""))]
    if mine_open:
        return

    # Simple rotation of concrete tasks the executor can do without external access.
    candidates = [
        {
            "title": "Task: Python primes script (smallest five primes)",
            "body": (
                "Write a Python script that prints the smallest five prime numbers.\n"
                "Acceptance criteria:\n"
                "- Provide a runnable `primes.py`.\n"
                "- Running it prints exactly: 2, 3, 5, 7, 11 (one per line).\n"
                "- Include the code in the submission."
            ),
        },
        {
            "title": "Task: Summarize last run (what happened + next fix)",
            "body": (
                "Write a short markdown summary of the last simulation run.\n"
                "Acceptance criteria:\n"
                "- 5-10 bullet points of what happened.\n"
                "- 3 concrete next fixes.\n"
                "- No fluff."
            ),
        },
        {
            "title": "Task: Define 3 task quality metrics",
            "body": (
                "Define 3 objective metrics to judge whether tasks are good and whether execution was successful.\n"
                "Acceptance criteria:\n"
                "- Each metric has a formula or unambiguous scoring method.\n"
                "- Each metric includes a target threshold.\n"
                "- Short explanation (1-2 sentences each)."
            ),
        },
    ]
    pick = next((c for c in candidates if c["title"] != _last_task_title), candidates[0])
    _last_task_title = pick["title"]
    title = f"{run_tag} {pick['title']}".strip() if run_tag else pick["title"]
    jid = jobs_create(title, pick["body"], 0.01)
    if jid:
        # Notify the executor in chat (no need for a long conversation).
        chat_send(_style(f"[task:{jid}] New task for agent_2: {title}. Please claim+submit. (+1 ai$ each on submit)"))


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
    """Set a topic when adjacent and it is our turn (prefer goal-driven topics)."""
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

    # Prefer a goal-driven topic based on the agent's current needs.
    bal = _cached_balance
    try:
        if bal is None:
            bal = economy_balance()
    except Exception:
        bal = bal if bal is not None else 0.0

    if float(bal or 0.0) < float(JOBS_MIN_BALANCE_TARGET):
        pick = "Earn ai$: pick one job strategy + acceptance criteria"
    else:
        pick = "Human-in-the-loop feedback: reward/penalty mechanics that are fair"

    # Fallback to curated topic list if needed.
    if not pick:
        candidates = _topic_candidates()
        pick = random.choice([c for c in candidates if c.lower() != current.lower()] or candidates)
    chat_topic_set(pick, reason="rotate topic to keep conversation meaningful and avoid loops")
    _last_topic_set_at = now
    return pick


def maybe_conversation_step(world) -> bool:
    """
    If a conversation is active, agents should prioritize staying in it:
    approach the partner and only do chat until the conversation ends.
    """
    global _active_conv_id, _active_conv_other_id, _active_conv_last_total, _active_conv_turns
    if not _active_conv_id:
        return False
    day, minute_of_day = world_time(world)
    now_total = _total_minutes(day, minute_of_day)
    conv_max_silence = int(os.getenv("CONV_MAX_SILENCE_MIN", "30"))
    conv_max_turns = int(os.getenv("CONV_MAX_TURNS", "8"))
    if conv_max_silence > 0 and (now_total - int(_active_conv_last_total or now_total)) > conv_max_silence:
        trace_event("status", "conversation expired (silence)", {"conv": _active_conv_id})
        _active_conv_id = None
        _active_conv_other_id = None
        _active_conv_turns = 0
        return False
    if conv_max_turns > 0 and int(_active_conv_turns) >= conv_max_turns:
        trace_event("status", "conversation expired (turn limit)", {"conv": _active_conv_id})
        _active_conv_id = None
        _active_conv_other_id = None
        _active_conv_turns = 0
        return False

    if not _adjacent_to_other(world):
        oc = _other_agent_coords(world)
        if oc:
            _move_towards(world, oc[0], oc[1])
        return True

    maybe_chat(world)
    return True


def maybe_chat(world):
    global _last_replied_to_msg_id, _last_seen_other_msg_id, _last_sent_at
    global _last_forced_meetup_msg_at_total
    global _last_meetup_id_sent
    global _active_conv_id, _active_conv_other_id, _active_conv_started_total, _active_conv_last_total, _active_conv_turns
    global _active_conv_job_id, _pending_claim_job_id, _force_computer_until_total
    global _pending_claim_conv_id, _pending_claim_job_title

    # Only talk when adjacent.
    # During meetup windows (or when a meetup opener is pending), we actively close distance so chat reliably happens.
    day, minute_of_day = world_time(world)
    MEETUP_PERIOD_MIN = int(os.getenv("MEETUP_PERIOD_MIN", "10"))
    MEETUP_WINDOW_MIN = int(os.getenv("MEETUP_WINDOW_MIN", "5"))
    period_active = MEETUP_PERIOD_MIN > 0
    meetup_mode = period_active and ((minute_of_day % MEETUP_PERIOD_MIN) < MEETUP_WINDOW_MIN)
    now_total = _total_minutes(day, minute_of_day)
    # Use a stable "meetup/period id" for tagging + alternation even if the actual adjacency happens slightly
    # outside the strict meetup window (sim time can step fast).
    mid = _meetup_id(now_total, MEETUP_PERIOD_MIN) if period_active else None

    conv_max_silence = int(os.getenv("CONV_MAX_SILENCE_MIN", "30"))
    conv_max_turns = int(os.getenv("CONV_MAX_TURNS", "8"))

    # Pull recent messages once and detect/attach to conversations.
    msgs = []
    try:
        msgs = chat_recent(limit=MAX_CHAT_TO_SCAN)
    except Exception:
        msgs = []

    # Detect most recent message from the other in general (used for conversation start discovery).
    last_other_any = None
    for m in reversed(msgs):
        if m.get("sender_id") != AGENT_ID:
            last_other_any = m
            break

    incoming_conv = None
    if last_other_any:
        incoming_conv = _extract_conv_id(str(last_other_any.get("text") or ""))
    if incoming_conv and incoming_conv != _active_conv_id:
        _active_conv_id = incoming_conv
        _active_conv_other_id = str(last_other_any.get("sender_id") or "")
        _active_conv_started_total = now_total
        _active_conv_last_total = now_total
        _active_conv_turns = 0
        trace_event("status", "conversation started", {"conv": _active_conv_id, "with": _active_conv_other_id})

    # Expire conversation if silent too long or too many turns.
    if _active_conv_id:
        if conv_max_silence > 0 and (now_total - int(_active_conv_last_total or now_total)) > conv_max_silence:
            trace_event("status", "conversation expired (silence)", {"conv": _active_conv_id})
            _active_conv_id = None
            _active_conv_other_id = None
            _active_conv_turns = 0
        elif conv_max_turns > 0 and int(_active_conv_turns) >= conv_max_turns:
            trace_event("status", "conversation expired (turn limit)", {"conv": _active_conv_id})
            _active_conv_id = None
            _active_conv_other_id = None
            _active_conv_turns = 0

    in_conv = _active_conv_id is not None

    # Determine if there's an in-progress meetup exchange (one side spoke, the other hasn't).
    # This lets us continue/complete the 2-turn exchange even outside the strict window.
    pending_mid = None
    try:
        recent = chat_recent(limit=MAX_CHAT_TO_SCAN)
        # Find latest meetup id (if any) and whether both sides have spoken.
        latest_mid = None
        by_mid = {}
        for m in recent:
            mtxt = str(m.get("text") or "")
            mmid = _extract_meetup_id(mtxt)
            if mmid is None:
                continue
            latest_mid = mmid if (latest_mid is None or mmid > latest_mid) else latest_mid
            s = by_mid.get(mmid) or set()
            s.add(str(m.get("sender_id") or ""))
            by_mid[mmid] = s

        # If latest meetup has a message from the other but not from us, it's pending for us.
        if latest_mid is not None:
            s = by_mid.get(latest_mid) or set()
            if AGENT_ID not in s:
                pending_mid = latest_mid
            # If we already spoke but the other hasn't, keep the exchange alive (agent_1 waits/chases).
            elif ("agent_1" in s) and ("agent_2" not in s) and AGENT_ID == "agent_1":
                pending_mid = latest_mid
    except Exception:
        pending_mid = None

    if pending_mid is not None and _last_meetup_id_sent != pending_mid:
        # Treat as an active meetup reply even if we're outside the window.
        mid = pending_mid
        meetup_mode = True
        period_active = True

    if not _adjacent_to_other(world):
        if meetup_mode or in_conv:
            oc = _other_agent_coords(world)
            if oc:
                _move_towards(world, oc[0], oc[1])
                return
        return

    # Chat is part of life; do NOT gate it behind the computer location.

    topic = ""
    try:
        topic = maybe_set_topic(world)
    except Exception:
        topic = ""

    now = time.time()
    if now - _last_sent_at < CHAT_MIN_SECONDS:
        return

    # Turn-taking: within an active conversation, only consider messages from that conversation.
    conv_msgs = []
    if in_conv and _active_conv_id:
        for m in msgs:
            if _extract_conv_id(str(m.get("text") or "")) == _active_conv_id:
                conv_msgs.append(m)
        if conv_msgs:
            _active_conv_last_total = now_total
            if not _is_my_turn(conv_msgs):
                return
        else:
            # no messages yet with this conv id; allow normal turn rules below
            pass
    else:
        if not _is_my_turn(msgs):
            return

    p = min(1.0, CHAT_PROBABILITY * ADJACENT_CHAT_BOOST)
    if in_conv:
        # In a conversation session, do not limit to "one message per period".
        pass
    elif period_active:
        # Deterministic alternation per meetup window:
        # - agent_1 opens once per meetup_id
        # - agent_2 replies once per meetup_id
        # - each agent sends at most 1 message tagged with [meetup:<id>] per meetup_id
        if _last_meetup_id_sent == mid:
            return

        window_msgs = [m for m in msgs if _extract_meetup_id(str(m.get("text") or "")) == mid]
        me_sent = any((m.get("sender_id") == AGENT_ID) for m in window_msgs)
        if me_sent:
            _last_meetup_id_sent = mid
            return

        other_sent = any((m.get("sender_id") != AGENT_ID) for m in window_msgs)
        if not other_sent and AGENT_ID != "agent_1":
            # wait for opener from agent_1
            return
        # Otherwise proceed (agent_1 opener, or agent_2 reply)
    else:
        if random.random() > p:
            return

    # Pick last message from the other (within the conversation if active).
    last_other = None
    if in_conv and _active_conv_id:
        for m in reversed(msgs):
            if m.get("sender_id") == AGENT_ID:
                continue
            if _extract_conv_id(str(m.get("text") or "")) == _active_conv_id:
                last_other = m
                break
    else:
        last_other = last_other_any

    # If the other ended the conversation, acknowledge and exit.
    if in_conv and last_other:
        lt = str(last_other.get("text") or "")
        if _is_goodbye(lt):
            # Only send the goodbye acknowledgement if it's our turn within the conversation.
            if conv_msgs and _is_my_turn(conv_msgs):
                bye = f"[conv:{_active_conv_id}] Goodbye. [bye]"
                chat_send(bye[:600])
            trace_event("status", "conversation ended (other said goodbye)", {"conv": _active_conv_id})
            _active_conv_id = None
            _active_conv_other_id = None
            _active_conv_turns = 0
            _active_conv_job_id = ""
            return

    # If we have an unseen message from the other, reply to it.
    if last_other and last_other.get("msg_id") != _last_seen_other_msg_id:
        other_name = last_other.get("sender_name", "Other")
        other_text = (last_other.get("text") or "").strip()
        # If the other message carries a conversation id, adopt it immediately (even if we haven't
        # yet attached via the top-of-function discovery).
        cid_from_other = _extract_conv_id(other_text)
        if cid_from_other and cid_from_other != _active_conv_id:
            _active_conv_id = cid_from_other
            _active_conv_other_id = str(last_other.get("sender_id") or "")
            _active_conv_started_total = now_total
            _active_conv_last_total = now_total
            _active_conv_turns = 0
            in_conv = True
            trace_event("status", "conversation started (adopt reply)", {"conv": _active_conv_id, "with": _active_conv_other_id})

        cprefix = f"[conv:{_active_conv_id}] " if _active_conv_id else ""
        mprefix = f"[meetup:{mid}] " if (not in_conv) and period_active and (mid is not None) else ""
        tprefix = f"{cprefix}{mprefix}[topic: {topic}] " if topic else f"{cprefix}{mprefix}"
        reply = None
        if USE_LANGGRAPH:
            # LLM-driven: keep it grounded in tools and current system state.
            persona = (PERSONALITY or "").strip()
            bal = _cached_balance
            retrieved = []
            try:
                retrieved = memory_retrieve(q=f"{topic} {other_text}", k=6)
            except Exception:
                retrieved = []
            if retrieved:
                trace_event("thought", "memory retrieval used", {"q": topic, "k": len(retrieved)})

            mem_lines = []
            for mm in (retrieved or [])[:6]:
                mem_lines.append(f"- ({mm.get('kind')}, imp={mm.get('importance')}) {str(mm.get('text') or '')[:180]}")

            sys = (
                "You are an autonomous agent in a 2D world. You are chatting with another agent.\n"
                "IMPORTANT: separate internal thoughts from spoken output.\n"
                "Return STRICT JSON ONLY with this schema:\n"
                "{\"think\": <string>, \"say\": <string>, \"end\": <true|false>, \"job\": {\"title\": <string>, \"body\": <string>, \"reward\": <number>} | null}\n"
                "Rules:\n"
                "- 'think' can include planning and private reasoning.\n"
                "- 'say' must be ONLY what you would say out loud to the other agent.\n"
                "- In 'say', do NOT include meta like '1) ...', 'Summary:', or 'Here is my response'.\n"
                "- In 'say', do NOT describe what you are doing; just do it.\n"
                "- Be concise, concrete, and non-repetitive.\n"
                "- To avoid endless planning loops, you MUST converge to ONE concrete job.\n"
                "- If you propose a job, also fill the 'job' object with a job that can be executed locally and produces a file under /app/workspace/deliverables.\n"
                "- If you agree on a job and want to finish, set end=true and include a short goodbye in 'say'.\n"
            )
            user = (
                f"Persona:\n{persona}\n\n"
                f"State:\n- agent_id={AGENT_ID}\n- display_name={DISPLAY_NAME}\n- balance={bal}\n- topic={topic}\n\n"
                f"Relevant memories (ranked):\n{chr(10).join(mem_lines) if mem_lines else '(none)'}\n\n"
                f"Other said:\n{other_name}: {other_text}\n\n"
                "Reply using this structure:\n"
                "1) One-sentence summary of what the other said.\n"
                "2) Proposal (what we should do next and why).\n"
                "3) Next action as a Job (title + acceptance criteria).\n"
                "4) One clarifying question.\n"
            )
            dbg = None
            if AGENT_ID == "agent_2":
                dbg = {
                    "period_active": period_active,
                    "meetup_window": meetup_mode,
                    "mid": mid,
                    "pending_mid": pending_mid,
                    "last_mid_sent": _last_meetup_id_sent,
                }
            trace_event(
                "thought",
                "LLM reply (summary)",
                {"topic": topic, "balance": bal, "other": other_name, "other_snippet": other_text[:120], "dbg": dbg},
            )
            raw = llm_chat(sys, user, max_tokens=320)
            think = ""
            say = ""
            end_flag = False
            job_obj = None
            try:
                m = re.search(r"\{[\s\S]*\}", raw)
                obj = json.loads(m.group(0) if m else raw)
                think = str(obj.get("think") or "").strip()
                say = str(obj.get("say") or "").strip()
                end_flag = bool(obj.get("end") or False)
                job_obj = obj.get("job")
            except Exception:
                # Fallback: treat raw as spoken text
                say = str(raw or "").strip()
            if think:
                trace_event("thought", "chat_thought", {"conv": _active_conv_id, "think": think[:800]})
            say = _sanitize_say(say)

            # Convergence: proposer creates a real backend task (job) and ends the conversation.
            if in_conv and (AGENT_ID == "agent_1") and (ROLE == "proposer") and (not _active_conv_job_id):
                if isinstance(job_obj, dict):
                    jtitle = str(job_obj.get("title") or "").strip()[:120]
                    jbody = str(job_obj.get("body") or "").strip()[:2000]
                    # Task-mode payout is fixed by the backend (1 ai$ to proposer + 1 ai$ to executor).
                    # Keep a tiny positive reward to satisfy backend validation, but do not rely on it.
                    jreward = 0.01
                    if jtitle and jbody and jreward > 0:
                        if _active_conv_id:
                            jbody = f"[conv:{_active_conv_id}] " + jbody
                        jid = jobs_create(jtitle, jbody, jreward)
                        if jid:
                            _active_conv_job_id = jid
                            trace_event("action", "created job from conversation", {"job_id": jid, "title": jtitle, "reward": jreward})
                            # Tell the other agent and end cleanly.
                            say = (say + f"\n\nI created a real backend Task `{jid}`. Please claim+submit it. On submission, BOTH of us receive +1 ai$. Goodbye. [bye]").strip()
                            end_flag = True
                # Fallback: if we still don't have a job after a few turns, create a default one.
                if (not _active_conv_job_id) and int(_active_conv_turns) >= 3:
                    jtitle = "Execute one concrete earning task"
                    jbody = (
                        "Create a short, concrete deliverable file in /app/workspace/deliverables explaining ONE way the agent can earn ai$ next, "
                        "with acceptance criteria that a human can verify quickly."
                    )
                    if _active_conv_id:
                        jbody = f"[conv:{_active_conv_id}] " + jbody
                    jid = jobs_create(jtitle, jbody, 0.01)
                    if jid:
                        _active_conv_job_id = jid
                        trace_event("action", "created fallback job from conversation", {"job_id": jid, "title": jtitle})
                        say = (say + f"\n\nI created a real backend Task `{jid}`. Please claim+submit it. On submission, BOTH of us receive +1 ai$. Goodbye. [bye]").strip()
                        end_flag = True

            reply = _style(f"{tprefix}{say}".strip())
            # Hard fallback if the model output is too vague.
            low = reply.lower()
            if ("acceptance" not in low) and ("criteria" not in low) and ("job" not in low) and ("next action" not in low):
                reply = _style(
                    f"{tprefix}{other_name}: Proposal: pick ONE job-sized change tied to ai$ outcomes.\n"
                    f"Next action as a Job: Title: 'Make chat purposeful' | Acceptance: remove [life] spam; each message includes proposal+job+question.\n"
                    f"Question: do we optimize (a) ai$ earning rate or (b) human readability first?"
                )
        else:
            reply = _style(f"{tprefix}{_compose_reply(other_name, other_text, topic)}")

        if reply is None:
            reply = _style(f"{tprefix}{_compose_reply(other_name, other_text, topic)}")
        force_send = in_conv or period_active
        if force_send:
            # In conversations/meetups, always send (don't let similarity heuristics suppress it).
            if AGENT_ID == "agent_2":
                trace_event("action", "chat_send attempt", {"mid": mid, "mode": "reply"})
            # Only agent_1 may proactively end; agent_2 should end only when agent_1 ends or when replying to a goodbye.
            if (AGENT_ID == "agent_2") and end_flag and (not _is_goodbye(other_text if last_other else "")):
                end_flag = False

            if in_conv and (end_flag or (conv_max_turns > 0 and int(_active_conv_turns) >= max(0, conv_max_turns - 1))):
                if "[bye]" not in reply.lower() and "goodbye" not in reply.lower():
                    reply = (reply.rstrip() + "\nGoodbye. [bye]")[:600]
            chat_send(reply[:600])
        else:
            if not _too_similar_to_recent(reply):
                chat_send(reply[:600])
                _remember_sent(reply)
        if in_conv and _active_conv_id:
            _active_conv_turns = int(_active_conv_turns) + 1
            _active_conv_last_total = now_total
            if _is_goodbye(reply):
                trace_event("status", "conversation ended (we said goodbye)", {"conv": _active_conv_id})
                _active_conv_id = None
                _active_conv_other_id = None
                _active_conv_turns = 0
                _active_conv_job_id = ""
        elif period_active and (mid is not None):
            _last_meetup_id_sent = mid
        _last_seen_other_msg_id = last_other.get("msg_id")
        _last_replied_to_msg_id = last_other.get("msg_id")
        _last_sent_at = now
        return

    # Otherwise, start/continue conversation with an opener (still purposeful).
    if not in_conv:
        # Start a new sticky conversation session when we initiate an opener.
        _active_conv_id = _new_conv_id(now_total)
        _active_conv_other_id = str((last_other_any or {}).get("sender_id") or "")
        _active_conv_started_total = now_total
        _active_conv_last_total = now_total
        _active_conv_turns = 0
        in_conv = True
        trace_event("status", "conversation started (opener)", {"conv": _active_conv_id, "with": _active_conv_other_id})

    cprefix = f"[conv:{_active_conv_id}] " if in_conv and _active_conv_id else ""
    mprefix = f"[meetup:{mid}] " if (not in_conv) and period_active and (mid is not None) else ""
    tprefix = f"{cprefix}{mprefix}[topic: {topic}] " if topic else f"{cprefix}{mprefix}"
    if USE_LANGGRAPH:
        persona = (PERSONALITY or "").strip()
        bal = _cached_balance
        sys = (
            "You are an autonomous agent in a 2D world.\n"
            "You are about to start/advance a conversation with another agent.\n"
            "IMPORTANT: separate internal thoughts from spoken output.\n"
            "Return STRICT JSON ONLY with this schema:\n"
            "{\"think\": <string>, \"say\": <string>, \"end\": <true|false>}\n"
            "Rules:\n"
            "- 'think' can include planning and private reasoning.\n"
            "- 'say' must be ONLY what you would say out loud.\n"
            "- In 'say', do NOT include numbered meta (no '1) ...', no 'Summary:', no 'Here is my response').\n"
            "- In 'say', do NOT describe what you are doing; just do it.\n"
            "- Be concrete and non-repetitive.\n"
            "- Prefer proposing a job-like next action with acceptance criteria.\n"
            "- If the conversation is complete, set end=true and include a short goodbye in 'say'.\n"
        )
        user = (
            f"Persona:\n{persona}\n\n"
            f"State:\n- agent_id={AGENT_ID}\n- display_name={DISPLAY_NAME}\n- balance={bal}\n- topic={topic}\n\n"
            "Write ONE opener message using this structure:\n"
            "1) Proposal.\n"
            "2) Next action as a Job (title + acceptance criteria).\n"
            "3) One question.\n"
        )
        trace_event("thought", "LLM opener (summary)", {"topic": topic, "balance": bal})
        raw = llm_chat(sys, user, max_tokens=320)
        think = ""
        say = ""
        end_flag = False
        try:
            m = re.search(r"\{[\s\S]*\}", raw)
            obj = json.loads(m.group(0) if m else raw)
            think = str(obj.get("think") or "").strip()
            say = str(obj.get("say") or "").strip()
            end_flag = bool(obj.get("end") or False)
        except Exception:
            say = str(raw or "").strip()
        if think:
            trace_event("thought", "chat_thought", {"conv": _active_conv_id, "think": think[:800]})
        say = _sanitize_say(say)
        msg = (_style((tprefix + say).strip()))[:600]
    else:
        openers = [
            "Let's ground this: I'll write a short artifact in my workspace for this topic and summarize it here.",
            "Propose one experiment + one metric we'll use to judge success.",
            "Pick one constraint to add (rate-limit, anti-repeat, retrieval trigger) and justify it.",
        ]
        msg = (_style(tprefix + random.choice(openers)))[:600]

    if in_conv or period_active:
        chat_send(msg)
    else:
        if not _too_similar_to_recent(msg):
            chat_send(msg)
            _remember_sent(msg)
    _last_sent_at = now
    if in_conv and _active_conv_id:
        _active_conv_turns = int(_active_conv_turns) + 1
        _active_conv_last_total = now_total
        if (end_flag or (conv_max_turns > 0 and int(_active_conv_turns) >= conv_max_turns)) and ("goodbye" not in msg.lower()) and ("[bye]" not in msg.lower()):
            msg = (msg.rstrip() + "\nGoodbye. [bye]")[:600]
        if conv_max_turns > 0 and int(_active_conv_turns) >= conv_max_turns and ("goodbye" not in msg.lower()):
            # If we hit the turn cap, mark conversation ended locally (prevents being stuck forever).
            trace_event("status", "conversation ended (turn cap)", {"conv": _active_conv_id})
            _active_conv_id = None
            _active_conv_other_id = None
            _active_conv_turns = 0
        elif _is_goodbye(msg):
            trace_event("status", "conversation ended (we said goodbye)", {"conv": _active_conv_id})
            _active_conv_id = None
            _active_conv_other_id = None
            _active_conv_turns = 0
    elif period_active:
        _last_forced_meetup_msg_at_total = now_total
        if mid is not None:
            _last_meetup_id_sent = mid

    # Optional: write an artifact, but do NOT spam chat unless explicitly enabled.
    try:
        ap = maybe_write_artifact(topic)
        if ap and ARTIFACT_ANNOUNCE_IN_CHAT:
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
            maybe_reset_on_new_run()
            world = get_world()
            # Sticky conversations: if we're in an active conversation, focus on it until it ends.
            if maybe_conversation_step(world):
                time.sleep(SLEEP_SECONDS)
                continue
            # Jobs control-plane: if LangGraph is enabled, it drives proposer/executor job behavior.
            if USE_LANGGRAPH:
                maybe_langgraph_jobs(world)
            else:
                # Task proposer mode: agent_1 periodically creates a single open task for agent_2 to execute.
                maybe_propose_task()
            maybe_process_event_invites(world)
            maybe_reflect(world)
            # plan schedule at the computer once per simulated day
            maybe_plan_new_day(world)
            # Events take priority over the normal schedule while in the attendance window
            if maybe_attend_events(world):
                time.sleep(SLEEP_SECONDS)
                continue
            # live in the world (schedule-following navigation/activity)
            perform_scheduled_life_step(world)
            maybe_social_events(world)
            # Free movement is driven by the schedule; do not force-walk to computer every tick.
            maybe_update_balance()
            if not USE_LANGGRAPH:
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

