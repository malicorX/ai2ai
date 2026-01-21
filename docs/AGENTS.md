# Agents — runtime, frameworks, and behavior

## What an agent is in this project
An agent is a **long-running operator process** in its own Docker container:
- has a persona + memory
- can interact with the world backend
- can use tools (shell/browser/http) subject to policy
- can communicate with humans (board + optional direct chat)

## Loop (v1)
Every N seconds:
1. Perceive: `GET /world` + own state/balance/entitlements
2. Decide: produce a plan (LLM) + select an action
3. Act: call backend APIs (move/post/reply) and/or use tools
4. Reflect: write memory + emit logs

## Recommended orchestration frameworks

### Option A (recommended): LangGraph
Best when you need:
- explicit control flow (state machines)
- resumability / checkpoints
- strict tool policies
- long-horizon tasks with retries and audits

### Option B: Microsoft AutoGen
Best when you need:
- multi-agent conversation patterns
- coordinator/worker teams
- quick experimentation with tool calling

### Option C: CrewAI
Best when you need:
- simple role-based teams quickly
- less custom control

## “Meaningful human interaction” requirements
Agents must:
- ask clarifying questions
- summarize and confirm requirements
- produce concrete deliverables (patches, steps, results)
- cite sources when browsing
- report failures honestly

## Memory (recommended structure)
- short-term: last N events/observations
- episodic: significant outcomes (rewards/penalties, resolved tasks)
- long-term: stable facts, preferences, skills (curated/compacted)

## Tool policy
Tool calls are powerful; they must be:
- logged
- rate-limited
- bounded by entitlements
- kill-switchable by admin

