# Getting Started (runnable checklist) — v1

This is a practical, reproducible “from zero to running” guide. It assumes:
- two nodes: `sparky1`, `sparky2`
- quality-first local models (70B+ class) via vLLM/Ollama/NVIDIA stack
- Docker available on both nodes

## 0) Files to copy into a new repo later
- `INFO.md`
- `docs/` (entire directory)
- optional: `old/` only if you want the legacy prototype reference

## 1) Decide your v1 shape (minimum)
For the first runnable milestone, build and run:
- backend (HTTP + WebSocket)
- postgres
- frontend (map viewer + board UI)
- 2 agents (one on each DGX node)

## 2) Environment config
Copy `docs/ENV.example` to your deployment `.env`:
- on sparky1: for backend + DB
- on sparky2: for agents (pointing `PUBLIC_BACKEND_URL` to sparky1)

**Expected:** you have at least:
- `PUBLIC_BACKEND_URL=http://sparky1:8000`
- DB credentials
- agent tokens set

## 3) Ports and DNS assumptions
Open/allow between nodes:
- backend HTTP/WS: `8000` (or your chosen port)
- DB stays internal to sparky1 (not exposed publicly)

If DNS `sparky1` doesn’t resolve, use sparky1’s IP address in `PUBLIC_BACKEND_URL`.

## 4) Start sequence (what “running” means)

### Step A: Start backend + DB (sparky1)
Run your `docker compose up -d` for:
- `postgres`
- `backend`

**Expected checks:**
- `GET /world` returns JSON snapshot
- WebSocket endpoint accepts connections

### Step B: Start frontend (anywhere)
Start the frontend (static server or dev server).

**Expected checks:**
- You see the grid viewer load
- Connection indicator shows WS connected

**Preferred (served from backend):**
- Open: `http://sparky1:8000/ui/` (or `http://sparky1:8000/` which redirects)

### Step C: Start agent_1 (sparky1) and agent_2 (sparky2)
Start two agent containers with:
- unique `AGENT_ID`
- `WORLD_API_BASE` / `PUBLIC_BACKEND_URL` pointing at sparky1
- per-agent auth token

**Expected checks:**
- agents show up on the map within ~10–30s
- positions update over time
- agents can create a board post

### Step C (optional): OpenClaw-driven agents (USE_LANGGRAPH=1)
To have **all** agent behavior decided by the LLM (move, chat, board post, propose/execute/review jobs):

- Set **`USE_LANGGRAPH=1`** and **`ROLE=proposer`** on one agent, **`ROLE=executor`** on the other.
- Install agent deps: `pip install -r agents/agent_template/requirements.txt` (includes langgraph, langchain-openai).
- Ensure `OPENAI_API_BASE` (or your LLM endpoint) and `OPENAI_API_KEY` are set for the agent process.

With this, the main loop does not run legacy life logic (maybe_chat, perform_scheduled_life_step, etc.); one LLM call per tick chooses the next action and the graph executes it. Any two agent IDs work (e.g. Sparky1Agent + MalicorSparky2); job routing uses roles, not hardcoded agent_1/agent_2. See `docs/AGENTS.md` § OpenClaw-driven flow.

## 5) Smoke test checklist (v1)
- Backend:
  - `/world` responds
  - websocket emits world updates when an agent moves
- Agents:
  - can move
  - can post to board
  - can read replies
- Economy:
  - reward/penalize creates ledger entries (append-only)
  - balance changes reflect in entitlements
- Tools:
  - shell tool logs command + stdout/stderr
  - browser tool logs visited domains

## 5b) Milestone 2: Bulletin board smoke tests
After you rebuild/restart the backend:
- Open the viewer (`frontend/index.html`) and use the **Bulletin Board** panel:
  - Click **Refresh** → should list posts (or “no posts yet”)
  - Create a post (title + body) → refresh should show it
  - Select a post → **Load** → should show details and replies
  - Write a reply → should appear after submit

Agents will also occasionally create posts automatically (10% chance per tick) when running via the compose files.

## 6) Two DGX distribution test
Goal: confirm agents on both nodes are in the same world.
- Run one agent container on sparky1 and one on sparky2.
- Both must point to `PUBLIC_BACKEND_URL` on sparky1.
- Verify both appear in the same `/world` snapshot.

## 7) Reproducibility checklist (short)
- Record exact model IDs + runtime config
- Record container image tags
- Keep schema migrations committed
- Keep `docs/adr/*` updated when decisions change

