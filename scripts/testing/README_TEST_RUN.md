# Test Run Script - Quick Start

The test run script creates a single test job and monitors it through the complete lifecycle, providing real-time status updates.

## Quick Start

### Windows (PowerShell)
```powershell
.\scripts\testing\test_run.ps1 -BackendUrl http://sparky1:8000
```

### Linux/Mac (Bash)
```bash
bash scripts/testing/test_run.sh
# Or with custom backend URL:
BACKEND_URL=http://sparky1:8000 bash scripts/testing/test_run.sh
```

## What It Does

The script performs a complete end-to-end test:

1. **Tests Backend Connection** - Verifies backend is accessible
2. **Creates Test Job** - Creates a simple, verifiable JSON task
3. **Waits for Claim** - Monitors until an agent claims the job (or claims manually)
4. **Waits for Agent to Submit** - Polls until the claiming agent (sparky2) produces and submits via do_job + jobs_submit; creativity lives on agents. Use `-ForceSubmit` to submit a minimal deliverable if the agent times out (backend-only test).
5. **Waits for Verification** - Monitors auto-verification results
6. **Approves Job** - Approves the job if verification passed
7. **Checks Economy** - Shows ai$ balance changes
8. **Displays Summary** - Provides final status and job ID

## Output

The script provides color-coded, real-time status updates:

- ✅ **Green** - Success/Pass
- ❌ **Red** - Failure/Error
- ⚠️ **Yellow** - Warning/In Progress
- ℹ️ **Cyan** - Information
- ⏳ **Gray** - Waiting/Polling

## Example Output

```
============================================================
AI Village Test Run - Single Job Lifecycle
============================================================
[14:23:15] Backend URL: http://sparky1:8000
[14:23:15] Poll Interval: 3 seconds
[14:23:15] Max Wait Time: 300 seconds

============================================================
Step 1: Testing Backend Connection
============================================================
[14:23:15] ✅ Backend is accessible
[14:23:15] Initial balances:
  agent_1: 100 ai$
  agent_2: 100 ai$

============================================================
Step 2: Creating Test Job
============================================================
[14:23:16] ✅ Job created successfully
  Job ID: abc123-def456-...
  Title: [TEST RUN] Creative JSON Task
  Status: open
  Reward: 10 ai$

============================================================
Step 3: Waiting for Job to be Claimed
============================================================
[14:23:19] ⏳ Waiting for agent to claim job...
[14:23:22] ✅ Job claimed by: agent_2

============================================================
Step 4: Waiting for agent to submit (creativity on sparky1/sparky2)
============================================================
[14:23:23] [OK] Agent agent_2 submitted

============================================================
Step 5: Waiting for Auto-Verification
============================================================
[14:23:25] ✅ Auto-verification PASSED
   Verifier: json_list

============================================================
Step 6: Approving Job
============================================================
[14:23:26] ✅ Job approved successfully

============================================================
Step 7: Final Status Check
============================================================
  Status: approved
  Reviewed By: test_run_script

============================================================
Step 8: Economy Update
============================================================
Final balances:
  agent_1: 100 ai$
  agent_2: 110 ai$ (+10)

============================================================
Test Run Summary
============================================================
[14:23:28] ✅ Test run completed successfully!
[14:23:28]    Job was created, claimed, submitted, verified, and approved
[14:23:28]    Economy was updated correctly

View job in UI: http://sparky1:8000/ui/
Job ID: abc123-def456-...
```

## Task types

- **`json_list`** (default) — Structured JSON list task with auto_verify (3 items, name/category/value). Run manually: `.\scripts\testing\test_run.ps1` (not used by `run_all_tests.ps1`).
- **`gig`** — Canned Fiverr-style short deliverable (tagline, feature list, social post, etc.). Uses `[verifier:proposer_review]`; script approves. Used by `run_all_tests.ps1` (step 3).
- **`fiverr`** — **Real Fiverr:** script does *not* create a job; it waits for agent_1 to create one via discover_fiverr (web_search + optional web_fetch). Requires agent_1 running and `WEB_SEARCH_ENABLED=1`, `SERPER_API_KEY`; optionally `WEB_FETCH_ENABLED=1`, `fiverr.com` in `WEB_FETCH_ALLOWLIST`. Run: `.\scripts\testing\test_run.ps1 -TaskType fiverr`.

## Parameters

### PowerShell
- `-BackendUrl` - Backend URL (default: `http://sparky1:8000`)
- `-TaskType` - `json_list` (default), `gig` (canned Fiverr-style), or `fiverr` (wait for agent_1 real Fiverr job)
- `-PollInterval` - Polling interval in seconds (default: `3`)
- `-MaxWaitSeconds` - Maximum wait time for claim (default: `300`)
- `-MaxWaitSubmitSeconds` - Maximum wait for agent to submit (default: `600`)
- `-MaxWaitFiverrJobSeconds` - When `-TaskType fiverr`, max wait for agent_1 to create a Fiverr job (default: `180`)
- `-ForceSubmit` - If agent does not submit in time, submit minimal deliverable (backend-only test)

### Bash
- `BACKEND_URL` - Backend URL (default: `http://sparky1:8000`)
- `POLL_INTERVAL` - Polling interval in seconds (default: `3`)
- `MAX_WAIT_SECONDS` - Maximum wait time for claim (default: `300`)

## Troubleshooting

### "Backend is not accessible"
- Verify backend is running: `docker ps | grep backend`
- Check backend URL is correct
- Verify network connectivity to sparky1

### "Job not claimed within timeout"
- Check if agent_2 is running: `docker ps | grep agent_2`
- Check agent_2 logs: `docker logs agent_2`
- The script will attempt to claim manually if possible

### Script stuck on "[!!] Job status changed to: approved" (Step 3)
- If the agent was very fast, the job may already be submitted/approved when the script first polls. The script now treats "submitted" or "approved" in Step 3 as success and proceeds to Step 4–8. Upgrade to the latest test_run.ps1 if you see an infinite loop here.

### "Auto-verification did not complete"
- Verification may need manual trigger
- Check backend logs for verification errors
- Verify job has correct verifier tag

### "invalid json (Expecting value: line 1 column 2)" / verifier extracts `[run:...]`
- Backend json_list verifier may be outdated. Rebuild and restart the backend on sparky1 so it uses the updated extraction (```json fence first, then array-of-objects). See deployment/README § After code changes.

### "Failed to approve job"
- Check if verification passed
- Verify job status is "submitted"
- Check backend logs for errors

## Integration with CI/CD

The script returns exit code 0 on success, 1 on failure, making it suitable for CI/CD pipelines:

```bash
if bash scripts/testing/test_run.sh; then
    echo "✅ Workflow test passed"
else
    echo "❌ Workflow test failed"
    exit 1
fi
```

## LangGraph / OpenClaw step test (no backend)

To verify the OpenClaw-driven graph (USE_LANGGRAPH=1) builds and runs one step with stub tools:

```bash
pip install -r agents/agent_template/requirements.txt
python scripts/testing/test_langgraph_step.py
```

Set `OPENAI_API_BASE` and `OPENAI_API_KEY` for a full step (the decide node calls the LLM once). Without them, the script may fail at the LLM call with a clear error.

## OpenClaw gateway tools test suite

Tests each agent (sparky1, sparky2) against every available gateway tool: sends a prompt that should trigger the tool, then checks the gateway log for evidence the tool was used.

**Run (PowerShell):**
```powershell
.\scripts\testing\test_openclaw_tools_suite.ps1
```

- **Default:** both hosts, all non-optional tools (web_fetch, browser, web_search, read, write, session_status). Optional tool `exec` is skipped unless requested.
- **One host:** `-Hosts sparky2`
- **One tool:** `-Tools web_fetch`
- **Include exec test:** `-IncludeOptional` (and `-SkipOptionalExec:$false` if you want exec in the default set)

**Requirements:** SSH to each host; gateway on 18789; token in `~/.openclaw/openclaw.json` or `~/.clawdbot/clawdbot.json`. Test definitions: `scripts/testing/openclaw_tool_tests.json`.

**Output:** Pass/fail per (host, tool) and a summary table. Fail means HTTP ≠ 200/201/202 or the tool’s log pattern was not found in the gateway log after the wait window.

**sparky1 (Clawdbot):** If POST /v1/responses returns 405, the suite tries POST /hooks/agent then POST /hooks/wake. Enable hooks on sparky1: run `scripts/clawd/enable_hooks_on_sparky.sh` with `CLAW=clawdbot` (e.g. via scp+ssh). See `scripts/clawd/test_wake_endpoints.sh` and PROJECT_OVERVIEW.md.

**Log patterns:** Pass/fail for “tool used” is determined by matching `openclaw_tool_tests.json` **logPattern** against the last 1200 lines of `~/.openclaw/gateway.log` or `~/.clawdbot/gateway.log`. If your gateway logs tool calls in a different format, edit **logPattern** (regex) in that JSON to match. Increase wait times or log line count in the script if the agent is slow or logs are verbose.

## MoltWorld: two OpenClaw agents relate in chat

To verify that Sparky1Agent and MalicorSparky2 relate to each other (reply to what the other said, not generic openers):

```powershell
.\scripts\testing\test_moltworld_bots_relate.ps1
```

The test fetches recent chat from theebie and asserts:
1. At least one consecutive bot→bot reply is **not** a generic opener (e.g. "Hello!", "What would you like to talk about?").
2. At least one reply **relates** to the previous message: it references it (shares a meaningful word) or substantively answers it (previous is a question and reply length > 30). Such pairs are marked [RELATES]; others only [RELATED].

By default the script also triggers narrator (sparky1) then replier (sparky2) via pull-and-wake before checking. Requires SSH to `sparky1` and `sparky2`. Use `-SkipTrigger` to only assert on current chat (no SSH), or `-TriggerNarrator:$false` / `-TriggerReplier:$false` to trigger only one side.

**Unit test (no network):** `python scripts/testing/test_moltworld_bots_relate_criteria.py` — validates the same generic/references-previous logic on mock (prev, reply) pairs so the criteria can be verified offline.

To run this as part of the full test suite: `.\scripts\testing\run_all_tests.ps1 -IncludeMoltworldRelate`. That runs the criteria unit test then the theebie chat test in check-only mode (last 25 messages).

## Next Steps

After a successful test run:
1. Check the job in the UI: `http://sparky1:8000/ui/`
2. Verify learning patterns were stored
3. Check agent memory for reflections
4. Review economy ledger for entries
