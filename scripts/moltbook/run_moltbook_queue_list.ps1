# Copy moltbook_queue_list_on_sparky.sh to sparky2 and run it. Run from dev machine.
# Usage: .\scripts\moltbook\run_moltbook_queue_list.ps1 [-Target sparky2]
param(
    [string]$Target = "sparky2",
    [string]$RemoteScriptsPath = "~/ai2ai/scripts/moltbook"
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$localScript = Join-Path $scriptDir "moltbook_queue_list_on_sparky.sh"

if (-not (Test-Path $localScript)) {
    Write-Host "Missing $localScript" -ForegroundColor Red
    exit 1
}

Write-Host "Copying moltbook_queue_list_on_sparky.sh to ${Target}:$RemoteScriptsPath" -ForegroundColor Cyan
ssh $Target "mkdir -p $RemoteScriptsPath" 2>$null
scp -q $localScript "${Target}:$RemoteScriptsPath/moltbook_queue_list_on_sparky.sh"
ssh $Target "sed -i 's/\r$//' $RemoteScriptsPath/moltbook_queue_list_on_sparky.sh 2>/dev/null; chmod +x $RemoteScriptsPath/moltbook_queue_list_on_sparky.sh"
Write-Host ""
ssh $Target "bash $RemoteScriptsPath/moltbook_queue_list_on_sparky.sh"
