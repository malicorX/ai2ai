# ADR 0001: Agent framework choice (LangGraph vs AutoGen)

## Status
Proposed

## Context
Agents must be long-running operators with:
- complex tool policies + audit logging
- resumable workflows
- multi-agent collaboration
- “quality over speed” execution

## Decision (proposed)
Use **LangGraph** as the primary agent orchestration framework.

## Consequences
- Pros: explicit control flow, checkpoints, strong governance over tool use.
- Cons: more upfront structure than simpler agent loops; requires deliberate design.

## Alternatives considered
- **Microsoft AutoGen**: excellent for multi-agent dialogue orchestration; less explicit graph control.
- **CrewAI**: fast to prototype role teams; less flexible for strict tool governance.

