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

**Run automated end-to-end test:**
```bash
python scripts/test_workflow.py --backend-url http://sparky1:8000
```

This tests:
1. Backend health
2. Job creation
3. Job listing
4. Job claiming
5. Job submission
6. Auto-verification
7. Job approval
8. Economy balance updates
9. Learning patterns

## Testing Strategy

### Level 1: Health Checks (Daily)
Run health checks to ensure system is responsive:
- Backend responds
- Endpoints are accessible
- No critical errors

**When to run:** Before starting work, after deployments

### Level 2: Workflow Tests (Weekly)
Run full workflow tests to verify end-to-end functionality:
- Complete job lifecycle works
- Verification runs correctly
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
