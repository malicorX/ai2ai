# TODO — “Smarter from the inside” (LangGraph control-plane)

This file captures the current architecture and the concrete places to improve agent intelligence **from inside the agent runtime** (LangGraph/state machine), not by external “hand-holding”.

## Current architecture (as implemented)

### Backend (`backend/app/main.py`)
- **Authoritative world**: world state, agents, landmarks; UI via websocket + REST.
- **Runs**: `/admin/new_run` archives logs into run folder, resets in-memory state.
- **Jobs board**: Jobs are created/claimed/submitted/reviewed; job events persisted append-only.
- **Verification + incentives**:
  - Auto-verification runs on submission (task-type-specific).
  - **Reward only on approval**; failed verification triggers **penalty** (ai$ deduction).
- **Memory store**: append + retrieve endpoints, ranked retrieval with recency/importance + optional embeddings.

### UI (`backend/app/static/index.html`)
- Static frontend served at `/ui/` to control runs, inspect summaries, open per-run viewers, trigger verify-pending.

### Agents (`agents/agent_template/agent.py`)
- Long-running loop: perceive → decide → act → reflect.
- Today: control flow is mostly **hand-coded** with occasional LLM calls as subroutines.
- Conversation “stickiness” exists (`[conv:<id>]` + `[bye]`) and has its own state.
- Agent roles:
  - **proposer** (`agent_1`): create jobs.
  - **executor** (`agent_2`): claim + produce deliverable + submit.

### LangGraph usage today
- `agents/agent_template/langgraph_runtime.py` currently provides a basic `llm_chat()` wrapper.
- `langgraph` is installed, but the agent loop is **not** a real LangGraph state machine yet.

## Why we’re changing it

Agents must internalize:
- “submitted” ≠ “done”; only “approved” ≈ done.
- work must be **verifiable**; talk is not evidence.
- expected value thinking: \(E[\$] = reward \cdot P(pass) - penalty \cdot P(fail)\).

We want these behaviors to be enforced by the agent’s **internal control-plane** (LangGraph graph + state + invariants), not by external UI rules.

## High-leverage “attack points” (inside agent runtime)

### 1) Perception → structured world model
Create a compact JSON world model each tick (noise-free):
- time/day/minute, self position/place, nearby agents, nearby landmarks
- open/claimed/submitted jobs relevant to role
- constraints: ai$ balance, tool budget, conversation state

### 2) Decision policy → explicit state machine with invariants
Replace “do a bunch of maybes” with a graph:
- `Perceive → Recall → SelectGoal → Plan → Act → Verify/Wait → Reflect`
- hard invariants (code, not prompt-only):
  - never claim completion without evidence
  - “done” only when job status is `approved`
  - executor: one job at a time
  - proposer: only propose tasks that have a verification plan

### 3) Verification-first planning
Proposer must produce tasks with:
- acceptance criteria
- required artifacts/evidence format
- verifier type/strategy (deterministic / artifact / human)
If no verifiable plan exists, route to “ask for clarification” or pick another task.

### 4) Memory used only at the right points
- `Recall` before choosing a goal (retrieve failures/successes and current commitments)
- `Reflect` after outcome (especially verifier fail) to update strategy

### 5) Tool use gated + auditable
Only allow tool-heavy work from specific graph states, record evidence.

## Implementation roadmap (incremental)

### Phase A — Introduce LangGraph control-plane module (no behavior break)
- Add a module that defines:
  - `AgentState` schema (TypedDict / pydantic)
  - `Action` schema (enum + payload)
  - minimal graph skeleton and runner
- Wire into `agent.py` under `USE_LANGGRAPH=1` while keeping legacy path available.

### Phase B — Move job logic into the graph (highest ROI)
- Proposer path:
  - propose *verifiable* job with acceptance criteria + evidence requirements
  - post it, notify executor in chat, end conversation if appropriate
- Executor path:
  - claim job, produce deliverable artifacts (markdown + code fences), submit
  - explicitly include “Evidence:” section in submission

### Phase C — Memory + outcome-driven improvements
- Recall “what failed verification?” and avoid repeating.
- Reflect after verify/review events; store short strategy updates.

### Phase D — Replace remaining legacy “maybe_*” control flow
- Move movement goals and social behaviors under graph states (optional).

## Acceptance criteria for “start implementing”
- LangGraph step runs without crashing when `USE_LANGGRAPH=1`.
- Agent produces **structured** actions (even if minimal at first).
- Job submissions consistently include verifiable evidence formatting.
- Docker images copy the new LangGraph module(s) into containers.

