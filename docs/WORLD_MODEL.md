# World Model — what agents should “understand”

## Goal
Agents stop acting randomly when they have:
- a **compact, stable representation** of the world (not raw logs)
- clear **affordances** (what actions are possible where)
- a consistent notion of **time**, **place**, **resources**, and **other agents**

This doc defines the minimum world concepts we should feed into agent decision-making every tick.

## Entities
- **Tile world**: \(32 \times 32\) grid (v1), each tile can contain multiple entities.
- **Agent**
  - id, name, personality
  - position (x,y)
  - **goal tiers** (see below): short-term, medium-term, long-term
  - ai$ balance, entitlements (compute budget/rate limits)
  - current task state (none / executing / waiting review)
- **Landmarks** (typed)
  - `home_agent_*` (rest / personal storage)
  - `cafe` (social hub)
  - `market` (trade hub)
  - `board` (human-facing bulletin board)
  - `computer` / `computer_access` (tool-heavy actions; can be a gating zone or an “affordance booster”)
- **Jobs/Tasks** (global queue)
  - id, title, body, acceptance criteria, verification type
  - status: open → claimed → submitted → approved/rejected
  - proposer/executor ids
- **Events** (optional)
  - invitations, start/end time, location

## Affordances (what actions are possible)
Agents should model actions as **affordances** tied to location/time/state:

- **Move**: step toward a target (landmark, other agent, waypoint)
- **Propose task**: create a job/task with verification plan
  - recommended location: anywhere (v1) or `computer` (v2 gating)
- **Execute task**: do tool/code work and submit artifacts/evidence
  - recommended location: `computer` if we enforce gating; otherwise allowed anywhere
- **Social**: short conversation / negotiation / coordination
  - best at `cafe` or when adjacent
- **Interact with humans**: board posts/replies, ask for requirements, request rewards
  - best at `board`
- **Rest/reflect**: memory writes, plan next steps
  - best at `home`

## Perception payload (what to feed the LLM each tick)
Do NOT dump raw world JSON and logs. Provide a structured summary like:

1. **Time**
   - day, minute_of_day, “phase” (morning/afternoon/evening)
2. **Self**
   - position, current activity, ai$ balance, last reward/penalty
   - current goals (short/medium/long term if any): target + why; see § Goal tiers
3. **Nearby (radius 3–5)**
   - other agents with relative positions
   - landmarks within radius + what they enable
4. **Global opportunities**
   - top N open tasks (scoped to current run) with:
     - title, acceptance criteria, verification method, reward/penalty risk
5. **Commitments**
   - currently claimed/submitted tasks and what remains to finish/verify
6. **Constraints**
   - tool/compute entitlements and current limits

This is the “world model” the agent reasons over.

## Goal tiers (short / medium / long)

Agents should maintain **goal continuity**: do not drop or switch a goal mid-way unless it is achieved or explicitly abandoned with a reason.

- **Short-term goal** — one concrete, in-world step (e.g. “move to cafe”, “reach the board”). The agent should **continue until done**: e.g. keep moving toward the cafe every tick until it arrives, then clear or replace the goal. Do **not** turn around to approach another agent or change destination just because something else caught your attention; finish or explicitly abandon first.
- **Medium-term goal** — a small sequence or outcome (e.g. “have a short sync at cafe with agent X”, “post one bulletin and wait for replies”). Can span several short-term steps. Replace only when done or when abandoning with a stated reason.
- **Long-term goal** — broader objective (e.g. “increase ai$ this week”, “complete two jobs”). Guides which medium/short goals to pick; update rarely.

**Rule:** When you have an active short-term goal (e.g. move to a place), your next action should either (1) advance that goal (e.g. one step toward the target), or (2) explicitly set a new short-term goal and state why you abandoned the previous one. Do not output a move that contradicts your current short-term goal (e.g. walking away from the cafe when your goal is “move to cafe”) unless you are abandoning it.

Implementation: the LLM sees `current_goals` in state each tick and can output optional goal updates (set/clear short_term, medium_term, long_term). Landmark positions are provided so the LLM can choose (dx, dy) that step toward the short-term target.

## Verification types (proof mechanisms)
Every task should declare a verification type:
- **deterministic**: run code/tests, compare output, validate files/hashes
- **schema**: validate JSON shape, required fields
- **artifact**: required file paths exist + contain expected sections
- **human**: requires manual approval (with rubric)

## Why this helps
Randomness happens when:
- the agent lacks a stable state summary
- there’s no “next best action” objective
- actions aren’t tied to affordances/constraints

This world model is the minimum to make actions interpretable and goal-driven.

