# Tail Clawd gateway log on sparky. Run from dev machine.
# Usage: .\scripts\clawd\run_clawd_logs.ps1 [-Target sparky2] [-Lines 80]
param(
    [string]$Target = "sparky2",
    [int]$Lines = 80
)

$ErrorActionPreference = "Continue"
ssh $Target "tail -n $Lines ~/.clawdbot/gateway.log" 2>&1 | ForEach-Object { Write-Host $_ }
