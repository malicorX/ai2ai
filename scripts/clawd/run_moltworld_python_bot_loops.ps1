# Deploy and start Python MoltWorld bot loops: narrator on sparky1, poll loop on sparky2.
# Usage: .\scripts\clawd\run_moltworld_python_bot_loops.ps1 [-Background] [-NarratorIntervalSec 120] [-PollIntervalSec 10]
param(
    [switch]$Background,
    [int]$NarratorIntervalSec = 120,
    [int]$PollIntervalSec = 10,
    [string]$Sparky1Host = "sparky1",
    [string]$Sparky2Host = "sparky2",
    [string]$RemoteRepoPath = "~/ai_ai2ai"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Get-Item $scriptDir).Parent.Parent.FullName

$loopSh = Join-Path $projectRoot "scripts\clawd\run_moltworld_python_bot_loop.sh"
$pollSh = Join-Path $projectRoot "scripts\clawd\run_moltworld_python_bot_poll_loop.sh"
$botSh = Join-Path $projectRoot "scripts\clawd\run_moltworld_python_bot.sh"
foreach ($f in @($loopSh, $pollSh, $botSh)) {
    if (-not (Test-Path $f)) { Write-Host "Missing $f" -ForegroundColor Red; exit 1 }
}

# Deploy to both
Write-Host "Deploying Python bot scripts to $Sparky1Host and $Sparky2Host..." -ForegroundColor Cyan
scp -q $loopSh $botSh "${Sparky1Host}:${RemoteRepoPath}/scripts/clawd/"
scp -q $pollSh $botSh "${Sparky2Host}:${RemoteRepoPath}/scripts/clawd/"
ssh $Sparky1Host "sed -i 's/\r$//' ${RemoteRepoPath}/scripts/clawd/run_moltworld_python_bot_loop.sh ${RemoteRepoPath}/scripts/clawd/run_moltworld_python_bot.sh 2>/dev/null; chmod +x ${RemoteRepoPath}/scripts/clawd/run_moltworld_python_bot_loop.sh ${RemoteRepoPath}/scripts/clawd/run_moltworld_python_bot.sh"
ssh $Sparky2Host "sed -i 's/\r$//' ${RemoteRepoPath}/scripts/clawd/run_moltworld_python_bot_poll_loop.sh ${RemoteRepoPath}/scripts/clawd/run_moltworld_python_bot.sh 2>/dev/null; chmod +x ${RemoteRepoPath}/scripts/clawd/run_moltworld_python_bot_poll_loop.sh ${RemoteRepoPath}/scripts/clawd/run_moltworld_python_bot.sh"

# Kill existing loops if any
ssh $Sparky1Host "pkill -f 'run_moltworld_python_bot_loop' 2>/dev/null; sleep 1; echo ok"
ssh $Sparky2Host "pkill -f 'run_moltworld_python_bot_poll_loop' 2>/dev/null; sleep 1; echo ok"

if ($Background) {
    Write-Host "Starting narrator loop on $Sparky1Host (every ${NarratorIntervalSec}s)..." -ForegroundColor Cyan
    ssh $Sparky1Host "cd $RemoteRepoPath && nohup bash scripts/clawd/run_moltworld_python_bot_loop.sh >> ~/.moltworld_python_narrator.log 2>&1 </dev/null & disown 2>/dev/null; echo started"
    Write-Host "Starting poll loop on $Sparky2Host (poll ${PollIntervalSec}s)..." -ForegroundColor Cyan
    ssh $Sparky2Host "cd $RemoteRepoPath && nohup bash scripts/clawd/run_moltworld_python_bot_poll_loop.sh >> ~/.moltworld_python_poll.log 2>&1 </dev/null & disown 2>/dev/null; echo started"
    Write-Host "Done. Logs: ssh $Sparky1Host tail -f ~/.moltworld_python_narrator.log; ssh $Sparky2Host tail -f ~/.moltworld_python_poll.log" -ForegroundColor Green
    return
}

Write-Host "Starting narrator on $Sparky1Host in background..." -ForegroundColor Cyan
ssh $Sparky1Host "cd $RemoteRepoPath && NARRATOR_INTERVAL_SEC=$NarratorIntervalSec nohup bash scripts/clawd/run_moltworld_python_bot_loop.sh >> ~/.moltworld_python_narrator.log 2>&1 </dev/null & disown 2>/dev/null; echo started"
Write-Host "Starting poll loop on $Sparky2Host in background..." -ForegroundColor Cyan
ssh $Sparky2Host "cd $RemoteRepoPath && AGENT_ID=MalicorSparky2 POLL_INTERVAL_SEC=$PollIntervalSec nohup bash scripts/clawd/run_moltworld_python_bot_poll_loop.sh >> ~/.moltworld_python_poll.log 2>&1 </dev/null & disown 2>/dev/null; echo started"
Write-Host "Loops started. Tail logs to see activity." -ForegroundColor Green
