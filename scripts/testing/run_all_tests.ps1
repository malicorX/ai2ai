# Run full test suite: backend verifier (local) -> health -> single-job lifecycle (gig) -> proposer-review (approve + reject).
# Optional: -IncludeFiverr adds test_run (fiverr) — wait for agent_1 to create a real Fiverr job (requires WEB_SEARCH_ENABLED, agent_1 running).
# Exits on first failure. Use from repo root: .\scripts\testing\run_all_tests.ps1 -BackendUrl http://sparky1:8000
# All output is logged to scripts/testing/run_all_tests.<yyyyMMdd-HHmmss>.log

param(
    [string]$BackendUrl = "http://sparky1:8000",
    [switch]$SkipVerifierUnit,
    [switch]$IncludeFiverr
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $scriptDir "run_all_tests.$timestamp.log"
Start-Transcript -Path $logPath -Append:$false | Out-Null
try {
    Write-Host "Log file: $logPath" -ForegroundColor Gray
    Write-Host ""
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    $suiteDesc = "verifier_unit -> quick_test -> test_run (gig) -> test_proposer_review -> test_proposer_review_reject"
    if ($IncludeFiverr) { $suiteDesc += " -> test_run (fiverr)" }
    Write-Host "Test suite: $suiteDesc" -ForegroundColor Cyan
    Write-Host "Backend: $BackendUrl" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan

    if (-not $SkipVerifierUnit) {
        Write-Host ""
        Write-Host "--- 1/5 backend json_list verifier (local) ---" -ForegroundColor Yellow
        Push-Location "$root\backend" | Out-Null
        try {
            python test_json_list_verifier.py
            if ($LASTEXITCODE -ne 0) {
                Write-Host "backend/test_json_list_verifier.py failed (exit $LASTEXITCODE). Deploy backend to sparky1 so test_run passes." -ForegroundColor Red
                exit $LASTEXITCODE
            }
        } finally {
            Pop-Location | Out-Null
        }
    } else {
        Write-Host ""
        Write-Host "--- 1/5 backend json_list verifier (skipped -SkipVerifierUnit) ---" -ForegroundColor Gray
    }

    Write-Host ""
    Write-Host "--- 2/5 quick_test ---" -ForegroundColor Yellow
    & "$scriptDir\quick_test.ps1" -BackendUrl $BackendUrl
    if ($LASTEXITCODE -ne 0) {
        Write-Host "quick_test.ps1 failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }

    Write-Host ""
    Write-Host "--- 3/5 test_run (gig / Fiverr-style) ---" -ForegroundColor Yellow
    & "$scriptDir\test_run.ps1" -BackendUrl $BackendUrl -TaskType gig
    if ($LASTEXITCODE -ne 0) {
        Write-Host "test_run.ps1 -TaskType gig failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }

    Write-Host ""
    Write-Host "--- 4/5 test_proposer_review ---" -ForegroundColor Yellow
    & "$scriptDir\test_proposer_review.ps1" -BackendUrl $BackendUrl
    if ($LASTEXITCODE -ne 0) {
        Write-Host "test_proposer_review.ps1 failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }

    Write-Host ""
    Write-Host "--- 5/5 test_proposer_review_reject ---" -ForegroundColor Yellow
    & "$scriptDir\test_proposer_review_reject.ps1" -BackendUrl $BackendUrl -PenaltyAmount 1.0
    if ($LASTEXITCODE -ne 0) {
        Write-Host "test_proposer_review_reject.ps1 failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }

    if ($IncludeFiverr) {
        Write-Host ""
        Write-Host "--- 6/6 test_run (fiverr / real Fiverr from agent_1) ---" -ForegroundColor Yellow
        & "$scriptDir\test_run.ps1" -BackendUrl $BackendUrl -TaskType fiverr
        if ($LASTEXITCODE -ne 0) {
            Write-Host "test_run.ps1 -TaskType fiverr failed (exit $LASTEXITCODE). Ensure agent_1 is running and WEB_SEARCH_ENABLED=1, SERPER_API_KEY set." -ForegroundColor Red
            exit $LASTEXITCODE
        }
    }

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "All tests passed." -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    exit 0
} finally {
    try { Stop-Transcript | Out-Null } catch { }
    Pop-Location | Out-Null
}
