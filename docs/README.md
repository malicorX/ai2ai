# Documentation Hub — AI Village (DGX)

This `docs/` directory is meant to be **copy/paste portable** into future repos. It splits the big idea into small, reproducible documents.

## Start here
- **Top-level spec:** `INFO.md` (root)
- **Architecture:** `docs/ARCHITECTURE.md`
- **Build milestones / acceptance criteria:** `INFO.md` (Milestones) + `docs/OPERATIONS.md` (runbooks)

## What each doc is for
- `docs/ARCHITECTURE.md` — system components, boundaries, diagrams, and key flows
- `docs/API.md` — HTTP + WebSocket API (contracts, payloads, status codes)
- `docs/DATA_MODEL.md` — database schema (tables, indices, constraints) and invariants
- `docs/AGENTS.md` — how agents run (loop, memory, coordination) and agent framework notes
- `docs/TOOLS.md` — tool surface (shell/browser/APIs), sandboxing, and audit logging requirements
- `docs/ECONOMY.md` — aiDollar ledger rules, reward/penalty mechanics, compute entitlements
- `docs/DEPLOYMENT.md` — docker/compose + multi-node DGX deployment strategy
- `docs/SECURITY.md` — auth, permissions, secrets, network policy, payment safety
- `docs/OPERATIONS.md` — runbooks: start/stop, migrations, backups, incident response
- `docs/REPRODUCIBILITY.md` — how to make builds repeatable (versions, env, migrations, fixtures)
- `docs/GETTING_STARTED.md` — runnable checklist to bring up a minimal v1
- `docs/ENV.example` — portable environment variables example (copy to `.env`)

## Decision log (ADR)
Use `docs/adr/` to record decisions that must be reproducible later.
- Template: `docs/adr/0000-template.md`
- Initial ADRs: `docs/adr/0001-agent-framework.md`, `docs/adr/0002-llm-runtime.md`, `docs/adr/0003-payments.md`

