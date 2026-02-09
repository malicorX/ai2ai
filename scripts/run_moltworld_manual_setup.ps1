# Full manual MoltWorld setup: issue tokens, write env files, push to sparky1 and sparky2.
# Prereq: Set ADMIN_TOKEN (from the MoltWorld backend / theebie.de). Optional: MOLTWORLD_BASE_URL.
# Usage: .\scripts\run_moltworld_manual_setup.ps1 [-SkipPush] [-EnvFile path]
#   -SkipPush: only issue tokens and write deployment/*_moltworld.env; do not scp to sparkies.
#   -EnvFile: path to .env to load (e.g. deployment/.env) to read ADMIN_TOKEN from file.
param([switch]$SkipPush = $false, [string]$EnvFile = "")

$ErrorActionPreference = "Stop"
$projectRoot = (Get-Item $PSScriptRoot).Parent.FullName

if ($EnvFile -and (Test-Path $EnvFile)) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*ADMIN_TOKEN\s*=\s*(.+)$') { $env:ADMIN_TOKEN = $matches[1].Trim().Trim('"').Trim("'") }
        if ($_ -match '^\s*MOLTWORLD_BASE_URL\s*=\s*(.+)$') { $env:MOLTWORLD_BASE_URL = $matches[1].Trim().Trim('"').Trim("'") }
    }
}

if (-not $env:ADMIN_TOKEN) {
    Write-Host "ADMIN_TOKEN is not set. Set it (e.g. from your backend/theebie admin) and re-run." -ForegroundColor Red
    Write-Host "  `$env:ADMIN_TOKEN = 'your_admin_token'" -ForegroundColor Yellow
    Write-Host "  .\scripts\run_moltworld_manual_setup.ps1" -ForegroundColor Yellow
    Write-Host "See docs/MOLTWORLD_MANUAL_SETUP_SPARKIES.md" -ForegroundColor Cyan
    exit 1
}

Write-Host "Issuing MoltWorld tokens for Sparky1Agent and MalicorSparky2..." -ForegroundColor Cyan
Push-Location $projectRoot
try {
    python scripts/issue_moltworld_tokens.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

$env1 = Join-Path $projectRoot "deployment\sparky1_moltworld.env"
$env2 = Join-Path $projectRoot "deployment\sparky2_moltworld.env"
if (-not (Test-Path $env1) -or -not (Test-Path $env2)) {
    Write-Host "Env files not found. Check script output above." -ForegroundColor Red
    exit 1
}

if ($SkipPush) {
    Write-Host "SkipPush: not copying env to sparkies. Copy manually or run without -SkipPush." -ForegroundColor Yellow
    Write-Host "  scp deployment/sparky1_moltworld.env sparky1:~/.moltworld.env" -ForegroundColor Gray
    Write-Host "  scp deployment/sparky2_moltworld.env sparky2:~/.moltworld.env" -ForegroundColor Gray
    exit 0
}

Write-Host "Copying env to sparky1 and sparky2..." -ForegroundColor Cyan
scp $env1 sparky1:~/.moltworld.env
scp $env2 sparky2:~/.moltworld.env

Write-Host "Done. On each host, source the env before running the agent:" -ForegroundColor Green
Write-Host "  sparky1: set -a; . ~/.moltworld.env; set +a;  # then start agent" -ForegroundColor Gray
Write-Host "  sparky2: set -a; . ~/.moltworld.env; set +a;  # then start agent" -ForegroundColor Gray
Write-Host "Or in Docker: pass env file or individual vars (WORLD_API_BASE, AGENT_ID, DISPLAY_NAME, WORLD_AGENT_TOKEN)." -ForegroundColor Gray
