# Moltbook karma plan (MalicorSparky2)

Goal: **Grow karma early** while Moltbook is new (~2 days old) so we have no entrenched leaders yet. Karma = upvotes on your posts and comments; downvotes reduce it. [Top agents](https://www.moltbook.com/u) are ranked by karma — early consistency pays off.

---

## 1. Why now

- **Platform is 2 days old** — No one has a big edge. Leaderboard is still formable.
- **Low volume** — Each quality post gets more visibility than it will in a few weeks.
- **First-mover in niches** — Post useful content about Clawd, Fiverr, Ollama, sparky2; others searching for that will find you and upvote.
- **Reputation carries** — Karma is shown to apps that use "Sign in with Moltbook"; high karma = trust signal later.

---

## 2. Rate limits (stay within them)

From [Moltbook skill](https://www.moltbook.com/skill.md):

| Action        | Limit              | Implication                    |
|---------------|--------------------|--------------------------------|
| Posts         | 1 per 30 minutes   | Max ~48 posts/day; quality > quantity |
| Comments      | 1 per 20 seconds   | Up to 50/day (generous)        |
| Comments/day  | 50 per day         | Use for engagement, not spam   |
| Requests      | 100/minute         | Plenty for feed + post + comment |

**Strategy:** Post at most every 30+ min; comment on a few high-visibility or relevant posts per day; upvote liberally (no limit stated). No farming — community will downvote obvious spam.

---

## 3. Content strategy (what to post)

**Post things others will upvote:**

1. **Useful how-to / learnings**
   - "What we learned running Clawd on sparky2 with Ollama"
   - "Fiverr screening from a Clawd agent: what works, what doesn’t"
   - "Tool-calling and openai-completions: the Moltbot #1866 workaround"
   - Short, concrete, actionable — not manifestos.

2. **Welcome & help new agents**
   - When you see "just claimed" or "first post" — welcome them or offer one concrete tip. They (and lurkers) upvote.

3. **Submolts**
   - Find or create a submolt that fits (e.g. `general`, or create one like `m/clawd` or `m/earning`). Post there so your content is discoverable by topic.

4. **Share results, not vibes**
   - "We ran the hot feed and here are 3 threads worth reading" (with 1-line summaries) — useful, shareable.
   - Avoid low-effort takes; avoid token/coin shilling unless it’s clearly allowed and valuable.

5. **One strong post per day**
   - With 1 post / 30 min you can do ~2–4/day without stress. Prefer **one high-quality post** over many mediocre ones — early feed is small, so one good post can stay visible.

---

## 4. Engagement strategy (comments + upvotes)

- **Comment thoughtfully** on 2–5 posts per day (within 50/day). Pick hot or new posts where your comment adds info (e.g. "We hit the same 401 until we completed the claim — key was using the exact claim URL").
- **Upvote** good posts and comments (no stated limit). Upvoting others increases chance they notice you and reciprocate; it also surfaces good content.
- **Don’t** downvote unless something is clearly bad (spam, abuse). Downvote wars don’t help karma.
- **Follow sparingly** — Moltbook says follow rarely; follow agents whose posts you consistently want in your feed. Being followed back can help visibility.

---

## 5. Automation (heartbeat on sparky2)

**Idea:** A small heartbeat (cron or script run every 4–6 hours) that:

1. **Fetches** hot feed (`./moltbook_learn_on_sparky.sh` or direct `GET /posts?sort=hot`).
2. **Optionally posts** once per run only if we have something new (e.g. "Today’s Fiverr screen summary" or "One thing we learned from the feed"). Enforce 30+ min between posts (store last post time in `~/.config/moltbook/last_post_ts`).
3. **Optionally comments** on 1–2 posts per run (e.g. top hot post we haven’t commented on yet). Keep a simple list of commented post IDs so we don’t double-comment.
4. **Upvotes** a few posts (e.g. top 2–3 from feed) via `POST /posts/POST_ID/upvote`.

**Scripts to add:**

- **`moltbook_post_on_sparky.sh`** — Post one message: `./moltbook_post_on_sparky.sh "Title" "Content" [submolt]` (default submolt `general`). Reads credentials, checks last-post time (skip if < 30 min), POSTs, updates last-post time.
- **`moltbook_heartbeat_on_sparky.sh`** — (Optional) Runs feed fetch, then optionally: post if we have content and 30+ min passed; comment on 1 post; upvote 2–3 posts. Can be called from cron every 4–6 hours.

Start with **manual** posting + commenting until we’re happy with tone and quality; then add the heartbeat so we don’t depend on remembering.

---

## 5a. Where to see your posts

- **Direct link:** The API returns `"url": "/post/<uuid>"`. Open **https://www.moltbook.com** + that path (e.g. `https://www.moltbook.com/post/4093ae1a-a8fa-43bc-920d-cccfeb51130b`).
- **Home / feed:** [https://www.moltbook.com](https://www.moltbook.com) — your post appears in the feed and in submolt `general`.
- **Your profile:** Your agent’s profile page (e.g. agent name link from a post) shows all your posts.

## 5b. Test by hand first

1. **Copy scripts to sparky2** (from your PC): `.\scripts\moltbook\run_moltbook_post.ps1`
2. **On sparky2, post once:** `./moltbook_post_on_sparky.sh "Test post from MalicorSparky2" "Testing the post script. If you see this on Moltbook, it works." general`
3. **Run the cron-style heartbeat:** `./moltbook_cron_post_on_sparky.sh` — posts "MalicorSparky2 heartbeat" + timestamp (or skips with "Rate limit" if < 30 min since last post).
4. **Confirm** the post appears on [moltbook.com](https://www.moltbook.com) or your profile. Then add cron.

## 5c. Add cron job (after hand test works)

**Cron frequency vs posts per day:** The script allows at most 1 post per 30 minutes. The doc recommends **quality over quantity** — “one strong post per day” or 2–4/day with real content, not a fixed “5 per day” target. For a **heartbeat** only: run cron every hour (up to 24 heartbeat posts/day) or **5 times per day** (e.g. 8:00, 12:00, 16:00, 20:00, 00:00) for at most 5 heartbeat posts/day.

On sparky2 run `crontab -e` and add one line:

- **Every hour:** `0 * * * * /home/malicor/ai2ai/scripts/moltbook/moltbook_cron_post_on_sparky.sh >> /tmp/moltbook_cron.log 2>&1`
- **Five times per day (example):** `0 8,12,16,20,0 * * * /home/malicor/ai2ai/scripts/moltbook/moltbook_cron_post_on_sparky.sh >> /tmp/moltbook_cron.log 2>&1`
- **Every 30 min:** `*/30 * * * * /home/malicor/ai2ai/scripts/moltbook/moltbook_cron_post_on_sparky.sh >> /tmp/moltbook_cron.log 2>&1`

Use your actual path if different. Check logs: `tail -f /tmp/moltbook_cron.log`.

## 5d. Meaningful posts = real learnings, not cron-generated variety

**What actually helps other Clawdbots** is real stuff: "We ran Clawd on sparky2 with Ollama — here's what broke and how we fixed it", "Fiverr screening: this prompt worked, that one didn't", "Moltbot + tools: we hit this bug, workaround was X." That comes from real work (a run, a fix, a result), then one post that sums it up. It can't be faked by cron.

**Don't automate "meaningful" with:** pre-written tip pools, LLM-generated summaries, or "best of feed" reposts. That's generated filler — not the concrete learnings others need. It clutters the feed and doesn't build real karma.

**Practical split:**

- **Cron:** Use it for **heartbeat only** (presence check-in). The current `moltbook_cron_post_on_sparky.sh` is fine for that.
- **Meaningful posts:** When something real happens (test run, deployment, bug workaround, Fiverr result), post once — manually or via a script that has the **actual facts** (e.g. "post this run summary" triggered by your pipeline, not by a timer with random/LLM text).

So: cron = heartbeat. Meaningful = event-driven or manual, when you have something real to share.

## 5e. Hourly cron: post only when there is something to post (queue + daily cap)

**Flow:** Cron runs **once per hour**. It (a) checks if we already posted too many times today (daily cap, default 5), (b) checks if there is something in the **queue** to post, (c) checks 30 min since last post. Only if all pass does it post **one** item from the queue. No fixed heartbeat — we only post when there is meaningful content.

**Mechanisms:**

1. **(a) Daily cap:** `~/.config/moltbook/daily_posts` stores how many posts we made today. Max 5/day by default (`MOLTBOOK_MAX_POSTS_PER_DAY`). If at cap, skip.
2. **(b) Meaningful content:** Posts come from a **queue** (`~/.config/moltbook/queue.json`). Add items with `./moltbook_queue_on_sparky.sh "Title" "Content" [submolt]`. Optional: `./moltbook_prepare_from_run_on_sparky.sh` looks for today's test run log and queues one summary (e.g. "Test run YYYY-MM-DD: all passed") — real data.
3. **(c) Prepare and post:** Cron runs `moltbook_prepare_from_run_on_sparky.sh` (optional), then `moltbook_maybe_post_on_sparky.sh` (check cap + 30 min + queue; if OK, post one from queue).

**Scripts:** `moltbook_post_on_sparky.sh` (post now), `moltbook_queue_on_sparky.sh` (add to queue), `moltbook_maybe_post_on_sparky.sh` (cron: check and post one), `moltbook_prepare_from_run_on_sparky.sh` (optional: queue today's run summary), `moltbook_solve_challenge.py` (parse API challenge for auto-verify). Copy with `.\scripts\moltbook\run_moltbook_post.ps1`.

**Verification:** Moltbook’s API often returns `verification_required: true` with a short math challenge. Without verification, posts stay **pending** and don’t appear in the feed. The post script runs `moltbook_solve_challenge.py` on the challenge text and calls `POST /api/v1/verify` so queue/cron posts publish automatically. The solver normalizes obfuscated text (e.g. collapses repeated letters so “thirtty” → “thirty”) and extracts numbers and operations (doubling, multiplied by, etc.). If verification fails, the post remains pending; run `moltbook_verify_on_sparky.sh VERIFICATION_CODE ANSWER` manually. Deploy the solver to sparkies with `.\scripts\moltbook\run_moltbook_post.ps1 -Target sparky1` and `-Target sparky2`.

**Cron (hourly):** `0 * * * * /path/moltbook_prepare_from_run_on_sparky.sh; /path/moltbook_maybe_post_on_sparky.sh >> /tmp/moltbook_cron.log 2>&1`

---

## 6. What not to do

- **Don’t** post more than once per 30 minutes (rate limit).
- **Don’t** comment more than 50/day or in bursts (looks like spam).
- **Don’t** post low-effort or copy-paste content; it gets downvoted and hurts karma.
- **Don’t** farm upvotes (e.g. alt accounts); Moltbook is small and it will be obvious.
- **Don’t** ignore submolts — post in relevant submolts so your content is discoverable.

---

## 7. Weekly cadence (suggested)

| Day   | Focus                                      |
|-------|---------------------------------------------|
| Daily | 1 quality post (if you have something); 2–5 thoughtful comments; upvote 5–10 good posts |
| 1x/wk | Review hot feed and top agents; adjust topics if a niche is underserved |
| 1x/wk | Consider one “summary” post (e.g. “Best of the feed this week” or “3 things we tried”) |

---

## 8. Success metrics

- **Karma** — Check `./moltbook_check_status_on_sparky.sh` or `GET /agents/me`; karma is in the profile.
- **Leaderboard** — [moltbook.com/u](https://www.moltbook.com/u) (Top AI Agents by karma).
- **Visibility** — If your posts get upvotes and thoughtful replies, you’re on track.

Start with **one strong post** (e.g. Clawd + sparky2 + Ollama learnings or Fiverr screening setup), then **comment on 2–3 hot posts** the same day. Repeat daily; add heartbeat once the habit is in place.
