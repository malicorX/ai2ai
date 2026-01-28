# Run full test suite: backend verifier (local) -> health -> single-job lifecycle (gig) -> proposer-review (approve + reject).
# Exits on first failure. Use from repo root: .\scripts\run_all_tests.ps1 -BackendUrl http://sparky1:8000
# All output is logged to scripts/run_all_tests.<yyyyMMdd-HHmmss>.log

param(
    [string]$BackendUrl = "http://sparky1:8000",
    [switch]$SkipVerifierUnit
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
    Write-Host "Test suite: verifier_unit -> quick_test -> test_run (gig) -> test_proposer_review -> test_proposer_review_reject" -ForegroundColor Cyan
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
