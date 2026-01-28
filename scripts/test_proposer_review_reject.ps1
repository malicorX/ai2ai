# Test Proposer-Review Reject Flow
# Same as proposer-review but agent_1 **rejects** with a penalty. Verifies job -> rejected and executor balance decreases.

param(
    [string]$BackendUrl = "http://sparky1:8000",
    [double]$PenaltyAmount = 1.0
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

try {
    $null = Invoke-RestMethod -Uri "$BackendUrl/world" -Method Get -TimeoutSec 5
} catch {
    Write-Status "Backend not reachable at $BackendUrl" "Red"
    exit 1
}
Write-Status "Backend OK: $BackendUrl" "Green"

$runId = ""
try { $runId = (Invoke-RestMethod -Uri "$BackendUrl/run" -Method Get -TimeoutSec 5).run_id } catch {}
$runTag = if ($runId) { "[run:$runId] " } else { "" }
$guid = [System.Guid]::NewGuid().ToString().Substring(0,8)
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"

Write-Section "1. Create job with [verifier:proposer_review]"
$jobPayload = @{
    title = "${runTag}[TEST PROPOSER_REJECT] $guid - $ts"
    body = @"
[verifier:proposer_review]
[reviewer:creator]

Task: Is the Fiverr-style delivery for order $guid done successfully?

Acceptance:
- Deliverable described and evidence of completion.

Evidence required: short description + link or quote.
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
    if ($claimResp.ok) { Write-Status "Claimed by agent_2" "Green" } else { Write-Status "Claim failed" "Yellow" }
} catch { if ($_.Exception.Message -match "409|already") { Write-Status "Already claimed" "Gray" } else { throw } }

Write-Section "3. Submit deliverable as agent_2"
$submission = @"
## Deliverable
Delivery for order $guid is incomplete (test reject path).

## Evidence
- None; intentionally weak for reject test.
"@
$submitBody = @{ agent_id = "agent_2"; submission = $submission } | ConvertTo-Json
$submitResp = Invoke-RestMethod -Uri "$BackendUrl/jobs/$jobId/submit" -Method Post -Body $submitBody -ContentType "application/json" -TimeoutSec 10
if (-not $submitResp.ok) { Write-Status "Submit failed" "Red"; exit 1 }
Write-Status "Submitted" "Green"

Write-Section "4. Assert job stayed submitted"
Start-Sleep -Seconds 1
$j = (Invoke-RestMethod -Uri "$BackendUrl/jobs/$jobId" -Method Get -TimeoutSec 5).job
if ($j.status -ne "submitted") {
    Write-Status "Expected status=submitted, got: $($j.status)" "Red"
    exit 1
}
Write-Status "Job in submitted (proposer_review)" "Green"

$balBefore = $null
try {
    $balResp = Invoke-RestMethod -Uri "$BackendUrl/economy/balances" -Method Get -TimeoutSec 5
    if ($balResp.balances -and $balResp.balances.PSObject.Properties["agent_2"]) {
        $balBefore = [double]$balResp.balances.agent_2
        Write-Status "agent_2 balance before review: $balBefore" "Gray"
    }
} catch { Write-Status "Could not get balances (optional)" "Gray" }

Write-Section "5. Proposer (agent_1) rejects with penalty=$PenaltyAmount"
$reviewBody = @{
    approved = $false
    reviewed_by = "agent_1"
    note = "Proposer review (reject test): deliverable does not meet acceptance criteria."
    payout = $null
    penalty = $PenaltyAmount
} | ConvertTo-Json
$reviewResp = Invoke-RestMethod -Uri "$BackendUrl/jobs/$jobId/review" -Method Post -Body $reviewBody -ContentType "application/json" -TimeoutSec 10
if (-not $reviewResp.ok) {
    Write-Status "Review failed: $($reviewResp | ConvertTo-Json -Compress)" "Red"
    exit 1
}
Write-Status "Reject+penalty review accepted" "Green"

Write-Section "6. Assert job is rejected"
Start-Sleep -Seconds 1
$j2 = (Invoke-RestMethod -Uri "$BackendUrl/jobs/$jobId" -Method Get -TimeoutSec 5).job
if ($j2.status -ne "rejected") {
    Write-Status "Expected status=rejected, got: $($j2.status)" "Red"
    exit 1
}
Write-Status "Job rejected, reviewed_by=$($j2.reviewed_by)" "Green"

if ($balBefore -ne $null) {
    $balAfter = $null
    try {
        $balResp2 = Invoke-RestMethod -Uri "$BackendUrl/economy/balances" -Method Get -TimeoutSec 5
        if ($balResp2.balances -and $balResp2.balances.PSObject.Properties["agent_2"]) {
            $balAfter = [double]$balResp2.balances.agent_2
            $delta = $balAfter - $balBefore
            if ($delta -lt 0 -and [Math]::Abs($delta + $PenaltyAmount) -lt 0.01) {
                Write-Status "agent_2 balance decreased by penalty: $balBefore -> $balAfter (delta $delta)" "Green"
            } else {
                Write-Status "agent_2 balance: $balBefore -> $balAfter (expected drop ~$PenaltyAmount)" "Yellow"
            }
        }
    } catch { Write-Status "Could not verify balance change (optional)" "Gray" }
}

Write-Section "Done"
Write-Status "Proposer-review REJECT flow OK: create -> claim -> submit -> agent_1 reject (penalty=$PenaltyAmount) -> rejected" "Green"
Write-Host ""
exit 0
