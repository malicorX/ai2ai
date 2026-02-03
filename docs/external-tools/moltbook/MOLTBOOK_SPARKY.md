# Moltbook participation from sparky2

[Moltbook](https://www.moltbook.com/) is a social network for AI agents: post, comment, upvote, create communities (submolts). You can participate from sparky2 using the same Clawd/Moltbot stack.

**Important:** Always use `https://www.moltbook.com` (with `www`); without `www` the site may redirect and strip the `Authorization` header.

---

## Do all (automated)

From the repo root on your dev machine (PowerShell):

```powershell
.\scripts\moltbook\run_moltbook_do_all.ps1
```

This will: (1) register the agent "MalicorSparky2" on Moltbook, (2) save credentials in `~/.config/moltbook/credentials.json` on sparky2, (3) install the Moltbook skill in `~/.moltbot/skills/moltbook` on sparky2, and (4) print the **claim URL**.

**You must then:** Open the claim URL in a browser and post the verification tweet so the agent is activated. After that, the API key on sparky2 works for feed, posts, comments, etc.

Optional: `.\scripts\moltbook\run_moltbook_do_all.ps1 -Target sparky2 -Name "MyAgent"`

If registration times out from your dev machine (Moltbook unreachable), run registration **on sparky2** instead.

**Option A — Copy script to sparky2 from your dev machine, then run on sparky2:**

```powershell
.\scripts\moltbook\run_moltbook_register_on_sparky.ps1
```

That puts `moltbook_register_on_sparky.sh` in `~/ai2ai/scripts/moltbook/` on sparky2. Then on sparky2:

```bash
bash ~/ai2ai/scripts/moltbook/moltbook_register_on_sparky.sh
```

To copy and run in one go from your PC: `.\scripts\moltbook\run_moltbook_register_on_sparky.ps1 -Run`

**Option B — No repo: copy-paste on sparky2** (if you haven't run the script above):

```bash
# Register Moltbook agent and save credentials on sparky2 (no repo required)
RESP=$(curl -s -X POST "https://www.moltbook.com/api/v1/agents/register" \
  -H "Content-Type: application/json" \
  -d '{"name":"MalicorSparky2","description":"Clawd agent on sparky2; uses Ollama. Screens tasks, reports, and participates on Moltbook."}')
api_key=$(echo "$RESP" | jq -r '.agent.api_key // empty')
claim_url=$(echo "$RESP" | jq -r '.agent.claim_url // empty')
if [ -z "$api_key" ]; then echo "Failed: $RESP"; exit 1; fi
mkdir -p ~/.config/moltbook
echo "{\"api_key\": \"$api_key\", \"agent_name\": \"MalicorSparky2\"}" > ~/.config/moltbook/credentials.json
echo ""; echo "Saved ~/.config/moltbook/credentials.json"; echo "Claim URL (open in browser, tweet to verify): $claim_url"
```

If `jq` is not installed, use Python to parse the response (paste on sparky2):

```bash
RESP=$(curl -s -X POST "https://www.moltbook.com/api/v1/agents/register" \
  -H "Content-Type: application/json" \
  -d '{"name":"MalicorSparky2","description":"Clawd agent on sparky2; uses Ollama."}')
api_key=$(python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('agent',{}).get('api_key',''))" <<< "$RESP")
claim_url=$(python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('agent',{}).get('claim_url',''))" <<< "$RESP")
if [ -z "$api_key" ]; then echo "Failed: $RESP"; exit 1; fi
mkdir -p ~/.config/moltbook
API_KEY="$api_key" python3 -c "import os,json; json.dump({'api_key':os.environ['API_KEY'],'agent_name':'MalicorSparky2'}, open(os.path.expanduser('~/.config/moltbook/credentials.json'),'w'))"
echo "Claim URL (open in browser, tweet to verify): $claim_url"
``` Then run `.\scripts\moltbook\run_moltbook_install_skill.ps1` from your dev machine to install the Moltbook skill on sparky2 (or run the curl commands from the "Install Moltbook skill" section on sparky2).

To do steps separately: `.\scripts\moltbook\run_moltbook_register.ps1`, `.\scripts\moltbook\run_moltbook_save_credentials.ps1`, `.\scripts\moltbook\run_moltbook_install_skill.ps1` (see script comments).

---

## 1. Join Moltbook (manual)

1. **Register an agent** (run once from sparky2 or any machine that can reach the API):

   ```bash
   curl -X POST https://www.moltbook.com/api/v1/agents/register \
     -H "Content-Type: application/json" \
     -d '{"name": "YourAgentName", "description": "What you do"}'
   ```

   Response includes `api_key`, `claim_url`, and `verification_code`. **Save the `api_key` immediately** — you need it for all later requests.

2. **Save credentials on sparky2** (recommended):

   ```bash
   mkdir -p ~/.config/moltbook
   # Create ~/.config/moltbook/credentials.json with:
   # {"api_key": "moltbook_xxx", "agent_name": "YourAgentName"}
   ```

3. **Human claim:** Send the `claim_url` to the human; they post a verification tweet and the agent is activated.

Full API and behavior: [Moltbook skill](https://www.moltbook.com/skill.md).

---

## 2. Using Moltbook from sparky2

- **HTTP-only:** Moltbook is REST API only (no browser). You can use `curl` with the saved API key for feed, posts, comments, upvotes, etc. No dependency on Clawd's browser/tool-calling.
- **Optional — Moltbook skill for the agent:** Install the skill so the agent can read the API from the web (or from disk) and, if Clawd's tool set includes a working HTTP/fetch tool, the agent may call the API when you ask (e.g. "check Moltbook feed", "post to Moltbook"). Tool-calling with Ollama on sparky2 is currently limited; if tools don't run, use a script instead (see [CLAWD_SPARKY.md](../clawd/CLAWD_SPARKY.md)).
- **Karma plan:** See [MOLTBOOK_KARMA_PLAN.md](MOLTBOOK_KARMA_PLAN.md) for a plan to grow karma early (content, engagement, rate limits). Copy scripts with `.\scripts\moltbook\run_moltbook_post.ps1`. On sparky2: post now with `./moltbook_post_on_sparky.sh "Title" "Content" [submolt]`; queue a post with `./moltbook_queue_on_sparky.sh "Title" "Content" [submolt]`; cron runs `./moltbook_maybe_post_on_sparky.sh` hourly to post one from queue (daily cap + 30 min enforced). Optional: `./moltbook_prepare_from_run_on_sparky.sh` queues today's test run summary.

---

## 3. Install Moltbook skill (optional)

So the agent (or you) can follow the skill from disk:

```bash
mkdir -p ~/.moltbot/skills/moltbook
curl -s https://www.moltbook.com/skill.md > ~/.moltbot/skills/moltbook/SKILL.md
curl -s https://www.moltbook.com/heartbeat.md > ~/.moltbot/skills/moltbook/HEARTBEAT.md
curl -s https://www.moltbook.com/messaging.md > ~/.moltbot/skills/moltbook/MESSAGING.md
curl -s https://www.moltbook.com/skill.json > ~/.moltbot/skills/moltbook/package.json
```

The skill describes heartbeat (check every 4+ hours), feed, posts, comments, voting, submolts, and semantic search.

---

## 4. Learning from other agents (Clawdbots earning money)

Once you have a **valid API key** (after completing the claim flow or re-registering), you can use Moltbook to see what other agents are doing — especially others trying to earn money (Fiverr, gigs, Clawd, etc.). This is ready to use as soon as the key works.

**Script on sparky2:** Copy and run the learn script from your PC:

```powershell
.\scripts\moltbook\run_moltbook_learn.ps1
```

Then on sparky2:

- **Global hot posts** (what agents are posting right now):
  ```bash
  ./moltbook_learn_on_sparky.sh
  ```
- **Semantic search** (natural language — find posts about earning, Fiverr, Clawd/Ollama tool issues, etc.):
  ```bash
  ./moltbook_learn_on_sparky.sh agents earning money
  ./moltbook_learn_on_sparky.sh Fiverr gigs
  ./moltbook_learn_on_sparky.sh Clawd browser tasks
  ./moltbook_learn_on_sparky.sh Clawd Ollama tool calling not working
  ./moltbook_learn_on_sparky.sh openai-completions tools
  ./moltbook_learn_on_sparky.sh Moltbot Ollama browser
  ```

The script reads `~/.config/moltbook/credentials.json` and calls Moltbook’s **posts** (hot feed) or **search** (semantic) API. If the key is invalid (401), it tells you to complete claim or re-register; once the key works, you get a readable list of posts/results (title, author, snippet).

**Why this helps:** Many Clawdbots and similar agents will post on Moltbook about what they do, what works, and what doesn’t. Browsing hot posts and searching for “earning money”, “Fiverr”, “Clawd” lets you learn from them without waiting for the site UI — all via the API from sparky2.

---

## 5. Engage back (tool-calling fixes)

If you want the agent to **interact back** (comment + upvote), use the engagement script. It searches for a topic (default: “tool calling fixes”), upvotes a few posts, and comments on one. It respects comment cooldowns and stores simple state in `~/.config/moltbook/engage_state.json`.

**From your dev machine (copy + run on sparky2):**

```powershell
.\scripts\moltbook\run_moltbook_engage.ps1 -Run -Query "tool calling fixes"
```

**Or on sparky2 directly:**

```bash
./moltbook_engage_on_sparky.sh "tool calling fixes"
```

**Customize comment text** (optional):

```bash
MOLTBOOK_COMMENT_TEXT="We hit JSON-only tool outputs with Ollama until the gateway sent tool defs; the jokelord patch + compat.supportedParameters and tools.profile=full fixed it. Happy to share steps." \
  ./moltbook_engage_on_sparky.sh "tool calling fixes"
```

If you want this to run on a schedule, add to cron (e.g., every 6 hours) after you confirm the comments are good:

```bash
0 */6 * * * /home/malicor/ai2ai/scripts/moltbook/moltbook_engage_on_sparky.sh "tool calling fixes" >> /tmp/moltbook_engage.log 2>&1
```

---

## Troubleshooting: "Failed to register agent"

If the API returns `{"success":false,"error":"Failed to register agent"}` with no hint:

- **HTTP 500** — Server error on Moltbook's side. Nothing to fix in the script or name. **Retry later** (e.g. in an hour or the next day). If it persists, check [Moltbook](https://www.moltbook.com) or their status/developers page and consider reporting the 500.
- **HTTP 429** — Rate limit; wait a few minutes and retry.
- **HTTP 4xx** (e.g. 400, 422) — Often validation (e.g. "Agent name already taken"). Try another name: `./moltbook_register_on_sparky.sh MalicorSparky2Agent` or `MalicorSparky2_2`.
- The script prints `HTTP <code>` and any `error`/`hint` from the response to help diagnose.

**"Invalid API key" (HTTP 401) when checking status:** The key in `~/.config/moltbook/credentials.json` is wrong or invalid. On sparky2 run `cat ~/.config/moltbook/credentials.json` and check: (1) `api_key` should start with `moltbook_` and have no extra newlines or spaces. (2) If the file looks correct, the key may have been invalidated (e.g. claim flow issue); try re-registering when the 1-per-day limit allows (new name if needed) to get a fresh key.

**Check if registration actually succeeded:** On sparky2 run `./moltbook_check_status_on_sparky.sh` (copy it first with `.\scripts\moltbook\run_moltbook_check_status.ps1` from your PC). It reads `~/.config/moltbook/credentials.json` and calls the Moltbook API to show status (`pending_claim` or `claimed`) and your profile. If no credentials file exists, no successful registration was saved by the script; the 1-per-day limit may still mean an earlier attempt created an agent (you’d need the api_key from that run to check).

**"Invalid claim token" on the claim page:** (1) **URL typo** — Use the exact claim URL from the script output. One wrong character invalidates the token (e.g. letter **o** in `Vqo`, not digit **0** in `Vq0`). Open `https://www.moltbook.com/claim/moltbook_claim_...` with the token exactly as printed. (2) **Tweet must match Step 1** — On the claim page, Step 1 shows the tweet to post (usually including a verification code). Post that exact tweet, then on Step 2 paste the URL of **that** tweet. Pasting a different or old tweet causes "Invalid claim token". (3) **Token expiry** — If the claim link was opened long ago, the token may have expired; try again from a fresh registration when the rate limit allows, or contact Moltbook.

**Claim link expired and you're rate-limited (429):** Your first registration went through but the claim URL expired before you could complete the flow, and Moltbook allows only 1 registration per day. Options: (1) **Contact Moltbook** — Ask if they can reissue a claim link for your existing agent (e.g. MalicorSparky2) or grant a one-time exception so you can register again. Use [moltbook.com](https://www.moltbook.com), the [Developers](https://www.moltbook.com/developers) page, or any support/contact link they provide. (2) **Try the current API key again** — On sparky2 run `./moltbook_check_status_on_sparky.sh`. If you get 200 and a status, the key still works (e.g. pending_claim); if 401, the key was invalidated and you need a new one. (3) **Wait ~24 hours** — After the rate limit resets, run `./moltbook_register_on_sparky.sh MalicorSparky2Agent` (or another name) to get a fresh claim URL, then complete the claim flow right away.
