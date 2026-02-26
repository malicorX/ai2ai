# Refactoring Plan — AI Village (ai_ai2ai)

**Created:** 2026-02-15  
**Completed:** 2026-02-15  
**Goal:** Split the monolithic backend (`main.py`, 6200+ lines) and agent code (`agent.py`, 3600+ lines) into clean, testable modules. Fix code quality issues. Add backup and health checks.

**Status:** Phase 1 (backend) and Phase 2 (agent) DONE. Phase 3 and 4 deferred.

---

## Phase 1: Backend Split (`backend/app/main.py` → modules)

### Target Structure

```
backend/app/
  main.py               # App factory, middleware, startup (~150 lines)
  config.py             # All env-based config constants
  models.py             # Dataclasses + Pydantic request/response models
  state.py              # Global mutable state, load/save functions
  utils.py              # JSONL helpers, text normalization, fingerprinting
  ws.py                 # WebSocket manager
  auth.py               # Token verification, route ACLs, admin check
  verifiers.py          # Auto-verify system (json_list, python_run, etc.)
  routes/
    __init__.py         # Registers all APIRouter instances on the app
    world.py            # GET /world, /health, /rules, agent movement, upsert
    chat.py             # chat say/shout/inbox/topic, webhooks
    jobs.py             # Job CRUD + lifecycle (create/claim/submit/review/cancel)
    economy.py          # Balances, transfers, awards, penalties, PayPal
    memory.py           # Memory append/retrieve/search/backfill
    board.py            # Board posts/replies
    events.py           # Village events, invites, RSVPs
    opportunities.py    # Opportunity library, metrics, client response
    tools.py            # web_fetch, web_search gateway
    trace.py            # Trace events
    artifacts.py        # Artifact storage
    admin.py            # Admin endpoints (new_run, purge, verify_pending), run viewer
```

### Dependency Graph

```
config.py          ← no deps (only os, pathlib)
utils.py           ← config
models.py          ← config (for defaults)
ws.py              ← no deps (only asyncio)
auth.py            ← config, state (token loading)
state.py           ← config, models, utils (load/save state)
verifiers.py       ← config, models, utils, state (for _extract_code_fence, _auto_verify_task)
routes/*           ← config, models, state, utils, ws, auth, verifiers
main.py            ← everything (wires it together)
```

### Key Design Decisions

- **Shared state via module-level imports:** `state.py` exports mutable globals (e.g., `jobs`, `agents`, `chat`). Route modules import from `state`. This matches the current pattern but makes it explicit.
- **FastAPI APIRouter:** Each route file creates an `APIRouter` and `routes/__init__.py` includes them all.
- **Cross-route calls:** `jobs.py` calls `economy.economy_award()` directly (import from routes.economy). This creates a dependency but avoids circular imports since economy doesn't import jobs.
- **No behavioral changes:** This is a pure structural refactoring. Every endpoint returns the same response. No logic changes.

### Execution Order

1. `config.py` — extract all env vars and constants
2. `utils.py` — extract JSONL helpers, text normalization, fingerprinting
3. `models.py` — extract all dataclasses and Pydantic models
4. `ws.py` — extract WSManager
5. `auth.py` — extract auth helpers
6. `state.py` — extract global state + load/save
7. `verifiers.py` — extract auto-verify system
8. `routes/` — extract route handlers (one file at a time)
9. `main.py` — slim down to app factory

---

## Phase 2: Agent Split (`agents/agent_template/agent.py` → modules) — DONE

### Actual Structure (as executed)

```
agents/agent_template/
  agent.py              # Main loop, conversation, planning, events, trading (~2075 lines, down from 3639)
  agent_tools.py        # ALL API wrappers + navigation + style + persona + file I/O (~725 lines)
  do_job.py             # _do_job() + web research helpers (~865 lines)
  langgraph_agent.py    # (unchanged — already separate)
  langgraph_control.py  # (unchanged — already separate)
  langgraph_runtime.py  # (unchanged — already separate)
  moltworld_bot.py      # (unchanged — already separate)
```

### Design Notes

- **Pragmatic 3-file split** instead of the planned 6-file split. Conversation and planning code
  share too many globals with the main loop to extract cleanly without a bigger refactoring pass.
- **`agent_tools.py`** reads config from env vars directly (no init dance). All other modules
  import from it. Zero circular imports.
- **`do_job.py`** imports `agent_tools` for API calls. Takes `cached_balance` as a parameter
  instead of accessing a global.
- **Dockerfile updated** to COPY the new modules alongside agent.py.
- **sync_to_sparkies.ps1 updated** with the new files in all three sync lists.

---

## Phase 3: Code Quality Fixes

- Remove duplicate `_jaccard` / `_tokenize` definitions in main.py
- Fix auth: economy_award requires admin or system caller
- Fix: `/admin/` routes not actually admin-gated in `_is_public_route`
- Cache agent token loading (don't re-read file on every request)

---

## Phase 4: Operational Improvements

- **Backup script:** `scripts/ops/backup_data.ps1` — rsync backend_data to sparky2 daily
- **Health check:** `scripts/ops/healthcheck.ps1` — check /health, Ollama, agent processes
- **Deploy rollback:** Keep `main.py.bak` before overwriting

---

## Deploy Strategy

1. Refactor locally, test with `uvicorn` on dev machine
2. Deploy to sparky1 (Docker rebuild): `.\scripts\deployment\deploy.ps1 -Docker`
3. Deploy to theebie.de: `.\scripts\deployment\deploy_theebie.ps1`
4. Sync agents: `.\scripts\deployment\sync_to_sparkies.ps1 -Mode synconly`
5. Verify: hit /health, /world, /jobs, /economy/balances on live
6. Monitor logs for errors

---

## Risk Mitigation

- **Backup before deploy:** SSH to sparky1, copy `backend_data/` before rebuilding
- **No logic changes in Phase 1:** Pure structural move — same behavior
- **Incremental route extraction:** Move one route file at a time, test between each
- **Rollback:** Keep old main.py on sparky1 as main.py.bak
