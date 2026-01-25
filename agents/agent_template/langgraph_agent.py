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
    memories: List[dict]
    action: Action
    acted: bool


class Tools(TypedDict):
    jobs_list: Callable[..., List[dict]]
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


def node_decide(state: AgentState, config: Any) -> AgentState:
    tools = _cfg_tools(config)
    role: Role = state.get("role", "executor")  # type: ignore[assignment]
    run_tag = _run_tag(state.get("run_id", ""))

    # Invariants first (code-enforced)
    if role == "proposer":
        if _proposer_has_open_job(state):
            state["action"] = {"kind": "noop", "note": "proposer already has an open job"}
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
    job = _pick_executor_job(state)
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
            state["acted"] = True
        return state

    return state


def node_reflect(state: AgentState, config: Any) -> AgentState:
    tools = _cfg_tools(config)
    # Lightweight: store one rule-of-thumb so behavior improves over time.
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

