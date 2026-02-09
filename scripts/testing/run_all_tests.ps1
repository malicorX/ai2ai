# Run full test suite: backend verifier (local) -> health -> single-job lifecycle (gig) -> proposer-review (approve + reject).
# Optional: -IncludeFiverr adds test_run (fiverr) — wait for agent_1 to create a real Fiverr job (requires WEB_SEARCH_ENABLED, agent_1 running).
# Exits on first failure. Use from repo root: .\scripts\testing\run_all_tests.ps1 -BackendUrl http://sparky1:8000
# All output is logged to scripts/testing/run_all_tests.<yyyyMMdd-HHmmss>.log

param(
    [string]$BackendUrl = "https://www.theebie.de",
    [string]$BackendToken = "",
    [switch]$SkipVerifierUnit,
    [switch]$IncludeFiverr,
    [switch]$ForceSubmit
)
if (-not $BackendToken) { $BackendToken = $env:BACKEND_TOKEN }
# When using theebie and no token set, try to fetch one agent token from theebie (for jobs API)
if (-not $BackendToken -and $BackendUrl -match "theebie") {
    try {
        $json = ssh root@84.38.65.246 "cat /opt/ai_ai2ai/backend_data/agent_tokens.json 2>/dev/null || echo '{}'"
        $tokenMap = $json | ConvertFrom-Json
        foreach ($p in $tokenMap.PSObject.Properties) {
            $BackendToken = $p.Name
            Write-Host "Using agent token from theebie for jobs API." -ForegroundColor Gray
            break
        }
    } catch { }
}

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $scriptDir)   # repo root (ai_ai2ai)
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
    $quickArgs = @{ BackendUrl = $BackendUrl }
    if ($BackendToken) { $quickArgs.BackendToken = $BackendToken }
    & "$scriptDir\quick_test.ps1" @quickArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "quick_test.ps1 failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }

    Write-Host ""
    Write-Host "--- 3/5 test_run (gig / Fiverr-style) ---" -ForegroundColor Yellow
    $testRunArgs = @{ BackendUrl = $BackendUrl; TaskType = "gig" }; if ($BackendToken) { $testRunArgs.BackendToken = $BackendToken }; if ($ForceSubmit) { $testRunArgs.ForceSubmit = $true; $testRunArgs.MaxWaitSubmitSeconds = 45 }
    & "$scriptDir\test_run.ps1" @testRunArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "test_run.ps1 -TaskType gig failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }

    Write-Host ""
    Write-Host "--- 4/5 test_proposer_review ---" -ForegroundColor Yellow
    $tprArgs = @{ BackendUrl = $BackendUrl }; if ($BackendToken) { $tprArgs.BackendToken = $BackendToken }
    & "$scriptDir\test_proposer_review.ps1" @tprArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "test_proposer_review.ps1 failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }

    Write-Host ""
    Write-Host "--- 5/5 test_proposer_review_reject ---" -ForegroundColor Yellow
    $tprrArgs = @{ BackendUrl = $BackendUrl; PenaltyAmount = 1.0 }; if ($BackendToken) { $tprrArgs.BackendToken = $BackendToken }
    & "$scriptDir\test_proposer_review_reject.ps1" @tprrArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "test_proposer_review_reject.ps1 failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }

    if ($IncludeFiverr) {
        Write-Host ""
        Write-Host "--- 6/6 test_run (fiverr / real Fiverr from agent_1) ---" -ForegroundColor Yellow
        $testRunArgs = @{ BackendUrl = $BackendUrl; TaskType = "fiverr" }; if ($BackendToken) { $testRunArgs.BackendToken = $BackendToken }; & "$scriptDir\test_run.ps1" @testRunArgs
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
