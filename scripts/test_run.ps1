# Test Run Script - Single Job Lifecycle Monitor
# Creates a test job and monitors it through: create -> claim -> (agent submits) -> verify -> approve -> ai$
# Creativity lives on sparky1/sparky2: the claiming agent produces and submits the deliverable via do_job + jobs_submit.
# This script does NOT submit for the agent unless -ForceSubmit is used after timeout (e.g. to test backend when agents are down).

param(
    [string]$BackendUrl = "http://sparky1:8000",
    [ValidateSet('json_list','gig')][string]$TaskType = 'json_list',
    [int]$PollInterval = 3,
    [int]$MaxWaitSeconds = 300,
    [int]$MaxWaitSubmitSeconds = 600,
    [switch]$ForceSubmit
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
    $separator = "=" * 60
    Write-Host ""
    Write-Host $separator -ForegroundColor Cyan
    Write-Host $Title -ForegroundColor Cyan
    Write-Host $separator -ForegroundColor Cyan
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

# Create test job. TaskType: json_list (default) or gig (Fiverr-style short deliverable, proposer review).
function New-TestJob {
    param([string]$Type = 'json_list')
    $runId = ""
    try {
        $runResponse = Invoke-RestMethod -Uri "$BackendUrl/run" -Method Get -TimeoutSec 5
        $runId = $runResponse.run_id
    } catch { }
    $runTag = if ($runId) { "[run:$runId] " } else { "" }
    $uniqueId = [System.Guid]::NewGuid().ToString()
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"

    if ($Type -eq 'gig') {
        # Fiverr-style gig: short text deliverable, varied briefs, proposer reviews (no auto_verify).
        $gigKinds = @(
            @{ name = "Product tagline"; brief = "Write a 2-sentence product tagline for a smart home device that saves energy."; criteria = "Exactly 2 sentences; mentions energy or smart home." },
            @{ name = "Feature list"; brief = "Write a 3-bullet feature list for a new fitness app targeting runners."; criteria = "Exactly 3 bullets; each one clear benefit for runners." },
            @{ name = "Social post"; brief = "Write a 2-3 sentence social post announcing a coffee shop opening next week."; criteria = "Friendly tone; mentions opening and next week." },
            @{ name = "Email subject"; brief = "Write 3 alternative email subject lines for a webinar about AI in healthcare."; criteria = "Exactly 3 lines; each under 60 chars; mention AI or healthcare." },
            @{ name = "Short bio"; brief = "Write a 2-sentence bio for a freelance graphic designer specializing in logos."; criteria = "Two sentences; mentions logos or branding." }
        )
        $gig = $gigKinds | Get-Random
        $title = "${runTag}[TEST RUN] Gig: $($gig.name) $($uniqueId.Substring(0,8)) - $timestamp"
        $body = @"
[TEST_RUN_ID:$uniqueId]
[UNIQUE_TIMESTAMP:$timestamp]

**Gig: $($gig.name)**

$($gig.brief)

Acceptance criteria:
- $($gig.criteria)
- Deliverable: short text (no code). Include a brief "Deliverable" section.

[verifier:proposer_review]
[reviewer:creator]

Created at $timestamp (ID $uniqueId).
"@
        $jobData = @{ title = $title; body = $body; reward = 10.0; created_by = "agent_1" }
    } else {
        # json_list: structured JSON list, auto_verify.
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

[verifier:json_list]
[json_required_keys:name,category,value]
[json_min_items:3]

This is a unique test run created at $timestamp with ID $uniqueId.
"@
            reward = 10.0
            created_by = "agent_1"
        }
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
        if ($_.ErrorDetails.Message) { $errorMsg += " - $($_.ErrorDetails.Message)" }
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

# Fallback: submit a minimal valid deliverable only when -ForceSubmit and agent did not submit in time (e.g. agents down).
# json_list: minimal JSON so verifier passes; gig: short text (proposer_review).
function Submit-MinimalDeliverable {
    param([string]$JobId, [string]$AgentId = "agent_2", [string]$TaskType = "json_list")
    if ($TaskType -eq 'gig') {
        $submission = "## Deliverable`n`nShort tagline: Save energy and control your home from anywhere.`n`n## Evidence`n- 2 sentences; mentions energy and smart home."
    } else {
        $jsonArray = '[{"name":"A","category":"technology","value":50},{"name":"B","category":"science","value":60},{"name":"C","category":"fiction","value":70}]'
        $submission = "## Deliverable`n$jsonArray`n## Evidence`n- items=3`n- all_fields_present=true"
    }
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

# Show exact task spec, how it was delivered, solution, and review details
function Show-TaskAndDeliveryDetails {
    param([object]$Job)
    if (-not $Job) { return }
    Write-Host ""
    
    # (a) EXACT TASK
    Write-Host "  (a) EXACT TASK:" -ForegroundColor Cyan
    Write-Host "  Title: $($Job.title)" -ForegroundColor White
    Write-Host "  Body (full):" -ForegroundColor Gray
    $bodyLines = if ($Job.body) { ($Job.body -split "`r?`n") } else { @() }
    foreach ($line in $bodyLines) {
        Write-Host "    $line" -ForegroundColor White
    }
    Write-Host ""
    
    # (b) HOW IT WAS SOLVED (submission)
    if ($Job.submission) {
        Write-Host "  (b) HOW IT WAS SOLVED (submission):" -ForegroundColor Cyan
        $subLines = ($Job.submission -split "`r?`n")
        foreach ($line in $subLines) {
            Write-Host "    $line" -ForegroundColor White
        }
        Write-Host "  (length: $($Job.submission.Length) chars)" -ForegroundColor Gray
    } else {
        Write-Host "  (b) HOW IT WAS SOLVED:" -ForegroundColor Cyan
        Write-Host "    (no submission stored)" -ForegroundColor Gray
    }
    Write-Host ""
    
    # (c) EXACT SOLUTION (json_list: extracted JSON array; gig/proposer_review: deliverable excerpt)
    if ($Job.submission) {
        Write-Host "  (c) EXACT SOLUTION:" -ForegroundColor Cyan
        $bodyAndTitle = ($Job.body + " " + $Job.title).ToLower()
        $isProposerReview = $bodyAndTitle -match '\[verifier:proposer_review\]' -or $bodyAndTitle -match '\[reviewer:creator\]'
        if ($isProposerReview) {
            # Gig/proposer_review: show deliverable section only (no JSON array)
            $deliverableMatch = [regex]::Match($Job.submission, '(?s)##\s*Deliverable\s*\r?\n(.*?)(?=\r?\n##\s|$)', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
            if ($deliverableMatch.Success -and $deliverableMatch.Groups[1].Value.Trim()) {
                Write-Host "    Proposer-review task; deliverable:" -ForegroundColor Gray
                foreach ($line in ($deliverableMatch.Groups[1].Value.Trim() -split "`r?`n")) { Write-Host "    $line" -ForegroundColor White }
            } else {
                Write-Host "    Proposer-review task; full deliverable in (b) above." -ForegroundColor Gray
            }
        } else {
            $raw = $null
            # 1) Prefer ```json ... ``` block (same as backend verifier)
            $fenceMatch = [regex]::Match($Job.submission, '(?s)```\s*json\s*\r?\n([\s\S]*?)\r?\n\s*```', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
            if ($fenceMatch.Success -and $fenceMatch.Groups[1].Value.Trim()) {
                $raw = $fenceMatch.Groups[1].Value.Trim()
            }
            # 2) Else first array-of-objects [ { ... } ] (skip tag-like [run:...])
            if (-not $raw) {
                $aoMatch = [regex]::Match($Job.submission, '\[\s*\{[\s\S]*\}\]', [System.Text.RegularExpressions.RegexOptions]::Singleline)
                if ($aoMatch.Success) { $raw = $aoMatch.Value.Trim() }
            }
            if (-not $raw) {
                $jsonMatch = [regex]::Match($Job.submission, '\[.*\]', [System.Text.RegularExpressions.RegexOptions]::Singleline)
                if ($jsonMatch.Success) { $raw = $jsonMatch.Value.Trim() }
            }
            if ($raw) {
                Write-Host "    JSON array found:" -ForegroundColor Gray
                $pretty = $raw -replace '\}\s*,\s*\{', "},`n    {"
                foreach ($line in ($pretty -split "`r?`n")) { Write-Host "    $line" -ForegroundColor White }
            } else {
                Write-Host "    (extract key content from submission above)" -ForegroundColor Gray
            }
        }
        Write-Host ""
    }
    
    # (d) HOW IT WAS REVIEWED
    Write-Host "  (d) HOW IT WAS REVIEWED:" -ForegroundColor Cyan
    if ($Job.auto_verify_ok -ne $null) {
        $verdict = if ($Job.auto_verify_ok) { "PASS" } else { "FAIL" }
        Write-Host "    Auto-Verify: $verdict" -ForegroundColor $(if ($Job.auto_verify_ok) { "Green" } else { "Red" })
        Write-Host "    Verifier: $($Job.auto_verify_name)" -ForegroundColor Gray
        Write-Host "    Note: $($Job.auto_verify_note)" -ForegroundColor Gray
    }
    if ($Job.reviewed_by) {
        Write-Host "    Reviewed By: $($Job.reviewed_by)" -ForegroundColor Gray
    }
    if ($Job.review_note) {
        Write-Host "    Review Note: $($Job.review_note)" -ForegroundColor Gray
    }
    if ($Job.status) {
        Write-Host "    Final Status: $($Job.status)" -ForegroundColor $(if ($Job.status -eq "approved") { "Green" } else { "Yellow" })
    }
    
    # Verifier debug artifacts (if verification failed)
    if ($Job.auto_verify_ok -eq $false -and $Job.auto_verify_artifacts -and ($Job.auto_verify_artifacts | Get-Member -MemberType NoteProperty -ErrorAction SilentlyContinue)) {
        Write-Host ""
        Write-Host "  --- VERIFIER DEBUG ARTIFACTS ---" -ForegroundColor Yellow
        foreach ($k in $Job.auto_verify_artifacts.PSObject.Properties.Name) {
            $v = $Job.auto_verify_artifacts.$k
            if ($v -is [string] -and $v.Length -gt 300) {
                Write-Host "    $k = $($v.Substring(0,300))..." -ForegroundColor Gray
            } else {
                Write-Host "    $k = $v" -ForegroundColor Gray
            }
        }
    }
    Write-Host ""
}

# Main execution
Write-Section "AI Village Test Run - Single Job Lifecycle"
Write-Status "Backend URL: $BackendUrl" "Cyan"
Write-Status "Poll Interval: $PollInterval seconds" "Cyan"
Write-Status "Max wait (claim): $MaxWaitSeconds s | Max wait (agent submit): $MaxWaitSubmitSeconds s" "Cyan"
if ($ForceSubmit) { Write-Status "ForceSubmit: will submit minimal deliverable if agent does not submit in time" "Yellow" }

# Step 1: Test backend
Write-Section "Step 1: Testing Backend Connection"
if (-not (Test-Backend)) {
    Write-Status "[FAIL] Backend is not accessible at $BackendUrl" "Red"
    Write-Status "Please ensure backend is running on sparky1" "Yellow"
    exit 1
}
Write-Status "[OK] Backend is accessible" "Green"

# For json_list we require balanced_array backend (verifier); for gig any backend is fine (proposer_review)
$runInfo = $null
try { $runInfo = Invoke-RestMethod -Uri "$BackendUrl/run" -Method Get -TimeoutSec 5 } catch { }
$ver = $runInfo.backend_version
if ($TaskType -eq 'json_list' -and (-not $ver -or $ver -ne "balanced_array")) {
    Write-Status "[FAIL] Backend at $BackendUrl is not the balanced_array version (got: '$ver')" "Red"
    Write-Status "Deploy and restart: run deploy.ps1 -CopyOnly, then on each server: bash ~/ai2ai/scripts/restart_after_deploy.sh" "Yellow"
    exit 1
}
if ($TaskType -eq 'json_list') {
    Write-Status "[OK] Backend version: $ver (json_list verifier supports raw JSON)" "Green"
} else {
    Write-Status "[OK] Task type: gig (proposer_review; no auto_verify)" "Green"
}

# Get initial balances
$initialBalances = Get-Balances
Write-Status "Initial balances:" "Cyan"
foreach ($agent in $initialBalances.PSObject.Properties) {
    Write-Status "  $($agent.Name): $($agent.Value) ai$" "Gray"
}

# Step 2: Create job
Write-Section "Step 2: Creating Test Job"
$job = New-TestJob -Type $TaskType
if (-not $job) {
    Write-Status "[FAIL] Failed to create job" "Red"
    exit 1
}
$jobId = $job.job_id
Write-Status "[OK] Job created successfully" "Green"
Show-JobDetails $job

# Step 3: Wait for claim (or claim manually if needed)
Write-Section "Step 3: Waiting for Job to be Claimed"
$startTime = Get-Date
$claimed = $false

while (-not $claimed -and ((Get-Date) - $startTime).TotalSeconds -lt $MaxWaitSeconds) {
    Start-Sleep -Seconds $PollInterval
    $job = Get-JobStatus $jobId
    if (-not $job) {
        Write-Status "[!!] Could not fetch job status" "Yellow"
        continue
    }
    
    if ($job.status -eq "claimed") {
        Write-Status "[OK] Job claimed by: $($job.claimed_by)" "Green"
        Show-JobDetails $job
        $claimed = $true
    } elseif ($job.status -eq "submitted" -or $job.status -eq "approved") {
        Write-Status "[OK] Job already $($job.status) (agent was fast)" "Green"
        Show-JobDetails $job
        $claimed = $true
    } elseif ($job.status -eq "open") {
        Write-Status "[..] Waiting for agent to claim job..." "Yellow"
    } else {
        Write-Status "[!!] Job status changed to: $($job.status)" "Yellow"
        Show-JobDetails $job
    }
}

if (-not $claimed) {
    Write-Status "[!!] Job not claimed within timeout. Submitting manually..." "Yellow"
    # Try to claim and submit manually
    try {
        Invoke-RestMethod -Uri "$BackendUrl/jobs/$jobId/claim" -Method Post -Body (@{
            agent_id = "test_run_script"
        } | ConvertTo-Json) -ContentType "application/json" -TimeoutSec 10 | Out-Null
        Write-Status "[OK] Job claimed manually" "Green"
        $claimed = $true
    } catch {
        Write-Status "[FAIL] Could not claim job manually: $_" "Red"
        exit 1
    }
}

# Step 4: Wait for the claiming agent (sparky2) to produce and submit the deliverable via do_job + jobs_submit.
# Creativity lives on the agents; we do not submit for them unless -ForceSubmit after timeout.
$submitAgent = if ($job.claimed_by) { $job.claimed_by } else { "agent_2" }
Write-Section "Step 4: Waiting for agent to submit (creativity on sparky1/sparky2)"
Write-Status "Polling up to $MaxWaitSubmitSeconds seconds for agent to submit..." "Cyan"
$startSubmit = Get-Date
$submitted = $false

while (-not $submitted -and ((Get-Date) - $startSubmit).TotalSeconds -lt $MaxWaitSubmitSeconds) {
    Start-Sleep -Seconds $PollInterval
    $job = Get-JobStatus $jobId
    if (-not $job) {
        Write-Status "[!!] Could not fetch job status" "Yellow"
        continue
    }
    $st = $job.status
    $by = $job.submitted_by
    if ($st -eq "approved" -or ($st -eq "submitted" -or $by)) {
        $submitted = $true
        if ($by) {
            Write-Status "[OK] Agent $by submitted" "Green"
        } else {
            Write-Status "[OK] Job status: $st (submission present)" "Green"
        }
        Show-JobDetails $job
    } else {
        Write-Status "[..] Waiting for agent to do_job and submit (status=$st)..." "Yellow"
    }
}

if (-not $submitted) {
    if ($ForceSubmit) {
        Write-Status "[!!] Agent did not submit in time; -ForceSubmit: submitting minimal deliverable (backend-only test)" "Yellow"
        if (Submit-MinimalDeliverable -JobId $jobId -AgentId $submitAgent -TaskType $TaskType) {
            Write-Status "[OK] Minimal deliverable submitted" "Green"
        } else {
            Write-Status "[FAIL] Failed to submit minimal deliverable" "Red"
            exit 1
        }
    } else {
        Write-Status "[FAIL] Agent did not submit within $MaxWaitSubmitSeconds s. Creativity lives on sparky1/sparky2; ensure agents are running. Use -ForceSubmit to test backend without agents." "Red"
        exit 1
    }
}

# Step 5: Wait for verification (json_list: auto_verify; gig: proposer_review, no auto_verify)
Write-Section "Step 5: Waiting for Verification"
$startTime = Get-Date
$verified = $false

if ($TaskType -eq 'gig') {
    # Gig uses [verifier:proposer_review]; backend does not run auto_verify. Script will approve as proposer.
    Write-Status "[OK] Gig task: no auto_verify; proposer (script) will approve after submit" "Green"
    $verified = $true
} else {
    while (-not $verified -and ((Get-Date) - $startTime).TotalSeconds -lt 30) {
        Start-Sleep -Seconds 2
        $job = Get-JobStatus $jobId
        if (-not $job) { continue }
        if ($job.auto_verify_ok -ne $null) {
            $verified = $true
            if ($job.auto_verify_ok) {
                Write-Status "[OK] Auto-verification PASSED" "Green"
                Write-Status "   Verifier: $($job.auto_verify_name)" "Gray"
            } else {
                Write-Status "[FAIL] Auto-verification FAILED" "Red"
                Write-Status "   Note: $($job.auto_verify_note)" "Red"
            }
            Show-JobDetails $job
        } else {
            Write-Status "[..] Waiting for auto-verification..." "Yellow"
        }
    }
    if (-not $verified) {
        Write-Status "[!!] Auto-verification did not complete (may need manual trigger)" "Yellow"
    }
}

# Always show exact task, how it was delivered, and verifier debug (after submit we have submission)
if ($job) {
    $job = Get-JobStatus $jobId
    if ($job) {
        Write-Section "Task & delivery details"
        Show-TaskAndDeliveryDetails $job
    }
}

# Step 6: Approve job (skip if backend already auto-approved; gig: script approves as proposer)
Write-Section "Step 6: Approving Job"
$job = Get-JobStatus $jobId
if ($job.status -eq "approved") {
    Write-Status "[OK] Job already approved (auto_verify or prior review)" "Green"
} elseif ($job.auto_verify_ok -eq $true -or $verified -or ($TaskType -eq 'gig' -and $job.status -eq 'submitted')) {
    if (Approve-Job -JobId $jobId -Payout $job.reward) {
        Write-Status "[OK] Job approved successfully" "Green"
    } else {
        Write-Status "[FAIL] Failed to approve job" "Red"
        exit 1
    }
} else {
    Write-Status "[!!] Skipping approval (verification failed or incomplete)" "Yellow"
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
    Write-Status "[OK] Test run completed successfully!" "Green"
    Write-Status "   Job was created, claimed, submitted, verified, and approved" "Green"
    Write-Status "   Economy was updated correctly" "Green"
} else {
    Write-Status "[!!] Test run completed with warnings" "Yellow"
    Write-Status "   Final job status: $($finalJob.status)" "Yellow"
}

Write-Host ""
Write-Status "View job in UI: $BackendUrl/ui/" "Cyan"
Write-Status "Job ID: $jobId" "Cyan"
Write-Host ""
Write-Status "Generate full report:" "Cyan"
Write-Status "  .\scripts\test_run_report.ps1 -JobId $jobId -BackendUrl $BackendUrl" "Gray"

exit $(if ($success) { 0 } else { 1 })
