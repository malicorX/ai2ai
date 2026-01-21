# ADR 0002: Local LLM runtime on DGX (vLLM vs Ollama)

## Status
Proposed

## Context
We prefer **quality over speed** and will run locally on DGX hardware.
We need:
- stable serving
- control over batching, context length, and model selection
- predictable performance for tool-heavy agents

## Decision (proposed)
Use **vLLM** (or NVIDIA’s inference stack if preferred) as the primary model server for 70B+ class models.
Keep **Ollama** as a convenience option for quick swaps and smaller models.

## Consequences
- Pros: better serving control and throughput; clearer operational knobs.
- Cons: more setup complexity than Ollama.

## Alternatives considered
- Ollama only (simpler, less control)
- Remote APIs (not aligned with DGX local compute + privacy)

