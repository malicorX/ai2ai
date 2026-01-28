# Deployment (Milestone 1) — quick run

This brings up:
- backend + agent_1 on **sparky1**
- agent_2 on **sparky2** (talking to sparky1 backend)

## sparky1
```bash
cd /home/malicor/ai_ai2ai
docker compose -f deployment/docker-compose.sparky1.yml up -d --build
curl http://localhost:8000/health
curl http://localhost:8000/world
```

## sparky2
```bash
cd /home/malicor/ai_ai2ai
docker compose -f deployment/docker-compose.sparky2.yml up -d --build
```

## Viewer
Open `frontend/index.html` in a browser.

If you open it locally (not served by the backend host), edit `BACKEND_WS` inside the file to:
`ws://sparky1:8000/ws/world`

## After code changes

- **Backend:** Rebuild and restart on sparky1 (required after verifier changes, e.g. json_list extraction in `main.py`, so `test_run.ps1` auto-verify passes):
  ```bash
  docker compose -f deployment/docker-compose.sparky1.yml up -d --build backend
  ```
  After this, run the full suite from your dev machine: `.\scripts\run_all_tests.ps1 -BackendUrl http://sparky1:8000`. Suite has 5 steps (verifier_unit, quick_test, test_run gig, proposer_review, proposer_review_reject).

**Deploy then run suite (one command from dev machine):**
  ```powershell
  .\scripts\deploy_and_run_tests.ps1 -BackendUrl http://sparky1:8000
  ```
  This deploys the backend to sparky1 and then runs all five test steps. Use `-SkipVerifierUnit` to skip the local verifier step.
- **Agent code (e.g. `agents/agent_template/`):** Agent images are built from the template. Rebuild the agent(s) that use it:
  - **agent_1 (proposer)** — on sparky1:
    ```bash
    docker compose -f deployment/docker-compose.sparky1.yml up -d --build agent_1
    ```
  - **agent_2** — on sparky2:
    ```bash
    docker compose -f deployment/docker-compose.sparky2.yml up -d --build agent_2
    ```
  For **proposer-review** (agent_1 reviews its own tasks), agent_1 must run the updated template (review_job, my_submitted_jobs). Rebuild and restart agent_1 on sparky1 after pulling or editing `agents/agent_template/`.

## Real Fiverr discovery (agent_1 picks real Fiverr tasks)

Agent_1 (proposer) can **discover real Fiverr gigs** via web search and optional page fetch, then create jobs for the executor. No canned templates.

- **Backend:** Set `WEB_SEARCH_ENABLED=1` and `SERPER_API_KEY=<key>` (get a key at [serper.dev](https://serper.dev)). In compose, uncomment the web-search env lines under `backend` and set `SERPER_API_KEY` in `.env` or in the compose file.
- **Web fetch (recommended):** Set `WEB_FETCH_ENABLED=1` and add `fiverr.com` to `WEB_FETCH_ALLOWLIST` so agent_1 can fetch gig pages for full requirements (see docs/ENV.example). Compose already sets `WEB_FETCH_ENABLED=1`; ensure `WEB_FETCH_ALLOWLIST` includes `fiverr.com`.
- **Test with real Fiverr:** Run `.\scripts\test_run.ps1 -BackendUrl http://sparky1:8000 -TaskType fiverr`. The script waits for agent_1 to create a job from a real Fiverr gig (up to 180s), then monitors claim → submit → approve. Agent_1 must be running and web search (and optionally web_fetch) configured.
- Rebuild backend and agents after adding the key so discover_fiverr and web_fetch are used.

