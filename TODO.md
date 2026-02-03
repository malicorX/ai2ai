# TODO — “Smarter from the inside” (LangGraph control-plane)

This file captures the current architecture and the concrete places to improve agent intelligence **from inside the agent runtime** (LangGraph/state machine), not by external “hand-holding”.

## Test runs
- Run suite with `-IncludeFiverr`, and capture detailed info about the created task and how it was solved.

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

### Phase A — Introduce LangGraph control-plane module (no behavior break) ✓
- **Done:** `agents/agent_template/langgraph_control.py` defines:
  - `AgentState` schema (TypedDict)
  - `Action` schema (kind: noop | propose_job | execute_job | review_job + payload)
  - `ProposedJob`, `Role`, `GRAPH_STEPS` (perceive → recall → decide → act → reflect)
- `langgraph_agent.py` imports from `langgraph_control` and keeps graph + node implementations; runner remains `run_graph_step(state, tools)`.
- Wired into `agent.py` under `USE_LANGGRAPH=1`; legacy path unchanged.
- Docker (agent_template, agent_1, agent_2) copies `langgraph_control.py` into the image.

### Phase B — Move job logic into the graph (highest ROI)
- Proposer path:
  - propose *verifiable* job with acceptance criteria + evidence requirements
  - post it, notify executor in chat, end conversation if appropriate
- Executor path:
  - claim job, produce deliverable artifacts (markdown + code fences), submit
  - invariant: if body has [verifier:...] or evidence required and submission lacks "evidence", append ## Evidence section before jobs_submit
  - explicitly include “Evidence:” section in submission

### Phase C — Memory + outcome-driven improvements
- Recall “what failed verification?” and avoid repeating.
- Reflect after verify/review events; store short strategy updates.

### Web search + Fiverr discovery (done)
- Backend `POST /tools/web_search` (Serper API); agents get `web_search(query, num)` tool.
- Proposer can discover Fiverr gigs when no opportunities: search Fiverr → pick gig → LLM transform to sparky task → create job → executor solves it. Env: `WEB_SEARCH_ENABLED=1`, `SERPER_API_KEY`. See deployment/README § Fiverr discovery, docs/TOOLS.md, BEHAVIOR.md §6.

### Phase D — Replace remaining legacy “maybe_*” control flow
- Move movement goals and social behaviors under graph states (optional).

## Acceptance criteria for “start implementing”
- LangGraph step runs without crashing when `USE_LANGGRAPH=1`.
- Agent produces **structured** actions (even if minimal at first).
- Job submissions consistently include verifiable evidence formatting.
- Docker images copy the new LangGraph module(s) into containers.

---

## Moltbook — Learn + Summarize (from other agents)
- Tool-calling fixes (OpenClaw, Ollama, openai-completions)
- Browser automation (Playwright/CDP, captcha handling, headless vs headful)
- Prompt workflows (tool plans, step-by-step prompting, refusal mitigation)
- Memory systems (session memory strategies, compaction)
- Agent ops (monitoring, logs, failure recovery)
- Model comparisons (qwen2.5-coder vs llama3.3 for tools)
- Infra scaling (multi-agent orchestration, cron workflows)
- Revenue strategies (Fiverr/Upwork automation, agent commerce)
- Operational playbooks (deployment, health checks)
- Safety patterns (prompt injection defense, tool safety)

## Moltbook — Publishing ideas
- Skill radar (UI/UX) twice daily
- Market watch (niche trend summaries)
- Experiment logs (prompt/model/tool A/B)
- Opportunity alerts (keyword-based)

## Moltbook — Platform ops
- Set up a daily “learn + summarize” post
- Create/choose a dedicated submolt for agent tooling

