# Clawd (Moltbot) on sparky1 and sparky2

This doc covers installing **Clawd** (Moltbot) on the DGX nodes (sparky1, sparky2), wiring it to **Ollama**, and adding **proactive behavior** (e.g. screening Fiverr tasks and reporting).

- **Clawd:** [docs.clawd.bot](https://docs.clawd.bot) — personal AI assistant (Telegram/WhatsApp/Discord, browser, skills, cron).
- **Ollama:** Already used by the AI Village backend/agents on the same hosts; Clawd can use it as the LLM provider.
- **Proactive:** Use Clawd’s **cron** to run an isolated agent turn (e.g. “scan Fiverr and report”) and deliver the result to a channel.

---

## Quick start

Clawd runs **on sparky1 and sparky2**. The scripts that matter there are the **`.sh`** ones; the **`.ps1`** scripts are optional helpers for running those from a Windows dev machine.

### Option A — Repo is on the sparkies (use this if the repo is not on Windows)

Have the repo on each sparky (e.g. `~/ai_ai2ai` or `/home/malicor/ai_ai2ai`). Then **on each sparky**:

1. **Install Clawd** (Node 22 + Moltbot; run once per host):
   ```bash
   cd ~/ai_ai2ai   # or wherever the repo is
   bash scripts/clawd/install_clawd_on_sparky.sh
   ```
2. **Prep gateway and Ollama config** (gateway.mode local, full Ollama provider in config):
   ```bash
   source ~/.bashrc
   bash scripts/clawd/clawd_prepare_on_sparky.sh
   ```
3. **Onboard** (interactive; do this on the host where the gateway will run):
   ```bash
   source ~/.bashrc
   clawdbot onboard --install-daemon
   ```
4. **Start the gateway** (with Ollama env; after onboarding):
   ```bash
   bash scripts/clawd/start_clawd_gateway.sh
   ```
5. **Chat**: `source ~/.bashrc; clawdbot tui`

So: **clawd_prepare_on_sparky.sh**, **start_clawd_gateway.sh**, and **install_clawd_on_sparky.sh** live in the repo **on the sparkies** and you run them there. No `.ps1` on the sparkies.

### Option B — From a Windows dev machine (repo on m: or similar)

If the repo is on your Windows machine, you can use the `.ps1` scripts to **copy** the `.sh` scripts to each sparky and run them via SSH. The repo must also exist on each sparky (e.g. at `/home/malicor/ai_ai2ai`) so the copy has a destination.

From PowerShell, repo root (e.g. `m:\Data\Projects\ai_ai2ai`):

1. **Install Clawd on both sparkies**: `.\scripts\clawd\run_install_clawd.ps1`
2. **Prep on both**: `.\scripts\clawd\run_clawd_prepare.ps1`
3. **Onboard** (interactive on one host): `ssh sparky1`, then `source ~/.bashrc; clawdbot onboard --install-daemon`
4. **Restart gateway** (after prep): `.\scripts\clawd\run_start_clawd_gateway.ps1`
5. **Status**: `.\scripts\clawd\clawd_status.ps1`

**Automation from your PC (no manual SSH editing):**

- **Apply config + restart** — set `tools.deny` (sessions_send, **message**), browser, fix CRLF, restart gateway (scripts do not add compat.openaiCompletionsTools; stock Clawd rejects it):  
  `.\scripts\clawd\run_clawd_apply_config.ps1` (default: both sparkies) or `-Hosts sparky2`. If repo on sparky is `~/ai2ai`, use `-RemotePath /home/malicor/ai2ai/scripts/clawd`.
- **See gateway log** — tail last 80 lines on sparky2:  
  `.\scripts\clawd\run_clawd_logs.ps1` or `-Target sparky2 -Lines 100`
- **See config** — print `~/.clawdbot/clawdbot.json` from sparky2:  
  `.\scripts\clawd\run_clawd_config_get.ps1` or `-Target sparky2`

**Which model does Clawd use?** By default Clawd uses the model in its config (often a cloud model like `claude-opus-4-5`). To use **Ollama** as the default, on the host run:
```bash
clawdbot config set agents.defaults.model.primary "ollama/llama3.3"
```
Our prep script also writes `models.providers.ollama.apiKey: "ollama-local"` into `~/.clawdbot/` config so the gateway has it forever; we still add `OLLAMA_API_KEY` to `~/.bashrc` for CLI use. Pull an Ollama model (e.g. `ollama pull llama3.3`). See §3 below for details.

---

## Continue with Clawdbot (tool calling)

To get **tool calling** working with Ollama (browser, HTTP, Moltbook skill) on sparky2:

1. **Gateway build** — You need a build that includes [OpenClaw PR #4287](https://github.com/openclaw/openclaw/pull/4287) (openai-completions tool routing). If the PR was closed/reverted, cherry-pick it or apply the [PR diff](https://github.com/openclaw/openclaw/pull/4287.diff) and build. See §4.1 below.
2. **Apply config** — From your PC: `.\scripts\clawd\run_clawd_apply_config.ps1 -Hosts sparky2` (or `.\scripts\clawd\run_clawd_do_all.ps1 -Target sparky2`). This sets `tools.profile=full`, `tools.deny` (sessions_send, message), and browser. If your repo on sparky2 is at `~/ai2ai`, use `-RemotePath /home/malicor/ai2ai/scripts/clawd`.
3. **Restart gateway** — The apply script restarts the gateway; or on sparky2 run `bash ~/bin/start_clawd_gateway.sh` (or `clawdbot gateway stop; sleep 2; nohup clawdbot gateway >> ~/.clawdbot/gateway.log 2>&1 &`).
4. **Test** — In Chat/TUI ask: *"Use the browser tool to open https://google.com"* or *"Post a short test to Moltbook"* (with Moltbook skill installed). If tools run, you're good.

**Model:** [Reddit r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/comments/1qrywko/getting_openclaw_to_work_with_qwen314b_including/) reports **qwen3:14b** works well with many tools; qwen3:8b can lose context. Pull e.g. `ollama pull qwen3:14b` and set primary to `ollama/qwen3:14b` if you like.

**Working config reference:** [Hegghammer Gist: Working Clawdbot/Moltbot setup with local Ollama model](https://gist.github.com/Hegghammer/86d2070c0be8b3c62083d6653ad27c23) documents a tested setup (72B Qwen, 48GB VRAM) with **real** tool use. The Gist does **not** bypass the need for the gateway to send tools: if your Clawd build doesn't send tool definitions (e.g. stock without PR #4287), the model will only output JSON as text. What the Gist gives you: (1) **Custom Ollama model** — use a Modelfile with a SYSTEM prompt that tells the model to USE tools directly, be concise, not describe. We provide `scripts/clawd/clawd_qwen_agentic.Modelfile` (based on qwen2.5-coder:32b); on sparky2 run `ollama pull qwen2.5-coder:32b` then `ollama create qwen-agentic -f ~/ai2ai/scripts/clawd/clawd_qwen_agentic.Modelfile` and set primary to `ollama/qwen-agentic:latest`. (2) **exec.ask: "off"**, **exec.security: "full"** — our scripts already set these. (3) **SOUL.md brevity** — our apply script deploys `scripts/clawd/clawd_SOUL_message_fix.txt` to the workspace as SOUL.md (message fix + brevity). (4) [OpenClaw Ollama docs](https://docs.openclaw.ai/providers/ollama) describe standard provider config; they do not enable tool routing — you still need a gateway build that sends tools (PR #4287 or a release that includes it).

### Fix /new showing raw JSON (e.g. `{"name": "message", "arguments": {"message": "Hi! ..."}}`)

If a **new chat** (`/new`) shows the assistant "reply" as raw JSON instead of plain text, the model is calling a **message** tool instead of replying with text. Fix by applying our config so `~/.clawdbot/clawdbot.json` has `tools.deny` including **"message"** (and **"sessions_send"**), then restart the gateway.

**From your Windows PC (repo on m: or similar):**

1. Apply config on sparky2 (writes `tools.deny: ["sessions_send", "message"]`, browser, compat, restarts gateway):
   ```powershell
   cd m:\Data\Projects\ai_ai2ai
   .\scripts\clawd\run_clawd_apply_config.ps1 -Hosts sparky2
   ```
   Default RemotePath is `/home/malicor/ai2ai/scripts`; if your repo on sparky2 is elsewhere use `-RemotePath /path/to/scripts`.

2. Confirm config on sparky2:
   ```powershell
   .\scripts\clawd\run_clawd_config_get.ps1 -Target sparky2
   ```
   You must see `"deny": ["sessions_send", "message"]` (and `"profile": "full"`). If not, the script didn’t run on sparky2 or the copy failed — run step 1 again.

3. Open chat (browser or TUI), start a **new** chat, send a message. The reply should be plain text, not JSON.

**On sparky2 directly (no Windows):**

1. After syncing repo to sparky2: `cd ~/ai2ai/scripts/clawd` then `python3 clawd_patch_config_only.py` then `bash clawd_apply_config_remote.sh`.
2. Check: `grep -A2 '"deny"' ~/.clawdbot/clawdbot.json` — should show `"deny": ["sessions_send", "message"]`.
3. If the gateway didn’t restart, run: `clawdbot gateway stop; sleep 2; nohup clawdbot gateway >> ~/.clawdbot/gateway.log 2>&1 &`

**Expected config snippet** (what the apply script writes for tools):

```json
"tools": {
  "profile": "full",
  "deny": ["sessions_send", "message"],
  "exec": { "host": "gateway", "ask": "off", "security": "full" }
}
```

**compat.openaiCompletionsTools** — Stock Clawd (e.g. 2026.1.24-3) does **not** support this key and will report "Config invalid". Our scripts **no longer add it**; they remove it if present so `clawdbot update` and `clawdbot doctor` work. If you already have that key in config, run **once** on sparky2: `clawdbot doctor --fix` to remove it. When you use a gateway build that includes [OpenClaw PR #4287](https://github.com/openclaw/openclaw/pull/4287), add the key manually to each Ollama model entry in `~/.clawdbot/clawdbot.json` if you need tool calling.

### Stuck on /new (thinking forever, no reply)

If after `/new` the assistant shows "..." and never responds, the model is likely still **returning a `message` tool call**. The gateway denies it (so you don't see raw JSON), but it may not substitute that with text, so the UI has nothing to show and stays "thinking".

**1. Check the gateway log on sparky2:**

```bash
tail -80 ~/.clawdbot/gateway.log
```

Look for the request/response for the stuck turn. If you see a tool call for `message` and no assistant text, that confirms it.

**2. Tell the model to reply with plain text only** — add this to the agent workspace so the model sees it (Clawd loads SOUL.md from the workspace):

On sparky2, ensure the workspace exists and add or prepend to SOUL.md (your config has `agents.defaults.workspace: "/home/malicor/clawd"`):

```bash
mkdir -p /home/malicor/clawd
echo 'Never call the "message" tool. Reply only with plain text in your response.' >> /home/malicor/clawd/SOUL.md
```

Or create/edit `/home/malicor/clawd/SOUL.md` with:

```text
Never call the "message" tool. Reply only with plain text in your response.
```

Then start a **new** chat again (the model will see SOUL.md for the workspace).

**3. Optional: custom Ollama model with system prompt** — If the model still prefers a `message` tool, create a custom model with a SYSTEM prompt that says the same. Example Modelfile:

```text
FROM qwen2.5-coder:32b
SYSTEM Never use a "message" tool. Always reply with plain text only.
```

Then `ollama create qwen-chat -f Modelfile` and set primary to `ollama/qwen-chat`.

---

## 1. Prerequisites

- **Node.js >= 22** on each sparky (install via NodeSource or your distro).
- **Ollama** running on the same host (you already have this for backend/agents).
- A **tool-capable** Ollama model (Clawd auto-discovers only models that report tool support), e.g.:
  ```bash
  ollama pull llama3.3
  # or: ollama pull qwen2.5-coder:32b
  ```
- Optional: **Telegram** (or WhatsApp/Discord) bot token and chat ID for delivery (see [Channels](https://docs.clawd.bot/channels)).

---

## 2. Install Clawd on sparky1 and sparky2

On **each** host (sparky1, sparky2):

**Option A — Installer (recommended)**  
Installs `moltbot` globally and can run onboarding:

```bash
curl -fsSL https://molt.bot/install.sh | bash
# Next: moltbot onboard --install-daemon
```

Non-interactive (e.g. automation):

```bash
curl -fsSL https://molt.bot/install.sh | bash -s -- --no-onboard
# Then: moltbot onboard --install-daemon  # when ready
```

**Option B — Manual (npm)**  
If Node 22 is already installed:

```bash
npm install -g moltbot@latest
moltbot onboard --install-daemon
```

**After install**

- Run **onboarding** once per machine (pairing, identity, optional channels).
- Start the **gateway** (daemon); the installer can install it as a service.
- Quick check: `moltbot doctor`, `moltbot status`, `moltbot health`.

Details: [Install](https://docs.clawd.bot/install), [Docker](https://docs.clawd.bot/install/docker) (optional).

---

## 3. Hook Clawd up to Ollama

Ollama exposes an OpenAI-compatible API at `http://127.0.0.1:11434`. Clawd can **auto-discover** tool-capable models from that URL.

**Enable Ollama (any value works; Ollama doesn’t require a real key):**

```bash
export OLLAMA_API_KEY="ollama-local"
```

Our **prep script** (`run_clawd_prepare.ps1` → `clawd_prepare_on_sparky.sh`) writes the **full** Ollama provider into `~/.clawdbot/clawdbot.json` in one go (baseUrl, apiKey, and a `models` array are required by Clawd’s validation). That way the gateway has Ollama forever, even when started without `OLLAMA_API_KEY` in the environment. We still add `OLLAMA_API_KEY` to `~/.bashrc` for CLI use. Default model in that block is `llama3.1:70b`; edit the JSON to add more models or change IDs if needed.

**Use an Ollama model as primary:**

In your agent config (see [Ollama provider](https://docs.clawd.bot/providers/ollama)):

```yaml
agents:
  defaults:
    model:
      primary: "ollama/llama3.3"
      # fallback: ["ollama/qwen2.5-coder:32b"]
```

If Ollama is on **another host** (e.g. only on sparky1), on sparky2 set explicit provider:

```yaml
models:
  providers:
    ollama:
      baseUrl: "http://sparky1:11434/v1"
      apiKey: "ollama-local"
      # Define models manually when using custom baseUrl (no auto-discovery)
      models:
        - id: "llama3.3"
          name: "Llama 3.3"
          contextWindow: 8192
          maxTokens: 81920
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }
```

**Notes:**  
- Clawd recommends at least **64k context** for Ollama when possible.  
- List models: `ollama list`, `moltbot models list`.

---

## 4. Proactive behavior: screen Fiverr and report

Use Clawd’s **cron** to run a scheduled agent turn that “screens” Fiverr (e.g. search or fetch public gigs) and **reports** the result to you (e.g. Telegram).

### 4.1 Cron job (isolated session + delivery)

**Recurring “Fiverr screen” job** — runs in an **isolated** session (no main chat clutter), then delivers the reply to a channel:

```bash
moltbot cron add \
  --name "Fiverr screen" \
  --cron "0 */6 * * *" \
  --tz "America/Los_Angeles" \
  --session isolated \
  --message "Use web search or web fetch to find current Fiverr gigs (e.g. 'writing', 'logo design', 'data entry'). Summarize up to 10: title, price, link. Report in a short bullet list. Do not log in; use only public pages." \
  --deliver \
  --channel telegram \
  --to "YOUR_CHAT_OR_GROUP_ID"
```

- **Schedule:** `0 */6 * * *` = every 6 hours; adjust to your timezone (`--tz`).
- **Delivery:** Use `--channel telegram` (or `whatsapp`, `discord`, etc.) and `--to <target>`. If you omit `--to`, it can fall back to “last route”.
- **Model:** Uses the agent’s default model (e.g. Ollama). Override per job with `--model "ollama/llama3.3"` if needed.

The agent needs **web** (or **browser**) tool enabled so it can search/fetch; Clawd’s default tool set often includes web. If you use browser for logged-in Fiverr later, you’d configure that separately.

**Browser for Fiverr (local, no paid API):** Use the **browser** tool so the agent can open fiverr.com and read gigs. On Ubuntu, apt `chromium-browser` is often a snap stub Clawd can't launch — install **Google Chrome .deb** on sparky2, then apply config so Clawd uses it headless:
```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb
sudo apt --fix-broken install -y
```
From your PC: `.\scripts\clawd\run_clawd_apply_config.ps1 -Hosts sparky2` (sets browser.enabled, headless, noSandbox, executablePath, and **tools.profile: "full"** so the model gets the full tool set including browser). Then in Chat ask e.g. "Go to fiverr.com and list 5 logo design gigs." See [Browser Linux](https://docs.clawd.bot/tools/browser-linux-troubleshooting).

**If the assistant replies "function definitions do not fully cover" or "function definitions are not suitable for this task"**, the model is not getting (or not using) the browser tool. Do this:

1. **Re-run apply config and restart the gateway** so `tools.profile` is `"full"` and only `sessions_send` is denied:  
   `.\scripts\clawd\run_clawd_apply_config.ps1 -Hosts sparky2`
2. **Confirm config on sparky2:**  
   `.\scripts\clawd\run_clawd_config_get.ps1 -Target sparky2` — look for `"tools": { "profile": "full", "deny": ["sessions_send", "message"] }` and `"browser": { "enabled": true, ... }`.
3. **Check gateway log for browser errors:**  
   `.\scripts\clawd\run_clawd_logs.ps1 -Target sparky2` — if you see "Failed to start Chrome CDP" or similar, fix Chrome path / install (see Browser Linux troubleshooting above).

**Still getting "function definitions are not suitable"?** Do this in order:

1. **Confirm you re-ran apply config after the latest script change** (the one that set `tools.profile: "full"` and removed `tools.allow`). From repo root:  
   `.\scripts\clawd\run_clawd_apply_config.ps1 -Hosts sparky2`  
   Ensure the run finishes and says "Config applied + gateway restarted".
2. **Verify config on sparky2:**  
   `.\scripts\clawd\run_clawd_config_get.ps1 -Target sparky2`  
   You should see `"tools": { "profile": "full", "deny": ["sessions_send", "message"] }` and no `"allow"` array, and `"browser": { "enabled": true, "executablePath": "/usr/bin/google-chrome-stable", ... }`. If you still see `"allow": ["browser", ...]` or no `"profile": "full"`, the updated script wasn’t applied — re-copy/run the apply script from the repo that has the latest changes. If the gateway was already running and didn't restart, SSH to sparky2 and run: `clawdbot gateway stop; sleep 2; OLLAMA_API_KEY=ollama-local nohup clawdbot gateway >> ~/.clawdbot/gateway.log 2>&1 &` so the new config is loaded.
3. **Check if the browser actually starts on sparky2.** SSH to sparky2 and run:  
   `curl -s http://127.0.0.1:18791/ | head -5`  
   (18791 is the default browser control port; see Clawd docs if different.) If the gateway hasn’t started the browser yet, send a chat message that uses the browser, then run:  
   `tail -100 ~/.clawdbot/gateway.log`  
   Look for "Failed to start Chrome CDP" or "Chrome" / "browser" errors. If Chrome fails to start, the browser tool won’t be in the schema and the model can reply with "function definitions not suitable".
4. **Try a different Ollama model.** The phrase "function definitions are not suitable" or "functions are insufficient" is almost certainly **from the model** (e.g. llama3.3), not from Clawd. Some models are better at tool use. On sparky2:  
   `ollama pull qwen2.5-coder:32b`  
   Then patch config with that model and restart: from your PC run `.\scripts\clawd\run_clawd_do_all.ps1 -Target sparky2 -PrimaryModel ollama/qwen2.5-coder:32b` (or set primary in Control UI and restart the gateway), then try the Fiverr prompt again.

**Browser tool: "functions are insufficient" checklist**

- **Config:** Ensure `tools.profile: "full"` and `browser.executablePath` set (Chrome or chromium-browser). Run `.\scripts\clawd\run_clawd_do_all.ps1 -Target sparky2` to patch config and restart the gateway.
- **Chrome:** For reliable browser automation, install Google Chrome .deb on sparky2 (sudo required): `wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && sudo dpkg -i google-chrome-stable_current_amd64.deb && sudo apt --fix-broken install -y`. Then re-run the patch so `executablePath` becomes `/usr/bin/google-chrome-stable`.
- **Model:** If llama3.3 keeps refusing, use a model with better tool use: `ollama pull qwen2.5-coder:32b` on sparky2, then `.\scripts\clawd\run_clawd_do_all.ps1 -Target sparky2 -PrimaryModel ollama/qwen2.5-coder:32b`.

**If the assistant replies "Your input is lacking necessary details"** instead of using the browser, the model has the tools but is being cautious. Use a more explicit prompt so it goes ahead and uses the browser, for example:

- *"Use the browser tool: open https://www.fiverr.com, go to the logo design category or search for 'logo design', then list 5 gigs with title and price. You have the browser tool available—please use it now."*

Or break it into steps: first *"Open fiverr.com in the browser"*, then *"List 5 logo design gigs with title and price from this page."*

**Assistant outputs a plan (JSON tool calls) but doesn't execute them and doesn't complete the task**

**Still seeing this?** The assistant shows JSON like `{"name": "browser", "arguments": {"action": "open", "url": "…"}}` but nothing runs. That means the **gateway is not sending tool definitions** to the model (or the model is replying with text instead of `tool_calls`). The **only fix** is to run a gateway build that includes [PR #4287](https://github.com/openclaw/openclaw/pull/4287). Stock Clawd rejects that key; our scripts no longer add it. When you have a gateway with PR #4287, add `compat.openaiCompletionsTools` manually; until then, tool calls will not execute. Check: (1) Which OpenClaw/clawdbot version is installed on sparky2? (2) If it's a stock npm install, it almost certainly does **not** have PR #4287. You must [apply the PR diff](https://github.com/openclaw/openclaw/pull/4287.diff) to an OpenClaw clone, build, and install that build on sparky2 — or use a fork/release that includes it. Until then, tool calls will not execute.

Clawd's [agent loop](https://docs.clawd.bot/concepts/agent-loop) is designed to run **autonomously** until the task is done: the model can call tools → the gateway executes them and returns results → the model continues (calls more tools or replies with the final answer). So in theory the assistant should open Fiverr, search, extract gigs, and then reply with "Here are 5 gigs: …" in one run.

If you see the assistant **output a list of JSON objects** (e.g. `{"name": "browser", "arguments": {"action": "open", "url": "…"}}`) as its **message** and then **stop**, that usually means:

1. **Tool calls as text, not as structured tool_calls** — The model is emitting the tool "plan" as **plain text** (content of the assistant message) instead of using the API's **tool_calls** format. The gateway only **executes** structured tool_calls; it does not parse JSON from the message content. So the run ends after one turn with no execution.
2. **Ollama tool format** — Some Ollama models expose tool use in a different way than OpenAI-style `tool_calls`. If the gateway expects one format and the model returns another, tool execution may not happen. This is a known class of issue with local models and Clawd.

**What to do:**

- **Check logs** — After sending the Fiverr message, check whether the gateway actually ran any tools. On sparky2:  
  `tail -100 /tmp/clawdbot/clawdbot-$(date +%Y-%m-%d).log`  
  and look for `tool` or `browser` or `tool_call` events. If there are **no** tool events, the model did not send structured tool_calls.
- **Prompt the flow** — Ask the model to **use** the browser step by step in natural language, e.g.: *"First use the browser tool to navigate to https://www.fiverr.com. After you get the result, use the browser again to take a snapshot and find the search box, then type 'logo design' and run the search. Then list 5 gigs with title and price."* Sometimes prompting one step at a time (and waiting for the result) can help the model emit real tool_calls instead of a text plan.
- **Clawd browser API** — The browser tool in Clawd uses actions like `navigate`, `snapshot`, `act` (click, type, etc.), not arbitrary names like `input`/`wait_for_element`/`extract_elements`. If the model is "planning" with a different API in mind, it may still be outputting text. Pointing the model at [Browser (Clawd)](https://docs.clawd.bot/tools#browser) and asking it to use **only** those actions can help.
- **Report** — If the model and config are correct but tool_calls never run, report to Clawd/Moltbot (version, model name e.g. `ollama/qwen2.5-coder:32b`, and that you see a JSON plan in the message but no tool execution in the log).

**What syntax Clawd needs, and where the fix is (leverage point)**

Clawd expects **OpenAI-style tool_calls**:

- **Request:** The model must receive a `tools` array in the API request, e.g. `[{ "type": "function", "function": { "name": "browser", "description": "...", "parameters": { ... } } }]`. Optional `tool_choice: "auto"`.
- **Response:** The gateway only **executes** when the model returns a `tool_calls` array in the message, e.g. `message.tool_calls = [{ "id": "...", "type": "function", "function": { "name": "browser", "arguments": "{\"action\":\"navigate\",\"url\":\"...\"}" } }]`. (`arguments` is typically a JSON **string** in OpenAI/Ollama.)

**Ollama** can produce that: its [chat API](https://docs.ollama.com/api/chat) accepts a `tools` parameter and returns `message.tool_calls` with `function.name` and `function.arguments`. So Ollama is not the blocker.

**The actual blocker:** Our Ollama provider is configured with `api: "openai-completions"`. In that mode, **Clawd/Moltbot does not send tool definitions to the model** (known bug: [clawdbot/clawdbot #1866](https://github.com/clawdbot/clawdbot/issues/1866) — open Jan 2026; no config workaround; [Clawd Ollama docs](https://docs.clawd.bot/providers/ollama) don’t document tool routing for this API). So Ollama never gets `tools` in the request → the model has no tool schema → it can only reply with text (e.g. a JSON “plan”). The gateway never sees `tool_calls` in the response because the model was never asked to use tools in the first place.

**Leverage point:** The fix is in **Clawd/Moltbot**, not in Ollama or in our config. Options:

1. **Upvote / comment on [clawdbot/clawdbot #1866](https://github.com/clawdbot/clawdbot/issues/1866)** — “Add tool calling support for openai-completions API mode.” Request that when using Ollama (or any openai-completions provider), the gateway (a) includes `tools` in the request to the model, and (b) parses `tool_calls` from the response. That would enable Ollama + browser automation.
2. **jokelord patch (community, tested):** [jokelord/openclaw-local-model-tool-calling-patch](https://github.com/jokelord/openclaw-local-model-tool-calling-patch) — Enables tool calling for `openai-completions` by adding `compat.supportedParameters: ["tools", "tool_choice"]` to the schema and using it in the gateway so tools are sent when the model declares support. **Steps:** (1) Clone Clawdbot source (same version as installed, e.g. 2026.1.24), (2) apply the patch (4 files: `zod-schema.core.ts`, `types.models.ts`, `model-compat.ts`, `attempt.ts` — see the repo README for copy-paste snippets), (3) build and install on sparky2 (`npm run build`, `sudo npm install -g .`), (4) add to each Ollama model in `~/.clawdbot/clawdbot.json`: `"compat": { "supportedParameters": ["tools", "tool_choice"] }`, (5) restart the gateway. The patch was verified with sglang/vLLM; **Ollama** also accepts `tools` and returns `tool_calls`, so the same patch works with Ollama once applied. No need for sglang/vLLM tool-call-parser when using Ollama directly.
3. **PR #4287 (openclaw):** [openclaw/openclaw PR #4287](https://github.com/openclaw/openclaw/pull/4287) — Alternative fix using `compat.openaiCompletionsTools: true`. If that PR is merged or you apply its diff, use that config instead. Our scripts do not set compat (stock Clawd rejects it). When you have a gateway build that includes PR #4287, add the key manually to Ollama model entries.
4. **Watch for a new API mode** — The issue suggests a mode like `openai-chat-with-tools` that uses `/v1/chat/completions`, sends tools, and parses tool_calls. If that lands, we could set `models.providers.ollama.api` to that value (and restart the gateway).
5. **Until then** — Use a cloud provider (OpenAI, Anthropic, etc.) for tool-heavy tasks, or run the Fiverr-style task outside Clawd (e.g. script or another client that calls Ollama with `tools` and handles `tool_calls`).

**If PR #4287 was closed/reverted:** Get the patch from [PR #4287 diff](https://github.com/openclaw/openclaw/pull/4287.diff). It touches: `src/agents/pi-embedded-runner/tool-split.ts`, `run/attempt.ts`, `compact.ts`, `src/config/types.models.ts`, `zod-schema.core.ts`, and docs. Cherry-pick the PR branch or apply the diff to your OpenClaw clone, then build and install that build on sparky2. Add compat.openaiCompletionsTools manually to model entries when your gateway supports it.

**From your dev machine (after onboarding + Telegram channel):** Use the helper script to add the cron on sparky1:

```powershell
.\scripts\clawd\add_fiverr_cron.ps1 -TelegramChatId "YOUR_CHAT_OR_GROUP_ID"
# Or -Host sparky2 if the gateway runs there
```

Without `-TelegramChatId` the script prints the exact command to run on the host.

**One-shot test (run once in ~1 minute):**

```bash
moltbot cron add \
  --name "Fiverr screen test" \
  --every "60000" \
  --session isolated \
  --message "Search the web for 3 Fiverr gigs about 'blog writing'. List title, price, and link." \
  --deliver \
  --channel telegram \
  --to "YOUR_CHAT_ID" \
  --delete-after-run
```

Cron docs: [Cron jobs](https://docs.clawd.bot/automation/cron-jobs), [CLI cron](https://docs.clawd.bot/cli/cron).

### 4.2 Include AI Village backend in the report (optional)

To have Clawd also report **open jobs** from our backend (e.g. “Fiverr screen + open jobs”):

- Give the agent a way to call the backend: e.g. **HTTP tool** (if available in your Clawd setup) or **exec** (e.g. `curl http://sparky1:8000/jobs?status=open`).
- In the same cron **message**, ask the agent to: (1) run the Fiverr screen, (2) call the backend (or run the curl command), (3) summarize both in one report.

Example prompt addition:

```text
Also run: curl -s http://sparky1:8000/jobs?status=open (or the appropriate backend URL). Include a one-line summary of how many open jobs exist and their titles.
```

You can later replace this with a proper **skill** or **webhook** that calls `GET /jobs` and formats the result.

---

## 5. Where this fits in the stack

| Component        | Role |
|-----------------|------|
| **Backend**     | Source of truth for jobs, agents, ai$ (unchanged). |
| **agent_1 / agent_2** | Proposer/executor; discover and do work (unchanged). |
| **Clawd**       | Operator interface (chat), optional automation (cron), and future order ingestion/delivery via browser or skills. |
| **Ollama**      | Shared LLM for both agents and Clawd on the same host. |

Clawd does **not** replace the backend; it sits in front of it for human-in-the-loop and proactive tasks (e.g. Fiverr screening, later: “new order → create job”, “approved job → deliver to Fiverr”). See [ROADMAP_REAL_MONEY.md](../../roadmaps/ROADMAP_REAL_MONEY.md#could-clawd-moltbot-help-clawdbot--moltbot) for the bigger picture.

---

## 6. Quick reference

| Task | On sparky (repo on sparky) | From Windows dev (Option B) |
|------|----------------------------|-----------------------------|
| Install | `bash scripts/clawd/install_clawd_on_sparky.sh` | `.\scripts\clawd\run_install_clawd.ps1` |
| Prep | `bash scripts/clawd/clawd_prepare_on_sparky.sh` | `.\scripts\clawd\run_clawd_prepare.ps1` |
| Restart gateway | `bash scripts/clawd/start_clawd_gateway.sh` | `.\scripts\clawd\run_start_clawd_gateway.ps1` |
| Onboard + daemon | `clawdbot onboard --install-daemon` (interactive) | same: SSH to host, then run that |
| Status | (see gateway.log, `clawdbot status`) | `.\scripts\clawd\clawd_status.ps1` |
| Apply config + restart | (edit JSON on host, then restart) | `.\scripts\clawd\run_clawd_apply_config.ps1` |
| Gateway log | `tail ~/.clawdbot/gateway.log` on host | `.\scripts\clawd\run_clawd_logs.ps1` |
| Show config | `cat ~/.clawdbot/clawdbot.json` on host | `.\scripts\clawd\run_clawd_config_get.ps1` |
| **Show model** (config + running) | — | `.\scripts\clawd\run_clawd_show_model.ps1` or `-Target sparky2` |
| Fiverr cron | (run `moltbot cron add ...` on host) | `.\scripts\clawd\add_fiverr_cron.ps1 -TelegramChatId YOUR_CHAT_ID` |
| Ollama | `export OLLAMA_API_KEY=ollama-local`; use `ollama/<model>` in agent config | — |
| Cron list | `moltbot cron list` or `clawdbot cron list` | — |
| Cron run now | `moltbot cron run <jobId> --force` | — |
| Docs | [docs.clawd.bot](https://docs.clawd.bot) — Install, Ollama, Cron, Channels | — |
| Moltbook (agent social network) | Register, claim, then use API with saved key; optional skill in `~/.moltbot/skills/moltbook` | See [MOLTBOOK_SPARKY.md](../moltbook/MOLTBOOK_SPARKY.md) |

---

## 6.1 Chat in the browser (Control UI) from your PC

If the **TUI** has display bugs (reply only after restart, "Cannot read properties of undefined"), use the **Control UI** in a browser instead. It's a separate web app served by the gateway and may not hit the same bugs.

**On your Cursor computer (Windows):**

1. **Open an SSH tunnel** to the sparky where the gateway runs (e.g. sparky2):
   ```powershell
   ssh -N -L 18789:127.0.0.1:18789 malicor@sparky2
   ```
   Leave this running (no output is normal).

2. **In your browser** open: [http://127.0.0.1:18789/](http://127.0.0.1:18789/)

3. **Paste the gateway token** when the UI asks. On sparky2:
   ```bash
   grep -A1 '"auth"' ~/.clawdbot/clawdbot.json
   ```
   Use the value of `"token"` (e.g. `5d670845a55742a4137a0ab996966718e22cf71449e4fc1d`).

4. Open the **Chat** tab and send messages. Same sessions and agent as the TUI, different UI.

See [Control UI](https://docs.clawd.bot/web/control-ui) and [Remote](https://docs.clawd.bot/gateway/remote).

**Control UI: "gateway token mismatch"**

- **SSH tunnel must be running** on your PC: leave a terminal open with `ssh -N -L 18789:127.0.0.1:18789 malicor@sparky2`. If the tunnel is closed, the browser may hit nothing or another process on port 18789.
- **Restart the gateway on sparky2** so it reloads the token from `clawdbot.json`: `ssh sparky2 'bash ~/bin/start_clawd_gateway.sh'`. Then open the tokenized URL again.
- **Nothing else on your PC** should be using port 18789 (e.g. another Clawd gateway). On Windows: `netstat -ano | findstr 18789` — you want only the SSH client.

**If the Control UI from your PC keeps failing with token mismatch**, use it **directly on the sparky**: SSH to sparky2, open a browser there, and go to `http://127.0.0.1:18789/` (paste the token when asked). Same Chat and sessions, no tunnel needed.

---

## 7. Troubleshooting: TUI shows “tokens 0” and no response

If `clawdbot tui` is **connected** but **no tokens** are generated when you send a message (status stays “tokens 0/200k”), the gateway is not calling Ollama. Do the following on the host where the TUI runs (e.g. sparky1).

### 7.1 Restart the gateway with OLLAMA_API_KEY

The gateway process must have `OLLAMA_API_KEY` in its environment. If you started it with plain `clawdbot gateway` from a shell that didn’t have the variable, it won’t use Ollama.

**From your dev machine:**

```powershell
.\scripts\clawd\run_start_clawd_gateway.ps1
```

This copies and runs `start_clawd_gateway.sh` on both sparkies, which stops the gateway, sets `OLLAMA_API_KEY=ollama-local`, and starts it again.

**Or on the host (sparky1/sparky2):**

```bash
source ~/.bashrc   # so OLLAMA_API_KEY is set
# If you ran clawd_prepare_on_sparky.sh from the repo, the script was copied to ~/bin:
bash ~/bin/start_clawd_gateway.sh
# Or from repo: bash ~/ai_ai2ai/scripts/clawd/start_clawd_gateway.sh  (use your repo path)
# Or manually:
clawdbot gateway stop 2>/dev/null; sleep 2
export OLLAMA_API_KEY=ollama-local
nohup clawdbot gateway >> ~/.clawdbot/gateway.log 2>&1 &
```

Then try TUI again: `clawdbot tui` and send a message.

### 7.2 Confirm Ollama is running and the model is available

On the host:

```bash
curl -s http://127.0.0.1:11434/api/tags
ollama list
```

If Ollama isn’t running, start it (e.g. `ollama serve` in the background or your usual service). Ensure the model you use in Clawd (e.g. `llama3.1:70b`) is pulled: `ollama pull llama3.1:70b`.

### 7.3 Confirm Clawd sees the Ollama model

Clawd **auto-discovers** only models that report **tool support** from Ollama. If your model doesn’t report tools, it won’t appear in the catalog and the gateway won’t use it.

On the host (with `OLLAMA_API_KEY` set, e.g. after `source ~/.bashrc`):

```bash
clawdbot models list
```

If `ollama/llama3.1:70b` (or your primary model) is **not** listed:

- Either switch to a tool-capable model, e.g. `clawdbot config set agents.defaults.model.primary "ollama/llama3.3"` and `ollama pull llama3.3`, or  
- Define the model explicitly so Clawd doesn’t rely on auto-discovery: see [Ollama provider — Explicit setup](https://docs.clawd.bot/providers/ollama) and add `models.providers.ollama` with your model in `~/.clawdbot/clawdbot.json`.

### 7.4 Check gateway logs

On the host:

```bash
tail -50 ~/.clawdbot/gateway.log
```

Look for errors when you send a message in TUI (e.g. connection refused to Ollama, or “model not found”).

### 7.5 Control UI / Chat: assistant shows **no response at all** (empty message bubble)

If the assistant's reply is **completely empty** (no text, no "thinking"), the gateway is likely using a **primary model that isn't in the Clawd models list**. The run finishes in a few ms and returns nothing.

**Fix:**

1. **Use a model that's in the list**  
   From your PC:  
   `.\scripts\clawd\run_clawd_do_all.ps1 -Target sparky2 -PrimaryModel ollama/llama3.3:latest`  
   This sets primary to `ollama/llama3.3:latest` (which Clawd already knows from Ollama) and restarts the gateway. Retry your message.

2. **If you want qwen2.5-coder:32b**  
   On sparky2: `ollama pull qwen2.5-coder:32b`.  
   Then from your PC: `.\scripts\clawd\run_clawd_do_all.ps1 -Target sparky2 -PrimaryModel ollama/qwen2.5-coder:32b`.  
   The patch script adds that model to the config list; if Clawd later overwrites the list from Ollama discovery, ensure the model is tool-capable and appears in `clawdbot models list` on the host.

**Check:** `.\scripts\clawd\run_clawd_config_get.ps1 -Target sparky2` — under `models.providers.ollama.models` you should see an entry whose `id` matches the model name in `agents.defaults.model.primary` (e.g. `llama3.3:latest` or `qwen2.5-coder:32b`).

---

## 9. Troubleshooting: TUI shows raw tool output instead of natural reply

If the TUI shows **token usage** (e.g. 4k/131k) but the "reply" is **raw tool JSON** (e.g. `<|python_tag|>{"type": "function", "name": "sessions_send", ...}`) or "(no output)", the model is **using the session tool to "send" its reply** instead of outputting plain text.

### How Clawd is meant to work

- **Normal flow:** You send a message → the model **outputs assistant text** → the TUI shows that text (and optionally tool cards for real tool use).
- **Session tools** (`sessions_send`, `sessions_list`, etc.) are for **sending to *other* sessions** (e.g. another chat or cron), not for replying in the *current* TUI session.
- When the model is given `sessions_send`, some models (e.g. llama3.1:70b) may **over-use it** and "reply" by calling `sessions_send` with a short `message` (e.g. `"I"`) instead of writing natural language. The TUI then shows the **tool call** as a card (or raw tag), not as the assistant message.

### Is our clawdbot.json correct?

**Yes.** The block we write in `clawd_prepare_on_sparky.sh` is valid:

- `models.providers.ollama` with `baseUrl`, `apiKey`, and a `models` array matches [Clawd's Ollama provider](https://docs.clawd.bot/providers/ollama) and validation.
- We do **not** set `tools` there; the agent gets the **default tool set** (typically full), which includes `sessions_send`. You must run the apply script so the config gets `tools.deny: ["sessions_send", "message"]`; otherwise the mistake is **not** in the Ollama block—it's that the **model** is choosing to reply via a tool instead of text.

### What to do

1. **Restrict session tools for chat-only use**  
   So the model can't call `sessions_send` and must reply with text. In `~/.clawdbot/clawdbot.json` (on the host), add under the top-level object:

   ```json
   "tools": {
     "profile": "full",
     "deny": ["sessions_send", "message"]
   }
   ```

   The apply script does this for you: run `.\scripts\clawd\run_clawd_apply_config.ps1 -Hosts sparky2` from your PC (or on sparky2: `bash /path/to/clawd_apply_config_remote.sh`), then restart the gateway. Adding **"message"** to deny stops the model from "replying" via a fake `message` tool (which shows as raw JSON like `{"name": "message", "arguments": {"message": "Hi! ..."}}`).

   Or use a minimal tool profile (only `session_status`):

   ```json
   "tools": {
     "profile": "minimal"
   }
   ```

   Then restart the gateway and try TUI again. See [Tools – Disabling tools](https://docs.clawd.bot/tools#disabling-tools) and [Tool profiles](https://docs.clawd.bot/tools#tool-profiles-base-allowlist).

2. **Try a different Ollama model**  
   Some models follow "reply with text" better. For example: `ollama pull llama3.3` and set primary to `ollama/llama3.3`.

3. **Update Clawd/Moltbot**  
   Newer versions may improve tool handling or TUI rendering of tool results; run `clawdbot update` (or re-run the installer) and retest.

### 8.1 TUI: reply only shows after Ctrl-C and restarting TUI

With Clawd 2026.1.24-3 and Ollama (e.g. llama3.3:latest), the TUI may **not redraw** when the model streams or finishes a reply: the footer shows tokens (e.g. 4.1k/131k) but the message area stays empty until you **Ctrl-C and run `clawdbot tui` again**, at which point the reply appears (loaded from history). This is a **display/streaming bug** in the TUI, not a gateway or config issue.

**Workaround:** After sending a message, if nothing appears, exit the TUI (Ctrl-C) and start it again to see the reply in history.

**Also seen:** `Cannot read properties of undefined (reading 'includes')` when the first message is rendered; adding `"tools": { "profile": "full", "deny": ["sessions_send", "message"] }` can avoid some code paths that hit undefined. Report both behaviors to Clawd/Moltbot (version + TUI) so they can fix the redraw and guard the `.includes()` call.
