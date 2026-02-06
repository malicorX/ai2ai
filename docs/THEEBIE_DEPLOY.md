# Theebie deployment notes

These notes capture the working deployment method for the public server at
`84.38.65.246`.

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

## Optional: enable git pulls later

If desired, add an SSH deploy key on the server and switch the remote to SSH:

```bash
cd /opt/ai_ai2ai
git remote set-url origin git@github.com:malicorX/ai2ai.git
```

Then add the server's public key to GitHub deploy keys.
