# Run one MoltWorld step with the Python bot on a sparky (or locally).
# Usage: .\scripts\clawd\run_moltworld_python_bot.ps1 -AgentId Sparky1Agent
#        .\scripts\clawd\run_moltworld_python_bot.ps1 -AgentId MalicorSparky2 -TargetHost sparky2
# Optional: -TargetHost sparky1 | sparky2 (default: none = run locally)
# -RemoteRepoPath: on host, run from this path (e.g. ~/ai_ai2ai) so venv is used. If empty, uses /tmp/ai_ai2ai_agents.
param(
    [Parameter(Mandatory = $true)]
    [string]$AgentId,
    [string]$TargetHost = "",
    [string]$WorldApiBase = "https://www.theebie.de",
    [string]$RemoteRepoPath = "~/ai_ai2ai",
    [switch]$NoDeploy
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Get-Item $scriptDir).Parent.Parent.FullName

if ($TargetHost) {
    $botSh = Join-Path $projectRoot "scripts\clawd\run_moltworld_python_bot.sh"
    $setupSh = Join-Path $projectRoot "scripts\clawd\setup_moltworld_bot_venv.sh"
    $envStr = "WORLD_API_BASE=$WorldApiBase AGENT_ID=$AgentId DISPLAY_NAME=$AgentId"
    Write-Host "Running Python bot on $TargetHost as $AgentId..." -ForegroundColor Cyan
    # Prefer running from repo on host (so venv is used); fallback to /tmp deploy
    $remoteRepo = $RemoteRepoPath.Trim()
    if (-not $NoDeploy -and $remoteRepo) {
        scp -q $botSh "${TargetHost}:${remoteRepo}/scripts/clawd/run_moltworld_python_bot.sh"
        scp -q $setupSh "${TargetHost}:${remoteRepo}/scripts/clawd/setup_moltworld_bot_venv.sh"
        ssh $TargetHost "sed -i 's/\r$//' ${remoteRepo}/scripts/clawd/run_moltworld_python_bot.sh ${remoteRepo}/scripts/clawd/setup_moltworld_bot_venv.sh 2>/dev/null; chmod +x ${remoteRepo}/scripts/clawd/run_moltworld_python_bot.sh ${remoteRepo}/scripts/clawd/setup_moltworld_bot_venv.sh"
    }
    $runCmd = "cd $remoteRepo && source ~/.moltworld.env 2>/dev/null; export $envStr; bash scripts/clawd/run_moltworld_python_bot.sh"
    $out = ssh $TargetHost $runCmd 2>&1
    Write-Host $out
    if ($out -match "^(sent|noop|moved|error)$") {
        if ($out -eq "error") { exit 1 }
        exit 0
    }
    exit 0
}

# Local run
$env:WORLD_API_BASE = $WorldApiBase
$env:AGENT_ID = $AgentId
$env:DISPLAY_NAME = $AgentId
$env:PYTHONPATH = (Join-Path $projectRoot "agents")
if (-not $env:WORLD_AGENT_TOKEN -and (Test-Path "$env:USERPROFILE\.moltworld.env")) {
    Get-Content "$env:USERPROFILE\.moltworld.env" | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process") }
    }
}
Write-Host "Running Python bot locally as $AgentId..." -ForegroundColor Cyan
Push-Location $projectRoot
try {
    python -m agent_template.moltworld_bot
} finally {
    Pop-Location
}
