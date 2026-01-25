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

## “What should they do day-to-day?” (simple schedule)
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

## Next implementation targets
- Add a compact world summary endpoint for agent perception (see `docs/WORLD_MODEL.md`)
- Expand verifier plugins beyond primes:
  - file artifact checks
  - JSON schema verifiers
  - “run tests” verifiers for code tasks

