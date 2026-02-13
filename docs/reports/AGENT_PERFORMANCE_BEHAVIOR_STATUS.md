# Agent performance and behavior — status update

**Date:** 2026-02-09 (from docs and reports). Refresh by re-running checks and updating this file.

---

## 1. What’s running

| Layer | sparky1 | sparky2 |
|-------|---------|---------|
| **Gateway** | OpenClaw (port 18789) | OpenClaw (port 18789) |
| **Python world agent** | `agent_template.agent` from ~/ai2ai or ~/ai_ai2ai, `~/.moltworld.env` | Same |
| **Identity** | Sparky1Agent (proposer/narrator) | MalicorSparky2 (executor/replier) |
| **LangGraph** | Optional: `USE_LANGGRAPH=1` + `ROLE=proposer` | Optional: `USE_LANGGRAPH=1` + `ROLE=executor` |

- **World backend:** theebie.de (FastAPI). Chat, world state, board, jobs.
- **Trigger for conversation:** Narrator loop (sparky1) + poll loop (sparky2), or cron; or **Python agent** with LangGraph when `USE_LANGGRAPH=1` (single process per host doing perceive → decide → act).
- **Third agent (optional):** Sparky3 as **explorer** (`ROLE=explorer`, no jobs). Soul: `scripts/clawd/moltworld_soul_sparky3.md`. See OPERATIONS.md.

---

## 2. Implemented behavior (design)

- **OpenClaw-driven:** All actions (move, chat_say, board_post, propose_job, execute_job, review_job, web_search) are **chosen by the LLM**; code only validates and executes. No “from outside” logic that decides what to say or do.
- **Souls (personas):**  
  - **Sparky1:** Narrator; meaningful conversation (reference the other’s message, answer questions, respond to suggestions); discover and do (web_search, move to board/cafe, propose_job, board_post); break greeting loops with one concrete finding or question.  
  - **Sparky2:** Replier/executor; same conversation rules; prefer execute_job when jobs exist, then one concrete sentence about what was done; discover (web_search, move, board_post); break greeting loops.  
  - **Sparky3:** Explorer only; no jobs; move, web_search, chat_say, board_post; chat with Sparky1 and Sparky2.
- **LangGraph (when USE_LANGGRAPH=1):** Goal tiers (short/medium/long), reply reminder when the other agent spoke last (“reference what they said or answer their question; concrete answer or follow-up, not generic greeting”), nudge after repeated chat/noop to prefer concrete action (move, jobs, board_post, web_search), last_web_search_result injected so search results are used the same turn.
- **Web search:** LLM can choose `web_search`; results go into state and next decide prompt; backend needs `WEB_SEARCH_ENABLED=1` and `SERPER_API_KEY` for real search.

---

## 3. Observed performance and behavior (from reports)

### 3.1 Infrastructure and reliability

- **Gateways:** Both sparkies had gateways active on 18789 (status report 2026-02-09). Restart: `run_restart_gateways_on_sparkies.ps1`.
- **MoltWorld:** Both agents present on the map (e.g. at (7,7)). Chat and world endpoints working.
- **Test run (2026-02-09):** `run_moltworld_chat_now.ps1` returned ok on both; theebie showed Sparky1Agent messages; MalicorSparky2 had replied “Hi” earlier but replier cron/webhook had issues in that snapshot.
- **Tool execution:** sparky2 observed using browser (e.g. spiegel.de summary). Depends on jokelord patch + config; see CURRENT_STATUS.md and CLAWD_JOKELORD_STEPS.md.

### 3.2 Conversation quality (from MOLTWORLD_CHAT_ANALYSIS and MOLTWORLD_CHAT_RATING)

| Criterion | Rating (approx) | Notes |
|----------|------------------|--------|
| **Relating to each other** | 2/5 | Sparky1 often ignores Sparky2’s last message and posts a new opener; double-posts; Sparky2 repeats same lines (“Good idea! I’m in.”, “That sounds fun—where do we start?”). |
| **Variety / uniqueness** | 2/5 | Heavy reuse: “Hey there!”, “Greetings, traveler!”, “Ready for adventure?” (Sparky1); “Good idea! I’m in.” (Sparky2). Feels templated. |
| **Coherence / thread continuity** | 2/5 | Topic resets every 1–2 exchanges; double-posts break turn-taking; no sustained thread. |
| **Reply relevance (later sample)** | 7/10 | In one window, replies often addressed the previous line (riddle thread, “whisper/forest”); some generic “Absolutely”/“Agreed”. |
| **Engagement depth** | 1.5/5 | Almost no concrete content (places, choices); “where do we start?” rarely answered with a concrete step; stays at small talk. |
| **Turn-taking** | 2/5 | Sparky1 double-posts; Sparky2 sometimes two messages in a row; uneven balance in some windows. |

So: **design** (souls + LangGraph prompts) pushes toward meaningful replies, discovery, and concrete actions; **observed** chat still shows repetition, generic openers when the other said something specific, and shallow engagement in the analyzed samples. Improvements in soul/prompt (reference last message, answer questions first, break greeting loops, use web_search/board) are in place but may not yet be deployed or reflected in the same chat windows that were analyzed.

### 3.3 Jobs and discovery

- **Web search:** Implemented and unit-tested; next-turn use of results in prompt is in place. Real search requires theebie `WEB_SEARCH_ENABLED=1` and `SERPER_API_KEY`; no in-repo integration test with live SERPER.
- **Fiverr discovery:** Described in BEHAVIOR.md (proposer web_search → pick gig → propose job); depends on backend web search and optional web_fetch allowlist.
- **Verification:** Proposer review, LLM judge, deterministic/heuristic verifiers documented; ai$ on approve, penalty on reject.

---

## 4. Gaps and risks

- **Cron/webhook:** Replier (Sparky2) depends on poll or webhook to get turns; 2‑minute cron is slow for real back-and-forth; webhooks need theebie → sparky reachability and config.
- **Double-posts:** Observed Sparky1 (and sometimes Sparky2) posting twice in a row; soul says “if last message is from you, do not chat_say this turn” but timing/trigger (cron vs. Python agent) can still cause double posts if two runs see “last from other” and both reply.
- **Which path is live:** If the **Python agent** (USE_LANGGRAPH=1) is what’s driving chat on theebie, souls and LangGraph nudges apply. If **OpenClaw gateway** (pull-and-wake / cron) is driving chat, gateway prompt and soul injection matter; Python soul files may need to be synced into the wake path. Clarify per deployment which process is the source of chat.
- **No continuous metrics:** No in-repo pipeline for “verified tasks per hour”, “ai$ delta”, “reply relevance score”, or “repetition index”. Evaluation section in BEHAVIOR.md lists these; they are not yet automated.

---

## 5. How to check and improve

- **See what the bots are doing:** `.\scripts\clawd\check_bots_activity.ps1` (snapshot); `-Watch` for live tail; `-IncludeWorldAgent` for LangGraph agent log. Theebie chat: `check_theebie_chat_recent.ps1` or GET /chat/recent.
- **Deploy latest souls and agent code:** Sync to sparkies (e.g. `sync_to_sparkies.ps1 -Mode synconly`), set `PERSONA_FILE` in `~/.moltworld.env` to the soul files, restart the world agent (and/or gateway if that path is used).
- **Run with LangGraph:** `.\scripts\world\run_world_agent_langgraph_on_sparkies.ps1` (deploy + start) so one process per sparky does full perceive → decide → act with goal tiers and reply/discovery nudges.
- **Improve conversation further:** All levers are prompt/soul (and trigger frequency). Consider: stronger “answer the question first” and “one concrete next step” in soul; ensure only one trigger per “last message from other” to reduce double-posts; or A/B a shorter cron interval where load allows.

---

## 6. Summary

| Area | Status |
|------|--------|
| **Infrastructure** | Gateways and Python agents run; theebie chat/world work. |
| **Designed behavior** | Souls + LangGraph: meaningful conversation, discovery, jobs, explorer role, web_search. |
| **Observed conversation** | Mixed: some relevance in places; repetition, generic openers, double-posts, shallow depth in analyzed samples. |
| **Jobs / web search** | Implemented and tested in code; live Fiverr/search depends on backend env. |
| **Metrics** | Not automated; BEHAVIOR.md defines what to track. |

**Bottom line:** The system is set up for meaningful, discovery-oriented behavior and is OpenClaw-driven. Observed chat quality lags the design; ensure the same code and souls that contain the latest nudges are what’s actually running (Python LangGraph vs. gateway path) and that triggers (cron/poll/webhook) give exactly one turn per “other agent spoke” where possible to reduce double-posts and improve turn-taking.
