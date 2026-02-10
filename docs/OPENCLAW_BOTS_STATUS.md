# OpenClaw / Clawd bots on sparky1 and sparky2 — current setup

Summary of **how they're set up** and **what they can and can't do** as of the last inventory (see [SPARKY_INVENTORY_FINDINGS.md](SPARKY_INVENTORY_FINDINGS.md)). **Why we previously said tools don't work:** We inferred from the upstream issue [#1866](https://github.com/clawdbot/clawdbot/issues/1866) and the inventory (no live test). Once sparky2 was tested (e.g. "what's on spiegel.de"), browser use was confirmed; docs updated accordingly.

---

## How they're set up

| | sparky1 | sparky2 |
|---|---------|---------|
| **Runtime** | Clawd (clawdbot + clawdbot-gateway) | OpenClaw (openclaw-gateway) |
| **Config** | `~/.clawdbot/` | `~/.openclaw/` (`.clawdbot` → symlink to `.openclaw`) |
| **LLM** | **Ollama locally** at 127.0.0.1:11434 (no cloud API key) | Same |
| **Primary model** | ollama/qwen2.5-coder:32b | ollama/llama3.3:latest |
| **Tools** | profile: full; deny: sessions_send, message, tts, sessions_spawn | Same |
| **Browser** | enabled, chromium-browser | enabled, chromium-browser |
| **Channels** | Telegram enabled | Telegram enabled (plugins.entries.telegram) |
| **API mode** | openai-completions | openai-completions |

**Ollama models:** Run `ssh sparky1 "ollama list"` and `ssh sparky2 "ollama list"` to see current models. See [OLLAMA_LOCAL.md](OLLAMA_LOCAL.md).

Separately, **both** sparkies run our **Python agent** (`python3 -m agent_template.agent` from `~/ai2ai/agents`) with `~/.moltworld.env` — that agent talks to MoltWorld (theebie.de) as Sparky1Agent / MalicorSparky2. The OpenClaw/Clawd gateways are **different processes** (chat/cron UI), not the same identity as those world agents.

---

## What they CAN do

- **Chat** — TUI (`clawdbot tui` / `openclaw tui`) or Control UI in the browser (gateway port 18789, token from config). The model replies with **text**.
- **Use Ollama** — Both gateways call Ollama; no cloud API required.
- **Cron** — Scheduled jobs (e.g. "Fiverr screen") can be added; delivery to Telegram works if configured.
- **Browser / tools** — **sparky2** has been observed using the browser (e.g. fetching and summarizing www.spiegel.de), so tool execution (browser, web) **does work** there. **We run the jokelord patch** to enable it: patched gateway build + `compat.supportedParameters: ["tools", "tool_choice"]` in Ollama model config. See [CLAWD_JOKELORD_STEPS.md](external-tools/clawd/CLAWD_JOKELORD_STEPS.md). sparky1 (Clawd) may use the same fix; if you see tools working there too, update this doc.

---

## What they CAN'T do (or don't have yet)

### 1. MoltWorld (world_state, world_action, board_post)

- **Status (as of 2026-02):** The **MoltWorld plugin** is **installed and configured** on both sparkies (via `scripts/clawd/run_install_moltworld_plugin_on_sparkies.ps1`). A **“MoltWorld chat turn” cron** runs on each gateway (generic prompt: use world_state, then optionally chat_say); added via `scripts/clawd/add_moltworld_chat_cron.ps1`. Sparky1 cron runs regularly (Status ok); sparky2 cron has run but sometimes shows Status error (check gateway logs). Both agents (Sparky1Agent, MalicorSparky2) appear in the world at theebie.de; verify with `.\scripts\clawd\verify_moltworld_cron.ps1`. See [OPENCLAW_MOLTWORLD_CHAT_PLAN.md](OPENCLAW_MOLTWORLD_CHAT_PLAN.md) and [AGENT_CHAT_DEBUG.md](AGENT_CHAT_DEBUG.md) §5.
- **To (re)add or fix:** On each host: `openclaw`/`clawdbot` `plugins install @moltworld/openclaw-moltworld`, then in config add `plugins.entries["openclaw-moltworld"]` with `enabled: true` and `config.baseUrl`, `config.agentId`, `config.agentName`, `config.token` (e.g. from `~/.moltworld.env`). Restart the gateway. Clawd expects `clawdbot.plugin.json` in the extension dir; the install script copies from `openclaw.plugin.json` if missing. See [MOLTWORLD_OUTSIDERS_QUICKSTART.md](MOLTWORLD_OUTSIDERS_QUICKSTART.md) and [extensions/moltworld/README.md](../extensions/moltworld/README.md).

### 2. Same identity as the Python world agents

- The **Python agent** (Sparky1Agent / MalicorSparky2) is what appears on the map and in chat on theebie. The **OpenClaw/Clawd** gateway is a separate process: it's for human-in-the-loop chat and cron, not (currently) the same "agent" in MoltWorld. So "OpenClaw bots" here = the gateways; "world agents" = the Python processes.

---

## Summary table

| Capability | sparky1 (Clawd) | sparky2 (OpenClaw) |
|------------|------------------|---------------------|
| Gateway + Ollama chat (text) | ✅ | ✅ |
| Telegram delivery | ✅ | ✅ |
| Cron (scheduled prompts) | ✅ | ✅ |
| **Tool execution** (browser, web) | unconfirmed | ✅ observed (e.g. spiegel.de) |
| **MoltWorld** (world_state, world_action, board_post) | ✅ plugin + cron (chat turn) | ✅ plugin + cron (chat turn; cron sometimes error) |
| Python agent (MoltWorld) on same host | ✅ separate process | ✅ separate process |

So **right now** both can do **text chat, cron, and MoltWorld** (plugin + “MoltWorld chat turn” cron); sparky2 has **browser/tools** confirmed; sparky1 tool use unconfirmed. Verify MoltWorld cron and world presence with `.\scripts\clawd\verify_moltworld_cron.ps1`. If a gateway doesn't get tools (e.g. after a reinstall), see [CLAWD_SPARKY.md](external-tools/clawd/CLAWD_SPARKY.md) for the #1866 workarounds (jokelord patch / PR #4287).
