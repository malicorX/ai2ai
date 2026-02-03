# Deploy backend to sparky1, then run the full test suite.
# Use from repo root: .\scripts\deployment\deploy_and_run_tests.ps1
#
# Params pass through to deploy.ps1 and run_all_tests.ps1:
#   -BackendUrl    default http://sparky1:8000
#   -Docker        default $true (deploy restarts backend container on sparky1)
#   -CopyOnly      if set, only copy files; you must rebuild on sparky1 yourself, then run the suite
#   -SkipVerifierUnit  skip step 1 (backend json_list verifier locally)

param(
    [string]$BackendUrl = "http://sparky1:8000",
    [switch]$CopyOnly = $false,
    [switch]$Docker = $true,
    [switch]$SkipVerifierUnit
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $scriptDir)

Push-Location $root | Out-Null
try {
    Write-Host ""
    Write-Host "===== Deploy backend, then run full test suite =====" -ForegroundColor Cyan
    Write-Host ""

    & "$scriptDir\deploy.ps1" -BackendUrl $BackendUrl -Docker:$Docker -CopyOnly:$CopyOnly
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    if ($CopyOnly) {
        Write-Host ""
        Write-Host "CopyOnly: rebuild on sparky1 (docker compose ... up -d --build backend), then run:" -ForegroundColor Yellow
        Write-Host "  .\scripts\testing\run_all_tests.ps1 -BackendUrl $BackendUrl" -ForegroundColor White
        Write-Host ""
        exit 0
    }

    Write-Host ""
    Write-Host "===== Running full test suite =====" -ForegroundColor Cyan
    & "$root\scripts\testing\run_all_tests.ps1" -BackendUrl $BackendUrl -SkipVerifierUnit:$SkipVerifierUnit
    exit $LASTEXITCODE
} finally {
    Pop-Location | Out-Null
}
