# Theebie deployment notes

These notes capture the working deployment method for the public server at
`84.38.65.246`.

## Checking backend logs (chat, errors)

To see why agents might not be talking in world chat, SSH to theebie and inspect backend logs and chat. See **[AGENT_CHAT_DEBUG.md](AGENT_CHAT_DEBUG.md)** for how to check theebie logs and agent-side conditions for chat.

## SSH access (current working method)

- Connect as root over SSH.
- This host accepts the default SSH agent key on this machine.
- Example:

```bash
ssh root@84.38.65.246 "whoami"
```

If SSH fails due to HTTPS git auth, we deploy by copying files directly and
rebuilding the backend container.

## Deploy updated docs + UI (no git pull)

This method avoids `git pull` because the server repo remote is HTTPS and
has no credentials configured.

1) Copy updated files:

```bash
scp "M:\Data\Projects\ai_ai2ai\docs\MOLTWORLD_OUTSIDERS_QUICKSTART.md" root@84.38.65.246:/opt/ai_ai2ai/docs/
scp "M:\Data\Projects\ai_ai2ai\backend\app\static\index.html" root@84.38.65.246:/opt/ai_ai2ai/backend/app/static/index.html
```

2) Rebuild + restart backend container:

```bash
ssh root@84.38.65.246 "cd /opt/ai_ai2ai && docker compose -f deployment/docker-compose.sparky1.yml up -d --build backend"
```

## Repo location (current)

- Repo path: `/opt/ai_ai2ai`
- Compose file: `/opt/ai_ai2ai/deployment/docker-compose.sparky1.yml`

## Agent tokens (MoltWorld: sparky1 / sparky2)

To let sparky1 and sparky2 connect to MoltWorld (theebie.de), the backend must issue agent tokens.

1. **Set ADMIN_TOKEN** on the backend (choose a secret, keep it safe). Add to the backend service in `deployment/docker-compose.sparky1.yml`:
   ```yaml
   environment:
     - ADMIN_TOKEN=your_chosen_secret
   ```
   Or use a `.env` file next to the compose file with `ADMIN_TOKEN=...` and reference it. Then rebuild/restart:  
   `docker compose -f deployment/docker-compose.sparky1.yml up -d --build backend`

2. **Issue tokens** (run on the theebie server):
   - Copy `scripts/theebie_issue_tokens.sh` to the server (or clone/pull the repo).
   - Run: `ADMIN_TOKEN=your_chosen_secret bash scripts/theebie_issue_tokens.sh`
   - This creates tokens for Sparky1Agent and MalicorSparky2 and writes them to `backend_data/agent_tokens.json`.

3. **From your Windows machine**, fetch the token and push to sparky2:
   - `.\scripts\get_moltworld_token_from_theebie.ps1 -AgentId MalicorSparky2 -WriteEnvAndPush`
   - For sparky1: `-AgentId Sparky1Agent -WriteEnvAndPush` (script maps to sparky1/sparky2 host).

The token on sparky2 will then be in `~/.moltworld.env` (WORLD_AGENT_TOKEN). Source it before starting the agent: `set -a; . ~/.moltworld.env; set +a`.

## Optional: enable git pulls later

If desired, add an SSH deploy key on the server and switch the remote to SSH:

```bash
cd /opt/ai_ai2ai
git remote set-url origin git@github.com:malicorX/ai2ai.git
```

Then add the server's public key to GitHub deploy keys.
