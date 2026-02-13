# Set up sparky1 to use OpenClaw for MoltWorld (like sparky2): bootstrap .openclaw, install plugin, fix config, start gateway.
# Prereqs: sparky1 has ~/.moltworld.env with AGENT_ID=Sparky1Agent, DISPLAY_NAME=Sparky1Agent, WORLD_AGENT_TOKEN=...
# Usage: .\scripts\clawd\run_setup_openclaw_on_sparky1.ps1 [-Sparky1Host sparky1] [-RemotePath ...]
# RemotePath: directory on sparky1 where scripts live (e.g. /home/malicor/ai_ai2ai/scripts/clawd or .../ai2ai/scripts/clawd).
param(
    [string]$Sparky1Host = "sparky1",
    [string]$RemotePath = "/home/malicor/ai_ai2ai/scripts/clawd"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Get-Item $scriptDir).Parent.Parent.FullName

$bootstrapSh = Join-Path $scriptDir "bootstrap_openclaw_on_sparky1.sh"
$installSh = Join-Path $scriptDir "install_moltworld_plugin_on_sparky.sh"
$fixSh = Join-Path $scriptDir "sparky1_fix_moltworld_config.sh"
$gatewaySh = Join-Path $scriptDir "sparky1_kill_orphan_and_start_gateway.sh"

foreach ($f in @($bootstrapSh, $installSh, $fixSh, $gatewaySh)) {
    if (-not (Test-Path $f)) { Write-Host "Missing $f" -ForegroundColor Red; exit 1 }
}

Write-Host "Setting up OpenClaw on $Sparky1Host (like sparky2)..." -ForegroundColor Cyan
ssh $Sparky1Host "mkdir -p $RemotePath"
scp -q $bootstrapSh $installSh $fixSh $gatewaySh "${Sparky1Host}:$RemotePath/"
ssh $Sparky1Host "sed -i 's/\r$//' $RemotePath/*.sh 2>/dev/null; chmod +x $RemotePath/bootstrap_openclaw_on_sparky1.sh $RemotePath/install_moltworld_plugin_on_sparky.sh $RemotePath/sparky1_fix_moltworld_config.sh $RemotePath/sparky1_kill_orphan_and_start_gateway.sh"

Write-Host "Step 1: Bootstrap ~/.openclaw on $Sparky1Host..." -ForegroundColor Cyan
ssh $Sparky1Host "bash $RemotePath/bootstrap_openclaw_on_sparky1.sh"

Write-Host "Step 2: Install MoltWorld plugin (uses ~/.moltworld.env)..." -ForegroundColor Cyan
ssh $Sparky1Host "bash $RemotePath/install_moltworld_plugin_on_sparky.sh"

Write-Host "Step 3: Fix config for Sparky1Agent and start OpenClaw gateway..." -ForegroundColor Cyan
ssh $Sparky1Host "bash $RemotePath/sparky1_fix_moltworld_config.sh"

Write-Host "Step 4: Ensure gateway is running (kill orphan, start openclaw)..." -ForegroundColor Cyan
ssh $Sparky1Host "bash $RemotePath/sparky1_kill_orphan_and_start_gateway.sh"

Write-Host "Deploying SOUL to sparky1 ~/.openclaw..." -ForegroundColor Cyan
$soulPath = Join-Path $scriptDir "moltworld_soul_sparky1.md"
$toolsPath = Join-Path $scriptDir "moltworld_tools.md"
ssh $Sparky1Host "mkdir -p ~/.openclaw"
scp -q $soulPath "${Sparky1Host}:~/.openclaw/SOUL.md"
scp -q $toolsPath "${Sparky1Host}:~/.openclaw/MOLTWORLD_TOOLS.md"

Write-Host "Done. Sparky1 now uses OpenClaw like sparky2. Deploy loops with: .\scripts\clawd\run_moltworld_openclaw_loops.ps1 -UseOpenClawNarrator -Background" -ForegroundColor Green
