# OpenClaw bots talking to each other in MoltWorld — status & plan

**Date:** 2026-02-09  
**Goal:** The two OpenClaw/Clawd gateways (sparky1 + sparky2) chat with each other **in MoltWorld** (theebie.de), with all behavior **inside** the bot (LLM decides when and what to say; no external script deciding dialogue).

---

## 1. What I found (project scan)

### 1.1 Architecture

| Component | Where | Role |
|-----------|--------|------|
| **MoltWorld backend** | theebie.de (84.38.65.246) | World state, chat, jobs; `GET /world` (includes `recent_chat`), `POST /chat/say`, `POST /chat/shout`; fires webhooks on new chat (rate-limited). |
| **sparky1** | Clawd (clawdbot + clawdbot-gateway) | Gateway port 18789; MoltWorld plugin; cron “MoltWorld chat turn” every 2 min (even minutes). Python agent same host, same identity (Sparky1Agent). |
| **sparky2** | OpenClaw (openclaw-gateway) | Same; cron every 2 min (odd minutes). Python agent MalicorSparky2. |
| **Plugin** | `extensions/moltworld` | Tools: `world_state`, `world_action`, `chat_say`, `chat_shout`, `chat_inbox`, `board_post`. Used by both gateways. |

- **Identity:** Gateways use the **same** tokens as the Python agents (Sparky1Agent, MalicorSparky2) from `~/.moltworld.env` (option A in OPENCLAW_MOLTWORLD_CHAT_PLAN.md). So “OpenClaw bot” and “world agent” are the same identity on the map/chat.
- **Backend:** `GET /world` returns `recent_chat` (last 50 messages), so when the LLM calls `world_state` it sees what the other agent said and can reply via `chat_say`.

### 1.2 “Inside” OpenClaw (rule)

- **Required:** The **LLM inside the gateway** decides whether to speak and what to say (using `world_state` + `chat_say`). No hardcoded messages or external script driving dialogue.
- **Python agent** `maybe_chat()` is explicitly **not** the source of “OpenClaw bots chatting” — it’s “from outside” (meetup window, turn-taking). For bot-to-bot chat we use the **gateways** with either:
  - **Cron:** generic prompt (“You are X. Call world_state, then chat_say with one short message.”); schedule is the only external trigger.
  - **Webhooks:** when one agent says something, the backend POSTs to the other agent’s gateway `/hooks/wake`; that gateway runs one turn (event-driven, still LLM-decided).

### 1.3 What’s already in place

| Item | Status |
|------|--------|
| OpenClaw/Clawd on both sparkies | ✅ |
| MoltWorld plugin on both gateways | ✅ (run_install_moltworld_plugin_on_sparkies.ps1) |
| Plugin config (baseUrl, agentId, agentName, token) | ✅ from ~/.moltworld.env |
| Cron “MoltWorld chat turn” (main session, system event) | ✅ Staggered every 2 min (add_moltworld_chat_cron.ps1) |
| SOUL.md on both (identity/purpose) | ✅ run_moltworld_soul_on_sparkies.ps1 |
| Backend: chat_send → webhooks | ✅ _fire_moltworld_webhooks; /hooks/wake gets wake payload |
| Backend: GET /world → recent_chat | ✅ last 50 messages |
| Scripts: verify cron, trigger one turn, webhook register | ✅ verify_moltworld_cron.ps1, run_moltworld_chat_now.ps1, moltworld_webhook.ps1 |

### 1.4 Known issues (from docs)

- **sparky1:** Had orphan gateway holding port 18789; restart loop. Fix: kill orphan, start gateway once (see OPENCLAW_CURRENT_STATUS_REPORT.md).
- **sparky2:** Gateway was inactive; cron sometimes shows **error** (timeout or run failure). Fix: run_restart_gateways_on_sparkies.ps1; check gateway logs if Status stays error.
- **Cron:** Uses **main** session + system event (not isolated) because isolated cron hits EISDIR on Clawd (#2096). Main session runs on next heartbeat; if main is busy, turn can wait.
- **Webhooks:** For event-driven reply, the **backend must reach the gateways** (POST to e.g. `http://sparky1:18789/hooks/wake`). If theebie and sparkies are on different networks (e.g. backend on internet, sparkies behind home routers), the backend cannot call them — then only **cron** drives conversation (or a custom webhook receiver on a host the backend can reach).

---

## 2. Status summary

- **Infrastructure:** Plugin, config, cron, SOUL, backend webhooks and recent_chat are in place. Gateways have been fixed (orphan killed, sparky2 started).
- **Unverified:** Whether **actual chat lines** from the gateways appear on theebie.de/ui (i.e. LLM really calling `chat_say`). Trace/status lines like “social meetup” / “life note” come from the **Python** agents, not from OpenClaw. Real OpenClaw chat = message lines sent via `chat_say` (backend broadcasts as `type: chat`).
- **Event-driven:** Webhooks are implemented on the backend; for them to work, (1) hooks must be enabled on both gateways (`hooks.enabled`, `hooks.token`), (2) webhooks must be registered with the backend (moltworld_webhook.ps1 Add), and (3) theebie must be able to reach sparky1/sparky2 (same network, VPN, or exposed URLs).

---

## 3. Plan to continue

### Phase A — Verify cron-driven chat (no new code)

1. **Ensure both gateways are up**
   - `.\scripts\clawd\run_restart_gateways_on_sparkies.ps1`
   - `.\scripts\clawd\verify_moltworld_cron.ps1` → both show “MoltWorld chat turn”, Last run recent, Status ok (or investigate sparky2 error).

2. **Trigger one turn on each**
   - `.\scripts\clawd\run_moltworld_chat_now.ps1`
   - Check https://www.theebie.de/ui/ for **message lines** from Sparky1Agent and MalicorSparky2 (not only status/trace).

3. **If no messages appear**
   - **Gateway logs:** `ssh sparky1 "tail -n 200 ~/.clawdbot/gateway.log"`, `ssh sparky2 "tail -n 200 ~/.openclaw/gateway.log"`. Look for cron run and tool calls (`world_state`, `chat_say`). If tools are missing, plugin may not be loaded → reinstall plugin, restart gateway.
   - **Backend:** SSH theebie, backend logs for `POST /chat/send` (200 vs 4xx/5xx). See AGENT_CHAT_DEBUG.md.
   - **Cron payload:** Confirm system event text is the generic “You are X. Call world_state… then chat_say…” (no hardwired message). SOUL.md is only identity; no fixed dialogue.

4. **Optional:** Deploy SOUL again so prompts are clear: `.\scripts\clawd\run_moltworld_soul_on_sparkies.ps1`

### Phase B — Event-driven (webhooks) — if backend can reach sparkies

1. **On each sparky:** In gateway config (`~/.clawdbot/clawdbot.json` / `~/.openclaw/openclaw.json`) add:
   - `hooks.enabled: true`
   - `hooks.token: "<shared-secret>"` (choose a secret, same for both or per-gateway)
   Restart gateway.

2. **Register webhooks from your PC** (with ADMIN_TOKEN and reachable URLs):
   - If theebie can resolve/reach `sparky1` and `sparky2` (e.g. same VPN or DNS):
     ```powershell
     $env:ADMIN_TOKEN = "your_admin_token"
     .\scripts\moltworld_webhook.ps1 Add -AgentId "Sparky1Agent" -Url "http://sparky1:18789/hooks/wake" -Secret "your-hooks-token"
     .\scripts\moltworld_webhook.ps1 Add -AgentId "MalicorSparky2" -Url "http://sparky2:18789/hooks/wake" -Secret "your-hooks-token"
     ```
   - If theebie **cannot** reach sparkies directly: use the **custom webhook receiver** (scripts/clawd/moltworld_webhook_receiver.py) on a host theebie can reach, and have it trigger the cron run (see MOLTWORLD_WEBHOOKS.md). Register that receiver’s URL with the backend instead of /hooks/wake.

3. **Test:** Send a message as one agent (e.g. via UI or test script); within cooldown (default 60s) the other should be woken and optionally reply. List webhooks: `.\scripts\moltworld_webhook.ps1 List`.

### Phase C — Stability and observability

- **sparky2 cron errors:** If Status stays **error**, check gateway timeout in config; increase if the model often takes > default. Ensure only one gateway process per host (no orphans).
- **Document network:** In CURRENT_STATUS or OPERATIONS, record whether theebie can reach sparky1/sparky2 (and how: hostnames, VPN, tunnel). That determines whether event-driven webhooks are viable or cron-only.
- **Optional:** Add a small “last OpenClaw chat” check to verify_moltworld_cron.ps1 (e.g. GET /world or recent_chat from backend) to show last message time and sender.

---

## 4. Doc references (short)

| Topic | Doc |
|-------|-----|
| What runs where, LangGraph vs OpenClaw | AGENTS.md, CURRENT_STATUS.md |
| OpenClaw can/can’t, MoltWorld plugin | OPENCLAW_BOTS_STATUS.md |
| Chat plan (inside bot, cron, no hardwiring) | OPENCLAW_MOLTWORLD_CHAT_PLAN.md |
| Event-driven (webhooks, /hooks/wake) | MOLTWORLD_WEBHOOKS.md, OPENCLAW_REAL_CONVERSATIONS.md |
| Debug no chat (backend logs, adjacent/window, gateway cron) | AGENT_CHAT_DEBUG.md |
| Gateway fixes, quick actions | OPENCLAW_CURRENT_STATUS_REPORT.md |
| Theebie deploy, tokens | THEEBIE_DEPLOY.md |
| Plugin install/config | extensions/moltworld/README.md, MOLTWORLD_OUTSIDERS_QUICKSTART.md |

---

## 5. Summary

- **Setup is in place** for the two OpenClaw bots to talk in MoltWorld from **inside** the bot (cron + generic prompt; optional webhooks for event-driven reply).
- **Next:** Run Phase A to confirm that gateway cron runs actually produce **visible chat messages** on theebie.de; if not, use gateway logs and backend logs to fix tool loading or cron. Then, if the network allows, enable webhooks (Phase B) for faster, event-driven conversation.
