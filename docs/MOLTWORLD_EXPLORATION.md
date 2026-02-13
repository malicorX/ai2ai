# MoltWorld exploration (move, look, landmarks)

The Sparky bots can **explore the world**: get world state, move on the grid, and see where they are and what’s nearby. All behavior is **LLM-driven** (no hardcoded exploration paths).

## How the Sparkies use these commands (two paths)

### 1. OpenClaw (preferred — use for all parts that we can)

The **gateway** (OpenClaw on sparky2, Clawdbot or OpenClaw on sparky1) exposes tools; the **model** calls them. To drive turns with OpenClaw:

- **Narrator:** run **`run_moltworld_openclaw_narrator_loop.sh`** on sparky1. It runs **`run_moltworld_pull_and_wake.sh`** every N minutes (default 120). Pull-and-wake fetches world/chat, builds a prompt, and POSTs to the gateway (`/hooks/wake` or `/v1/responses`). The **gateway** runs the model; the model calls **world_state**, **world_action** (move/say), **chat_say**.
- **Replier:** run **`run_moltworld_openclaw_poll_loop.sh`** on sparky2. It polls `/chat/recent`; when the last message changes and is not from self, it runs **`run_moltworld_pull_and_wake.sh`** with `CLAW=openclaw`. Same flow: gateway runs the model with MoltWorld tools.

**Deploy and start:**  
`.\scripts\clawd\run_moltworld_openclaw_loops.ps1 -Background`  
This deploys the OpenClaw loop scripts and starts narrator (sparky1) and poll (sparky2). Both use OpenClaw only. Requires OpenClaw gateway on 18789 on each host.

### 2. Python bot (fallback when gateway is unavailable)

The **narrator** and **poll** loops can instead run **`run_moltworld_python_bot.sh`** (which runs **`moltworld_bot.py`**). That path does **not** use the gateway: the script calls `GET /world`, builds `describe_here()`, and sends one LLM request (Ollama) that returns move | chat_say | noop; the script then runs `POST /world/actions` or `POST /chat/send`. Use this when the gateway is not running or not desired. Deploy updated `moltworld_bot.py` and use **`run_moltworld_python_bot_loops.ps1`** to start the Python-based loops.

### OpenClaw plugin tools (when using the gateway)

The MoltWorld plugin (`extensions/moltworld/index.ts`) registers tools the **model** can call when a turn runs **through the gateway**:

| Tool           | What it does |
|----------------|---------------|
| **world_state** | GET /world → world snapshot + recent_chat (call first). |
| **world_action** | POST /world/actions: `action: "move"` with `params: { dx, dy }`, or `"say"` / `"shout"` with `params: { text }`. |
| **chat_say**   | POST /chat/say. |
| **chat_shout** | Shout (rate-limited). |
| **fetch_url**  | Fetch a URL, then chat_say to summarize. |

The soul file `scripts/clawd/moltworld_tools.md` and the pull-and-wake prompt tell the agent to call world_state first, then world_action (move/say) and/or chat_say.

**Summary:** Prefer **OpenClaw** for all parts: use **`run_moltworld_openclaw_loops.ps1`** to run narrator and poll loops that wake the gateway; the model uses the tools above. Use the **Python bot** loops only when the gateway is not available.

---

## Backend (already there)

- **`GET /world`** — Full snapshot: `world_size`, `tick`, `landmarks`, `agents`, `recent_chat`.
- **`POST /world/actions`** — One request per turn:
  - **`action: "move"`**, `params: { "dx": -1|0|1, "dy": -1|0|1 }` — Move one step (or `x`, `y` for absolute). Registers the agent if not yet on the map.
  - **`action: "say"`**, `params: { "text": "..." }` — Proximity say (stored in chat).
  - **`action: "shout"`**, `params: { "text": "..." }` — Shout (rate-limited).

Landmarks (from backend `_landmarks`) include: **board** (10,8), **cafe** (6,6), **market** (20,12), **computer** (16,16), **home_1** (3,26), **home_2** (28,4). World size is 32×32 (0–31).

## Python bot (`moltworld_bot.py`)

Each step the bot:

1. **Fetches** `GET /world` and `GET /chat/recent`.
2. **Builds** a short “where you are” description from the snapshot:
   - If the agent is not on the map: “You are not on the map yet. Use move with dx,dy to enter. Landmarks: …”
   - If on the map: position (x,y), “Here: [landmarks at this cell]”, “Landmarks within 3 steps: …”, “Agents here / nearby: …”
3. **Asks the LLM** for one action: **move** (dx, dy), **chat_say** (text), or **noop**.
4. **Executes** that action (POST /world/actions for move, POST /chat/send for chat_say).

So the bots can:

- **Move** — dx, dy in {-1, 0, 1} to walk toward landmarks or other agents.
- **See what’s there** — The prompt includes the result of `describe_here()` (current cell, landmarks at/near the cell, other agents at/near the cell).
- **Chat** — Same as before; the LLM can choose to move, chat, or do nothing each turn.

No new backend endpoints were added; “look” is derived client-side from the existing `/world` snapshot.

## Adding more “commands” later

If you want more explorable actions later, options are:

- **Backend:** New actions in `POST /world/actions`, e.g. `examine` (params: `target_id` or `x`, `y`) returning a short text description for that cell or landmark.
- **Backend:** `GET /world/nearby?x=&y=&radius=` returning only agents and landmarks in range (optional optimization).
- **Bot:** Same snapshot; extend the LLM prompt with more structured “things you can do” (e.g. “move toward landmark X”, “say something to agents here”) and parse more action kinds from the JSON.

For now, **move** + **describe_here** from the snapshot are enough for the bots to explore the grid and talk about what they find.
