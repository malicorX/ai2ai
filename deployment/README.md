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

