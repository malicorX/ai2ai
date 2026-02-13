# Deploy MoltWorld SOUL.md to each sparky so the OpenClaw bot has identity and purpose (no fixed dialogue).
# Usage: .\scripts\clawd\run_moltworld_soul_on_sparkies.ps1
# Sparky1: deploys to ~/.openclaw (OpenClaw) and ~/clawd (Clawdbot fallback). Sparky2: ~/.openclaw.
param(
    [string]$Sparky1OpenClawWorkspace = "/home/malicor/.openclaw",
    [string]$Sparky1ClawdbotWorkspace = "/home/malicor/clawd",
    [string]$Sparky2Workspace = "/home/malicor/.openclaw"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$soul1Path = Join-Path $scriptDir "moltworld_soul_sparky1.md"
$soul2Path = Join-Path $scriptDir "moltworld_soul_sparky2.md"
$toolsPath = Join-Path $scriptDir "moltworld_tools.md"

Write-Host "Deploying MoltWorld SOUL + MOLTWORLD_TOOLS to sparky1 (~/.openclaw and ~/clawd)..." -ForegroundColor Cyan
ssh sparky1 "mkdir -p $Sparky1OpenClawWorkspace $Sparky1ClawdbotWorkspace"
scp -q $soul1Path "sparky1:${Sparky1OpenClawWorkspace}/SOUL.md"
scp -q $toolsPath "sparky1:${Sparky1OpenClawWorkspace}/MOLTWORLD_TOOLS.md"
scp -q $soul1Path "sparky1:${Sparky1ClawdbotWorkspace}/SOUL.md"
scp -q $toolsPath "sparky1:${Sparky1ClawdbotWorkspace}/MOLTWORLD_TOOLS.md"
Write-Host "Deploying MoltWorld SOUL + MOLTWORLD_TOOLS to sparky2 ($Sparky2Workspace)..." -ForegroundColor Cyan
ssh sparky2 "mkdir -p $Sparky2Workspace"
scp -q $soul2Path "sparky2:${Sparky2Workspace}/SOUL.md"
scp -q $toolsPath "sparky2:${Sparky2Workspace}/MOLTWORLD_TOOLS.md"
Write-Host "Done. Restart gateway or start a new session for SOUL to apply." -ForegroundColor Green
