# Testing Guide for AI Village

This document explains how to test the complete AI Village workflow to ensure stability.

## Quick Start

### 1. Health Check (30 seconds)

**On Windows (cursorComputer):**
```powershell
.\scripts\quick_test.ps1 -BackendUrl http://sparky1:8000
```

**On Linux (sparky1/sparky2):**
```bash
BACKEND_URL=http://sparky1:8000 bash scripts/health_check.sh
```

This verifies:
- ✅ Backend is responding
- ✅ World state is accessible
- ✅ Jobs endpoint works
- ✅ Economy endpoint works
- ✅ Memory/learning endpoints work
- ✅ Opportunities endpoint works

### 2. Full Workflow Test (2-5 minutes)

**Option A – Python:**
```bash
python scripts/test_workflow.py --backend-url http://sparky1:8000
```

**Option B – PowerShell (single job lifecycle):**
```powershell
.\scripts\test_run.ps1 -BackendUrl http://sparky1:8000
```

`test_run.ps1` requires the backend to report `backend_version: "balanced_array"` from `GET /run`. If the script reports a version mismatch, rebuild/restart the backend (e.g. via deploy) so it serves the current code. **After any backend verifier change** (e.g. json_list extraction logic in `backend/app/main.py`), rebuild and restart the backend on sparky1 so auto-verify uses the new code; otherwise test_run can fail with “invalid json (Expecting value: line 1 column 2)” when the verifier still picks tag-like `[run:...]` instead of the ```json block. See `scripts/README_TEST_RUN.md` for details.

Both workflows test:
1. Backend health
2. Job creation / listing / claim / submission
3. Auto-verification (or proposer review where applicable)
4. Job approval and economy updates
5. (Python) Learning patterns

**json_list verifier (local, no deploy):** To check that the backend extraction fix works without deploying to sparky1:
```bash
cd backend && pip install -q -r requirements.txt && python test_json_list_verifier.py
```
This verifies the verifier uses the ```json fence (or array-of-objects), not tag-like `[run:...]`. If both tests pass, deploy the backend to sparky1 and re-run `test_run.ps1`.

### 3. Proposer-Review Test (~30 seconds)

**Run the proposer-review E2E test:**
```powershell
.\scripts\test_proposer_review.ps1 -BackendUrl http://sparky1:8000
```

This verifies:
1. Job with `[verifier:proposer_review]` and `[reviewer:creator]` is created by agent_1
2. agent_2 claims and submits
3. Job stays **submitted** (backend skips auto_verify for proposer_review)
4. agent_1 (proposer) calls `POST /jobs/{id}/review` and approves
5. Job ends in **approved** with `reviewed_by=agent_1`

For a **live** agent_1 to perform proposer-review (fetch "my submitted jobs" and call the review API), agent_1 must be built from the current `agents/agent_template/`. Rebuild agent_1 on sparky1 after template changes; see `deployment/README.md` (§ After code changes).

**Reject path (proposer rejects with penalty):**
```powershell
.\scripts\test_proposer_review_reject.ps1 -BackendUrl http://sparky1:8000 -PenaltyAmount 1.0
```
Creates a proposer_review job, claim+submit as agent_2, then agent_1 rejects with `approved=false` and `penalty=1.0`. Asserts job ends in **rejected** and (when balances are available) executor balance drops by the penalty.

### 4. Run All Tests (one command)

**From repo root (Windows):**
```powershell
.\scripts\run_all_tests.ps1 -BackendUrl http://sparky1:8000
```
All output is logged to `scripts/run_all_tests.<yyyyMMdd-HHmmss>.log` (e.g. `run_all_tests.20260128-163145.log`). The script prints the log path at start.

**Deploy backend to sparky1, then run full suite:**
```powershell
.\scripts\deploy_and_run_tests.ps1 -BackendUrl http://sparky1:8000
```
Use this after verifier changes so the backend on sparky1 is rebuilt before the suite runs. Add `-SkipVerifierUnit` to skip the local verifier step (e.g. when backend deps aren’t installed locally).

Runs in order: **(1)** backend json_list verifier (local), **(2)** `quick_test.ps1`, **(3)** `test_run.ps1`, **(4)** `test_proposer_review.ps1`, **(5)** `test_proposer_review_reject.ps1`. Stops on first failure. Use `-SkipVerifierUnit` to skip step 1 (e.g. when backend deps aren’t installed locally). If step 1 passes but step 3 (test_run) fails with “invalid json (Expecting value…)”, deploy the backend to sparky1 and re-run.

## Test Scripts Overview

| Script | Purpose |
|--------|---------|
| `scripts/deploy_and_run_tests.ps1` | Deploy backend to sparky1, then run full suite. Use after verifier/backend changes. Params: `-BackendUrl`, `-SkipVerifierUnit`, `-CopyOnly`, `-Docker`. |
| `scripts/run_all_tests.ps1` | Run full suite: verifier_unit → quick_test → test_run → test_proposer_review → test_proposer_review_reject. Stop on first failure. Logs to `scripts/run_all_tests.<timestamp>.log`. `-SkipVerifierUnit` skips the backend json_list test. |
| `backend/test_json_list_verifier.py` | Local unit test for json_list extraction (```json fence, array-of-objects). Run from backend dir with deps. |
| `scripts/quick_test.ps1` | Health check (backend, world, jobs, economy, memory, opportunities). ~30 s. |
| `scripts/test_run.ps1` | Single-job lifecycle: create → claim → submit → verify → approve. Default `-TaskType json_list` (auto_verify); use `-TaskType gig` for Fiverr-style short deliverable (proposer_review). json_list requires `backend_version: "balanced_array"`. |
| **Fiverr discovery (optional)** | When backend has `WEB_SEARCH_ENABLED=1` and `SERPER_API_KEY`, proposer can search Fiverr → pick gig → transform to sparky task → create job for executor. See deployment/README § Fiverr discovery. Suite does not require this. |
| `scripts/test_proposer_review.ps1` | Proposer-review E2E: job with `[verifier:proposer_review]` stays submitted, agent_1 reviews and approves. |
| `scripts/test_proposer_review_reject.ps1` | Proposer-review reject: agent_1 rejects with penalty; asserts job rejected and executor balance drops. |
| `scripts/test_workflow.py` | Python E2E: health, jobs, claim, submit, auto-verify, approval, economy, learning. |

To “run the suite” from a Windows dev machine: use `run_all_tests.ps1` (see §4 above).

## Testing Strategy

### Level 1: Health Checks (Daily)
Run health checks to ensure system is responsive:
- Backend responds
- Endpoints are accessible
- No critical errors

**When to run:** Before starting work, after deployments

### Level 2: Workflow Tests (Weekly)
Run full workflow tests to verify end-to-end functionality:
- Complete job lifecycle works (`test_run.ps1` or `test_workflow.py`)
- Verification runs correctly (proposer-review via `test_proposer_review.ps1`, reject+penalty via `test_proposer_review_reject.ps1`)
- Economy updates properly
- Learning is active

**When to run:** After major changes, before releases

### Level 3: Manual Testing (As Needed)
Use UI to manually verify:
- Agents appear on map
- Jobs are created/claimed/submitted
- UI displays correctly
- Learning patterns show up

**When to run:** When investigating specific issues

## Common Workflow Issues

### Issue: "Backend version mismatch" (test_run.ps1)
**Symptoms:** `test_run.ps1` exits with "Backend at … is not the balanced_array version"

**Cause:** The backend running on the host (or in Docker) is an older build that doesn’t set `backend_version: "balanced_array"` on `GET /run`.

**Fix:**
- Rebuild and restart the backend so it serves the current code (e.g. run deploy with Docker: `docker compose -f deployment/docker-compose.sparky1.yml up -d --build backend` on the target host).
- Or run tests against a backend you’ve already updated.

### Issue: "Backend not responding"
**Symptoms:** Health check fails, UI shows errors

**Diagnosis:**
```bash
# Check if backend container is running
docker ps | grep backend

# Check backend logs
docker logs backend

# Check if port is accessible
curl http://sparky1:8000/world
```

**Fix:**
- Restart backend: `docker compose restart backend`
- Check docker-compose.yml configuration
- Verify network connectivity

### Issue: "Agents not creating jobs"
**Symptoms:** No new jobs appear, proposer seems idle

**Diagnosis:**
```bash
# Check agent_1 logs
docker logs agent_1

# Check if agent_1 is running
docker ps | grep agent_1

# Check agent memory/learning
curl http://sparky1:8000/memory/agent_1/recent?limit=5
```

**Fix:**
- Restart agent_1: `docker compose restart agent_1`
- Check `USE_LANGGRAPH=1` is set
- Verify LLM endpoint is accessible
- Check for errors in logs

### Issue: "Jobs not being claimed"
**Symptoms:** Jobs stay in "open" status, executor seems idle

**Diagnosis:**
```bash
# Check agent_2 logs
docker logs agent_2

# Check open jobs
curl http://sparky1:8000/jobs?status=open

# Check if parent job is blocking
curl http://sparky1:8000/jobs/{job_id}
```

**Fix:**
- Restart agent_2: `docker compose restart agent_2`
- Verify parent job is approved (for sub-tasks)
- Check for race conditions (multiple executors)
- Verify agent_2 can reach backend

### Issue: "Verification failing"
**Symptoms:** Auto-verification shows FAIL, jobs get rejected

**Diagnosis:**
```bash
# Check job details
curl http://sparky1:8000/jobs/{job_id}

# Check auto_verify_note for details
# Look for: missing evidence, code errors, test failures
```

**Fix:**
- Review job acceptance criteria
- Check submission format matches verifier expectations
- Verify evidence section is included
- For code tasks: ensure tests pass

**Specific: json_list verifier extracts `[run:...]` (test_run fails with "invalid json (Expecting value…)")**  
If test_run shows `extracted_preview = [run:...]` in the VERIFIER DEBUG ARTIFACTS, the backend on sparky1 is still on the old verifier (it uses the first `[..]` as JSON instead of the ```json block). Deploy and re-run: `.\scripts\deploy_and_run_tests.ps1 -BackendUrl http://sparky1:8000`. See `scripts/README_TEST_RUN.md` and deployment/README § After code changes.

### Issue: "Economy not updating"
**Symptoms:** Agent balances don't change after approval

**Diagnosis:**
```bash
# Check economy ledger
curl http://sparky1:8000/economy/ledger?limit=20

# Check balances
curl http://sparky1:8000/economy/balances

# Verify job was actually approved
curl http://sparky1:8000/jobs/{job_id}
```

**Fix:**
- Verify job status is "approved" (not just "submitted")
- Check review included payout > 0
- Restart backend if ledger seems stuck
- Check for errors in backend logs

## Stability Checklist

Before considering the system "stable", verify:

- [ ] Health checks pass consistently
- [ ] Agents create jobs regularly (every 5-10 minutes)
- [ ] Jobs are claimed within reasonable time (< 2 minutes)
- [ ] Submissions include proper evidence
- [ ] Auto-verification works for common task types
- [ ] Approved jobs credit ai$ correctly
- [ ] Learning patterns accumulate over time
- [ ] UI displays all information correctly
- [ ] No excessive errors in logs
- [ ] System recovers from restarts gracefully

## Continuous Monitoring

For ongoing stability, monitor:

1. **Job Pipeline Health:**
   - Open → Claimed transition time
   - Claimed → Submitted transition time
   - Submission → Approval rate

2. **Agent Activity:**
   - Trace logs show regular activity
   - Agents don't get stuck in loops
   - Memory/learning is accumulating

3. **System Performance:**
   - API response times < 1s
   - No memory leaks
   - Docker containers stay healthy

4. **Data Integrity:**
   - Economy ledger is append-only
   - Jobs have valid state transitions
   - Opportunities are properly linked

## Next Steps

Once basic workflow is stable:

1. **Test Multi-Agent Competition:**
   - Multiple executors competing for same job
   - Race condition handling
   - Fair distribution of work

2. **Test Opportunity Pipeline:**
   - Market scans discover opportunities
   - Opportunities are prioritized correctly
   - Deliver opportunity jobs execute successfully

3. **Test Learning Effectiveness:**
   - Agents actually avoid failed patterns
   - Success patterns guide future proposals
   - Learning improves over time

4. **Test Edge Cases:**
   - Job cancellation
   - Agent disconnection/reconnection
   - Backend restart during active jobs
   - Concurrent job creation/claiming

## Getting Help

If tests fail or system is unstable:

1. **Check Logs:**
   - Backend: `docker logs backend`
   - Agent_1: `docker logs agent_1`
   - Agent_2: `docker logs agent_2`

2. **Check Status:**
   - Run health check script
   - Verify all containers are running
   - Check network connectivity

3. **Review Recent Changes:**
   - Check git log for recent commits
   - Verify configuration matches deployment
   - Check for breaking changes

4. **Reset if Needed:**
   - Create new run: `POST /admin/new_run`
   - Restart all containers
   - Clear problematic data if necessary
