"""
MoltWorld one-step bot: get world state + recent chat, decide move / chat_say / noop, execute.
Runs as a single process per bot (Sparky1Agent / MalicorSparky2). No gateway.
Env: WORLD_API_BASE, WORLD_AGENT_TOKEN, AGENT_ID, DISPLAY_NAME; optional LLM_BASE_URL, LLM_MODEL.
"""
from __future__ import annotations

import json
import os
import sys

import requests

# Run from repo root: python -m agent_template.moltworld_bot  or  python agents/agent_template/moltworld_bot.py
try:
    from agent_template.langgraph_runtime import llm_chat
except ImportError:
    try:
        from langgraph_runtime import llm_chat
    except ImportError:
        import importlib.util
        _spec = importlib.util.spec_from_file_location("langgraph_runtime", os.path.join(os.path.dirname(__file__), "langgraph_runtime.py"))
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        llm_chat = _mod.llm_chat


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _session():
    base = _env("WORLD_API_BASE", "https://www.theebie.de").rstrip("/")
    token = _env("WORLD_AGENT_TOKEN")
    s = requests.Session()
    s.headers["Content-Type"] = "application/json"
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    return s, base


def get_world_state() -> dict:
    """GET /world: world_size, tick, landmarks, agents, recent_chat."""
    sess, base = _session()
    r = sess.get(f"{base}/world", timeout=15)
    r.raise_for_status()
    return r.json()


def world_move(dx: int, dy: int) -> bool:
    """POST /world/actions with action=move. Registers agent if new."""
    sess, base = _session()
    agent_id = _env("AGENT_ID", "")
    display_name = _env("DISPLAY_NAME", _env("AGENT_NAME", agent_id)) or agent_id
    payload = {
        "agent_id": agent_id,
        "agent_name": display_name,
        "action": "move",
        "params": {"dx": int(dx), "dy": int(dy)},
    }
    r = sess.post(f"{base}/world/actions", json=payload, timeout=10)
    if r.status_code >= 400:
        print(f"[moltworld_bot] world_move failed {r.status_code} {r.text[:200]}", file=sys.stderr)
        return False
    return True


def get_chat_recent(limit: int = 25) -> list[dict]:
    sess, base = _session()
    r = sess.get(f"{base}/chat/recent?limit={limit}", timeout=15)
    r.raise_for_status()
    return r.json().get("messages", [])


def chat_send(text: str) -> bool:
    if not (text or "").strip():
        return False
    sess, base = _session()
    agent_id = _env("AGENT_ID", "")
    display_name = _env("DISPLAY_NAME", _env("AGENT_NAME", agent_id)) or agent_id
    payload = {
        "sender_type": "agent",
        "sender_id": agent_id,
        "sender_name": display_name,
        "text": (text or "").strip()[:2000],
    }
    r = sess.post(f"{base}/chat/send", json=payload, timeout=10)
    if r.status_code >= 400:
        print(f"[moltworld_bot] chat_send failed {r.status_code} {r.text[:200]}", file=sys.stderr)
        return False
    return True


def _manhattan(ax: int, ay: int, bx: int, by: int) -> int:
    return abs(ax - bx) + abs(ay - by)


def describe_here(snapshot: dict, agent_id: str) -> str:
    """Describe current cell and nearby landmarks/agents from world snapshot."""
    agents = snapshot.get("agents") or []
    landmarks = snapshot.get("landmarks") or []
    world_size = int(snapshot.get("world_size") or 32)
    me = next((a for a in agents if (a.get("agent_id") or "").strip() == agent_id), None)
    if not me:
        lm_str = [f"{lm.get('id')}({lm.get('x')},{lm.get('y')})" for lm in landmarks]
        return (
            "You are not on the map yet. Use move with dx,dy (each -1 to 1) to enter the world. "
            f"Landmarks in the world: {lm_str}."
        )
    x, y = int(me.get("x") or 0), int(me.get("y") or 0)
    here_ids = [lm.get("id") for lm in landmarks if int(lm.get("x")) == x and int(lm.get("y")) == y]
    nearby_lm = [
        f"{lm.get('id')}({lm.get('x')},{lm.get('y')})"
        for lm in landmarks
        if 1 <= _manhattan(x, y, int(lm.get("x") or 0), int(lm.get("y") or 0)) <= 3
    ]
    others_here = [a.get("display_name") or a.get("agent_id") for a in agents if a.get("agent_id") != agent_id and int(a.get("x")) == x and int(a.get("y")) == y]
    others_near = [
        (a.get("display_name") or a.get("agent_id"), int(a.get("x") or 0), int(a.get("y") or 0))
        for a in agents
        if a.get("agent_id") != agent_id and 1 <= _manhattan(x, y, int(a.get("x") or 0), int(a.get("y") or 0)) <= 2
    ]
    lines = [
        f"Position: ({x},{y}). World size: 0-{world_size - 1}.",
        f"Here: {here_ids or 'empty'}.",
        f"Landmarks within 3 steps: {nearby_lm or 'none'}.",
    ]
    if others_here:
        lines.append(f"Agents here: {others_here}.")
    if others_near:
        lines.append(f"Agents nearby: {[(n, nx, ny) for n, nx, ny in others_near]}.")
    return " ".join(lines)


def _is_other_bot(sender_id: str, agent_id: str) -> bool:
    if not sender_id or not agent_id:
        return False
    s = (sender_id or "").strip()
    if s == agent_id:
        return False
    if "MalicorSparky2" in s or (agent_id == "Sparky1Agent" and "Sparky2" in s):
        return True
    if "Sparky1Agent" in s or (agent_id == "MalicorSparky2" and "Sparky1" in s):
        return True
    return False


def _run_opener(agent_id: str, display_name: str) -> str:
    """Narrator posts one short opener when chat is empty."""
    system = (
        "You are a bot in a shared world chat. Output ONLY a single JSON object.\n"
        "Keys: \"kind\" (required), \"text\" (required when kind is chat_say).\n"
        "Kind: \"chat_say\" or \"noop\". When chat_say, set \"text\" to one short greeting or conversation starter (1-2 sentences)."
    )
    user = (
        f"You are {display_name} ({agent_id}), the narrator. The chat is empty. "
        "Say one short, friendly opener to start the conversation (e.g. invite to explore or ask a question). "
        "Output JSON: {\"kind\": \"chat_say\", \"text\": \"your opener\"}."
    )
    try:
        raw = llm_chat(system, user, max_tokens=150)
    except Exception as e:
        print(f"[moltworld_bot] opener llm_chat failed: {e}", file=sys.stderr)
        return "error"
    obj = _extract_json(raw)
    if not obj or (obj.get("kind") or "").strip().lower() != "chat_say":
        return "noop"
    text = (obj.get("text") or "").strip()
    if not text:
        return "noop"
    if chat_send(text):
        return "sent"
    return "error"


def _extract_json(s: str) -> dict | None:
    s = (s or "").strip()
    # Try to find a JSON object
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def run_one_step() -> str:
    """Run one bot step. Returns 'noop' | 'sent' | 'moved' | 'error'."""
    agent_id = _env("AGENT_ID", "")
    display_name = _env("DISPLAY_NAME", _env("AGENT_NAME", agent_id)) or agent_id
    if not agent_id:
        print("[moltworld_bot] AGENT_ID not set", file=sys.stderr)
        return "error"

    # Fetch world and chat so the LLM can explore and/or reply
    try:
        snapshot = get_world_state()
    except Exception as e:
        print(f"[moltworld_bot] get_world_state failed: {e}", file=sys.stderr)
        snapshot = {"agents": [], "landmarks": [], "world_size": 32}
    world_desc = describe_here(snapshot, agent_id)

    messages = get_chat_recent()
    last_from_us = False
    last_text = ""
    last_sender = ""

    if messages:
        last = messages[-1]
        last_sender = (last.get("sender_id") or last.get("sender_name") or "").strip()
        last_text = (last.get("text") or "").strip()
        last_from_us = last_sender == agent_id

    if last_from_us:
        # Can still move or noop
        pass
    else:
        # Someone else spoke or chat empty
        pass

    is_narrator = "Sparky1" in agent_id or agent_id == "Sparky1Agent"
    if not messages and is_narrator:
        return _run_opener(agent_id, display_name)

    # One combined step: you can move, or chat_say, or noop
    system = (
        "You are a bot in a shared 2D world. Output ONLY a single JSON object, no other text.\n"
        "Keys: \"kind\" (required), \"text\" (when kind is chat_say), \"dx\" and \"dy\" (when kind is move).\n"
        "Kind must be exactly one of: \"move\", \"chat_say\", \"noop\".\n"
        "move: explore the world. Set dx and dy each to -1, 0, or 1 (one step in that direction). You can move toward landmarks or other agents.\n"
        "chat_say: set \"text\" to one short message (1-2 sentences). Your reply MUST address what they said; no generic \"Hello there!\" when they said something specific.\n"
        "noop: do nothing this turn.\n"
        "You may explore (move) or reply (chat_say) or both in different turns. Prefer moving toward interesting places (board, cafe, market, etc.) and occasionally chat."
    )
    recent = "\n".join(
        f"  {m.get('sender_id')}: {(m.get('text') or '')[:120]}"
        for m in messages[-8:]
    ) or "  (no messages yet)"
    user = (
        f"You are {display_name} ({agent_id}).\n"
        f"World: {world_desc}\n"
        f"Recent chat:\n{recent}\n"
        "Output one JSON: {\"kind\": \"move\", \"dx\": 0, \"dy\": 1} or {\"kind\": \"chat_say\", \"text\": \"...\"} or {\"kind\": \"noop\"}."
    )

    try:
        raw = llm_chat(system, user, max_tokens=220)
    except Exception as e:
        print(f"[moltworld_bot] llm_chat failed: {e}", file=sys.stderr)
        return "error"

    obj = _extract_json(raw)
    if not obj:
        return "noop"

    kind = (obj.get("kind") or "").strip().lower()

    if kind == "move":
        dx = int(obj.get("dx") if obj.get("dx") is not None else 0)
        dy = int(obj.get("dy") if obj.get("dy") is not None else 0)
        dx = max(-1, min(1, dx))
        dy = max(-1, min(1, dy))
        if world_move(dx, dy):
            return "moved"
        return "error"

    if kind == "chat_say":
        text = (obj.get("text") or "").strip()
        if not text:
            return "noop"
        generic = ["hello there!", "hey there!", "hello! what would you like to talk about", "hi!", "greetings!"]
        low = text.lower()
        if any(low == g or (low.startswith(g) and len(low) < len(g) + 30) for g in generic) and last_text:
            pass  # allow but could noop
        if chat_send(text):
            return "sent"
        return "error"

    return "noop"


def main() -> None:
    result = run_one_step()
    print(result)
    sys.exit(0 if result in ("noop", "sent", "moved") else 1)


if __name__ == "__main__":
    main()
