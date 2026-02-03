# Copy moltbook_register_on_sparky.sh to sparky2 and optionally run it. Run from dev machine.
# Creates the script at ~/ai2ai/scripts/moltbook/ on sparky2 so you can run it there: bash ~/ai2ai/scripts/moltbook/moltbook_register_on_sparky.sh
# Usage: .\scripts\moltbook\run_moltbook_register_on_sparky.ps1 [-Target sparky2] [-RemoteScriptsPath "~/ai2ai/scripts/moltbook"] [-Run]
param(
    [string]$Target = "sparky2",
    [string]$RemoteScriptsPath = "~/ai2ai/scripts/moltbook",
    [switch]$Run   # If set, run the script on sparky2 after copying (so you get the claim URL in one go)
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$localScript = Join-Path $scriptDir "moltbook_register_on_sparky.sh"

if (-not (Test-Path $localScript)) {
    Write-Host "Missing $localScript" -ForegroundColor Red
    exit 1
}

Write-Host "Copying moltbook_register_on_sparky.sh to ${Target}:$RemoteScriptsPath" -ForegroundColor Cyan
ssh $Target "mkdir -p $RemoteScriptsPath" 2>$null
scp -q $localScript "${Target}:$RemoteScriptsPath/moltbook_register_on_sparky.sh"
ssh $Target "sed -i 's/\r$//' $RemoteScriptsPath/moltbook_register_on_sparky.sh 2>/dev/null; chmod +x $RemoteScriptsPath/moltbook_register_on_sparky.sh"
Write-Host "Script is on sparky2 at $RemoteScriptsPath/moltbook_register_on_sparky.sh" -ForegroundColor Green
Write-Host "On sparky2 run: bash $RemoteScriptsPath/moltbook_register_on_sparky.sh" -ForegroundColor Cyan

if ($Run) {
    Write-Host ""
    Write-Host "Running it now on $Target..." -ForegroundColor Cyan
    ssh $Target "bash $RemoteScriptsPath/moltbook_register_on_sparky.sh"
}
