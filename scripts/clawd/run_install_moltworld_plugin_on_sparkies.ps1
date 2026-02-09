# Copy install_moltworld_plugin_on_sparky.sh to both sparkies and run it (uses existing ~/.moltworld.env on each).
# Usage: .\scripts\clawd\run_install_moltworld_plugin_on_sparkies.ps1 [-Hosts sparky1,sparky2] [-RemotePath /home/malicor/ai2ai/scripts/clawd]
# Requires: each sparky has ~/.moltworld.env with AGENT_ID, DISPLAY_NAME (or AGENT_NAME), WORLD_AGENT_TOKEN.
param(
    [string[]]$Hosts = @("sparky1", "sparky2"),
    [string]$RemotePath = "/home/malicor/ai2ai/scripts/clawd"
)

$ErrorActionPreference = "Continue"
$scriptDir = $PSScriptRoot
$installScript = Join-Path $scriptDir "install_moltworld_plugin_on_sparky.sh"
$remoteScript = "$RemotePath/install_moltworld_plugin_on_sparky.sh"

if (-not (Test-Path $installScript)) {
    Write-Host "Missing $installScript" -ForegroundColor Red
    exit 1
}

Write-Host "Installing MoltWorld plugin on sparkies (using existing ~/.moltworld.env on each host)..." -ForegroundColor Cyan
foreach ($h in $Hosts) {
    Write-Host "`n=== $h ===" -ForegroundColor Cyan
    try {
        ssh $h "mkdir -p $RemotePath" 2>$null
        scp -q $installScript "${h}:$remoteScript"
        ssh $h "sed -i 's/\r$//' $remoteScript 2>/dev/null; chmod +x $remoteScript; bash $remoteScript" 2>&1 | ForEach-Object { Write-Host $_ }
        Write-Host "  [OK] Plugin install completed on $h" -ForegroundColor Green
    } catch {
        Write-Host "  [WARN] $h : $_" -ForegroundColor Yellow
    }
}
Write-Host "`nVerify: In TUI or Control UI on each sparky, ask to use world_state then chat_say." -ForegroundColor Cyan
