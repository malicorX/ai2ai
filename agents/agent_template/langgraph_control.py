"""
LangGraph control-plane: AgentState, Action, and graph topology.

Phase A (TODO.md): Minimal module defining the agent state schema and action schema
so the graph skeleton and runner can be wired in agent.py under USE_LANGGRAPH=1
without changing legacy behavior. Node implementations live in langgraph_agent.
"""

from __future__ import annotations

from typing import List, Literal, TypedDict


Role = Literal["proposer", "executor", "explorer"]


class ProposedJob(TypedDict):
    title: str
    body: str
    reward: float


class Action(TypedDict, total=False):
    kind: Literal["noop", "propose_job", "execute_job", "review_job", "move", "go_to", "chat_say", "board_post", "web_search"]
    note: str
    query: str
    num: int
    job: ProposedJob
    job_id: str
    job_obj: dict
    approved: bool
    dx: int
    dy: int
    target: str  # landmark id for go_to (e.g. board, cafe, rules)
    text: str
    title: str
    body: str


class AgentState(TypedDict, total=False):
    role: Role
    agent_id: str
    display_name: str
    persona: str
    run_id: str
    world: dict
    balance: float
    chat_recent: List[dict]
    open_jobs: List[dict]
    my_claimed_jobs: List[dict]
    rejected_jobs: List[dict]
    recent_jobs: List[dict]
    my_submitted_jobs: List[dict]
    memories: List[dict]
    world_model: dict
    last_job_id: str
    last_job: dict
    handled_rejection_job_id: str
    outcome_ack_job_id: str
    redo_capped_root_ids: List[str]
    propose_failed_count: int
    max_redo_attempts_per_root: int
    __tools: dict
    __wake_only: bool  # True when turn is MoltWorld wake with only recent_chat (skip jobs/memory for speed)
    current_goals: dict  # optional short_term, medium_term, long_term (see WORLD_MODEL § Goal tiers)
    last_action_kinds: List[str]  # last 3 action kinds (for nudge: prefer concrete action after repeated chat/noop)
    last_web_search_result: dict  # {query, results: [...]} from last web_search action (for next decide)
    recent_earnings: List[dict]  # [{amount, reason, created_at}] so agent learns what earned ai$
    earn_how: str  # short text: how to earn ai$ (diversity + Fiverr discovery)
    action: Action
    acted: bool


# Graph topology: Perceive → Recall → Decide → Act → Reflect (TODO Phase 2: invariants live in nodes).
GRAPH_STEPS = ("perceive", "recall", "decide", "act", "reflect")
