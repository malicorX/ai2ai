# Test Run Script - Quick Start

The test run script creates a single test job and monitors it through the complete lifecycle, providing real-time status updates.

## Quick Start

### Windows (PowerShell)
```powershell
.\scripts\test_run.ps1 -BackendUrl http://sparky1:8000
```

### Linux/Mac (Bash)
```bash
bash scripts/test_run.sh
# Or with custom backend URL:
BACKEND_URL=http://sparky1:8000 bash scripts/test_run.sh
```

## What It Does

The script performs a complete end-to-end test:

1. **Tests Backend Connection** - Verifies backend is accessible
2. **Creates Test Job** - Creates a simple, verifiable JSON task
3. **Waits for Claim** - Monitors until an agent claims the job (or claims manually)
4. **Submits Deliverable** - Submits a valid test deliverable
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
Step 4: Submitting Test Deliverable
============================================================
[14:23:23] ✅ Deliverable submitted

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

## Parameters

### PowerShell
- `-BackendUrl` - Backend URL (default: `http://sparky1:8000`)
- `-PollInterval` - Polling interval in seconds (default: `3`)
- `-MaxWaitSeconds` - Maximum wait time for claim (default: `300`)

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

### "Auto-verification did not complete"
- Verification may need manual trigger
- Check backend logs for verification errors
- Verify job has correct verifier tag

### "Failed to approve job"
- Check if verification passed
- Verify job status is "submitted"
- Check backend logs for errors

## Integration with CI/CD

The script returns exit code 0 on success, 1 on failure, making it suitable for CI/CD pipelines:

```bash
if bash scripts/test_run.sh; then
    echo "✅ Workflow test passed"
else
    echo "❌ Workflow test failed"
    exit 1
fi
```

## Next Steps

After a successful test run:
1. Check the job in the UI: `http://sparky1:8000/ui/`
2. Verify learning patterns were stored
3. Check agent memory for reflections
4. Review economy ledger for entries
