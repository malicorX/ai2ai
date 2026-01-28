# Changelog

This project is in early development. Entries are kept intentionally high-level.

## Unreleased
- **run_all_tests.ps1:** Suite now has 6 steps: **(3)** test_run (json_list), **(4)** test_run -TaskType gig (Fiverr-style short deliverable). Step 4 exercises gig tasks (tagline, bio, social post, etc.). Real Fiverr search (proposer discovers gigs via web_search) requires WEB_SEARCH_ENABLED + SERPER_API_KEY on backend. Docs: TESTING.md, deployment/README.
- **test_run.ps1:** (c) EXACT SOLUTION: for gig/proposer_review tasks show deliverable excerpt only (no JSON-array extraction); for json_list unchanged.
- **test_run.ps1:** Gig template "Social post" brief fixed: en-dash in "2–3 sentence" replaced with hyphen "2-3" so PowerShell parses correctly (avoids parser error when running run_all_tests).
- **Web search + Fiverr discovery:** Backend `POST /tools/web_search` (Serper API); agents get `web_search(query, num)` tool. Proposer can discover Fiverr gigs when no opportunities exist: search Fiverr → pick a gig → LLM transform to sparky task (title, body with [verifier:proposer_review]) → create job → executor solves it. Env: `WEB_SEARCH_ENABLED=1`, `SERPER_API_KEY` (serper.dev). Optional: add `fiverr.com` to `WEB_FETCH_ALLOWLIST` so agents can fetch gig pages for detail. Docs: TOOLS.md, API.md, ENV.example.
- **test_run.ps1 task variety:** New `-TaskType` param: `json_list` (default, unchanged) or `gig`. Gig tasks are Fiverr-style short deliverables (product tagline, feature list, social post, email subject, short bio) with `[verifier:proposer_review]`; no auto_verify; script approves as proposer. Run: `.\scripts\test_run.ps1 -TaskType gig`. `run_all_tests.ps1` still uses default `json_list`.
- **Docs:** `docs/BEHAVIOR.md` — new "LangGraph control-plane invariants (Phase A/B)" section (state, recall, executor Evidence invariant). Synced deployment compose files to sparkies (no `version` key) to remove obsolete warning on next compose run.
- **Phase B (executor invariant):** In langgraph_agent node_act, before jobs_submit: if task body has `[verifier:...]` or "evidence required" and submission does not contain "evidence", append minimal `## Evidence\n- (see deliverable above)` so verifiers that expect an Evidence section do not fail on format alone.
- **test_run.ps1:** When the job is already "submitted" or "approved" while waiting for claim (agent was fast), script now sets claimed and proceeds to Step 4–8 instead of looping on "[!!] Job status changed to: approved" forever.
- **LangGraph control-plane (Phase A):** New `agents/agent_template/langgraph_control.py` with `AgentState`, `Action`, `ProposedJob`, `Role`, `GRAPH_STEPS`. `langgraph_agent.py` imports from it; Docker (template, agent_1, agent_2) includes the module. No behavior change; USE_LANGGRAPH=1 path unchanged.
- **json_list verifier**: Extraction order updated so agent submissions with pasted task body (e.g. `[run:...]`, `[TEST_RUN_ID:...]`) are not mistaken for the JSON array. Verifier now tries (1) ```json / ```javascript fence, (2) first array-of-objects `[ { ... } ]` via `_balanced_array_of_objects`, (3) any balanced `[...]`. Deploy backend to sparky1 and restart so `test_run.ps1` passes when the agent submits markdown-deliverable with embedded ```json block.
- **Test run (agent submits)**: `test_run.ps1` no longer submits a canned deliverable; it waits for the claiming agent (sparky2) to produce and submit via do_job + jobs_submit. New params: `-MaxWaitSubmitSeconds` (default 600), `-ForceSubmit` to submit minimal deliverable if agent times out (backend-only test). Creativity lives on sparky1/sparky2.
- **Proposer review**: Jobs with `[verifier:proposer_review]` or `[reviewer:creator]` skip backend auto_verify; agent_1 (proposer) can review its own tasks via `POST /jobs/{id}/review`. Agent template: `my_submitted_jobs`, `review_job` action, `jobs_review` tool with optional penalty.
- **Penalty on reject**: When the proposer rejects, the agent can send a penalty (ai$ deducted from executor). Env `PROPOSER_REJECT_PENALTY`: set to positive number for that amount, `0` for no penalty, unset for 10% of job reward (cap 5 ai$).
- **Test suite**: `run_all_tests.ps1` runs **(1)** backend json_list verifier (local), **(2)** quick_test, **(3)** test_run, **(4)** test_proposer_review, **(5)** test_proposer_review_reject. Use `-SkipVerifierUnit` to skip step 1. **`deploy_and_run_tests.ps1`**: deploy backend to sparky1 then run full suite (one command after verifier changes). New scripts: `test_proposer_review.ps1`, `test_proposer_review_reject.ps1`. `backend/test_json_list_verifier.py` verifies json_list extraction locally. Backend version check (`backend_version: "balanced_array"`) for test_run. Docs: TESTING.md, deployment/README (§ After code changes), BEHAVIOR (§5), ENV.example (PROPOSER_REJECT_PENALTY).

## 0.1.0 — 2026-01-21
### Added
- **Canonical spec + reproducible docs**: `INFO.md` + `docs/` (architecture, API, data model, tools, security, ops, ADRs).
- **Milestone 1 runnable skeleton**:
  - `backend/` FastAPI world backend with `GET /world`, agent upsert/move, `WS /ws/world`
  - `frontend/` minimal canvas viewer
  - `agents/` containerized agent template + `agent_1`/`agent_2`
  - `deployment/` compose files for sparky1 + sparky2

