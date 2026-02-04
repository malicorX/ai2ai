# Copy world_agent_autostart_on_sparky.sh to sparky2 and run it. Run from dev machine.
# Usage: .\scripts\world\run_world_agent_autostart.ps1 [-Target sparky2] [-WorldUrl http://sparky1:8000] [-AgentId MalicorSparky2] [-AgentName "MalicorSparky2"]
param(
    [string]$Target = "sparky2",
    [string]$WorldUrl = "http://sparky1:8000",
    [string]$AgentId = "MalicorSparky2",
    [string]$AgentName = "MalicorSparky2",
    [int]$StepSeconds = 6,
    [int]$SayEverySteps = 10
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$localScript = Join-Path $scriptDir "world_agent_autostart_on_sparky.sh"

if (-not (Test-Path $localScript)) {
    Write-Host "Missing $localScript" -ForegroundColor Red
    exit 1
}

ssh $Target "mkdir -p ~/ai2ai/scripts/world" 2>$null
scp -q $localScript "${Target}:~/ai2ai/scripts/world/world_agent_autostart_on_sparky.sh"
ssh $Target "sed -i 's/\r$//' ~/ai2ai/scripts/world/world_agent_autostart_on_sparky.sh 2>/dev/null; chmod +x ~/ai2ai/scripts/world/world_agent_autostart_on_sparky.sh"

$remoteCmd = "WORLD_URL='$WorldUrl' AGENT_ID='$AgentId' AGENT_NAME='$AgentName' STEP_SECONDS=$StepSeconds SAY_EVERY_STEPS=$SayEverySteps bash ~/ai2ai/scripts/world/world_agent_autostart_on_sparky.sh"
Write-Host "Installing cron autostart on $Target..." -ForegroundColor Cyan
ssh $Target $remoteCmd
