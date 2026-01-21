# Deployment (v1) — two DGX nodes (sparky1 + sparky2)

## Goals
- Reproducible bring-up with Docker Compose.
- Backend + DB on one node (start with sparky1).
- Agents distributed across sparky1 and sparky2.

## v1 approach (simple)
### sparky1 runs
- world-backend
- postgres
- (optional) redis
- N agent containers

### sparky2 runs
- M agent containers

## Configuration
Use environment variables (or `.env`) for:
- backend URL
- agent auth tokens
- DB connection strings
- model runtime endpoints (vLLM/Ollama)

## Compose notes
- Agents must know `WORLD_API_BASE` reachable across nodes.
- Use a stable hostname or static IP for backend.

## Ansible (optional)
If you want one-command deployment later, add:
- inventory for sparky1/sparky2
- tasks to install docker, copy stack, start compose

