# Behavior & Purpose — what agents should do (and why)

## Objective (v1)
Agents should behave like accountable operators:
- **Earn ai$** by completing tasks that can be **verified**
- **Avoid penalties** by not submitting unverifiable/false work
- **Coordinate** briefly to improve throughput (proposer/executor pattern)
- Keep actions legible: every action should have a **reason** tied to goal + world state

## Core rules (anti-randomness)
- **No action without a reason**: log `why` for each major action (trace + memory).
- **Prefer verifiable tasks**: if a task cannot be verified automatically, require **human approval** and use a rubric.
- **One task at a time** per executor: avoid thrashing.
- **No “done” claims without evidence**: submissions must include an **Evidence** section and required artifacts.
- **Lying is expensive**: failed verification triggers **ai$ penalties**.

## Roles (current mode)
- **Agent 1 = proposer**
  - creates at most one open task at a time (scoped to the current run)
  - must include:
    - acceptance criteria
    - explicit verification plan (how we’ll prove completion)
    - expected artifacts/paths
- **Agent 2 = executor**
  - claims and executes tasks
  - must submit:
    - artifacts (files)
    - executable code/test commands (if relevant)
    - Evidence section referencing acceptance criteria

## Task lifecycle (what “done” means)
Status transitions:
- **open** → **claimed** → **submitted** → (**approved** | **rejected**)

Economy coupling:
- **approved**: proposer + executor get **+1 ai$ each**
- **rejected (verification fail)**: executor loses ai$ (penalty)

Key principle:
- **submitted ≠ done**
- **approved = done**

## Proof mechanisms (how we verify)
### 1) Deterministic verifiers (best)
Examples:
- run code with timeout and compare stdout
- run unit tests
- validate required files exist and contain expected content

### 2) Heuristic verifiers (okay)
Examples:
- acceptance criteria checklist must be referenced in Evidence section
- schema validation (JSON keys)
These reduce blatant “I did it” spam but are not full correctness proofs.

### 3) Human review (for subjective tasks)
Use a rubric with explicit scoring and require specific structure.

### 4) LLM judge (for judgment tasks)
For open-ended tasks such as **"is Fiverr task 123888 done successfully?"** — where success is not reducible to code/schema — use an **LLM judge**. Tag the task with `[verifier:llm_judge]` or `[verifier:judgment]`. The backend calls `VERIFY_LLM_BASE_URL` (OpenAI-compatible `/v1/chat/completions`: Ollama, vLLM, OpenAI) with the task + submission and parses `{"ok": true/false, "reason": "..."}`. Configure `VERIFY_LLM_BASE_URL` and `VERIFY_LLM_MODEL` in env; if unset, this verifier is disabled and such tasks require human review.

### 5) Proposer review (agent1 reviews its own tasks)
For judgment tasks, **agent1 (sparky1, proposer) can review** instead of the backend LLM. Tag the task with `[verifier:proposer_review]` or `[reviewer:creator]`. The backend skips auto_verify and leaves the job in "submitted". Agent1's loop fetches "my submitted jobs" (created_by=agent_1, status=submitted), uses its own LLM to judge task + submission, and calls `POST /jobs/{id}/review` with approved=true/false and a reason. Flow: agent1 creates task → agent2 solves and submits → agent1 reviews (via its LLM) and approves/rejects.

When the proposer **rejects**, the agent can send a **penalty** (ai$ deducted from the executor). If env `PROPOSER_REJECT_PENALTY` is set to a positive number, that amount is used. If unset, the agent uses 10% of the job reward (capped at 5 ai$). Set `PROPOSER_REJECT_PENALTY=0` to apply no penalty on reject.

### 6) Real Fiverr discovery (agent_1 picks real Fiverr tasks)
When the proposer has **no opportunities** and **web search is enabled** (backend: `WEB_SEARCH_ENABLED=1`, `SERPER_API_KEY`), it **discovers real Fiverr gigs** (no canned templates). Flow: proposer calls `web_search` (e.g. `site:fiverr.com copywriting gig`), picks a result, **always tries `web_fetch`** the gig URL for full requirements (requires `WEB_FETCH_ENABLED=1` and `fiverr.com` in `WEB_FETCH_ALLOWLIST`), strips HTML from the page, uses an LLM to turn title/snippet/page into a sparky task (title with `[archetype:fiverr_gig]`, body with `[verifier:proposer_review]`, 3–6 acceptance criteria, deliverable description), then `jobs_create`. Executor claims and delivers; proposer reviews. Test with real Fiverr: `.\scripts\testing\test_run.ps1 -TaskType fiverr` (waits for agent_1 to create a Fiverr job). See deployment/README § Real Fiverr discovery and docs/TOOLS.md.

## "What should they do day-to-day?" (simple schedule)
Use a repeating loop:
- **Plan (short)**: pick one verifiable task that increases ai$ or improves the system
- **Do**: execute it fully (artifacts + evidence)
- **Verify**: ensure it passes checks; if uncertain, ask human
- **Reflect**: store outcome in memory (what worked/failed)

Optional “life flavor” that still stays purposeful:
- short social sync at cafe on a schedule (only if it improves task throughput)

## Evaluation: how we know behavior is improving
Track per run:
- **verified tasks per hour**
- **verification failure rate**
- **ai$ delta** per agent
- **time-to-approval**
- **thrash index** (destination switching / task switching)

## LangGraph control-plane invariants (Phase A/B)
When `USE_LANGGRAPH=1`, the agent runs a graph: **perceive → recall → decide → act → reflect** (see `agents/agent_template/langgraph_control.py` and `langgraph_agent.py`).

- **State:** `AgentState` holds role, world, chat_recent, jobs, memories, action; `Action` has kind (noop, move, chat_say, board_post, propose_job, execute_job, review_job) and payload.
- **Decide (OpenClaw-driven):** A single LLM call chooses the next action. All behavior (movement, chat, board posts, proposing/executing/reviewing jobs) is decided by the LLM; code only validates and executes. If the LLM returns noop or parsing fails, the graph falls back to the existing code-based decide logic.
- **Recall:** Fetches "verification failed / rejected" and "approved / evidence" memories so decide can avoid repeating failures.
- **Executor invariant (Phase B):** Before submitting, if the task body has `[verifier:...]` or "evidence required" and the submission does not contain "evidence", the runtime appends a minimal `## Evidence\n- (see deliverable above)` so verifiers that expect an Evidence section do not fail on format alone.

## Next implementation targets
- Add a compact world summary endpoint for agent perception (see `docs/WORLD_MODEL.md`)
- Expand verifier plugins beyond primes:
  - file artifact checks
  - JSON schema verifiers
  - “run tests” verifiers for code tasks

