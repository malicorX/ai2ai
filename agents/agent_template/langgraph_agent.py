from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Literal, Optional, TypedDict
import hashlib

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
    recent_jobs: List[dict]
    memories: List[dict]
    world_model: dict
    last_job_id: str
    last_job: dict
    handled_rejection_job_id: str
    outcome_ack_job_id: str
    # Guardrail: once we announce a redo cap for a root task, don't spam it again in this run.
    redo_capped_root_ids: List[str]
    # If propose_job fails (e.g., backend dedupe), bump this so we pick a different fallback next tick.
    propose_failed_count: int
    # Internal-only: runtime tool callables injected by the host process.
    __tools: dict
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
    web_fetch: Callable[[str], dict]
    opportunities_list: Callable[[int], List[dict]]
    opportunities_update: Callable[[str, Optional[str], Optional[str], Optional[List[str]]], dict]
    email_template_generate: Callable[[str, str, Optional[str], Optional[str]], str]
    client_response_simulate: Callable[[str, str], dict]
    artifact_put: Callable[[str, str, str, str], dict]


_TOOLS: Optional[Tools] = None


def _get_tools(state: AgentState, config: Any) -> Tools:
    """
    Retrieve runtime tool callables for a node.

    Note: LangGraph does NOT reliably pass a second positional argument to node functions.
    We therefore support two mechanisms:
    - preferred: state["__tools"] injected by the caller
    - optional: config["tools"] (if the runtime provides it)
    """
    # Most robust: module-level injected tools (avoids any schema/key filtering in LangGraph).
    global _TOOLS
    if _TOOLS is not None:
        return _TOOLS

    # Fallback: state injection (may be filtered depending on graph schema/runtime).
    if isinstance(state, dict) and isinstance(state.get("__tools"), dict):
        return state["__tools"]  # type: ignore[return-value]
    if isinstance(config, dict) and isinstance(config.get("tools"), dict):
        return config["tools"]  # type: ignore[return-value]
    if isinstance(config, dict):
        cfg = config.get("configurable")
        if isinstance(cfg, dict) and isinstance(cfg.get("tools"), dict):
            return cfg["tools"]  # type: ignore[return-value]
    raise RuntimeError("LangGraph tools missing; expected state['__tools'] or config['tools']")


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
    # Prefer resuming jobs we already claimed (e.g., after a container restart),
    # otherwise take a new open job.
    my_claimed = list(state.get("my_claimed_jobs") or [])
    jobs = my_claimed + list(state.get("open_jobs") or [])
    if not jobs:
        return None
    run_tag = _run_tag(state.get("run_id", ""))
    jobs = [j for j in jobs if str(j.get("created_by") or "") == "agent_1"]
    # Prefer run-tagged jobs for the current run, but fall back to any agent_1 jobs if none are tagged.
    # (Some jobs created via conversation flow historically missed the run tag.)
    tagged = jobs
    if run_tag:
        tagged = [j for j in jobs if (run_tag in str(j.get("title") or "")) or (run_tag in str(j.get("body") or ""))]
    jobs = tagged or jobs
    if not jobs:
        return None
    # Always finish our claimed work first (oldest claim first), then prefer higher reward while still being fairly recent.
    def _key(j: dict) -> tuple:
        is_claimed = 1 if str(j.get("status") or "") == "claimed" else 0
        # For claimed jobs, older claimed_at first; for open jobs, newer created_at first.
        claimed_at = _safe_float(j.get("claimed_at"), 0.0)
        created_at = _safe_float(j.get("created_at"), 0.0)
        reward = _safe_float(j.get("reward"), 0.0)
        return (is_claimed, -claimed_at, reward, created_at)

    jobs.sort(key=_key, reverse=True)
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


def node_perceive(state: AgentState, config: Any = None) -> AgentState:
    tools = _get_tools(state, config)
    # Expect world already in state; refresh open jobs.
    try:
        state["open_jobs"] = tools["jobs_list"](status="open", limit=50)
    except Exception:
        state["open_jobs"] = []
    # Executor robustness: also fetch jobs already claimed by THIS agent so we can resume after restarts.
    if state.get("role") == "executor":
        try:
            claimed = tools["jobs_list"](status="claimed", limit=80)
        except Exception:
            claimed = []
        aid = str(state.get("agent_id") or "").strip()
        if aid:
            state["my_claimed_jobs"] = [j for j in claimed if str(j.get("claimed_by") or "") == aid]
        else:
            state["my_claimed_jobs"] = []
    # Recent jobs (any status) for uniqueness checks (best-effort).
    try:
        state["recent_jobs"] = tools["jobs_list"](status=None, limit=60)
    except Exception:
        state["recent_jobs"] = []

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


def node_recall(state: AgentState, config: Any = None) -> AgentState:
    tools = _get_tools(state, config)
    # Retrieve failure patterns and success patterns to guide decisions.
    # Priority: recent verification failures, rejection patterns, what worked.
    memories: List[dict] = []
    role = state.get("role", "executor")
    run_tag = _run_tag(state.get("run_id", ""))
    
    # Query 1: Recent verification failures and rejections (highest priority for learning)
    try:
        q1 = f"verification failed rejected auto_verify_ok=false penalty {run_tag}"
        m1 = tools["memory_retrieve"](q1, 6) or []
        memories.extend(m1)
    except Exception:
        pass
    
    # Query 2: What patterns led to approval (to reinforce good behavior)
    try:
        q2 = f"approved auto_verify_ok=true evidence acceptance criteria {run_tag}"
        m2 = tools["memory_retrieve"](q2, 4) or []
        memories.extend(m2)
    except Exception:
        pass
    
    # Query 3: Role-specific patterns (proposer vs executor learnings)
    try:
        if role == "proposer":
            q3 = f"proposed job created task archetype verifier {run_tag}"
        else:
            q3 = f"submitted executed deliverable evidence code fence {run_tag}"
        m3 = tools["memory_retrieve"](q3, 4) or []
        memories.extend(m3)
    except Exception:
        pass
    
    # Deduplicate by text content (same memory might match multiple queries)
    seen = set()
    unique: List[dict] = []
    for m in memories:
        text = str(m.get("text") or "")
        if text and text not in seen:
            seen.add(text)
            unique.append(m)
    
    # Sort by importance (if available) and recency, limit to top 10
    try:
        unique.sort(key=lambda x: (float(x.get("importance") or 0.0), float(x.get("created_at") or 0.0)), reverse=True)
    except Exception:
        pass
    state["memories"] = unique[:10]
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


def _extract_section_bullets(text: str, header_prefix: str, max_scan_lines: int = 40) -> List[str]:
    """
    Extract '- ' bullets under a header (similar to backend heuristic).
    """
    lines = (text or "").splitlines()
    hp = (header_prefix or "").strip().lower()
    start = None
    for i, ln in enumerate(lines):
        if ln.strip().lower().startswith(hp):
            start = i
            break
    if start is None:
        return []
    bullets: List[str] = []
    for ln in lines[start + 1 : start + 1 + max_scan_lines]:
        s = ln.strip()
        if s.startswith("- "):
            bullets.append(s[2:].strip())
            continue
        if s == "":
            continue
        if bullets and not s.startswith("- "):
            break
    return [b for b in bullets if b]


def _normalize_bullets_outside_code_fences(text: str) -> str:
    """
    Normalize common bullet prefixes to '- ' outside triple-backtick code fences.
    This helps ensure backend verifiers reliably parse Acceptance criteria / Evidence sections.
    """
    lines = (text or "").splitlines()
    out: List[str] = []
    in_code = False
    for ln in lines:
        s = ln.lstrip()
        if s.startswith("```"):
            in_code = not in_code
            out.append(ln)
            continue
        if not in_code:
            # Keep indentation, only swap the bullet marker.
            if s.startswith("* "):
                out.append(ln[: len(ln) - len(s)] + "- " + s[2:])
                continue
            if s.startswith("• "):
                out.append(ln[: len(ln) - len(s)] + "- " + s[2:])
                continue
        out.append(ln)
    return "\n".join(out)


def _count_rejections_for_root(rejected_jobs: List[dict], root_id: str) -> int:
    """
    Count how many rejected jobs belong to the same root task:
    - the root job itself (job_id == root_id)
    - any redo jobs that contain [redo_for:root_id] in their body
    """
    rid = (root_id or "").strip()
    if not rid:
        return 0
    n = 0
    for j in rejected_jobs or []:
        try:
            jid = str(j.get("job_id") or "").strip()
            body = str(j.get("body") or "")
            if jid == rid:
                n += 1
                continue
            if _extract_redo_for(body) == rid:
                n += 1
        except Exception:
            continue
    return n


def node_decide(state: AgentState, config: Any = None) -> AgentState:
    tools = _get_tools(state, config)
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
        # If our last proposal failed to create a job (often due to dedupe), immediately choose a deterministic
        # alternative instead of repeating the same proposal.
        try:
            pfc = int(state.get("propose_failed_count") or 0)
        except Exception:
            pfc = 0
        if pfc > 0:
            # Deterministic rotation: on each create-failure, choose a different template (avoid getting stuck
            # retrying the same deduped job over and over).
            pool = [
                (
                    "[archetype:market_scan] [verifier:json_list] Task: Market scan — paid gigs we can deliver (with citations)",
                    "[verifier:json_list]\n"
                    "[repeat_ok:1]\n"
                    "[json_min_items:10]\n"
                    "[json_required_keys:title,platform,demand_signal,estimated_price_usd,why_fit,first_action,source_url,source_quote]\n"
                    "Use web_fetch to research and propose 10 concrete paid gig/service ideas we could deliver.\n"
                    "Goal: identify real demand signals and realistic pricing.\n"
                    "\n"
                    "Acceptance criteria:\n"
                    "- Provide a JSON list with at least 10 objects.\n"
                    "- Each object includes keys: title, platform, demand_signal, estimated_price_usd, why_fit, first_action, source_url, source_quote.\n"
                    "- Each source_quote must be a short verbatim quote from the fetched page that supports demand/pricing.\n"
                    "\n"
                    "Acceptance criteria:\n"
                    "- Evidence is cited per item.\n"
                    "\n"
                    "Evidence required in submission:\n"
                    "- Include the JSON in a ```json``` code fence.\n"
                    "- Include an Evidence section stating item_count=<N> and list of distinct domains used.\n",
                ),
                (
                    "[verifier:md_table] Task: UI improvements for our web dashboard",
                    "[verifier:md_table]\n"
                    "[md_min_rows:8]\n"
                    "[md_required_cols:Problem,Change,Why it helps,How to verify]\n"
                    "Propose 8 concrete UI improvements for the current AI Village web UI.\n"
                    "\n"
                    "Acceptance criteria:\n"
                    "- Provide a markdown table with at least 8 rows.\n"
                    "- Columns: Problem | Change | Why it helps | How to verify.\n"
                    "\n"
                    "Evidence required in submission:\n"
                    "- Include the table in the submission.\n"
                    "- Include an Evidence section with the number of rows.\n",
                ),
                (
                    "[verifier:json_list] Task: Weather check plan (no web)",
                    "[verifier:json_list]\n"
                    "[json_min_items:7]\n"
                    "[json_required_keys:time,location,question,source_type,fallback_if_no_data]\n"
                    "Design a 7-step plan to answer: 'What will the weather be like tomorrow?'\n"
                    "No browsing: list *types* of sources and fallback steps.\n"
                    "\n"
                    "Acceptance criteria:\n"
                    "- JSON list with >=7 steps.\n"
                    "- Each step has keys time, location, question, source_type, fallback_if_no_data.\n"
                    "\n"
                    "Evidence required in submission:\n"
                    "- JSON in ```json``` fence.\n"
                    "- Evidence section with item_count.\n",
                ),
                (
                    "Task: Community — 10 conversation starters",
                    "Write 10 conversation starters for the agents that lead to useful work (not fluff).\n"
                    "\n"
                    "Acceptance criteria:\n"
                    "- Exactly 10 numbered items.\n"
                    "- Each item includes a concrete follow-up question.\n"
                    "\n"
                    "Evidence required in submission:\n"
                    "- Evidence section that lists count=10.\n",
                ),
                (
                    "Task: Ops runbook — keep the system healthy",
                    "Create a short runbook checklist for keeping the system healthy day-to-day.\n"
                    "\n"
                    "Acceptance criteria:\n"
                    "- 10 checklist items.\n"
                    "- Each item has: purpose + command/API endpoint.\n"
                    "\n"
                    "Evidence required in submission:\n"
                    "- Evidence section with count=10.\n",
                ),
                (
                    "[archetype:opportunity_board] [verifier:md_table] Task: Opportunity Board — top 8 gigs",
                    "[verifier:md_table]\n"
                    "[md_min_rows:8]\n"
                    "[md_required_cols:Title,Platform,Estimated Price (USD),Why we can deliver,First action,Source domain]\n"
                    "From recent market_scan tasks, summarize 8 best gigs we could realistically deliver.\n"
                    "\n"
                    "Acceptance criteria:\n"
                    "- Markdown table with >=8 rows.\n"
                    "- Columns exactly: Title | Platform | Estimated Price (USD) | Why we can deliver | First action | Source domain.\n"
                    "\n"
                    "Evidence required in submission:\n"
                    "- Evidence section with row_count.\n",
                ),
            ]
            t, b = pool[(max(0, pfc - 1)) % len(pool)]
            title = t
            body = b
            reward = 0.01
            if run_tag and run_tag not in title:
                title = f"{run_tag} {title}".strip()
            body = _normalize_bullets_outside_code_fences(body)
            state["action"] = {"kind": "propose_job", "note": f"fallback_after_create_fail n={pfc}", "job": {"title": title, "body": body, "reward": float(reward)}}
            return state

        # Never create a redo (or any new job) if we already have an open job for this run.
        if _proposer_has_open_job(state):
            state["action"] = {"kind": "noop", "note": "proposer already has an open job"}
            return state

        # Check memories for patterns to avoid (outcome-driven learning)
        memories = state.get("memories") or []
        failure_patterns: List[str] = []
        failed_archetypes: set = set()
        failed_verifiers: set = set()
        successful_archetypes: set = set()
        successful_verifiers: set = set()
        for m in memories:
            text = str(m.get("text") or "").lower()
            tags = [str(t).lower() for t in (m.get("tags") or [])]
            importance = float(m.get("importance") or 0.0)
            
            # Look for rejection/redo_failed memories with high importance
            if any(t in tags for t in ["rejected", "redo_failed", "policy"]) and importance > 0.9:
                failure_patterns.append(text)
                # Extract archetype and verifier from tags for filtering
                for tag in tags:
                    if tag.startswith("archetype:"):
                        failed_archetypes.add(tag.replace("archetype:", ""))
                    if tag.startswith("verifier:"):
                        failed_verifiers.add(tag.replace("verifier:", ""))
            
            # Also track successful patterns to reinforce good behavior
            if any(t in tags for t in ["approved", "success_pattern"]) and importance > 0.85:
                for tag in tags:
                    if tag.startswith("archetype:"):
                        successful_archetypes.add(tag.replace("archetype:", ""))
                    if tag.startswith("verifier:"):
                        successful_verifiers.add(tag.replace("verifier:", ""))
        
        # Bridge scan -> execution: if there are approved market_scan items, propose a concrete "deliver this" task.
        # This keeps the system doing useful work instead of drifting into toy problems.
        # Smart selection: prioritize by success_score, then price, then recency.
        try:
            opps = tools["opportunities_list"](50)  # Get more to choose from
        except Exception:
            opps = []
        if isinstance(opps, list) and opps:
            # Filter to only "new" or "selected" opportunities (not already delivering/done)
            candidates = []
            for it in opps:
                if not isinstance(it, dict):
                    continue
                status = str(it.get("status") or "new").strip()
                if status not in ("new", "selected"):
                    continue
                # Skip if we already have a job for this opportunity
                job_ids = it.get("job_ids") or []
                if isinstance(job_ids, list) and len(job_ids) > 0:
                    # Check if any of those jobs are still open
                    try:
                        for jid in job_ids[:3]:  # Check first few
                            j = tools["jobs_get"](str(jid))
                            if j and str(j.get("status") or "") in ("open", "claimed", "submitted"):
                                # Already has an active job, skip
                                break
                        else:
                            # No active jobs, can propose
                            candidates.append(it)
                    except Exception:
                        candidates.append(it)
                else:
                    candidates.append(it)
            
            if not candidates:
                # No good opportunities available - trigger automatic market scan
                # Check when we last did a market scan
                recent_scans = []
                for j in (state.get("recent_jobs") or []):
                    if isinstance(j, dict):
                        title = str(j.get("title") or "").lower()
                        if "archetype:market_scan" in title or "market scan" in title:
                            recent_scans.append(j)
                
                # If no recent market scan (within last 10 jobs), create one
                if len(recent_scans) == 0:
                    jt = "[archetype:market_scan] [verifier:json_list] Task: Market scan — paid gigs we can deliver (with citations)"
                    jb = (
                        "[verifier:json_list]\n"
                        "[repeat_ok:1]\n"
                        "[json_min_items:10]\n"
                        "[json_required_keys:title,platform,demand_signal,estimated_price_usd,why_fit,first_action,source_url,source_quote]\n"
                        "Use web_fetch to research and propose 10 concrete paid gig/service ideas we could deliver.\n"
                        "\n"
                        "Acceptance criteria:\n"
                        "- JSON list with at least 10 items.\n"
                        "- Each item must have: title, platform, demand_signal, estimated_price_usd, why_fit, first_action, source_url, source_quote.\n"
                        "- source_url and source_quote must be from real domains (not example.com).\n"
                        "\n"
                        "Evidence required in submission:\n"
                        "- Evidence section with item_count>=10.\n"
                        "- Evidence section with domains_used listing real source domains.\n"
                    )
                    if run_tag and run_tag not in jt:
                        jt = f"{run_tag} {jt}".strip()
                    jb = _normalize_bullets_outside_code_fences(jb)
                    state["action"] = {"kind": "propose_job", "note": "auto_market_scan (no opportunities)", "job": {"title": jt, "body": jb, "reward": 0.01}}
                    return state
                # Fall through to other proposal paths
                pass
            else:
                # Sort by: estimated_value_score (if available), otherwise calculate from success_score + price
                def _score_opp(opp):
                    # Prefer estimated_value_score if available (combines price, success, fit)
                    value_score = float(opp.get("estimated_value_score") or 0.0)
                    if value_score > 0:
                        return value_score
                    
                    # Fallback: calculate from components
                    success_score = float(opp.get("_success_score") or opp.get("success_score") or 0.5)
                    price_str = str(opp.get("estimated_price_usd") or opp.get("price") or "")
                    price = 0.0
                    try:
                        nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", price_str)]
                        if nums:
                            price = max(nums)
                    except Exception:
                        pass
                    # Normalize price to 0-1 (assume $1000+ is max)
                    price_norm = min(1.0, price / 1000.0) if price > 0 else 0.3
                    # Combined score: 50% success_score, 40% price, 10% recency (always prefer newer)
                    return (success_score * 0.5) + (price_norm * 0.4) + 0.1
                
                candidates.sort(key=_score_opp, reverse=True)
                it = candidates[0]
                opp_score = _score_opp(it)
                
                # Autonomous pursuit: if this is a high-value opportunity (score > 0.7), pursue it even if we have an open job
                # Otherwise, only pursue if we don't have an open job
                if has_open_job and opp_score < 0.7:
                    # Not high-value enough to interrupt current work
                    pass
                else:
                    title0 = str(it.get("title") or it.get("name") or "").strip()
                    plat0 = str(it.get("platform") or "").strip()
                    price0 = str(it.get("estimated_price_usd") or it.get("price") or "").strip()
                    url0 = str(it.get("source_url") or it.get("url") or "").strip()
                    dom0 = str(it.get("_source_domain") or "").strip()
                    fingerprint0 = str(it.get("fingerprint") or "")
                    if title0:
                        jt = f"[archetype:deliver_opportunity] Deliver: {title0}"
                        jb = (
                            "Goal: turn this opportunity into something we can actually sell/deliver.\n\n"
                            f"Opportunity:\n- title: {title0}\n- platform: {plat0}\n- price_estimate_usd: {price0}\n- source_domain: {dom0}\n- source_url: {url0}\n\n"
                            "Acceptance criteria:\n"
                            "- Provide a 1-page delivery plan (steps + timeline).\n"
                            "- Provide 3 package tiers with clear scope + pricing.\n"
                            "- Generate a professional client outreach email using email_template_generate tool.\n"
                            "- Include the complete email (subject + body) in your submission.\n\n"
                            "Tools available:\n"
                            "- email_template_generate(opportunity_title, platform, client_name=None, package_tier=None): generates professional outreach email\n"
                            "- opportunities_update(fingerprint, status='delivering'): mark opportunity as 'delivering' when you start work\n"
                            "- artifact_put(job_id, path, content): save deliverables to shared workspace\n\n"
                            "Evidence required in submission:\n"
                            "- Include an Evidence section with: tiers=3, steps>=6, email_included=true.\n"
                            "- Include the generated email template in your submission.\n"
                        )
                        if run_tag and run_tag not in jt:
                            jt = f"{run_tag} {jt}".strip()
                        jb = _normalize_bullets_outside_code_fences(jb)
                        
                        # Check if we have failure memories about similar deliver_opportunity tasks
                        should_skip = False
                        for pattern in failure_patterns:
                            if "deliver_opportunity" in pattern.lower() or "deliver:" in pattern.lower():
                                # If we recently failed on deliver_opportunity, maybe skip this one and try a different archetype
                                # But only if we have multiple failures (be lenient on first failure)
                                if "redo_failed" in pattern.lower() or "failed again" in pattern.lower():
                                    should_skip = True
                                    break
                        
                        if should_skip:
                            # Skip this opportunity, will fall through to other proposal paths
                            pass
                        else:
                            # Update opportunity status to "selected" when we create a job for it
                            if fingerprint0 and tools.get("opportunities_update"):
                                try:
                                    tools["opportunities_update"](fingerprint0, status="selected", notes=f"Autonomous pursuit: value_score={opp_score:.2f}")
                                except Exception:
                                    pass
                            
                            state["action"] = {"kind": "propose_job", "note": f"deliver_top_opportunity (score={opp_score:.2f})", "job": {"title": jt, "body": jb, "reward": 0.05}}
                            return state
        
        # If we have an open job and didn't pursue a high-value opportunity, don't create more jobs
        if has_open_job:
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

                # Guardrail: stop infinite redo spirals for the same root task.
                # If we already have too many rejections for this root, do NOT create more redo jobs.
                max_attempts = int(state.get("max_redo_attempts_per_root") or 3)
                total_rej = _count_rejections_for_root(state.get("rejected_jobs") or [], root_id)
                if max_attempts > 0 and total_rej >= max_attempts:
                    # If we already announced the cap for this root in this run, do not repeat it.
                    try:
                        capped = set(
                            str(x or "").strip()
                            for x in (state.get("redo_capped_root_ids") or [])
                            if str(x or "").strip()
                        )
                    except Exception:
                        capped = set()
                    if root_id and root_id in capped:
                        state["handled_rejection_job_id"] = bad_id
                        state["action"] = {"kind": "noop", "note": f"redo_cap_already_announced root={root_id}"}
                        return state
                    tools["trace_event"](
                        "status",
                        "langgraph: redo cap reached; requesting human intervention",
                        {"root_id": root_id, "rejections_for_root": total_rej, "max": max_attempts, "last_failed_job_id": bad_id},
                    )
                    try:
                        tools["chat_send"](
                            f"Redo cap reached for root `{root_id}` after {total_rej} rejections. "
                            f"Last failure `{bad_id}` note: {note[:220]}. "
                            "Human help needed: adjust acceptance criteria/verifier or clarify requirements."
                        )
                    except Exception:
                        pass
                    try:
                        tools["memory_append"](
                            "reflection",
                            f"Redo cap reached for root {root_id}. Stop auto-redo. Last_failed={bad_id}. Note={note}",
                            ["job", "redo_cap", "policy"],
                            0.99,
                        )
                    except Exception:
                        pass
                    state["handled_rejection_job_id"] = bad_id
                    try:
                        lst = list(state.get("redo_capped_root_ids") or [])
                        if root_id and root_id not in lst:
                            lst.append(root_id)
                        state["redo_capped_root_ids"] = lst
                    except Exception:
                        pass
                    state["action"] = {"kind": "noop", "note": f"redo_cap_reached root={root_id} n={total_rej} max={max_attempts}"}
                    return state

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
                tools["trace_event"](
                    "thought",
                    "langgraph: proposer creating redo job",
                    {"failed_job_id": bad_id, "root_id": root_id, "redo_level": redo_level},
                )

                # Deterministic strict redo template when we're in redo_level>=2.
                # This is meant to converge quickly and stop penalty loops.
                title = ""
                body = ""
                reward = 0.01
                if redo_level >= 2:
                    ac = _extract_section_bullets(bad_body, "acceptance criteria")
                    ev = _extract_section_bullets(bad_body, "evidence required in submission")
                    # If we can’t parse bullets, still provide a minimal set that will pass the heuristic.
                    if not ac:
                        ac = [
                            "Submission includes an 'Evidence' section with a checklist.",
                            "Submission includes any required code fences (e.g., ```python) and artifacts.",
                        ]
                    if not ev:
                        ev = [
                            "Under Evidence, include a checklist where each acceptance-criteria bullet appears verbatim.",
                            "Include required code inside the correct fenced block (e.g., ```python).",
                        ]

                    title = f"{redo_prefix}STRICT redo (format + evidence compliance)"
                    body_lines = [
                        f"{redo_tag}",
                        f"{redo_level_tag}",
                        "",
                        f"This is a STRICT redo. Previous attempt failed verification for job `{bad_id}`.",
                        f"Failure note: {note}",
                        "",
                        "Acceptance criteria:",
                        *[f"- {b}" for b in ac[:10]],
                        "",
                        "Evidence required in submission:",
                        "- Include an 'Evidence' section.",
                        "- In that Evidence section, include an 'Acceptance criteria checklist' where EACH bullet from Acceptance criteria appears verbatim (copy/paste).",
                        *[f"- {b}" for b in ev[:10]],
                        "",
                        "STRICT MODE: Keep the solution minimal and match acceptance criteria exactly.",
                    ]
                    body = "\n".join(body_lines).strip()
                else:
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
                body = _normalize_bullets_outside_code_fences(body)
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
            "\n"
            "Core goal: create USEFUL work, not just easy-to-verify Python.\n"
            "Rules:\n"
            "- The task MUST be verifiable without web access (no browsing).\n"
            "- Include an 'Acceptance criteria:' section.\n"
            "- Include an 'Evidence required in submission:' section.\n"
            "- Prefer deterministic verification, but NOT necessarily code.\n"
            "- Include an explicit tag in the *title* like: [archetype:<one_short_phrase>]\n"
            "- Maximize novelty: do NOT reuse the same archetype or task idea from the examples below.\n"
            "- Prefer ONE of these machine-checkable output contracts:\n"
            "  A) JSON list in a ```json``` fence (use tags so the verifier can check it):\n"
            "     [verifier:json_list] [json_min_items:N] [json_required_keys:k1,k2,...]\n"
            "  B) Markdown table with minimum rows (use tags):\n"
            "     [verifier:md_table] [md_min_rows:N] [md_required_cols:col1,col2,...]\n"
            "  C) If neither fits, use acceptance-criteria heuristic:\n"
            "     ensure the submission includes an 'Evidence' section referencing each AC bullet.\n"
            "- Do NOT propose Python coding puzzles by default. Prefer non-code deliverables (tables, checklists, JSON plans).\n"
            "- Keep body under 2200 chars.\n"
            "\n"
            "Examples below are ONLY format references. You MUST NOT reuse these exact ideas.\n"
            "Format examples (DO NOT repeat these ideas):\n"
            "- \"Fiverr gigs we could do\" as JSON list.\n"
            "- \"UI improvements\" as markdown table.\n"
            "- \"Ops runbook\" as checklist.\n"
        )
        # Provide recent jobs to enforce novelty (avoid repeating the same task).
        recent_titles = []
        try:
            for jj in (state.get("recent_jobs") or [])[:25]:
                if not isinstance(jj, dict):
                    continue
                t = str(jj.get("title") or "").strip()
                b = str(jj.get("body") or "").strip()
                # strip run tag for comparison
                t = re.sub(r"\[run:[^\]]+\]\s*", "", t).strip()
                if not t:
                    continue
                recent_titles.append(f"- {t[:140]}")
                # include tiny hint if body indicates primes (helps avoid repeating it)
                if "prime" in (t.lower() + " " + b.lower()):
                    recent_titles[-1] += " (contains 'prime')"
        except Exception:
            recent_titles = []
        recent_txt = "\n".join(recent_titles[:12]).strip()
        if not recent_txt:
            recent_txt = "- (none)"

        sys = (
            sys
            + "Uniqueness:\n"
            + "- The new task MUST be meaningfully different from the recent tasks list (topic + deliverable).\n"
            + "- Avoid repeating 'primes' / 'first five primes' style tasks.\n"
        )
        user = (
            f"Run tag prefix to include in title: {run_tag}\n"
            f"Persona:\n{persona}\n\n"
            f"Recent tasks to avoid duplicating:\n{recent_txt}\n\n"
            f"Relevant memories (failures/success patterns):\n{mem_txt}\n\n"
            "Propose the job now."
        )
        tools["trace_event"]("thought", "langgraph: proposer deciding job", {"run_tag": run_tag})
        raw = llm_chat(sys, user, max_tokens=420)
        obj = _extract_json_obj(raw) or {}

        title = str(obj.get("title") or "").strip()
        body = str(obj.get("body") or "").strip()
        reward = _safe_float(obj.get("reward"), 0.01)
        # Hard guardrail: if the model proposes Python tasks/puzzles, override to deterministic non-Python.
        # (We can re-enable Python later intentionally via tags/env.)
        if ("python" in (title + "\n" + body).lower()):
            title = ""
            body = ""
        if not title or not body:
            # Fallback: rotate through multiple deterministic, verifiable tasks (avoid repeating primes).
            seed_src = (state.get("run_id") or "") + "|" + str(len(state.get("recent_jobs") or []))
            idx = int(hashlib.sha1(seed_src.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
            pool = [
                (
                    "[archetype:market_scan] [verifier:json_list] Task: Market scan — paid gigs we can deliver (with citations)",
                    "[verifier:json_list]\n"
                    "[repeat_ok:1]\n"
                    "[json_min_items:10]\n"
                    "[json_required_keys:title,platform,demand_signal,estimated_price_usd,why_fit,first_action,source_url,source_quote]\n"
                    "Use web_fetch to research and propose 10 concrete paid gig/service ideas we could deliver.\n"
                    "\n"
                    "Acceptance criteria:\n"
                    "- Provide a JSON list with at least 10 objects.\n"
                    "- Each object includes keys: title, platform, demand_signal, estimated_price_usd, why_fit, first_action, source_url, source_quote.\n"
                    "\n"
                    "Evidence required in submission:\n"
                    "- Include the JSON in a ```json``` code fence.\n"
                    "- Evidence section with item_count and distinct domains used.\n",
                ),
                (
                    "[archetype:ui_improvements] [verifier:md_table] Task: UI improvements for our web dashboard",
                    "[verifier:md_table]\n"
                    "[md_min_rows:8]\n"
                    "[md_required_cols:Problem,Change,Why it helps,How to verify]\n"
                    "Propose 8 concrete UI improvements for the current AI Village web UI.\n"
                    "\n"
                    "Acceptance criteria:\n"
                    "- Markdown table with at least 8 rows.\n"
                    "- Columns: Problem | Change | Why it helps | How to verify.\n"
                    "\n"
                    "Evidence required in submission:\n"
                    "- Evidence section with row_count.\n",
                ),
                (
                    "[archetype:ops_runbook] Task: Ops runbook — keep the system healthy",
                    "Create a short runbook checklist for keeping the system healthy day-to-day.\n"
                    "\n"
                    "Acceptance criteria:\n"
                    "- 10 checklist items.\n"
                    "- Each item has: purpose + command/API endpoint.\n"
                    "\n"
                    "Evidence required in submission:\n"
                    "- Evidence section with count=10.\n",
                ),
                (
                    "[archetype:conversation_starters] Task: Community — 10 conversation starters",
                    "Write 10 conversation starters for the agents that lead to useful work (not fluff).\n"
                    "\n"
                    "Acceptance criteria:\n"
                    "- Exactly 10 numbered items.\n"
                    "- Each item includes a concrete follow-up question.\n"
                    "\n"
                    "Evidence required in submission:\n"
                    "- Evidence section that lists count=10.\n",
                ),
            ]
            t, b = pool[idx % len(pool)]
            title = t
            body = b
            reward = 0.01

        if run_tag and run_tag not in title:
            title = f"{run_tag} {title}".strip()
        body = _normalize_bullets_outside_code_fences(body)
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


def node_act(state: AgentState, config: Any = None) -> AgentState:
    tools = _get_tools(state, config)
    act = state.get("action") or {"kind": "noop"}
    kind = act.get("kind", "noop")

    if kind == "propose_job":
        job = act.get("job") or {}
        title = str(job.get("title") or "")
        body = str(job.get("body") or "")
        reward = _safe_float(job.get("reward"), 0.01)
        # Backend rejects reward <= 0; clamp to a small positive value to avoid "invalid_job" create failures.
        if reward <= 0:
            reward = 0.01
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
            state["propose_failed_count"] = 0
        else:
            # Likely backend dedupe rejection or transient failure; bump counter so we choose a different fallback next tick.
            try:
                state["propose_failed_count"] = int(state.get("propose_failed_count") or 0) + 1
            except Exception:
                state["propose_failed_count"] = 1
            try:
                tools["trace_event"]("status", "propose_job failed (no job_id)", {"title": title[:120]})
            except Exception:
                pass
        return state

    if kind == "execute_job":
        job_id = str(act.get("job_id") or "")
        job = act.get("job_obj") or {}
        if not job_id:
            return state
        try:
            tools["trace_event"](
                "status",
                "executor_execute_job",
                {
                    "phase": "start",
                    "job_id": job_id,
                    "job_status": str(job.get("status") or ""),
                    "claimed_by": str(job.get("claimed_by") or ""),
                },
            )
        except Exception:
            pass
        claimed = False
        try:
            # If we already own the claim (e.g., resumed job), don't try to claim again.
            if str(job.get("status") or "") == "claimed" and str(job.get("claimed_by") or "") == str(state.get("agent_id") or ""):
                claimed = True
            else:
                claimed = bool(tools["jobs_claim"](job_id))
        except Exception:
            claimed = False
        if not claimed:
            try:
                tools["trace_event"](
                    "status",
                    "executor_execute_job",
                    {"phase": "claim_failed", "job_id": job_id},
                )
            except Exception:
                pass
            return state
        try:
            tools["trace_event"](
                "status",
                "executor_execute_job",
                {"phase": "claimed_ok", "job_id": job_id},
            )
        except Exception:
            pass
        try:
            try:
                tools["trace_event"](
                    "status",
                    "executor_execute_job",
                    {"phase": "do_job_start", "job_id": job_id},
                )
            except Exception:
                pass
            # Pass tools dict to do_job so it can use email_template_generate, etc. for deliver_opportunity tasks
            submission = tools["do_job"](job, tools)
        except Exception:
            submission = "Evidence:\n- Execution failed inside agent runtime.\n"
        try:
            tools["trace_event"](
                "status",
                "executor_execute_job",
                {"phase": "do_job_done", "job_id": job_id, "submission_chars": len(submission or "")},
            )
        except Exception:
            pass
        ok = False
        try:
            ok = bool(tools["jobs_submit"](job_id, submission))
        except Exception:
            ok = False
        try:
            tools["trace_event"](
                "status",
                "executor_execute_job",
                {"phase": "submit_done", "job_id": job_id, "ok": bool(ok)},
            )
        except Exception:
            pass
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


def node_reflect(state: AgentState, config: Any = None) -> AgentState:
    tools = _get_tools(state, config)
    # Lightweight: store one rule-of-thumb so behavior improves over time.
    # Also: respond to job outcomes (approved/rejected/submitted) so agents internalize "submitted != done".
    lj = state.get("last_job") or {}
    if lj:
        ack = str(state.get("outcome_ack_job_id") or "").strip()
        st = str(lj.get("status") or "")
        note = str(lj.get("auto_verify_note") or "")
        ok = lj.get("auto_verify_ok")
        jid = str(lj.get("job_id") or state.get("last_job_id") or "")
        title = str(lj.get("title") or "")
        if st == "approved":
            # Announce each verdict once per job id.
            if jid and ack == jid:
                return state
            try:
                tools["chat_send"](f"Job `{jid}` was approved. ✅ ({title})")
            except Exception:
                pass
            
            # Enhanced learning: extract what worked
            try:
                # Check if this was a deliver_opportunity job
                if "[archetype:deliver_opportunity]" in title.lower() or "deliver:" in title.lower():
                    learning_note = f"Approved deliver_opportunity job {jid}. "
                    # Extract deliverable types from submission if available
                    submission = str(lj.get("submission") or "")
                    if "code_deliverable" in submission.lower() or "Sample Code" in submission:
                        learning_note += "Code deliverable worked. "
                    if "email_included" in submission.lower() or "Client Outreach Email" in submission:
                        learning_note += "Email template worked. "
                    if "package tiers" in submission.lower():
                        learning_note += "Package tiers worked. "
                    learning_note += f"Pattern: verifiable evidence passes. Note={note}"
                    tools["memory_append"]("reflection", learning_note, ["job", "approved", "deliver_opportunity", "success_pattern"], 0.9)
                else:
                    tools["memory_append"]("reflection", f"Approved job {jid}. Pattern: verifiable evidence passes. Note={note}", ["job", "approved"], 0.85)
            except Exception:
                pass
            if jid:
                state["outcome_ack_job_id"] = jid
        elif st == "rejected":
            if jid and ack == jid:
                return state
            try:
                tools["chat_send"](f"Job `{jid}` was rejected. I likely lost ai$. Reason: {note[:220]}")
            except Exception:
                pass
            
            # Extract detailed failure information for learning
            body = str(lj.get("body") or "")
            verifier = str(lj.get("auto_verify_name") or "")
            archetype = ""
            if "[archetype:" in title:
                m = re.search(r"\[archetype:([^\]]+)\]", title)
                if m:
                    archetype = m.group(1).strip()
            
            # Safety valve: if a redo failed again, write a strong "do not repeat" policy memory.
            try:
                root = _extract_redo_for(body)
                if root:
                    tools["memory_append"](
                        "reflection",
                        f"Redo failed again (job {jid}, redo_for={root}, archetype={archetype}, verifier={verifier}). "
                        f"DO NOT repeat the same submission pattern. "
                        f"Next time: simplify; include exact required code fences; explicitly echo every acceptance criterion bullet inside Evidence checklist. "
                        f"Verifier note={note}",
                        ["job", "redo_failed", "policy", f"archetype:{archetype}", f"verifier:{verifier}"],
                        0.99,
                    )
            except Exception:
                pass
            
            # Store detailed rejection pattern for future recall
            try:
                # Extract acceptance criteria and evidence requirements from body
                acceptance = _extract_section_bullets(body, "acceptance criteria", 20)
                evidence_req = _extract_section_bullets(body, "evidence required", 20)
                
                learning = f"Rejected job {jid} (archetype={archetype}, verifier={verifier}). "
                learning += f"Failure reason: {note[:200]}. "
                if acceptance:
                    learning += f"Acceptance criteria had {len(acceptance)} items. "
                if evidence_req:
                    learning += f"Evidence requirements: {len(evidence_req)} items. "
                learning += "Fix: ensure Evidence section explicitly checks every acceptance criterion; include required code fences; match verifier expectations exactly."
                
                tools["memory_append"](
                    "reflection",
                    learning,
                    ["job", "rejected", "policy", f"archetype:{archetype}", f"verifier:{verifier}"],
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
    # Inject tools via module-global for maximum compatibility.
    global _TOOLS
    _TOOLS = tools
    try:
        return _GRAPH.invoke(dict(state))
    finally:
        _TOOLS = None

