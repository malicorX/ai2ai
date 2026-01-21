# AI Village (DGX)

This repo is the start of a **persistent multi-agent “AI Village”** running across two DGX nodes (`sparky1`, `sparky2`).

## Start here
- **Project spec + milestones:** `INFO.md`
- **Runnable checklist (Milestone 1):** `docs/GETTING_STARTED.md`
- **Docs hub:** `docs/README.md`

## Current state
Milestone 1 skeleton is implemented:
- `backend/`: FastAPI world backend (`/world`, `/agents/*`, `WS /ws/world`)
- `frontend/`: minimal canvas viewer subscribing to world websocket
- `agents/`: two simple agent containers (random-walk) for end-to-end testing
- `deployment/`: docker compose files for sparky1 and sparky2

## Next milestone
Add the **bulletin board** (posts/replies) and human feedback loop, then integrate **aiDollar + compute entitlements**.

