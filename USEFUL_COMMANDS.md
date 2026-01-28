# Useful Commands (copy/paste)

This file is a quick runbook of common commands for operating the AI Village stack.

## Deploy / update code to DGX nodes (no GitHub required)

### Copy current repo to sparky1
**What it does:** Streams a tar archive over SSH and extracts into `~/ai2ai`.

```bash
cd "M:\Data\Projects\ai_ai2ai"
tar -cf - --exclude=.git --exclude=__pycache__ --exclude=*.log --exclude=.env . | ssh -o BatchMode=yes malicor@sparky1 "mkdir -p ~/ai2ai && tar -xf - -C ~/ai2ai"
```

### Copy current repo to sparky2
**What it does:** Same as above, but to sparky2.

```bash
cd "M:\Data\Projects\ai_ai2ai"
tar -cf - --exclude=.git --exclude=__pycache__ --exclude=*.log --exclude=.env . | ssh -o BatchMode=yes malicor@sparky2 "mkdir -p ~/ai2ai && tar -xf - -C ~/ai2ai"
```

## Start / stop (Docker Compose)

### Start backend + agent_1 (sparky1)
**What it does:** Builds and starts the backend and agent_1 containers on sparky1.

```bash
ssh -o BatchMode=yes malicor@sparky1 "cd ~/ai2ai && docker compose -f deployment/docker-compose.sparky1.yml up -d --build"
```

### Start agent_2 (sparky2)
**What it does:** Builds and starts agent_2 on sparky2 (talking to backend on sparky1).

```bash
ssh -o BatchMode=yes malicor@sparky2 "cd ~/ai2ai && docker compose -f deployment/docker-compose.sparky2.yml up -d --build"
```

### Stop everything (sparky1)
**What it does:** Stops and removes containers for the sparky1 compose file.

```bash
ssh -o BatchMode=yes malicor@sparky1 "cd ~/ai2ai && docker compose -f deployment/docker-compose.sparky1.yml down"
```

### Stop everything (sparky2)
**What it does:** Stops and removes containers for the sparky2 compose file.

```bash
ssh -o BatchMode=yes malicor@sparky2 "cd ~/ai2ai && docker compose -f deployment/docker-compose.sparky2.yml down"
```

### Show running containers (sparky1)
**What it does:** Shows container status for sparky1 stack.

```bash
ssh -o BatchMode=yes malicor@sparky1 "cd ~/ai2ai && docker compose -f deployment/docker-compose.sparky1.yml ps"
```

### Show running containers (sparky2)
**What it does:** Shows container status for sparky2 stack.

```bash
ssh -o BatchMode=yes malicor@sparky2 "cd ~/ai2ai && docker compose -f deployment/docker-compose.sparky2.yml ps"
```

## Logs (debugging)

### Tail backend logs (sparky1)
**What it does:** Streams logs from the backend container.

```bash
ssh -o BatchMode=yes malicor@sparky1 "docker logs -f deployment-backend-1"
```

### Tail agent_1 logs (sparky1)
**What it does:** Streams logs from agent_1.

```bash
ssh -o BatchMode=yes malicor@sparky1 "docker logs -f deployment-agent_1-1"
```

### Tail agent_2 logs (sparky2)
**What it does:** Streams logs from agent_2.

```bash
ssh -o BatchMode=yes malicor@sparky2 "docker logs -f deployment-agent_2-1"
```

## Backend health checks

### Backend health (sparky1)
**What it does:** Checks backend is alive and shows world size + current agent count.

```bash
ssh -o BatchMode=yes malicor@sparky1 "curl -s http://localhost:8000/health"
```

### World snapshot (sparky1)
**What it does:** Returns current world state (agents + landmarks).

```bash
ssh -o BatchMode=yes malicor@sparky1 "curl -s http://localhost:8000/world"
```

### List bulletin board posts (sparky1)
**What it does:** Lists the latest board posts (agents/humans).

```bash
ssh -o BatchMode=yes malicor@sparky1 "curl -s http://localhost:8000/board/posts"
```

## Viewer

### Open the viewer
**What it does:** Loads the world canvas + bulletin board panel in your browser.

**Preferred (served from backend):**
- Open: `http://sparky1:8000/ui/` (or `http://sparky1:8000/` which redirects)

### Download the latest run results to local `result_viewer.html`
**What it does:** Downloads the HTML conversation viewer for the latest archived run and overwrites your local `result_viewer.html` so you can open it as a `file:///...` in Cursor/offline.

```powershell
pwsh -File .\scripts\pull_result_viewer.ps1 -BaseUrl "http://sparky1:8000" -RunId "latest" -OutPath "M:\Data\Projects\ai_ai2ai\result_viewer.html"
```

**Fallback (local file):**
- Open `frontend/index.html`
- If the backend isn’t the same host as the HTML page, set `BACKEND_WS` inside the file to:
  - `ws://sparky1:8000/ws/world`

## Fiverr discovery (optional)

**What it does:** Proposer can search Fiverr → pick a gig → create a sparky task for the executor when no opportunities exist.

1. Sync code to sparkies: `.\scripts\sync_to_sparkies.ps1 -Mode push` (after committing; or copy files manually).
2. On sparky1, set backend env: `WEB_SEARCH_ENABLED=1` and `SERPER_API_KEY=<key>` (get key at serper.dev). In compose, uncomment the web-search env lines under `backend` and set the key in `.env` or in the file.
3. Rebuild backend and agent_1 on sparky1, agent_2 on sparky2 (see deployment/README § After code changes and § Fiverr discovery).

## Git (local)

### Commit and push changes
**What it does:** Saves local changes and pushes to GitHub.

```bash
git add -A
git commit -m "your message"
git push
```

