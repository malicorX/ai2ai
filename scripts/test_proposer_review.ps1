# Test Proposer-Review Flow
# Creates a job with [verifier:proposer_review], claim+submit as executor, then review as agent_1 (proposer).
# Verifies: backend skips auto_verify (job stays submitted), then proposer review approves it.

param(
    [string]$BackendUrl = "http://sparky1:8000"
)

$ErrorActionPreference = "Stop"

function Write-Status { param([string]$Message, [string]$Color = "White")
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts] $Message" -ForegroundColor $Color
}
function Write-Section { param([string]$Title)
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
}

# Backend ok?
try {
    $null = Invoke-RestMethod -Uri "$BackendUrl/world" -Method Get -TimeoutSec 5
} catch {
    Write-Status "Backend not reachable at $BackendUrl" "Red"
    exit 1
}
Write-Status "Backend OK: $BackendUrl" "Green"

# Run id for tagging
$runId = ""
try { $runId = (Invoke-RestMethod -Uri "$BackendUrl/run" -Method Get -TimeoutSec 5).run_id } catch {}
$runTag = if ($runId) { "[run:$runId] " } else { "" }
$guid = [System.Guid]::NewGuid().ToString().Substring(0,8)
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"

Write-Section "1. Create job with [verifier:proposer_review]"
$jobPayload = @{
    title = "${runTag}[TEST PROPOSER_REVIEW] $guid - $ts"
    body = @"
[verifier:proposer_review]
[reviewer:creator]

Task: Is the Fiverr-style delivery for order $guid done successfully?

Acceptance:
- Deliverable described and evidence of completion (e.g. client approved, order complete).

Evidence required: short description + link or quote if applicable.
"@
    reward = 5.0
    created_by = "agent_1"
}
$createResp = Invoke-RestMethod -Uri "$BackendUrl/jobs/create" -Method Post -Body ($jobPayload | ConvertTo-Json -Depth 6) -ContentType "application/json" -TimeoutSec 10
if (-not $createResp.ok -or -not $createResp.job) {
    Write-Status "Job create failed: $($createResp | ConvertTo-Json -Compress)" "Red"
    exit 1
}
$jobId = $createResp.job.job_id
Write-Status "Job created: $jobId" "Green"

Write-Section "2. Claim as agent_2"
try {
    $claimResp = Invoke-RestMethod -Uri "$BackendUrl/jobs/$jobId/claim" -Method Post -Body '{"agent_id":"agent_2"}' -ContentType "application/json" -TimeoutSec 10
    if ($claimResp.ok) {
        Write-Status "Claimed by agent_2" "Green"
    } else {
        Write-Status "Claim failed (may already be claimed): $($claimResp | ConvertTo-Json -Compress)" "Yellow"
    }
} catch {
    if ($_.Exception.Message -match "409|already") { Write-Status "Already claimed" "Gray" } else { throw }
}

Write-Section "3. Submit deliverable as agent_2"
$submission = @"
## Deliverable
Fiverr-style delivery for order $guid is complete.

## Evidence
- Client approved the delivery.
- Order marked complete on platform.
- Deliverable: 500-word blog post on time travel, delivered on time.
"@
$submitBody = @{ agent_id = "agent_2"; submission = $submission } | ConvertTo-Json
$submitResp = Invoke-RestMethod -Uri "$BackendUrl/jobs/$jobId/submit" -Method Post -Body $submitBody -ContentType "application/json" -TimeoutSec 10
if (-not $submitResp.ok) {
    Write-Status "Submit failed" "Red"
    exit 1
}
Write-Status "Submitted" "Green"

Write-Section "4. Assert job stayed submitted (no auto_verify)"
Start-Sleep -Seconds 1
$j = Invoke-RestMethod -Uri "$BackendUrl/jobs/$jobId" -Method Get -TimeoutSec 5
$j = $j.job
if ($j.status -ne "submitted") {
    Write-Status "Expected status=submitted (proposer_review skips auto_verify), got: $($j.status)" "Red"
    if ($j.auto_verify_ok -ne $null) {
        Write-Status "  auto_verify_ok=$($j.auto_verify_ok) note=$($j.auto_verify_note)" "Red"
    }
    exit 1
}
Write-Status "Job correctly left in submitted (proposer_review)" "Green"

Write-Section "5. Proposer (agent_1) reviews and approves"
$reviewBody = @{
    approved = $true
    reviewed_by = "agent_1"
    note = "Proposer review: deliverable matches task; evidence of completion provided."
    payout = $null
    penalty = $null
} | ConvertTo-Json
$reviewResp = Invoke-RestMethod -Uri "$BackendUrl/jobs/$jobId/review" -Method Post -Body $reviewBody -ContentType "application/json" -TimeoutSec 10
if (-not $reviewResp.ok) {
    Write-Status "Review failed: $($reviewResp | ConvertTo-Json -Compress)" "Red"
    exit 1
}
Write-Status "Review accepted" "Green"

Write-Section "6. Assert job is approved"
Start-Sleep -Seconds 1
$j2 = (Invoke-RestMethod -Uri "$BackendUrl/jobs/$jobId" -Method Get -TimeoutSec 5).job
if ($j2.status -ne "approved") {
    Write-Status "Expected status=approved, got: $($j2.status)" "Red"
    exit 1
}
Write-Status "Job approved, reviewed_by=$($j2.reviewed_by)" "Green"

Write-Section "Done"
Write-Status "Proposer-review flow OK: create -> claim -> submit -> (no auto_verify) -> agent_1 review -> approved" "Green"
Write-Host ""
exit 0
