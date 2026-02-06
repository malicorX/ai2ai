# Copy moltbook_queue_list_on_sparky.sh to sparky1 or sparky2 and run it. Run from dev machine.
# Usage: .\scripts\moltbook\run_moltbook_queue_list.ps1 [-Target sparky2]  or  -Target sparky1
param(
    [string]$Target = "sparky2",
    [string]$RemoteScriptsPath = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
if (-not $RemoteScriptsPath) {
    $RemoteScriptsPath = if ($Target -eq "sparky1") { "~/moltbook_scripts" } else { "~/ai2ai/scripts/moltbook" }
}
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
