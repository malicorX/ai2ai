# Changelog

This project is in early development. Entries are kept intentionally high-level.

## Unreleased
- TBD

## 0.1.0 — 2026-01-21
### Added
- **Canonical spec + reproducible docs**: `INFO.md` + `docs/` (architecture, API, data model, tools, security, ops, ADRs).
- **Milestone 1 runnable skeleton**:
  - `backend/` FastAPI world backend with `GET /world`, agent upsert/move, `WS /ws/world`
  - `frontend/` minimal canvas viewer
  - `agents/` containerized agent template + `agent_1`/`agent_2`
  - `deployment/` compose files for sparky1 + sparky2

