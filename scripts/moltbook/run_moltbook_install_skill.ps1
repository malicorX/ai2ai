# Install Moltbook skill (~/.moltbot/skills/moltbook) on sparky. Run from dev machine.
# Usage: .\scripts\moltbook\run_moltbook_install_skill.ps1 [-Target sparky2]
param(
    [string]$Target = "sparky2"
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$remoteScript = Join-Path $scriptDir "moltbook_install_skill_on_sparky.sh"
$remotePath = "/home/malicor/ai_ai2ai/scripts/moltbook/moltbook_install_skill_on_sparky.sh"

if (-not (Test-Path $remoteScript)) {
    Write-Host "Missing $remoteScript" -ForegroundColor Red
    exit 1
}

ssh $Target "mkdir -p /home/malicor/ai_ai2ai/scripts/moltbook" 2>$null
scp -q $remoteScript "${Target}:$remotePath"
ssh $Target "sed -i 's/\r$//' $remotePath 2>/dev/null; chmod +x $remotePath; bash $remotePath"
Write-Host "Moltbook skill installed on $Target at ~/.moltbot/skills/moltbook" -ForegroundColor Green
