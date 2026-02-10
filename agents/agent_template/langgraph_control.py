"""
LangGraph control-plane: AgentState, Action, and graph topology.

Phase A (TODO.md): Minimal module defining the agent state schema and action schema
so the graph skeleton and runner can be wired in agent.py under USE_LANGGRAPH=1
without changing legacy behavior. Node implementations live in langgraph_agent.
"""

from __future__ import annotations

from typing import List, Literal, TypedDict


Role = Literal["proposer", "executor"]


class ProposedJob(TypedDict):
    title: str
    body: str
    reward: float


class Action(TypedDict, total=False):
    kind: Literal["noop", "propose_job", "execute_job", "review_job", "move", "chat_say", "board_post"]
    note: str
    job: ProposedJob
    job_id: str
    job_obj: dict
    approved: bool
    dx: int
    dy: int
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
    action: Action
    acted: bool


# Graph topology: Perceive → Recall → Decide → Act → Reflect (TODO Phase 2: invariants live in nodes).
GRAPH_STEPS = ("perceive", "recall", "decide", "act", "reflect")
