# Sparky inventory findings (from SSH)

This doc summarizes what is actually running on sparky1 and sparky2, as collected by `scripts/sparky_inventory.ps1` (SSH + optional zip fetch). Run from repo root:

```powershell
.\scripts\sparky_inventory.ps1           # text inventory only
.\scripts\sparky_inventory.ps1 -FetchZip # also fetch zips to sparky_inventory/
```

Output goes to **sparky_inventory/** (gitignored). The script redacts `token`, `apiKey`, `auth`, and `botToken` in the saved text.

---

## Summary (as of 2026-02-07)

| Item | sparky1 | sparky2 |
|------|---------|---------|
| **OpenClaw/Clawd gateway** | **clawdbot** + **clawdbot-gateway** | **openclaw-gateway** |
| **Config location** | `~/.clawdbot/` | `~/.openclaw/` (and `~/.clawdbot` → symlink to `~/.openclaw`) |
| **Python agent (MoltWorld)** | `python3 -m agent_template.agent` from `~/ai2ai/agents` | Same, from `~/ai2ai/agents` |
| **~/.moltworld.env** | yes | yes |
| **Repos on disk** | `~/ai_ai2ai`, `~/ai2ai` | `~/ai_ai2ai`, `~/ai2ai` |
| **Node/npm (which)** | (not in PATH or not found by which) | (not in PATH or not found by which) |

So we **do** run OpenClaw/Clawd on both nodes:

- **sparky1** uses **Clawd** (clawdbot, clawdbot-gateway), config in `~/.clawdbot/` (clawdbot.json, gateway.log, etc.).
- **sparky2** uses **OpenClaw** (openclaw-gateway), config in `~/.openclaw/` (openclaw.json, clawdbot.json, extensions/, etc.).

Both also run our **Python agent** (`agent_template.agent`) with `~/.moltworld.env` sourced, from the **~/ai2ai** repo (agents subdir).

---

## Process list (excerpt)

**sparky1**

- `clawdbot` (parent)
- `clawdbot-gateway`
- `bash -c cd ~/ai2ai/agents && . ~/.moltworld.env && nohup python3 -m agent_template.agent ...`
- `python3 -m agent_template.agent`

**sparky2**

- `openclaw-gateway`
- `bash -c cd ~/ai2ai/agents && . ~/.moltworld.env && nohup python3 -m agent_template.agent ...`
- `python3 -m agent_template.agent`

---

## Config (from inventory)

- **sparky1** `~/.clawdbot/clawdbot.json`: Ollama provider (baseUrl 127.0.0.1:11434), primary model `ollama/qwen2.5-coder:32b`, tools profile full with deny (sessions_send, message, tts, sessions_spawn), browser enabled (chromium-browser), gateway port 18789, Telegram channel enabled.
- **sparky2** `~/.openclaw` (and symlinked .clawdbot): Similar Ollama setup, primary `ollama/llama3.3:latest`, same tools deny, browser (chromium-browser), gateway 18789, has `extensions/` and `openclaw.json` in addition to clawdbot.json.

---

## How to re-run and inspect

1. From repo root: `.\scripts\sparky_inventory.ps1` (and optionally `-FetchZip`).
2. Open `sparky_inventory/sparky1_inventory.txt` and `sparky2_inventory.txt` for the latest text snapshot.
3. Unzip `sparky1_inventory.zip` / `sparky2_inventory.zip` locally to inspect config files (tokens redacted in the script that builds the zip on the host).

See also: [CLAWD_SPARKY.md](external-tools/clawd/CLAWD_SPARKY.md), [AGENTS.md](AGENTS.md) § "What runs where".
