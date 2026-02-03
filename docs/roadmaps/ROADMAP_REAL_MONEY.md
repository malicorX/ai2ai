# Step-by-step plan: from current stage to agents earning real money

This document outlines a concrete path from the current system (agents doing Fiverr-style gigs in a sandbox with ai$) to a setup where agent-delivered work generates real revenue.

---

## Current stage (where we are)

- **Agents:** agent_1 (proposer) and agent_2 (executor) on sparky1/sparky2.
- **Tasks:** Canned gigs (script) or real Fiverr discovery (agent_1 uses web_search + web_fetch to find gigs and create jobs). Executor delivers; proposer (or script) reviews.
- **Economy:** ai$ only (internal ledger). No real money.
- **Clients:** None. Jobs are created by the script or by agent_1 from Fiverr *listings* (we don’t yet fulfill real Fiverr *orders*).

---

## Step 1 — Real platform presence (one agent “seller”)

**Goal:** One real seller account on a freelancing platform (e.g. Fiverr) that can receive real orders from real buyers.

| Action | Details |
|--------|--------|
| 1.1 Create seller account | Register on Fiverr (or Upwork / other) with a clear identity (human or entity that will receive payouts). Use one account per “brand” to start. |
| 1.2 Publish a few gigs | Create 2–5 gigs that match what the executor can already do: e.g. “3 email subject lines for your webinar,” “2-sentence product tagline,” “short social post,” “3-bullet feature list.” Keep scope narrow and deliverable clear. |
| 1.3 Set pricing & delivery time | Set prices (e.g. $5–15) and delivery time (e.g. 24–48 h) so they’re achievable by the current agent flow. |
| 1.4 Document gig IDs / URLs | Record gig titles, URLs, and how they map to our internal task types (e.g. “Email subject” → body template X). |

**Exit criterion:** Real buyers can place orders on the platform; we’re not yet automating fulfillment.

---

## Step 2 — Order ingestion (platform → sparky job)

**Goal:** When a real order comes in on the platform, we create a sparky job and the executor can work on it.

| Action | Details |
|--------|--------|
| 2.1 Choose ingestion method | **Option A:** Manual — we check platform (Fiverr inbox/orders) and create a job via backend API or UI. **Option B:** Fiverr/Upwork API or webhooks (if available) to create jobs automatically. **Option C:** Browser automation (e.g. Playwright) to read “new order” and call our backend to create job. Start with A; move to B/C when stable. |
| 2.2 Define “order → job” mapping | For each order: platform order ID, buyer brief, delivery deadline, price. Map to sparky job: title (e.g. `[archetype:fiverr_order] Order #12345 – Email subject`), body = brief + acceptance criteria + `[verifier:proposer_review]`, reward = internal ai$ (or fixed). |
| 2.3 Create job via API | Backend endpoint or script: given order details, call `POST /jobs/create` with the mapped title/body/reward so the executor sees it as an open job. |
| 2.4 Claim & execute | Executor (agent_2) claims the job, runs `_do_job` (same as today), submits deliverable. Proposer (or human) reviews and approves. |

**Exit criterion:** A real order on the platform results in one sparky job that is claimed, executed, and submitted; deliverable is visible in our system.

---

## Step 3 — Delivery back to platform (submit to buyer)

**Goal:** The agent’s deliverable is sent to the buyer on the platform so they receive the work and can mark the order complete.

| Action | Details |
|--------|--------|
| 3.1 Extract deliverable | From the approved job submission, extract the “EXACT SOLUTION” (deliverable text) — same as we do for test_run today. |
| 3.2 Submit on platform | **Option A:** Manual — copy deliverable into Fiverr “Deliver order” and submit. **Option B:** Platform API (if available) to submit delivery. **Option C:** Browser automation to fill “Deliver order” and submit. Start with A. |
| 3.3 Mark complete in our system | When we deliver on platform, record in backend (e.g. job metadata or a small “orders” table): platform_order_id, delivered_at, status = delivered. |

**Exit criterion:** Buyer receives the deliverable on the platform; they can approve the order and release payment.

---

## Step 4 — Payment receipt (platform payout → us)

**Goal:** When the buyer approves the order, the platform pays us; we record that revenue.

| Action | Details |
|--------|--------|
| 4.1 Payout method | Fiverr (or other) pays out to our linked bank/PayPal according to their schedule. Ensure account is verified and payouts are enabled. |
| 4.2 Record revenue | When payout hits (e.g. weekly): log amount, platform, period. Simple: spreadsheet or a small “payouts” table (date, platform, amount, currency). Optional: credit ai$ to a “treasury” or “operator” agent for compute/entitlements (see ECONOMY.md). |
| 4.3 Reconcile | Periodically match orders delivered → buyer approved → payout. Ensures we’re not missing payments and that disputes/refunds are tracked. |

**Exit criterion:** We can say “this much real money was earned from agent-delivered orders this month.”

---

## Step 5 — Light automation (reduce manual steps)

**Goal:** Minimize manual copy-paste and clicking so more orders can be handled without a human in the loop for every step.

| Action | Details |
|--------|--------|
| 5.1 Automate “new order → create job” | Use platform API or browser automation to detect new orders and call our backend to create the sparky job. Proposer/executor flow unchanged. |
| 5.2 Automate “approved job → deliver to platform” | When a job is approved in our system and tagged as a platform order, run a small script (or backend job) that extracts the deliverable and submits it via API or browser automation. |
| 5.3 Alerts | Notify (e.g. email or chat) if: new order created, job failed/expired, delivery failed, or buyer requested revision. So a human can step in when needed. |

**Exit criterion:** One real order can flow: platform order → sparky job → executor delivers → we deliver to buyer, with only minimal manual checks (e.g. approve delivery before submitting to platform).

---

## Step 6 — Identity, compliance, and risk

**Goal:** Operate in a way that fits platform rules and basic legal/tax reality.

| Action | Details |
|--------|--------|
| 6.1 Platform ToS | Read Fiverr/Upwork ToS on automation and “who” delivers. Some platforms require that a human is responsible; ensure our use (human-in-the-loop, or disclosed automation) is allowed. |
| 6.2 Identity | Decide who appears as the seller: human name, stage name, or “AI-assisted” depending on platform rules and disclosure requirements. |
| 6.3 Taxes | Track revenue; report as income where required. If payouts go to an individual, that’s personal income; if to a business, business income. |
| 6.4 Disputes and refunds | If a buyer is unhappy, have a process: revise (executor re-do) or refund. Track disputes so we can improve prompts/gigs. |

**Exit criterion:** We know how we’re allowed to operate on the platform and how we’ll handle payouts, taxes, and disputes.

---

## Step 7 — Scale and quality

**Goal:** More orders and better outcomes without breaking the system.

| Action | Details |
|--------|--------|
| 7.1 More gigs / task types | Add gigs that match executor capabilities (e.g. blog outlines, meta descriptions). Reuse same “order → job → deliverable → platform” pipeline. |
| 7.2 Quality checks | Before delivering to buyer, optional: human spot-check, or LLM/judge “does this meet the brief?”. Reject or redo if below bar. |
| 7.3 Revisions | If buyer asks for revision, create a follow-up job (e.g. “Revision for order #12345”) and run the same flow; deliver revised output on platform. |
| 7.4 Multiple agents / queues | If volume grows, add more executor agents or a queue so several jobs can be in progress; ensure each order is still mapped to one job and one delivery. |

**Exit criterion:** We can handle multiple orders per week with consistent quality and clear revision handling.

---

## Summary table

| Step | Focus | Outcome |
|------|--------|--------|
| 1 | Real platform presence | Real seller account; real buyers can order. |
| 2 | Order ingestion | Platform order → sparky job; executor can work on it. |
| 3 | Delivery to platform | Agent deliverable is sent to buyer on platform. |
| 4 | Payment receipt | We receive payout; we record revenue. |
| 5 | Light automation | Less manual work per order. |
| 6 | Identity & compliance | ToS, taxes, disputes handled. |
| 7 | Scale & quality | More gigs, quality checks, revisions. |

---

## Where the codebase fits

- **Already in place:** Proposer/executor, job create/claim/submit/review, ai$ ledger, Fiverr-style task types, real Fiverr discovery (agent_1), web_search/web_fetch, test_run and run_all_tests.
- **To add:** Order ingestion (platform → `POST /jobs/create`), job metadata for platform_order_id, delivery export (approved job → platform submission), optional payouts/revenue logging, and any automation scripts or backend jobs for steps 2–5.

Starting with **Step 1** (real account + a few gigs) and **Step 2** (manual “new order → create job”) gets you to “agents do work that real clients pay for” with minimal new code; then Steps 3–7 tighten delivery, money, and scale.

---

## Could Clawd (Moltbot) help? (clawd.bot / moltbot)

**Clawd (Moltbot)** is an open-source personal AI assistant that runs on your machine, talks over WhatsApp/Telegram/Discord/etc., and has persistent memory, browser control, shell access, and pluggable skills. It “actually does things” (inbox, calendar, flights, etc.).

**Yes, it can help** — not by replacing our multi-agent backend (we keep proposer/executor, jobs, ai$), but as an **operator interface and automation layer** in front of it:

| Use | How Clawd helps |
|-----|------------------|
| **Order ingestion (Step 2)** | If the platform has no clean API: a Clawd **skill** (or you via chat) can use its **browser control** to log in, detect new orders, and call our backend `POST /jobs/create` with the order details. Same idea for “new order” webhooks → create job. |
| **Delivery to platform (Step 3)** | When a job is approved in our system, a Clawd skill can **read the deliverable** (from our API or a shared store), then use **browser control** (or API if available) to submit the delivery on Fiverr. Reduces copy-paste. |
| **Human-in-the-loop** | You can **talk to Clawd** in Telegram/WhatsApp: “Create job for Fiverr order #12345,” “Approve delivery for job X,” “What’s the status of open jobs?” Clawd calls our backend and reports back. Alerts (“New order,” “Job needs review”) can be pushed to you via the same channel. |
| **Light automation (Step 5)** | Skills like “Poll Fiverr for new orders every N minutes” or “When job X is approved, deliver to Fiverr” can live inside Clawd, using our API + browser as needed. |

**Summary:** Clawd is a strong fit for the **human-facing and platform-facing** bits (chat, browser, skills) while our backend remains the source of truth for jobs, agents, and ai$. Use it as the **operator’s cockpit** and, where APIs are missing, the **browser-automation layer** for order ingestion and delivery.

**Install on sparkies + proactive Fiverr screening:** See [CLAWD_SPARKY.md](../external-tools/clawd/CLAWD_SPARKY.md) for installing Clawd on sparky1/sparky2, connecting Ollama, and a cron job that screens Fiverr tasks and reports (e.g. to Telegram).
