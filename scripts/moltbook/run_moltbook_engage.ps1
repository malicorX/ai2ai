# Copy moltbook_engage_on_sparky.sh to sparky2 and optionally run it. Run from dev machine.
# Usage: .\scripts\moltbook\run_moltbook_engage.ps1 [-Target sparky2] [-Query "tool calling fixes"] [-Run]
param(
    [string]$Target = "sparky2",
    [string]$Query = "tool calling fixes",
    [string]$RemoteScriptsPath = "~/ai2ai/scripts/moltbook",
    [switch]$Run
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$localScript = Join-Path $scriptDir "moltbook_engage_on_sparky.sh"

if (-not (Test-Path $localScript)) {
    Write-Host "Missing $localScript" -ForegroundColor Red
    exit 1
}

Write-Host "Copying moltbook_engage_on_sparky.sh to ${Target}:$RemoteScriptsPath" -ForegroundColor Cyan
ssh $Target "mkdir -p $RemoteScriptsPath" 2>$null
scp -q $localScript "${Target}:$RemoteScriptsPath/moltbook_engage_on_sparky.sh"
ssh $Target "sed -i 's/\r$//' $RemoteScriptsPath/moltbook_engage_on_sparky.sh 2>/dev/null; chmod +x $RemoteScriptsPath/moltbook_engage_on_sparky.sh"
Write-Host "On sparky2 run: ./moltbook_engage_on_sparky.sh `"$Query`"" -ForegroundColor Green

if ($Run) {
    Write-Host ""
    Write-Host "Running on $Target..." -ForegroundColor Cyan
    ssh $Target "bash $RemoteScriptsPath/moltbook_engage_on_sparky.sh '$Query'"
}
