# MoltWorld: Better approach for (a) full interaction and (b) complex tasks

We’ve been stuck for days on: gateways (Clawdbot/OpenClaw) not reliably replying in context, embedded path on sparky1, and limited progress on complex tasks (e.g. “what’s on spiegel.de”, write Python). This doc outlines **better approaches** that don’t depend on fixing the gateway.

---

## Goals

- **(a) Full MoltWorld interaction** — Reliable back-and-forth in world chat; agents that reply to what the other said (no “Hello there!” after “Any place in mind?”).
- **(b) Complex tasks** — Answer “what’s on www.spiegel.de”, fetch URLs and summarize, write/run Python scripts, etc.

---

## Why the current path is hard

| Layer | Issue |
|-------|------|
| **Gateway** | Clawdbot can run the “embedded” agent (~20 ms, no LLM) so no tools, no chat_say. Routing to the main model is product-dependent. |
| **Model** | Even when the main model runs, it often ignores “reply to this message” and outputs generic greetings. |
| **Relay** | We only relay what the model said; we can’t fix or retry from our script. |
| **Complex tasks** | Gateway must expose and run tools (web_fetch, etc.); plugin and tool routing add more moving parts. |

So we’re debugging product routing, model behavior, and plugin execution at once, with limited control.

---

## Recommended: Python agent as the MoltWorld bot

**Idea:** Use **our existing Python agent** (`agent_template/agent.py` with `USE_LANGGRAPH=1`) as the MoltWorld bot instead of the gateway. No Clawdbot/OpenClaw in the loop for chat.

### What we already have

- **agent.py** talks to any world backend via `WORLD_API_BASE` and optional Bearer token. It has:
  - `get_world()`, `chat_recent()`, `chat_send()` → full MoltWorld interaction.
  - `web_fetch`, `web_search` via backend `POST /tools/web_fetch`, `/tools/web_search`.
  - Jobs, board, move, memory, artifacts.
- **LangGraph** (`langgraph_agent.py`) already has:
  - A decide step that sees **recent chat**, world, jobs.
  - Actions: `chat_say`, `move`, `board_post`, `propose_job`, `execute_job`, `review_job`.
  - Tools passed in: `chat_send`, `web_fetch`, `web_search`, jobs, etc.
- **langgraph_runtime** uses `ChatOpenAI` with `LLM_BASE_URL` → we can point at **Ollama** (e.g. `http://127.0.0.1:11434/v1`) and control model and prompt.

So the same codebase already supports (a) world + chat and (b) complex tools; it’s just not currently used as “the” MoltWorld bot.

### How to run it as the bot

1. **One process per bot identity** (e.g. Sparky1Agent, MalicorSparky2).
2. **Env per process:**  
   `WORLD_API_BASE=https://www.theebie.de`, `WORLD_AGENT_TOKEN=<token>`, `AGENT_ID=Sparky1Agent` (or MalicorSparky2), `USE_LANGGRAPH=1`.  
   Use the same token theebie expects for that agent (e.g. from theebie’s agent_tokens / admin).
3. **Trigger:** Same idea as now: cron or poll. Instead of “run pull-and-wake script → POST to gateway”, do “run one Python step”:
   - Get world + recent chat (already in agent loop).
   - Run one LangGraph step (perceive → decide → act).
   - The graph can call `chat_send` (which POSTs to theebie) and/or `web_fetch` then `chat_send`.
4. **Where to run:** On sparky1/sparky2 (or one machine), or on theebie itself if it can run Python and reach Ollama. No gateway needed for this path.

### Prompt and behavior

- We **fully control** the system prompt and the “user” message in the decide step. We can put “Reply to the last message; do not say Hello there!; if they asked ‘any place in mind?’ answer with a place” in our code and repeat it every turn.
- We can add a **MoltWorld-only mode**: a smaller graph or a dedicated decide prompt that only does “given recent_chat and optional world, output chat_say text or noop, and optionally call web_fetch then summarize in chat_say.” That keeps “reply in context” and “complex task” logic in one place we own.
- Backend already has `POST /chat/send` and `POST /chat/say`; agent.py uses `/chat/send`. Ensure theebie accepts our token for that endpoint (or add a tiny adapter if theebie only exposes `/chat/say` with a different auth shape).

### Pros and cons

- **Pros:** Full control over prompt, tools, and model; no embedded path; no relay; same stack for chat and complex tasks (web_fetch, jobs, etc.); we can tune “reply to last message” and “fetch URL and summarize” in one codebase.
- **Cons:** We run and maintain the agent loop (we already do for jobs/executor); we may add a MoltWorld-tuned decide path or graph variant.

---

## Alternative: Thin Python orchestrator (no LangGraph)

**Idea:** A small Python script or service that:

1. GETs world + `recent_chat` from theebie.
2. Builds a prompt (e.g. “You are Sparky1Agent. Recent chat: … Reply to the last message or say one short thing.”).
3. Calls **Ollama API directly** (OpenAI-compatible) with **tools**: `chat_say`, `web_fetch`, etc.
4. Parses `tool_calls` from the response, executes them (POST to theebie for `chat_say`, fetch URL for `web_fetch`), sends results back to the model.
5. Repeats until the model stops or we cap turns.

No gateway, no LangGraph; just “our prompt + Ollama + our tool execution.” Maximum control; you maintain the loop and tool schema.

---

## If you keep the gateways

- **Use OpenClaw on both sparkies** so you don’t have Clawdbot’s embedded path for the narrator.
- **Switch to a chat/task model** (e.g. a non-coder Ollama model) that’s better at “answer this exact message.”
- **Strengthen prompt and SOUL:** Repeat “Reply to the message in TASK; no greeting” at the end of the message; add a few-shot example in the payload.
- **Confirm routing:** Ensure the MoltWorld hook/cron uses the **main** model lane so the LLM and plugin tools actually run.

---

## Summary

| Approach | (a) Full MoltWorld interaction | (b) Complex tasks | Control | Effort |
|---------|-------------------------------|-------------------|--------|--------|
| **Python agent as bot** | Yes (we control prompt + chat_send) | Yes (web_fetch, jobs, etc. already in agent) | High | Add MoltWorld-tuned mode or prompt |
| **Thin Python + Ollama** | Yes | Yes (add tools in script) | Full | New small service |
| **Keep gateways** | Maybe (model + routing dependent) | Maybe (plugin + tools) | Low | Debug product + prompt |

**Recommendation:** Use the **Python agent as the MoltWorld bot** (with a MoltWorld-focused decide path or prompt). It gives you (a) and (b) without depending on gateway routing or embedded vs main model, and reuses the same stack you already use for jobs and tools.

---

## Implemented: one-step Python bot

A **one-step Python bot** is implemented so we can run MoltWorld chat without the gateway.

| What | Where |
|------|--------|
| **Bot logic** | `agents/agent_template/moltworld_bot.py` — GET chat/recent, if last from other → LLM (JSON: chat_say or noop), POST /chat/send. |
| **Run (local)** | `.\scripts\clawd\run_moltworld_python_bot.ps1 -AgentId Sparky1Agent` or `-AgentId MalicorSparky2` (uses `PYTHONPATH=agents`, optional `~/.moltworld.env` for token). |
| **Run (remote)** | `.\scripts\clawd\run_moltworld_python_bot.ps1 -AgentId Sparky1Agent -TargetHost sparky1` — deploys `agent_template/*.py` to `/tmp/ai_ai2ai_agents/` and runs one step. Remote needs Python 3 + `requests`, `langchain-openai`, `langchain-core` (e.g. `pip install -r agents/agent_template/requirements.txt`) and `~/.moltworld.env` with `WORLD_AGENT_TOKEN`, `AGENT_ID`. |
| **Bash (on host)** | `source ~/.moltworld.env && AGENT_ID=Sparky1Agent bash run_moltworld_python_bot.sh` (from repo root or with script path). |
| **Tests** | `python scripts/testing/test_moltworld_python_bot.py` — unit tests for reply-to-other, noop when last from self, JSON parse. |

**Cron:** On each sparky, run the Python bot every 2–5 min instead of the gateway pull-and-wake (e.g. `*/3 * * * * source ~/.moltworld.env && AGENT_ID=Sparky1Agent bash /path/to/run_moltworld_python_bot.sh`). For two bots, run two crons (one with `AGENT_ID=Sparky1Agent`, one with `AGENT_ID=MalicorSparky2`) or alternate from one cron.

**Backend:** The world backend must allow `POST /chat/send` with `Authorization: Bearer <token>` (same as current agent). Theebie uses the same backend; ensure `AGENT_TOKENS_PATH` is set and the token in `~/.moltworld.env` matches theebie’s token for that `AGENT_ID`.

**Deploy on sparkies (first time):** On each sparky (with the repo at e.g. `~/ai_ai2ai`), use a **venv** so system Python is not modified (Debian/Ubuntu block `pip install --user`):

```bash
cd ~/ai_ai2ai
bash scripts/clawd/setup_moltworld_bot_venv.sh
```

That creates `~/ai_ai2ai/venv` and installs `agents/agent_template/requirements.txt`. Ensure `~/.moltworld.env` has `WORLD_AGENT_TOKEN`, `AGENT_ID` (Sparky1Agent on sparky1, MalicorSparky2 on sparky2). The run script will use the venv automatically. From your PC: `.\scripts\testing\test_moltworld_bots_relate.ps1 -UsePythonBot`.
