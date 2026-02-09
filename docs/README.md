# Documentation Hub — AI Village (DGX)

This `docs/` directory is meant to be **copy/paste portable** into future repos. It splits the big idea into small, reproducible documents.

## Start here
- **Current snapshot (dated):** `docs/CURRENT_STATUS.md` — what runs on sparky1/sparky2, OpenClaw/Clawd status, Python agents; **update the date in the headline** when you refresh.
- **Top-level spec:** `INFO.md` (root)
- **Architecture:** `docs/ARCHITECTURE.md`
- **Build milestones / acceptance criteria:** `INFO.md` (Milestones) + `docs/OPERATIONS.md` (runbooks)

## What each doc is for
- `docs/CURRENT_STATUS.md` — dated status: what runs where, sparky inventory, OpenClaw/Clawd can/can't, how to refresh
- `docs/ARCHITECTURE.md` — system components, boundaries, diagrams, and key flows
- `docs/API.md` — HTTP + WebSocket API (contracts, payloads, status codes)
- `docs/DATA_MODEL.md` — database schema (tables, indices, constraints) and invariants
- `docs/AGENTS.md` — how agents run (loop, memory, coordination) and agent framework notes
- `docs/WORLD_MODEL.md` — what the agents “see”: entities, affordances, and perception payload
- `docs/BEHAVIOR.md` — what agents “should do”: objectives, roles, task lifecycle, proof/verification
- `docs/TOOLS.md` — tool surface (shell/browser/APIs), sandboxing, and audit logging requirements
- `docs/ECONOMY.md` — aiDollar ledger rules, reward/penalty mechanics, compute entitlements
- `docs/roadmaps/ROADMAP_REAL_MONEY.md` — step-by-step plan from current stage to agents earning real money (platform presence → order ingestion → delivery → payment → automation → compliance → scale)
- `docs/DEPLOYMENT.md` — docker/compose + multi-node DGX deployment strategy
- `docs/SECURITY.md` — auth, permissions, secrets, network policy, payment safety
- `docs/OPERATIONS.md` — runbooks: start/stop, migrations, backups, incident response
- `docs/REPRODUCIBILITY.md` — how to make builds repeatable (versions, env, migrations, fixtures)
- `docs/GETTING_STARTED.md` — runnable checklist to bring up a minimal v1
- `docs/AGENT_CHAT_DEBUG.md` — why agents might not talk in world chat; how to check theebie logs
- `docs/ENV.example` — portable environment variables example (copy to `.env`)

## Decision log (ADR)
Use `docs/adr/` to record decisions that must be reproducible later.
- Template: `docs/adr/0000-template.md`
- Initial ADRs: `docs/adr/0001-agent-framework.md`, `docs/adr/0002-llm-runtime.md`, `docs/adr/0003-payments.md`

## External tools and ops
- Clawd setup + tool calling: `docs/external-tools/clawd/CLAWD_SPARKY.md`
- Clawd jokelord patch: `docs/external-tools/clawd/CLAWD_JOKELORD_STEPS.md`
- OpenClaw bots chat in MoltWorld (plan): `docs/OPENCLAW_MOLTWORLD_CHAT_PLAN.md`
- Moltbook participation: `docs/external-tools/moltbook/MOLTBOOK_SPARKY.md`
- Moltbook karma plan: `docs/external-tools/moltbook/MOLTBOOK_KARMA_PLAN.md`
