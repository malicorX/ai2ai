from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from agent_template.langgraph_runtime import llm_chat


Role = Literal["proposer", "executor"]


class ProposedJob(TypedDict):
    title: str
    body: str
    reward: float


class Action(TypedDict, total=False):
    kind: Literal["noop", "propose_job", "execute_job"]
    note: str
    job: ProposedJob
    job_id: str
    job_obj: dict


class AgentState(TypedDict, total=False):
    role: Role
    agent_id: str
    display_name: str
    persona: str
    run_id: str
    world: dict
    balance: float
    open_jobs: List[dict]
    rejected_jobs: List[dict]
    memories: List[dict]
    world_model: dict
    last_job_id: str
    last_job: dict
    handled_rejection_job_id: str
    outcome_ack_job_id: str
    action: Action
    acted: bool


class Tools(TypedDict):
    jobs_list: Callable[..., List[dict]]
    jobs_get: Callable[[str], dict]
    jobs_create: Callable[[str, str, float], str]
    jobs_claim: Callable[[str], bool]
    jobs_submit: Callable[[str, str], bool]
    do_job: Callable[[dict], str]
    chat_send: Callable[[str], None]
    trace_event: Callable[[str, str, dict], None]
    memory_retrieve: Callable[[str, int], List[dict]]
    memory_append: Callable[[str, str, List[str], float], None]


def _cfg_tools(config: Any) -> Tools:
    """
    LangGraph passes a config dict as the second arg to nodes. We thread our runtime
    callables through config["tools"].
    """
    if isinstance(config, dict) and isinstance(config.get("tools"), dict):
        return config["tools"]  # type: ignore[return-value]
    # Fallback: allow nesting under configurable (common LangGraph pattern)
    if isinstance(config, dict):
        cfg = config.get("configurable")
        if isinstance(cfg, dict) and isinstance(cfg.get("tools"), dict):
            return cfg["tools"]  # type: ignore[return-value]
    raise RuntimeError("LangGraph tools missing from config; expected config['tools']")


def _run_tag(run_id: str) -> str:
    rid = (run_id or "").strip()
    return f"[run:{rid}]" if rid else ""


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _pick_executor_job(state: AgentState) -> Optional[dict]:
    """
    Select the next job for executor:
    - created by agent_1
    - matches current run tag (if known)
    - newest first
    """
    jobs = list(state.get("open_jobs") or [])
    if not jobs:
        return None
    run_tag = _run_tag(state.get("run_id", ""))
    jobs = [j for j in jobs if str(j.get("created_by") or "") == "agent_1"]
    if run_tag:
        jobs = [j for j in jobs if (run_tag in str(j.get("title") or "")) or (run_tag in str(j.get("body") or ""))]
    if not jobs:
        return None
    jobs.sort(key=lambda j: _safe_float(j.get("created_at"), 0.0), reverse=True)
    return jobs[0]

def _pick_redo_job(state: AgentState, failed_job_id: str) -> Optional[dict]:
    """
    Prefer redo/fix jobs when a prior job was rejected:
    - matches run tag (if known)
    - created by agent_1
    - title/body indicates redo OR references failed job id
    - newest first
    """
    fid = (failed_job_id or "").strip()
    if not fid:
        return None
    jobs = list(state.get("open_jobs") or [])
    if not jobs:
        return None
    run_tag = _run_tag(state.get("run_id", ""))
    # Tag-first: proposer emits [redo_for:<id>] for deterministic routing.
    tag = f"[redo_for:{fid}]"
    tagged = []
    out = []
    for j in jobs:
        if str(j.get("created_by") or "") != "agent_1":
            continue
        t = str(j.get("title") or "")
        b = str(j.get("body") or "")
        low = (t + " " + b).lower()
        if run_tag and not ((run_tag in t) or (run_tag in b)):
            continue
        if tag in b:
            tagged.append(j)
            continue
        if ("redo" in low) or ("fix" in low) or (fid in t) or (fid in b):
            out.append(j)
    if tagged:
        tagged.sort(key=lambda j: _safe_float(j.get("created_at"), 0.0), reverse=True)
        return tagged[0]
    if not out:
        return None
    out.sort(key=lambda j: _safe_float(j.get("created_at"), 0.0), reverse=True)
    return out[0]


def _proposer_has_open_job(state: AgentState) -> bool:
    run_tag = _run_tag(state.get("run_id", ""))
    for j in state.get("open_jobs") or []:
        if str(j.get("created_by") or "") != "agent_1":
            continue
        if run_tag and not ((run_tag in str(j.get("title") or "")) or (run_tag in str(j.get("body") or ""))):
            continue
        return True
    return False


def node_perceive(state: AgentState, config: Any) -> AgentState:
    tools = _cfg_tools(config)
    # Expect world already in state; refresh open jobs.
    try:
        state["open_jobs"] = tools["jobs_list"](status="open", limit=50)
    except Exception:
        state["open_jobs"] = []

    # Watch rejected jobs:
    # - proposer: to create "redo" tasks (verifier-aware recovery)
    # - executor: to prioritize redo/fix work after penalties
    if state.get("role") in ("proposer", "executor"):
        try:
            state["rejected_jobs"] = tools["jobs_list"](status="rejected", limit=50)
        except Exception:
            state["rejected_jobs"] = []
    else:
        state["rejected_jobs"] = []

    # Lightweight world model extraction (compact, stable input for reasoning).
    w = state.get("world") or {}
    me = None
    try:
        for a in (w.get("agents") or []):
            if a.get("agent_id") == state.get("agent_id"):
                me = a
                break
    except Exception:
        me = None

    place_id = ""
    nearby_agents: List[dict] = []
    try:
        if me:
            ax, ay = int(me.get("x", 0)), int(me.get("y", 0))
            # nearest landmark within 1 tile
            for lm in (w.get("landmarks") or []):
                lx, ly = int(lm.get("x", 0)), int(lm.get("y", 0))
                if max(abs(ax - lx), abs(ay - ly)) <= 1:
                    place_id = str(lm.get("id") or "")
                    break
            # nearby agents within 2 tiles
            for a in (w.get("agents") or []):
                if a.get("agent_id") == state.get("agent_id"):
                    continue
                bx, by = int(a.get("x", 0)), int(a.get("y", 0))
                if max(abs(ax - bx), abs(ay - by)) <= 2:
                    nearby_agents.append({"agent_id": a.get("agent_id"), "x": bx, "y": by, "display_name": a.get("display_name")})
    except Exception:
        place_id = place_id or ""

    state["world_model"] = {
        "day": int(w.get("day", 0) or 0),
        "minute_of_day": int(w.get("minute_of_day", 0) or 0),
        "topic": str(w.get("topic") or ""),
        "self": {"x": int(me.get("x", 0)) if me else 0, "y": int(me.get("y", 0)) if me else 0, "place_id": place_id},
        "nearby_agents": nearby_agents,
    }

    # Fetch last job status if available (supports verify/learn loop).
    last_id = str(state.get("last_job_id") or "").strip()
    if last_id:
        try:
            state["last_job"] = tools["jobs_get"](last_id) or {}
        except Exception:
            state["last_job"] = {}
    state["acted"] = False
    return state


def node_recall(state: AgentState, config: Any) -> AgentState:
    tools = _cfg_tools(config)
    # Retrieve only what helps decisions: recent failures/success patterns around verification and jobs.
    q = f"run {state.get('run_id','')} jobs verification failed penalty acceptance criteria evidence"
    try:
        state["memories"] = tools["memory_retrieve"](q, 8) or []
    except Exception:
        state["memories"] = []
    return state


def _extract_json_obj(raw: str) -> Optional[dict]:
    raw = (raw or "").strip()
    if not raw:
        return None
    # tolerant: find first {...} blob
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _extract_redo_for(body: str) -> str:
    """
    Parse a deterministic redo marker like: [redo_for:<job_id>]
    Returns empty string if missing.
    """
    txt = (body or "")
    m = re.search(r"\[redo_for:([a-f0-9\-]{8,})\]", txt, flags=re.IGNORECASE)
    return (m.group(1) if m else "").strip()


def node_decide(state: AgentState, config: Any) -> AgentState:
    tools = _cfg_tools(config)
    role: Role = state.get("role", "executor")  # type: ignore[assignment]
    run_tag = _run_tag(state.get("run_id", ""))

    # Outcome awareness: handle approved/rejected once, then continue normally.
    lj = state.get("last_job") or {}
    lj_status = str(lj.get("status") or "")
    lj_id = str(lj.get("job_id") or state.get("last_job_id") or "").strip()
    ack = str(state.get("outcome_ack_job_id") or "").strip()
    if lj_status in ("approved", "rejected") and lj_id and (ack != lj_id):
        state["action"] = {"kind": "noop", "note": f"last_job_outcome={lj_status}"}
        return state

    # Invariants first (code-enforced)
    if role == "proposer":
        # Never create a redo (or any new job) if we already have an open job for this run.
        if _proposer_has_open_job(state):
            state["action"] = {"kind": "noop", "note": "proposer already has an open job"}
            return state

        # If the executor got rejected on a recent job, create ONE redo job with clearer evidence rules.
        handled = str(state.get("handled_rejection_job_id") or "").strip()
        rej = list(state.get("rejected_jobs") or [])
        if rej:
            # Only consider jobs in this run proposed by agent_1 and executed by agent_2.
            cand = []
            for j in rej:
                if str(j.get("created_by") or "") != "agent_1":
                    continue
                if str(j.get("submitted_by") or "") != "agent_2":
                    continue
                if run_tag and not ((run_tag in str(j.get("title") or "")) or (run_tag in str(j.get("body") or ""))):
                    continue
                if handled and str(j.get("job_id") or "") == handled:
                    continue
                cand.append(j)
            cand.sort(key=lambda j: _safe_float(j.get("reviewed_at"), _safe_float(j.get("submitted_at"), 0.0)), reverse=True)
            if cand:
                bad = cand[0]
                bad_id = str(bad.get("job_id") or "")
                bad_title = str(bad.get("title") or "")
                bad_body = str(bad.get("body") or "")
                note = str(bad.get("auto_verify_note") or "")
                root_id = _extract_redo_for(bad_body) or bad_id
                # Escalation: if the failed job was itself a redo, we are in "strict mode".
                redo_level = 2 if _extract_redo_for(bad_body) else 1
                redo_prefix = f"Redo {root_id}: " if root_id else "Redo: "
                redo_tag = f"[redo_for:{root_id}]" if root_id else "[redo_for:unknown]"
                redo_level_tag = f"[redo_level:{redo_level}]"

                sys = (
                    "You are the proposer creating ONE 'redo' job after a failed verification.\n"
                    "Return STRICT JSON ONLY with schema:\n"
                    "{\"title\": <string>, \"body\": <string>, \"reward\": <number>}\n"
                    "Rules:\n"
                    "- The redo job must be easier to verify.\n"
                    "- If this is a second failure, drastically simplify the task and make evidence requirements explicit.\n"
                    "- Include 'Acceptance criteria:' and 'Evidence required in submission:' sections.\n"
                    "- Explicitly address the verifier failure note.\n"
                    "- Keep it executable without web access.\n"
                )
                user = (
                    f"Failed job id: {bad_id}\n"
                    f"Root job id (redo_for): {root_id}\n"
                    f"Redo escalation level: {redo_level}\n"
                    f"Original title: {bad_title}\n"
                    f"Original body:\n{bad_body}\n\n"
                    f"Verifier failure note:\n{note}\n\n"
                    f"Run tag: {run_tag}\n\n"
                    "Create a redo job now. Put these tags at the top of the body:\n"
                    f"{redo_tag}\n{redo_level_tag}\n"
                )
                tools["trace_event"]("thought", "langgraph: proposer creating redo job", {"failed_job_id": bad_id})
                raw = llm_chat(sys, user, max_tokens=420)
                obj = _extract_json_obj(raw) or {}

                title = str(obj.get("title") or "").strip()
                body = str(obj.get("body") or "").strip()
                reward = _safe_float(obj.get("reward"), 0.01)
                if not title or not body:
                    title = f"{redo_prefix}{bad_title}".strip() if bad_title else f"{redo_prefix}Verifiable task"
                    body = (
                        f"{redo_tag}\n{redo_level_tag}\n"
                        f"This is a redo of job `{bad_id}` which failed verification.\n"
                        f"Failure note: {note}\n\n"
                        "Acceptance criteria:\n"
                        "- Submission includes required code fences and an Evidence section.\n"
                        "- Output matches the expected result exactly.\n\n"
                        "Evidence required in submission:\n"
                        "- Include runnable code in the correct fence (e.g., ```python).\n"
                        "- Include an 'Evidence:' section listing observed output.\n"
                    )
                    reward = 0.01

                # Force deterministic redo labeling for executor routing + auditing.
                if root_id and not title.lower().startswith(f"redo {root_id}".lower()):
                    title = f"{redo_prefix}{title}".strip()
                if redo_tag not in body:
                    body = f"{redo_tag}\n{body}".strip()
                if redo_level_tag not in body:
                    body = f"{redo_level_tag}\n{body}".strip()

                # Strict-mode hinting: if redo_level >= 2, force a short "strict" note in body.
                if redo_level >= 2 and "strict mode" not in body.lower():
                    body = f"{body}\n\nSTRICT MODE: Keep the solution minimal and match acceptance criteria exactly.\n"

                if run_tag and run_tag not in title:
                    title = f"{run_tag} {title}".strip()
                state["handled_rejection_job_id"] = bad_id
                state["action"] = {"kind": "propose_job", "note": f"redo_for={root_id}|redo_level={redo_level}", "job": {"title": title, "body": body, "reward": float(reward)}}
                return state

        # LLM: propose a verifiable job (must include acceptance criteria + evidence format).
        persona = (state.get("persona") or "").strip()
        mem_lines = []
        for m in (state.get("memories") or [])[:6]:
            mem_lines.append(f"- {str(m.get('text') or '')[:220]}")
        mem_txt = "\n".join(mem_lines).strip()

        sys = (
            "You are the proposer agent creating ONE verifiable task for the executor.\n"
            "Return STRICT JSON ONLY with schema:\n"
            "{\"title\": <string>, \"body\": <string>, \"reward\": <number>}\n"
            "Rules:\n"
            "- The task MUST be verifiable without web access.\n"
            "- Include an 'Acceptance criteria:' section.\n"
            "- Include an 'Evidence required in submission:' section.\n"
            "- Prefer deterministic checks (e.g., runnable code + expected stdout).\n"
            "- Keep body under 2200 chars.\n"
        )
        user = (
            f"Run tag prefix to include in title: {run_tag}\n"
            f"Persona:\n{persona}\n\n"
            f"Relevant memories (failures/success patterns):\n{mem_txt}\n\n"
            "Propose the job now."
        )
        tools["trace_event"]("thought", "langgraph: proposer deciding job", {"run_tag": run_tag})
        raw = llm_chat(sys, user, max_tokens=420)
        obj = _extract_json_obj(raw) or {}

        title = str(obj.get("title") or "").strip()
        body = str(obj.get("body") or "").strip()
        reward = _safe_float(obj.get("reward"), 0.01)
        if not title or not body:
            # fallback: safe deterministic task
            title = "Task: Python primes script (smallest five primes)"
            body = (
                "Write a Python script that prints the smallest five prime numbers.\n"
                "Acceptance criteria:\n"
                "- Provide a runnable `primes.py`.\n"
                "- Running it prints exactly: 2, 3, 5, 7, 11 (one per line).\n"
                "Evidence required in submission:\n"
                "- Include the full code in a ```python code fence.\n"
                "- Include a short 'Evidence:' section describing the observed output.\n"
            )
            reward = 0.01

        if run_tag and run_tag not in title:
            title = f"{run_tag} {title}".strip()
        state["action"] = {"kind": "propose_job", "job": {"title": title, "body": body, "reward": float(reward)}}
        return state

    # executor
    # If we recently failed verification, prioritize a redo/fix job that references that failure.
    # Use most recent rejected job (submitted_by=agent_2) as the primary "failed id".
    failed_id = ""
    try:
        run_tag = _run_tag(state.get("run_id", ""))
        cand = []
        for j in (state.get("rejected_jobs") or [])[:50]:
            if str(j.get("submitted_by") or "") != "agent_2":
                continue
            if str(j.get("created_by") or "") != "agent_1":
                continue
            if run_tag and not ((run_tag in str(j.get("title") or "")) or (run_tag in str(j.get("body") or ""))):
                continue
            cand.append(j)
        cand.sort(key=lambda j: _safe_float(j.get("reviewed_at"), _safe_float(j.get("submitted_at"), 0.0)), reverse=True)
        if cand:
            failed_id = str(cand[0].get("job_id") or "").strip()
    except Exception:
        failed_id = ""
    if not failed_id:
        failed_id = str(state.get("last_job_id") or "").strip()

    redo = _pick_redo_job(state, failed_id)
    job = redo or _pick_executor_job(state)
    if not job or not job.get("job_id"):
        state["action"] = {"kind": "noop", "note": "no suitable open job"}
        return state
    state["action"] = {"kind": "execute_job", "job_id": str(job["job_id"]), "job_obj": job}
    return state


def node_act(state: AgentState, config: Any) -> AgentState:
    tools = _cfg_tools(config)
    act = state.get("action") or {"kind": "noop"}
    kind = act.get("kind", "noop")

    if kind == "propose_job":
        job = act.get("job") or {}
        title = str(job.get("title") or "")
        body = str(job.get("body") or "")
        reward = _safe_float(job.get("reward"), 0.01)
        jid = ""
        try:
            jid = tools["jobs_create"](title, body, reward)
        except Exception:
            jid = ""
        if jid:
            tools["chat_send"](f"[task:{jid}] New task posted: {title}. Please claim+submit with required evidence.")
            try:
                tools["memory_append"]("event", f"Proposed job {jid}: {title}", ["job", "proposed"], 0.6)
            except Exception:
                pass
            state["last_job_id"] = jid
            state["acted"] = True
        return state

    if kind == "execute_job":
        job_id = str(act.get("job_id") or "")
        job = act.get("job_obj") or {}
        if not job_id:
            return state
        claimed = False
        try:
            claimed = bool(tools["jobs_claim"](job_id))
        except Exception:
            claimed = False
        if not claimed:
            return state
        try:
            submission = tools["do_job"](job)
        except Exception:
            submission = "Evidence:\n- Execution failed inside agent runtime.\n"
        ok = False
        try:
            ok = bool(tools["jobs_submit"](job_id, submission))
        except Exception:
            ok = False
        if ok:
            tools["chat_send"](f"I submitted `{job_id}` for review. If verification fails, I will revise and resubmit with better evidence.")
            try:
                tools["memory_append"]("event", f"Submitted job {job_id}: {job.get('title')}", ["job", "submitted"], 0.7)
            except Exception:
                pass
            state["last_job_id"] = job_id
            state["acted"] = True
        return state

    return state


def node_reflect(state: AgentState, config: Any) -> AgentState:
    tools = _cfg_tools(config)
    # Lightweight: store one rule-of-thumb so behavior improves over time.
    # Also: respond to job outcomes (approved/rejected/submitted) so agents internalize "submitted != done".
    lj = state.get("last_job") or {}
    if lj:
        st = str(lj.get("status") or "")
        note = str(lj.get("auto_verify_note") or "")
        ok = lj.get("auto_verify_ok")
        jid = str(lj.get("job_id") or state.get("last_job_id") or "")
        title = str(lj.get("title") or "")
        if st == "approved":
            try:
                tools["chat_send"](f"Job `{jid}` was approved. ✅ ({title})")
            except Exception:
                pass
            try:
                tools["memory_append"]("reflection", f"Approved job {jid}. Pattern: verifiable evidence passes. Note={note}", ["job", "approved"], 0.85)
            except Exception:
                pass
            if jid:
                state["outcome_ack_job_id"] = jid
        elif st == "rejected":
            try:
                tools["chat_send"](f"Job `{jid}` was rejected. I likely lost ai$. Reason: {note[:220]}")
            except Exception:
                pass
            # Safety valve: if a redo failed again, write a strong "do not repeat" policy memory.
            try:
                body = str(lj.get("body") or "")
                root = _extract_redo_for(body)
                if root:
                    tools["memory_append"](
                        "reflection",
                        f"Redo failed again (job {jid}, redo_for={root}). DO NOT repeat the same submission pattern. "
                        f"Next time: simplify; include exact required code fences; explicitly echo every acceptance criterion bullet inside Evidence checklist. "
                        f"Verifier note={note}",
                        ["job", "redo_failed", "policy"],
                        0.99,
                    )
            except Exception:
                pass
            try:
                tools["memory_append"](
                    "reflection",
                    f"Rejected job {jid}. auto_verify_ok={ok}. Fix: ensure Evidence section + required code fences + match acceptance criteria. Note={note}",
                    ["job", "rejected", "policy"],
                    0.95,
                )
            except Exception:
                pass
            if jid:
                state["outcome_ack_job_id"] = jid
        elif st == "submitted":
            # This is the key behavioral distinction: not done yet.
            try:
                tools["memory_append"]("event", f"Job {jid} is submitted (pending approval).", ["job", "pending"], 0.55)
            except Exception:
                pass

    if not state.get("acted"):
        return state
    role = state.get("role", "executor")
    text = (
        f"Role={role}. I acted this tick. Rule: prefer tasks with deterministic verifiers; "
        "include an explicit Evidence section and code fences when required."
    )
    try:
        tools["memory_append"]("reflection", text, ["reflection", "policy"], 0.75)
    except Exception:
        pass
    return state


def build_graph() -> Any:
    g: StateGraph = StateGraph(AgentState)
    g.add_node("perceive", node_perceive)
    g.add_node("recall", node_recall)
    g.add_node("decide", node_decide)
    g.add_node("act", node_act)
    g.add_node("reflect", node_reflect)

    g.add_edge(START, "perceive")
    g.add_edge("perceive", "recall")
    g.add_edge("recall", "decide")
    g.add_edge("decide", "act")
    g.add_edge("act", "reflect")
    g.add_edge("reflect", END)
    return g.compile()


_GRAPH = None


def run_graph_step(state: AgentState, tools: Tools) -> AgentState:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    # LangGraph passes extra kwargs into node callables.
    return _GRAPH.invoke(state, {"tools": tools})

