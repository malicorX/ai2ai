# Comprehensive Test Run Report - Shows all details about task, solution, and rating/approval

param(
    [string]$BackendUrl = "http://sparky1:8000",
    [string]$JobId = ""
)

$ErrorActionPreference = "Continue"

function Write-Section {
    param([string]$Title, [string]$Color = "Cyan")
    Write-Host ""
    Write-Host "=" * 80 -ForegroundColor $Color
    Write-Host $Title -ForegroundColor $Color
    Write-Host "=" * 80 -ForegroundColor $Color
}

function Write-Info {
    param([string]$Label, [string]$Value, [string]$Color = "White")
    Write-Host "  $Label" -NoNewline -ForegroundColor Gray
    Write-Host ": $Value" -ForegroundColor $Color
}

function Write-Subsection {
    param([string]$Title)
    Write-Host ""
    Write-Host "  ─ $Title ─" -ForegroundColor Yellow
}

function Format-Timestamp {
    param([double]$Timestamp)
    if ($Timestamp -and $Timestamp -gt 0) {
        $epoch = Get-Date -Date "1970-01-01 00:00:00"
        $date = $epoch.AddSeconds($Timestamp)
        return $date.ToString("yyyy-MM-dd HH:mm:ss.fff")
    }
    return "N/A"
}

function Format-JSON {
    param([string]$JsonString)
    try {
        $obj = $JsonString | ConvertFrom-Json
        return ($obj | ConvertTo-Json -Depth 10)
    } catch {
        return $JsonString
    }
}

# Get job details
if (-not $JobId) {
    Write-Host "Usage: .\test_run_report.ps1 -JobId <job_id>" -ForegroundColor Red
    Write-Host "Or: .\test_run_report.ps1 -JobId <job_id> -BackendUrl http://sparky1:8000" -ForegroundColor Gray
    exit 1
}

Write-Section "Comprehensive Job Report" "Cyan"
Write-Info "Job ID" $JobId "White"
Write-Info "Backend URL" $BackendUrl "Gray"
Write-Info "Report Generated" (Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff") "Gray"

try {
    $job = Invoke-RestMethod -Uri "$BackendUrl/jobs/$JobId" -Method Get -TimeoutSec 10
    $job = $job.job
} catch {
    Write-Host "❌ Failed to fetch job: $_" -ForegroundColor Red
    exit 1
}

# ============================================================================
# SECTION 1: TASK DETAILS
# ============================================================================
Write-Section "1. TASK DETAILS" "Green"

Write-Subsection "Basic Information"
Write-Info "Job ID" $job.job_id
Write-Info "Title" $job.title
Write-Info "Status" $job.status
Write-Info "Reward" "$($job.reward) ai$"
Write-Info "Reward Mode" $job.reward_mode
Write-Info "Source" $job.source
Write-Info "Fingerprint" $job.fingerprint

Write-Subsection "Timeline"
Write-Info "Created At" (Format-Timestamp $job.created_at)
Write-Info "Created By" $job.created_by
Write-Info "Claimed At" (Format-Timestamp $job.claimed_at)
Write-Info "Claimed By" $(if ($job.claimed_by) { $job.claimed_by } else { "N/A" })
Write-Info "Submitted At" (Format-Timestamp $job.submitted_at)
Write-Info "Submitted By" $(if ($job.submitted_by) { $job.submitted_by } else { "N/A" })
Write-Info "Reviewed At" (Format-Timestamp $job.reviewed_at)
Write-Info "Reviewed By" $(if ($job.reviewed_by) { $job.reviewed_by } else { "N/A" })
Write-Info "Auto-Verified At" (Format-Timestamp $job.auto_verified_at)

Write-Subsection "Task Body (Full Description)"
Write-Host ""
Write-Host $job.body -ForegroundColor White
Write-Host ""

Write-Subsection "Ratings (Task Complexity Assessment)"
if ($job.ratings -and ($job.ratings | Get-Member -MemberType NoteProperty)) {
    $ratings = $job.ratings
    $ratingKeys = @("complexity", "difficulty", "external_tools", "uniqueness", "usefulness", 
                    "money_potential", "clarity", "verifiability", "impact", "time_cost", 
                    "risk", "learning_value")
    foreach ($key in $ratingKeys) {
        $value = $ratings.$key
        if ($value -ne $null -and $value -ne "") {
            Write-Info $key "$value/10"
        }
    }
} else {
    Write-Info "Ratings" "Not set"
}

Write-Subsection "Reward Calculation"
if ($job.reward_calc -and ($job.reward_calc | Get-Member -MemberType NoteProperty)) {
    $calc = $job.reward_calc
    Write-Info "Base" $calc.base
    Write-Info "Score" $calc.score
    Write-Info "Final Reward" "$($calc.final) ai$"
} else {
    Write-Info "Reward Calculation" "Not available"
}

# ============================================================================
# SECTION 2: SOLUTION DETAILS
# ============================================================================
Write-Section "2. SOLUTION DETAILS" "Blue"

if ($job.submission) {
    Write-Subsection "Submission Content"
    Write-Host ""
    Write-Host $job.submission -ForegroundColor White
    Write-Host ""
    
    Write-Subsection "Submission Metadata"
    Write-Info "Submission Length" "$($job.submission.Length) characters"
    Write-Info "Submitted By" $job.submitted_by
    Write-Info "Submitted At" (Format-Timestamp $job.submitted_at)
    
    # Try to extract JSON from submission
    Write-Subsection "Extracted JSON (if present)"
    $jsonMatch = [regex]::Match($job.submission, '```json\s*(\[.*?\])\s*```', [System.Text.RegularExpressions.RegexOptions]::Singleline)
    if ($jsonMatch.Success) {
        try {
            $jsonContent = $jsonMatch.Groups[1].Value | ConvertFrom-Json
            Write-Host ($jsonContent | ConvertTo-Json -Depth 10) -ForegroundColor Cyan
        } catch {
            Write-Host "  (Could not parse JSON)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  (No JSON code fence found in submission)" -ForegroundColor Gray
    }
    
    # Try to extract Evidence section
    Write-Subsection "Evidence Section (if present)"
    $evidenceMatch = [regex]::Match($job.submission, '(?i)##\s*Evidence\s*\n(.*?)(?=\n##|\Z)', [System.Text.RegularExpressions.RegexOptions]::Singleline)
    if ($evidenceMatch.Success) {
        Write-Host $evidenceMatch.Groups[1].Value.Trim() -ForegroundColor Green
    } else {
        Write-Host "  ❌ Evidence section not found" -ForegroundColor Red
    }
} else {
    Write-Host "  ❌ No submission available" -ForegroundColor Red
}

# ============================================================================
# SECTION 3: VERIFICATION & RATING DETAILS
# ============================================================================
Write-Section "3. VERIFICATION & RATING DETAILS" "Magenta"

Write-Subsection "Auto-Verification Results"
if ($job.auto_verify_ok -ne $null) {
    $verifyStatus = if ($job.auto_verify_ok) { "✅ PASSED" } else { "❌ FAILED" }
    $verifyColor = if ($job.auto_verify_ok) { "Green" } else { "Red" }
    Write-Info "Status" $verifyStatus $verifyColor
    Write-Info "Verifier Name" $(if ($job.auto_verify_name) { $job.auto_verify_name } else { "N/A" })
    Write-Info "Verification Note" $(if ($job.auto_verify_note) { $job.auto_verify_note } else { "N/A" })
    Write-Info "Verified At" (Format-Timestamp $job.auto_verified_at)
    
    if ($job.auto_verify_artifacts -and ($job.auto_verify_artifacts | Get-Member -MemberType NoteProperty)) {
        Write-Subsection "Verification Artifacts"
        $artifacts = $job.auto_verify_artifacts
        foreach ($key in $artifacts.PSObject.Properties.Name) {
            $value = $artifacts.$key
            if ($value -is [string] -and $value.Length -gt 200) {
                Write-Info $key "$($value.Substring(0, 200))... (truncated)"
            } else {
                Write-Info $key $value
            }
        }
    }
} else {
    Write-Info "Status" "⏳ Not yet verified" "Yellow"
}

Write-Subsection "Manual Review"
if ($job.reviewed_by) {
    Write-Info "Reviewed By" $job.reviewed_by
    Write-Info "Review Note" $(if ($job.review_note) { $job.review_note } else { "N/A" })
    Write-Info "Review At" (Format-Timestamp $job.reviewed_at)
    
    # Check if approved/rejected
    if ($job.status -eq "approved") {
        Write-Host ""
        Write-Host "  ✅ JOB APPROVED" -ForegroundColor Green
    } elseif ($job.status -eq "rejected") {
        Write-Host ""
        Write-Host "  ❌ JOB REJECTED" -ForegroundColor Red
    }
} else {
    Write-Info "Review Status" "⏳ Not yet reviewed" "Yellow"
}

# ============================================================================
# SECTION 4: ECONOMY IMPACT
# ============================================================================
Write-Section "4. ECONOMY IMPACT" "Yellow"

# Get economy ledger entries for this job
try {
    $ledger = Invoke-RestMethod -Uri "$BackendUrl/economy/ledger?limit=100" -Method Get -TimeoutSec 10
    $jobEntries = $ledger.entries | Where-Object { 
        $memo = $_.memo -or ""
        $memo -like "*$($job.job_id)*" -or $memo -like "*job*$($job.job_id)*"
    }
    
    if ($jobEntries) {
        Write-Subsection "Economy Transactions"
        foreach ($entry in $jobEntries) {
            Write-Host ""
            Write-Info "Entry ID" $entry.entry_id
            Write-Info "Type" $entry.entry_type
            Write-Info "Amount" "$($entry.amount) ai$"
            Write-Info "From" $(if ($entry.from_id) { $entry.from_id } else { "N/A" })
            Write-Info "To" $(if ($entry.to_id) { $entry.to_id } else { "N/A" })
            Write-Info "Memo" $entry.memo
            Write-Info "Created At" (Format-Timestamp $entry.created_at)
        }
    } else {
        Write-Host "  (No economy transactions found for this job)" -ForegroundColor Gray
    }
} catch {
    Write-Host "  ⚠️  Could not fetch economy ledger: $_" -ForegroundColor Yellow
}

# Get current balances
try {
    $balances = Invoke-RestMethod -Uri "$BackendUrl/economy/balances" -Method Get -TimeoutSec 5
    Write-Subsection "Current Balances"
    foreach ($agent in $balances.balances.PSObject.Properties) {
        Write-Info $agent.Name "$($agent.Value) ai$"
    }
} catch {
    Write-Host "  ⚠️  Could not fetch balances: $_" -ForegroundColor Yellow
}

# ============================================================================
# SECTION 5: ARTIFACTS & WORKSPACE
# ============================================================================
Write-Section "5. ARTIFACTS & WORKSPACE" "Cyan"

try {
    $artifacts = Invoke-RestMethod -Uri "$BackendUrl/artifacts/$JobId/list" -Method Get -TimeoutSec 5
    if ($artifacts.files -and $artifacts.files.Count -gt 0) {
        Write-Subsection "Workspace Files"
        foreach ($file in $artifacts.files) {
            Write-Info "File" "$($file.path) ($($file.size) bytes)"
            Write-Info "  SHA1" $file.sha1_16
        }
    } else {
        Write-Host "  (No artifacts found for this job)" -ForegroundColor Gray
    }
} catch {
    Write-Host "  ⚠️  Could not fetch artifacts: $_" -ForegroundColor Yellow
}

# ============================================================================
# SECTION 6: SUMMARY
# ============================================================================
Write-Section "6. SUMMARY" "White"

$summary = @{
    "Job Status" = $job.status
    "Created" = (Format-Timestamp $job.created_at)
    "Claimed" = if ($job.claimed_by) { "Yes by $($job.claimed_by)" } else { "No" }
    "Submitted" = if ($job.submitted_by) { "Yes by $($job.submitted_by)" } else { "No" }
    "Auto-Verified" = if ($job.auto_verify_ok -ne $null) { if ($job.auto_verify_ok) { "✅ PASSED" } else { "❌ FAILED" } } else { "⏳ Pending" }
    "Manually Reviewed" = if ($job.reviewed_by) { "Yes by $($job.reviewed_by)" } else { "No" }
    "Final Status" = $job.status
    "Reward" = "$($job.reward) ai$"
}

foreach ($key in $summary.Keys) {
    Write-Info $key $summary[$key]
}

Write-Host ""
Write-Host "View in UI: $BackendUrl/ui/" -ForegroundColor Cyan
Write-Host ""
