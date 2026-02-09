# Deploy MoltWorld SOUL.md to each sparky so the OpenClaw bot has identity and purpose (no fixed dialogue).
# Usage: .\scripts\clawd\run_moltworld_soul_on_sparkies.ps1
# Workspace paths: sparky1 default ~/clawd, sparky2 default ~/.openclaw (or set in gateway config).
param(
    [string]$Sparky1Workspace = "/home/malicor/clawd",
    [string]$Sparky2Workspace = "/home/malicor/.openclaw"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$soul1Path = Join-Path $scriptDir "moltworld_soul_sparky1.md"
$soul2Path = Join-Path $scriptDir "moltworld_soul_sparky2.md"
$toolsPath = Join-Path $scriptDir "moltworld_tools.md"

Write-Host "Deploying MoltWorld SOUL + MOLTWORLD_TOOLS to sparky1 ($Sparky1Workspace)..." -ForegroundColor Cyan
ssh sparky1 "mkdir -p $Sparky1Workspace"
scp -q $soul1Path "sparky1:${Sparky1Workspace}/SOUL.md"
scp -q $toolsPath "sparky1:${Sparky1Workspace}/MOLTWORLD_TOOLS.md"
Write-Host "Deploying MoltWorld SOUL + MOLTWORLD_TOOLS to sparky2 ($Sparky2Workspace)..." -ForegroundColor Cyan
ssh sparky2 "mkdir -p $Sparky2Workspace"
scp -q $soul2Path "sparky2:${Sparky2Workspace}/SOUL.md"
scp -q $toolsPath "sparky2:${Sparky2Workspace}/MOLTWORLD_TOOLS.md"
Write-Host "Done. Cron turns will use this identity and tool instructions. Restart gateway or start a new session for SOUL to apply." -ForegroundColor Green
