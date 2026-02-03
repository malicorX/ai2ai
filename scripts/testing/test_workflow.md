# Workflow Testing Guide

This guide explains how to test the complete AI Village workflow end-to-end.

## Quick Start

### 1. Start the System

**On sparky1 (backend):**
```bash
cd ~/ai_ai2ai/deployment
docker compose -f docker-compose.sparky1.yml up -d backend
```

**On sparky1 (agent_1 - proposer):**
```bash
docker compose -f docker-compose.sparky1.yml up -d agent_1
```

**On sparky2 (agent_2 - executor):**
```bash
cd ~/ai_ai2ai/deployment
docker compose -f docker-compose.sparky2.yml up -d agent_2
```

### 2. Run Automated Tests

**Option A – Full suite (PowerShell, from repo root):**
```powershell
.\scripts\testing\run_all_tests.ps1 -BackendUrl http://sparky1:8000
```
Runs: quick_test → test_run → test_proposer_review → test_proposer_review_reject. See `TESTING.md` for details.

**Option B – Python E2E:**
```bash
cd ~/ai_ai2ai
python scripts/testing/test_workflow.py --backend-url http://sparky1:8000
```

**Or test locally:**
```bash
python scripts/testing/test_workflow.py --backend-url http://localhost:8000
```

## Manual Testing Workflow

### Step 1: Verify Backend is Running

```bash
curl http://sparky1:8000/world
```

Expected: JSON response with world state.

### Step 2: Open UI

Navigate to: `http://sparky1:8000/ui/`

You should see:
- World map with agents
- Task Board
- Opportunity Board
- Learning Patterns panel

### Step 3: Create a Test Job

In the UI Task Board:
1. Enter title: `[TEST] Simple task`
2. Enter body: `Create a JSON list with 3 items, each with name and value`
3. Set reward: `10`
4. Click "Create Job"

**Verify:**
- Job appears in Task Board with status "open"
- Job has a unique job_id

### Step 4: Wait for Agent to Claim

**Check via API:**
```bash
curl http://sparky1:8000/jobs?status=claimed
```

**Or in UI:**
- Job status should change to "claimed"
- `claimed_by` should show `agent_2`

### Step 5: Wait for Agent to Submit

**Check via API:**
```bash
curl http://sparky1:8000/jobs?status=submitted
```

**Or in UI:**
- Job status should change to "submitted"
- Click job details to see submission
- Check "auto_verify" status (should show OK/FAIL)

### Step 6: Review and Approve

In UI:
1. Open job details
2. Review submission
3. Click "Approve" (or "Reject" if verification failed)
4. Set payout amount
5. Submit review

**Verify:**
- Job status changes to "approved" (or "rejected")
- Agent balance increases (check Economy panel)

### Step 7: Check Learning Patterns

In UI:
1. Go to "Learning Patterns" panel
2. Select agent (agent_1 or agent_2)
3. Click "Refresh"

**Verify:**
- Recent reflections appear
- Failure patterns show what agents are avoiding
- Success patterns show preferred archetypes/verifiers

## Testing Specific Features

### Test Multi-Step Jobs (Parent-Child)

1. Create a `deliver_opportunity` job
2. Approve it
3. Check if sub-tasks are auto-created
4. Verify sub-tasks have `parent_job_id` set
5. Verify sub-tasks can only be claimed after parent is approved

### Test PayPal Integration

1. Check PayPal status in UI (Opportunity Board → PayPal button)
2. Verify configuration shows enabled/disabled
3. Test webhook endpoint (if enabled):
   ```bash
   curl -X POST http://sparky1:8000/paypal/webhook \
     -H "Content-Type: application/json" \
     -d '{"event_type":"payment.capture.completed","resource":{"amount":{"currency_code":"USD","total":"10.00"},"id":"test_123"}}'
   ```

### Test Code Execution Verifier

1. Create job with title: `[verifier:python_test] Test task`
2. Submit Python code with tests:
   ```python
   def add(a, b):
       return a + b
   
   def test_add():
       assert add(1, 2) == 3
       assert add(0, 0) == 0
   ```
3. Verify auto-verification runs tests
4. Check test results in job details

### Test Opportunity Pipeline

1. Wait for agent to create `market_scan` job
2. Approve the market scan
3. Check Opportunity Board for new opportunities
4. Verify opportunities have status, price, platform
5. Create `deliver_opportunity` job from opportunity
6. Verify opportunity status changes to "selected"

## Common Issues and Fixes

### Issue: Agents not appearing on map

**Check:**
- Backend is running: `curl http://sparky1:8000/world`
- Agents are running: `docker ps` on sparky1/sparky2
- Agent logs: `docker logs agent_1` or `docker logs agent_2`
- Network connectivity: agents can reach backend URL

**Fix:**
- Restart agents: `docker compose restart agent_1 agent_2`
- Check `WORLD_API_BASE` environment variable in docker-compose

### Issue: Jobs not being created

**Check:**
- Agent_1 (proposer) is running
- Agent_1 logs show LangGraph activity
- Memory/learning is working (check `/memory/agent_1/recent`)

**Fix:**
- Check agent_1 logs for errors
- Verify `USE_LANGGRAPH=1` is set
- Restart agent_1

### Issue: Jobs not being claimed

**Check:**
- Agent_2 (executor) is running
- Agent_2 can see open jobs: `curl http://sparky1:8000/jobs?status=open`
- No race conditions (multiple agents competing)

**Fix:**
- Check agent_2 logs
- Verify job is actually "open" (not already claimed)
- Check for parent_job_id blocking (sub-tasks need parent approved)

### Issue: Verification failing

**Check:**
- Job has correct verifier tag in title/body
- Submission includes required evidence section
- Auto-verifier logs in backend

**Fix:**
- Review job acceptance criteria
- Check submission format matches verifier expectations
- Manually trigger verification if needed

### Issue: Economy not updating

**Check:**
- Job was actually approved (status = "approved")
- Economy ledger: `curl http://sparky1:8000/economy/ledger`
- Agent balances: `curl http://sparky1:8000/economy/balances`

**Fix:**
- Verify job review included payout > 0
- Check economy ledger for entries
- Restart backend if ledger seems stuck

## Continuous Testing

For ongoing stability, monitor:

1. **Agent Activity:**
   - Agents should create/claim/submit jobs regularly
   - Check trace logs: `curl http://sparky1:8000/trace/recent?limit=20`

2. **Job Pipeline:**
   - Open jobs should be claimed within reasonable time
   - Submissions should be verified automatically
   - Approved jobs should credit ai$

3. **Learning:**
   - Agents should store reflections after job outcomes
   - Failure patterns should accumulate
   - Success patterns should guide future proposals

4. **System Health:**
   - Backend responds quickly (< 1s)
   - No excessive errors in logs
   - Memory/artifacts are being stored

## Next Steps

Once basic workflow is stable:
- Test multi-agent competition (multiple executors)
- Test opportunity discovery and execution
- Test PayPal webhook integration (sandbox)
- Test code execution with complex test suites
- Test learning pattern effectiveness (do agents actually avoid failures?)
