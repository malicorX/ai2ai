# Show which model Clawd is configured and actually running with on sparky.
# Run from dev machine. Usage: .\scripts\clawd\run_clawd_show_model.ps1 [-Target sparky2]
param(
    [string]$Target = "sparky2"
)

$ErrorActionPreference = "Continue"

Write-Host "`n=== Clawd model on $Target ===" -ForegroundColor Cyan

# 1. Configured primary (from clawdbot.json)
$cfgLine = ssh $Target "grep primary ~/.clawdbot/clawdbot.json 2>/dev/null | head -1" 2>&1
if ($cfgLine -match ':\s*"([^"]+)"') {
    Write-Host "  Config (primary): " -NoNewline
    Write-Host $Matches[1] -ForegroundColor Green
} else {
    Write-Host "  Config (primary): (not found in config)" -ForegroundColor Yellow
}

# 2. Running agent model (last gateway startup in log)
$run = ssh $Target "grep 'agent model' ~/.clawdbot/gateway.log 2>/dev/null | tail -1" 2>&1
if ($run -match 'agent model:\s*(\S+)') {
    Write-Host "  Running (startup): " -NoNewline
    Write-Host $Matches[1] -ForegroundColor Green
} else {
    Write-Host "  Running: (no agent model line in gateway.log)" -ForegroundColor Yellow
}

Write-Host ""
