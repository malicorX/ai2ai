# Copy world_agent_move_loop.sh to sparky2 and run it. Run from dev machine.
# Usage: .\scripts\world\run_world_agent_move_loop.ps1 [-Target sparky2] [-WorldUrl http://sparky1:8000] [-AgentId openclaw_bot] [-DisplayName "OpenClaw Bot"] [-StepSeconds 5]
param(
    [string]$Target = "sparky2",
    [string]$WorldUrl = "http://sparky1:8000",
    [string]$AgentId = "openclaw_bot",
    [string]$DisplayName = "OpenClaw Bot",
    [int]$StepSeconds = 5
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$localScript = Join-Path $scriptDir "world_agent_move_loop.sh"

if (-not (Test-Path $localScript)) {
    Write-Host "Missing $localScript" -ForegroundColor Red
    exit 1
}

ssh $Target "mkdir -p ~/ai2ai/scripts/world" 2>$null
scp -q $localScript "${Target}:~/ai2ai/scripts/world/world_agent_move_loop.sh"
ssh $Target "sed -i 's/\r$//' ~/ai2ai/scripts/world/world_agent_move_loop.sh 2>/dev/null; chmod +x ~/ai2ai/scripts/world/world_agent_move_loop.sh"

$remoteCmd = "WORLD_URL='$WorldUrl' AGENT_ID='$AgentId' DISPLAY_NAME='$DisplayName' STEP_SECONDS=$StepSeconds bash ~/ai2ai/scripts/world/world_agent_move_loop.sh"
Write-Host "Starting move loop on $Target..." -ForegroundColor Cyan
ssh $Target $remoteCmd
