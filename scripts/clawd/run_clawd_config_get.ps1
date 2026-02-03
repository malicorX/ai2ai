# Print Clawd config from sparky. Run from dev machine.
# Usage: .\scripts\clawd\run_clawd_config_get.ps1 [-Target sparky2]
param(
    [string]$Target = "sparky2"
)

$ErrorActionPreference = "Continue"
ssh $Target "cat ~/.clawdbot/clawdbot.json" 2>&1 | ForEach-Object { Write-Host $_ }
