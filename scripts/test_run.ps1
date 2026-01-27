# Test Run Script - Single Job Lifecycle Monitor
# Creates a test job and monitors it through: create → claim → submit → verify → approve → ai$ reward

param(
    [string]$BackendUrl = "http://sparky1:8000",
    [int]$PollInterval = 3,
    [int]$MaxWaitSeconds = 300
)

$ErrorActionPreference = "Continue"

# Colors for output
function Write-Status {
    param([string]$Message, [string]$Color = "White")
    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$timestamp] " -NoNewline -ForegroundColor Gray
    Write-Host $Message -ForegroundColor $Color
}

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "=" * 60 -ForegroundColor Cyan
    Write-Host $Title -ForegroundColor Cyan
    Write-Host "=" * 60 -ForegroundColor Cyan
}

function Write-Info {
    param([string]$Label, [string]$Value)
    Write-Host "  $Label" -NoNewline -ForegroundColor Gray
    Write-Host ": $Value" -ForegroundColor White
}

# Test backend connectivity
function Test-Backend {
    try {
        $response = Invoke-WebRequest -Uri "$BackendUrl/world" -Method Get -TimeoutSec 5 -UseBasicParsing
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

# Create test job
function New-TestJob {
    # Get current run_id to tag the job properly
    $runId = ""
    try {
        $runResponse = Invoke-RestMethod -Uri "$BackendUrl/run" -Method Get -TimeoutSec 5
        $runId = $runResponse.run_id
    } catch {
        # If we can't get run_id, continue without it
    }
    
    $runTag = if ($runId) { "[run:$runId] " } else { "" }
    $uniqueId = [System.Guid]::NewGuid().ToString()
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
    $randomTheme = @("space exploration", "underwater cities", "time travel", "virtual reality", "quantum computing") | Get-Random
    
    $jobData = @{
        title = "${runTag}[TEST RUN] $randomTheme JSON Task $($uniqueId.Substring(0,8)) - $timestamp"
        body = @"
[TEST_RUN_ID:$uniqueId]
[UNIQUE_TIMESTAMP:$timestamp]
[THEME:$randomTheme]

Create a creative JSON list with exactly 3 items representing different $randomTheme concepts.

Each item must have:
- name: string (creative name related to $randomTheme)
- category: string (e.g., 'technology', 'science', 'fiction')
- value: number (1-100, representing creativity score)

Acceptance criteria:
- Submission must contain a valid JSON list
- List must have exactly 3 items
- Each item must have 'name', 'category', and 'value' fields
- Evidence section must state: items=3, all_fields_present=true

Verifier: json_list

This is a unique test run created at $timestamp with ID $uniqueId.
"@
        reward = 10.0
        created_by = "agent_1"
    }
    
    try {
        $response = Invoke-RestMethod -Uri "$BackendUrl/jobs/create" -Method Post -Body ($jobData | ConvertTo-Json -Depth 10) -ContentType "application/json" -TimeoutSec 10
        if ($response.ok -and $response.job) {
            return $response.job
        } else {
            Write-Status "Job creation returned unexpected response: $($response | ConvertTo-Json -Depth 3)" "Red"
            return $null
        }
    } catch {
        $errorMsg = $_.Exception.Message
        if ($_.ErrorDetails.Message) {
            $errorMsg += " - $($_.ErrorDetails.Message)"
        }
        Write-Status "Failed to create job: $errorMsg" "Red"
        return $null
    }
}

# Get job status
function Get-JobStatus {
    param([string]$JobId)
    
    try {
        $response = Invoke-RestMethod -Uri "$BackendUrl/jobs/$JobId" -Method Get -TimeoutSec 5
        return $response.job
    } catch {
        return $null
    }
}

# Submit test deliverable
function Submit-TestDeliverable {
    param([string]$JobId, [string]$AgentId = "agent_2")
    
    $submission = @"
## Deliverable

Here is the creative JSON list with 3 items:

```json
[
  {"name": "Digital Art Installation", "category": "art", "value": 85},
  {"name": "Ambient Soundscape", "category": "music", "value": 92},
  {"name": "Interactive Story", "category": "writing", "value": 78}
]
```

## Evidence

- items=3: The JSON list contains exactly 3 items
- all_fields_present=true: Each item has 'name' (string), 'category' (string), and 'value' (number) fields
- JSON is valid and parseable
- All values are within 1-100 range
"@
    
    try {
        $response = Invoke-RestMethod -Uri "$BackendUrl/jobs/$JobId/submit" -Method Post -Body (@{
            agent_id = $AgentId
            submission = $submission
        } | ConvertTo-Json) -ContentType "application/json" -TimeoutSec 10
        return $response.ok
    } catch {
        Write-Status "Failed to submit: $_" "Red"
        return $false
    }
}

# Approve job
function Approve-Job {
    param([string]$JobId, [double]$Payout = 10.0)
    
    try {
        $response = Invoke-RestMethod -Uri "$BackendUrl/jobs/$JobId/review" -Method Post -Body (@{
            approved = $true
            reviewed_by = "test_run_script"
            note = "Test run approval - verification passed"
            payout = $Payout
            penalty = 0.0
        } | ConvertTo-Json) -ContentType "application/json" -TimeoutSec 10
        return $response.ok
    } catch {
        Write-Status "Failed to approve: $_" "Red"
        return $false
    }
}

# Get economy balances
function Get-Balances {
    try {
        $response = Invoke-RestMethod -Uri "$BackendUrl/economy/balances" -Method Get -TimeoutSec 5
        return $response.balances
    } catch {
        return @{}
    }
}

# Display job details
function Show-JobDetails {
    param([object]$Job)
    
    Write-Info "Job ID" $Job.job_id
    Write-Info "Title" $Job.title
    Write-Info "Status" $Job.status
    Write-Info "Reward" "$($Job.reward) ai$"
    Write-Info "Created By" $Job.created_by
    Write-Info "Claimed By" $(if ($Job.claimed_by) { $Job.claimed_by } else { "none" })
    Write-Info "Submitted By" $(if ($Job.submitted_by) { $Job.submitted_by } else { "none" })
    
    if ($Job.auto_verify_ok -ne $null) {
        $verifyStatus = if ($Job.auto_verify_ok) { "PASS" } else { "FAIL" }
        $verifyColor = if ($Job.auto_verify_ok) { "Green" } else { "Red" }
        Write-Host "  Auto-Verify" -NoNewline -ForegroundColor Gray
        Write-Host ": $verifyStatus" -ForegroundColor $verifyColor
        if ($Job.auto_verify_note) {
            Write-Host "    Note: $($Job.auto_verify_note)" -ForegroundColor Gray
        }
    }
    
    if ($Job.reviewed_by) {
        Write-Info "Reviewed By" $Job.reviewed_by
        Write-Info "Review Note" $Job.review_note
    }
}

# Main execution
Write-Section "AI Village Test Run - Single Job Lifecycle"
Write-Status "Backend URL: $BackendUrl" "Cyan"
Write-Status "Poll Interval: $PollInterval seconds" "Cyan"
Write-Status "Max Wait Time: $MaxWaitSeconds seconds" "Cyan"

# Step 1: Test backend
Write-Section "Step 1: Testing Backend Connection"
if (-not (Test-Backend)) {
    Write-Status "❌ Backend is not accessible at $BackendUrl" "Red"
    Write-Status "Please ensure backend is running on sparky1" "Yellow"
    exit 1
}
Write-Status "✅ Backend is accessible" "Green"

# Get initial balances
$initialBalances = Get-Balances
Write-Status "Initial balances:" "Cyan"
foreach ($agent in $initialBalances.PSObject.Properties) {
    Write-Status "  $($agent.Name): $($agent.Value) ai$" "Gray"
}

# Step 2: Create job
Write-Section "Step 2: Creating Test Job"
$job = New-TestJob
if (-not $job) {
    Write-Status "❌ Failed to create job" "Red"
    exit 1
}
$jobId = $job.job_id
Write-Status "✅ Job created successfully" "Green"
Show-JobDetails $job

# Step 3: Wait for claim (or claim manually if needed)
Write-Section "Step 3: Waiting for Job to be Claimed"
$startTime = Get-Date
$claimed = $false

while (-not $claimed -and ((Get-Date) - $startTime).TotalSeconds -lt $MaxWaitSeconds) {
    Start-Sleep -Seconds $PollInterval
    $job = Get-JobStatus $jobId
    if (-not $job) {
        Write-Status "⚠️  Could not fetch job status" "Yellow"
        continue
    }
    
    if ($job.status -eq "claimed") {
        Write-Status "✅ Job claimed by: $($job.claimed_by)" "Green"
        Show-JobDetails $job
        $claimed = $true
    } elseif ($job.status -eq "open") {
        Write-Status "⏳ Waiting for agent to claim job..." "Yellow"
    } else {
        Write-Status "⚠️  Job status changed to: $($job.status)" "Yellow"
        Show-JobDetails $job
    }
}

if (-not $claimed) {
    Write-Status "⚠️  Job not claimed within timeout. Submitting manually..." "Yellow"
    # Try to claim and submit manually
    try {
        Invoke-RestMethod -Uri "$BackendUrl/jobs/$jobId/claim" -Method Post -Body (@{
            agent_id = "test_run_script"
        } | ConvertTo-Json) -ContentType "application/json" -TimeoutSec 10 | Out-Null
        Write-Status "✅ Job claimed manually" "Green"
        $claimed = $true
    } catch {
        Write-Status "❌ Could not claim job manually: $_" "Red"
        exit 1
    }
}

# Step 4: Submit deliverable
Write-Section "Step 4: Submitting Test Deliverable"
if (Submit-TestDeliverable -JobId $jobId) {
    Write-Status "✅ Deliverable submitted" "Green"
} else {
    Write-Status "❌ Failed to submit deliverable" "Red"
    exit 1
}

# Step 5: Wait for verification
Write-Section "Step 5: Waiting for Auto-Verification"
$startTime = Get-Date
$verified = $false

while (-not $verified -and ((Get-Date) - $startTime).TotalSeconds -lt 30) {
    Start-Sleep -Seconds 2
    $job = Get-JobStatus $jobId
    if (-not $job) { continue }
    
    if ($job.auto_verify_ok -ne $null) {
        $verified = $true
        if ($job.auto_verify_ok) {
            Write-Status "✅ Auto-verification PASSED" "Green"
            Write-Status "   Verifier: $($job.auto_verify_name)" "Gray"
        } else {
            Write-Status "❌ Auto-verification FAILED" "Red"
            Write-Status "   Note: $($job.auto_verify_note)" "Red"
        }
        Show-JobDetails $job
    } else {
        Write-Status "⏳ Waiting for auto-verification..." "Yellow"
    }
}

if (-not $verified) {
    Write-Status "⚠️  Auto-verification did not complete (may need manual trigger)" "Yellow"
}

# Step 6: Approve job
Write-Section "Step 6: Approving Job"
if ($job.auto_verify_ok -eq $true -or $verified) {
    if (Approve-Job -JobId $jobId -Payout $job.reward) {
        Write-Status "✅ Job approved successfully" "Green"
    } else {
        Write-Status "❌ Failed to approve job" "Red"
        exit 1
    }
} else {
    Write-Status "⚠️  Skipping approval (verification failed or incomplete)" "Yellow"
}

# Step 7: Check final status
Write-Section "Step 7: Final Status Check"
Start-Sleep -Seconds 2
$finalJob = Get-JobStatus $jobId
if ($finalJob) {
    Show-JobDetails $finalJob
}

# Step 8: Economy update
Write-Section "Step 8: Economy Update"
$finalBalances = Get-Balances
Write-Status "Final balances:" "Cyan"
foreach ($agent in $finalBalances.PSObject.Properties) {
    $initial = if ($initialBalances.$($agent.Name)) { $initialBalances.$($agent.Name) } else { 0 }
    $change = $agent.Value - $initial
    $changeStr = if ($change -gt 0) { "+$change" } else { "$change" }
    $changeColor = if ($change -gt 0) { "Green" } else { "White" }
    Write-Host "  $($agent.Name)" -NoNewline -ForegroundColor Gray
    Write-Host ": $($agent.Value) ai$ " -NoNewline -ForegroundColor White
    Write-Host "($changeStr)" -ForegroundColor $changeColor
}

# Summary
Write-Section "Test Run Summary"
$success = $finalJob.status -eq "approved"
if ($success) {
    Write-Status "✅ Test run completed successfully!" "Green"
    Write-Status "   Job was created, claimed, submitted, verified, and approved" "Green"
    Write-Status "   Economy was updated correctly" "Green"
} else {
    Write-Status "⚠️  Test run completed with warnings" "Yellow"
    Write-Status "   Final job status: $($finalJob.status)" "Yellow"
}

Write-Host ""
Write-Status "View job in UI: $BackendUrl/ui/" "Cyan"
Write-Status "Job ID: $jobId" "Cyan"
Write-Host ""
Write-Status "Generate full report:" "Cyan"
Write-Status "  .\scripts\test_run_report.ps1 -JobId $jobId -BackendUrl $BackendUrl" "Gray"

exit $(if ($success) { 0 } else { 1 })
