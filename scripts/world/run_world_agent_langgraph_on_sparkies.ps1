# Deploy and start the world agent with USE_LANGGRAPH=1 (goal tiers, LLM-driven move/chat/jobs) on both sparkies.
# Prereqs: ~/.moltworld.env on each sparky (WORLD_AGENT_TOKEN, AGENT_ID, WORLD_API_BASE=https://www.theebie.de or your backend).
# Usage:
#   .\scripts\world\run_world_agent_langgraph_on_sparkies.ps1                    # Deploy + start both
#   .\scripts\world\run_world_agent_langgraph_on_sparkies.ps1 -NoDeploy           # Start only (code already on sparkies)
#   .\scripts\world\run_world_agent_langgraph_on_sparkies.ps1 -Stop               # Stop the agent on both sparkies
param(
    [string]$Sparky1Host = "sparky1",
    [string]$Sparky2Host = "sparky2",
    [string]$RemotePath = "~/ai_ai2ai",
    [switch]$NoDeploy,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Get-Item $scriptDir).Parent.Parent.FullName

if ($Stop) {
    Write-Host "Stopping world agent (agent_template.agent) on $Sparky1Host and $Sparky2Host..." -ForegroundColor Cyan
    ssh $Sparky1Host "pkill -f 'agent_template.agent' 2>/dev/null; echo done"
    ssh $Sparky2Host "pkill -f 'agent_template.agent' 2>/dev/null; echo done"
    Write-Host "Done. Agents stopped." -ForegroundColor Green
    return
}

# Deploy agent code so sparkies have latest (including goal tiers in langgraph_agent.py / langgraph_control.py)
if (-not $NoDeploy) {
    Write-Host "Deploying agent code to sparkies..." -ForegroundColor Cyan
    & (Join-Path $projectRoot "scripts\deployment\sync_to_sparkies.ps1") -Mode synconly -RemotePath $RemotePath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Sync failed. Fix and retry or use -NoDeploy to start without syncing." -ForegroundColor Yellow
        exit 1
    }
}

# Single-line script for SSH: set env, then nohup the agent
$startSh = 'set -e; REPO="REMOTE_PATH_PLACEHOLDER"; cd "$REPO"; export PYTHONPATH="${REPO}/agents"; source ~/.moltworld.env 2>/dev/null || true; export USE_LANGGRAPH=1 ROLE="ROLE_PLACEHOLDER" AGENT_ID="AGENT_ID_PLACEHOLDER" DISPLAY_NAME="DISPLAY_NAME_PLACEHOLDER"; export WORLD_API_BASE="${WORLD_API_BASE:-https://www.theebie.de}"; if [ -x "${REPO}/venv/bin/python3" ]; then PYTHON="${REPO}/venv/bin/python3"; else PYTHON=python3; fi; nohup "$PYTHON" -m agent_template.agent >> ~/.world_agent_langgraph.log 2>&1 & echo Started'

# So that ~ expands on the remote, use $HOME/... when path starts with ~
$remotePathExpanded = $RemotePath -replace '^~/', '$HOME/'
# Start sparky1 (proposer)
$s1Script = $startSh -replace "REMOTE_PATH_PLACEHOLDER", $remotePathExpanded -replace "ROLE_PLACEHOLDER", "proposer" -replace "AGENT_ID_PLACEHOLDER", "Sparky1Agent" -replace "DISPLAY_NAME_PLACEHOLDER", "Sparky1Agent"
Write-Host "Starting world agent on $Sparky1Host (proposer, USE_LANGGRAPH=1)..." -ForegroundColor Cyan
ssh $Sparky1Host "pkill -f 'agent_template.agent' 2>/dev/null; sleep 2; $s1Script"

# Start sparky2 (executor)
$s2Script = $startSh -replace "REMOTE_PATH_PLACEHOLDER", $remotePathExpanded -replace "ROLE_PLACEHOLDER", "executor" -replace "AGENT_ID_PLACEHOLDER", "MalicorSparky2" -replace "DISPLAY_NAME_PLACEHOLDER", "MalicorSparky2"
Write-Host "Starting world agent on $Sparky2Host (executor, USE_LANGGRAPH=1)..." -ForegroundColor Cyan
ssh $Sparky2Host "pkill -f 'agent_template.agent' 2>/dev/null; sleep 2; $s2Script"

Write-Host "`nDone. Both agents run with USE_LANGGRAPH=1 (goal tiers in effect)." -ForegroundColor Green
Write-Host "Logs: ssh $Sparky1Host tail -f ~/.world_agent_langgraph.log" -ForegroundColor Gray
Write-Host "      ssh $Sparky2Host tail -f ~/.world_agent_langgraph.log" -ForegroundColor Gray
Write-Host "Stop:  .\scripts\world\run_world_agent_langgraph_on_sparkies.ps1 -Stop" -ForegroundColor Gray
