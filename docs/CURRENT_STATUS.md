# Current status — 2026-02-09

**When you update this doc, change the date in the headline above** so we keep track of progress (e.g. "Current status — 2026-03-15").

---

## 1. What runs where (overview)

| Layer | sparky1 | sparky2 |
|-------|---------|---------|
| **Gateway** | OpenClaw (openclaw-gateway) | OpenClaw (openclaw-gateway) |
| **Config** | `~/.openclaw/` | `~/.openclaw/` |
| **Python agent (MoltWorld)** | `python3 -m agent_template.agent` from `~/ai2ai/agents` | Same, from `~/ai2ai/agents` |
| **MoltWorld env** | `~/.moltworld.env` | `~/.moltworld.env` |
| **Repos** | `~/ai_ai2ai`, `~/ai2ai` | `~/ai_ai2ai`, `~/ai2ai` |

- **World agents** (on the map at theebie.de): the **Python** processes (Sparky1Agent, MalicorSparky2). They use `agent_template/agent.py`; with `USE_LANGGRAPH=0` (default) they use the legacy loop; with `USE_LANGGRAPH=1` they use the LangGraph path (LLM decides move/chat/jobs).
- **OpenClaw** on the sparkies: separate **gateway** processes for chat (TUI/Control UI) and cron. They are not the same identity as the world agents unless you add the MoltWorld plugin and wire the same token.

Details: [AGENTS.md](AGENTS.md) § "What runs where".

---

## 2. Sparky inventory (what we actually see)

Collected via `.\scripts\sparky_inventory.ps1` (and optionally `-FetchZip`). Output in **sparky_inventory/** (gitignored).

**Processes**

- **sparky1:** openclaw-gateway, python3 -m agent_template.agent (from ~/ai2ai/agents, .moltworld.env sourced).
- **sparky2:** openclaw-gateway, python3 -m agent_template.agent (same).

**Config (from inventory)**

- **sparky1** `~/.openclaw/openclaw.json`: Ollama 127.0.0.1:11434, primary `ollama/qwen2.5-coder:32b`, tools profile full, deny sessions_send/message/tts/sessions_spawn, browser (chromium-browser), gateway 18789, Telegram enabled.
- **sparky2** `~/.openclaw`: Same Ollama (local); primary `ollama/qwen-agentic:latest`; same tools/browser; has extensions/, openclaw.json.

Full snapshot and how to re-run: [SPARKY_INVENTORY_FINDINGS.md](SPARKY_INVENTORY_FINDINGS.md).

---

## 3. OpenClaw bots — what they can and can’t do

### What they CAN do

- **Chat** — TUI or Control UI (port 18789); model replies with **text** via Ollama.
- **Ollama** — No cloud API; both use local Ollama.
- **Cron** — Scheduled prompts (e.g. Fiverr screen); delivery to Telegram if configured.
- **Browser / tool use** — **sparky2** has been observed using the browser (e.g. fetching and summarizing www.spiegel.de). Tool execution (browser, web) **does work** on sparky2. We enable it by running the **jokelord patch**: patched gateway build + `compat.supportedParameters` in config. See [CLAWD_JOKELORD_STEPS.md](external-tools/clawd/CLAWD_JOKELORD_STEPS.md). sparky1 may use the same or similar setup; if you see tools working there too, update this section.

### What they CAN’T do (or don’t have yet)

| Gap | Reason |
|-----|--------|
| **MoltWorld** (world_state, world_action, board_post) | **Done:** Plugin installed on both; “MoltWorld chat turn” cron added (staggered every 2 min). Verify: `.\scripts\clawd\verify_moltworld_cron.ps1` (gateway reachability, last chat). Restart: `.\scripts\clawd\run_restart_gateways_on_sparkies.ps1` verifies 18789 and nohup fallback. See [OPENCLAW_MOLTWORLD_CHAT_PLAN.md](OPENCLAW_MOLTWORLD_CHAT_PLAN.md). |
| **Same identity as world agents** | Gateways use the same tokens (Sparky1Agent / MalicorSparky2) so they appear in the world as those names; Python agents are separate processes. |

**Why the docs said “can’t” before:** Status was written from the SSH inventory (config, process list) and the upstream issue [clawdbot #1866] (gateway doesn’t send tool definitions to Ollama). There was no live test or user report that tools actually run on sparky2, so we documented the theoretical blocker. After you tested it (e.g. asking sparky2 what’s on spiegel.de), we had evidence that browser works. When in doubt, verify with a quick live test and update this section.

**Summary table**

| Capability | sparky1 | sparky2 |
|------------|------------------|---------------------|
| Gateway + Ollama chat (text) | ✅ | ✅ |
| Telegram | ✅ | ✅ |
| Cron | ✅ | ✅ |
| Tool execution (browser, web) | unconfirmed | ✅ observed (e.g. spiegel.de) |
| MoltWorld (world/board) | ✅ plugin + cron | ✅ plugin + cron |
| Python agent on same host | ✅ separate process | ✅ separate process |

**Note on tool execution:** Upstream [clawdbot #1866](https://github.com/clawdbot/clawdbot/issues/1866) describes stock gateways that don’t send tool definitions to Ollama. **We run the jokelord patch** (patched build + `compat.supportedParameters`) so tools work on sparky2 (and optionally sparky1). Steps: [CLAWD_JOKELORD_STEPS.md](external-tools/clawd/CLAWD_JOKELORD_STEPS.md). If a node loses tool use after a reinstall, re-apply the patch and config; see [CLAWD_SPARKY.md](external-tools/clawd/CLAWD_SPARKY.md) for alternatives (PR #4287).

Full detail: [OPENCLAW_BOTS_STATUS.md](OPENCLAW_BOTS_STATUS.md).


---

## 4. Python agents (MoltWorld)

- **Where:** `~/ai2ai/agents` on both sparkies; started with `~/.moltworld.env` sourced.
- **What:** `agent_template/agent.py` — perceive world, decide (legacy loop or LangGraph when `USE_LANGGRAPH=1`), act (move, chat_send, jobs, board, etc.).
- **Identity:** Sparky1Agent (sparky1), MalicorSparky2 (sparky2) at theebie.de.
- **LangGraph:** Set `USE_LANGGRAPH=1` and `ROLE=proposer` / `ROLE=executor` to have the LLM decide all actions (move, chat_say, board_post, propose_job, execute_job, review_job). See [AGENTS.md](AGENTS.md) § “OpenClaw-driven flow”, [GETTING_STARTED.md](GETTING_STARTED.md) § “Step C (optional): OpenClaw-driven agents”.

---

## 5. How to refresh this snapshot

1. **Re-run inventory:**  
   `.\scripts\sparky_inventory.ps1` (and `-FetchZip` if you want zips).  
   Then review `sparky_inventory/sparky1_inventory.txt` and `sparky2_inventory.txt`.

2. **Update this doc:**  
   Adjust sections 1–4 if anything changed (new processes, config, plugins, blockers).  
   **Update the date in the headline** (e.g. to today’s date).

3. **Pointers to full docs:**  
   - [SPARKY_INVENTORY_FINDINGS.md](SPARKY_INVENTORY_FINDINGS.md) — inventory summary and how to run.  
   - [OPENCLAW_BOTS_STATUS.md](OPENCLAW_BOTS_STATUS.md) — OpenClaw/Clawd can/can’t and fixes.  
   - [AGENTS.md](AGENTS.md) — what runs where, OpenClaw-driven rule, LangGraph.  
   - [CLAWD_SPARKY.md](external-tools/clawd/CLAWD_SPARKY.md) — full Clawd/OpenClaw setup on sparkies.
