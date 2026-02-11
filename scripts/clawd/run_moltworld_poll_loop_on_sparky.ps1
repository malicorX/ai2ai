# Deploy and start the poll loop on the replier sparky (default: sparky2). Response time: ~5–10s to detect new chat + ~60–90s for the turn.
# Usage: .\scripts\clawd\run_moltworld_poll_loop_on_sparky.ps1
#   Or:  .\scripts\clawd\run_moltworld_poll_loop_on_sparky.ps1 -TargetHost sparky2 -Background
#   Or:  .\scripts\clawd\run_moltworld_poll_loop_on_sparky.ps1 -TargetHost sparky2 -Background -PollIntervalSec 10
param(
    [string]$TargetHost = "sparky2",
    [switch]$Background,  # if set, start loop in background (nohup) and exit
    [int]$PollIntervalSec = 5  # 5 or 10 recommended; 10 = less load, still responsive
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$loopSh = Join-Path $scriptDir "run_moltworld_poll_and_wake_loop.sh"
$pullSh = Join-Path $scriptDir "run_moltworld_pull_and_wake.sh"
if (-not (Test-Path $loopSh)) {
    Write-Host "ERROR: $loopSh not found." -ForegroundColor Red
    exit 1
}

$claw = if ($TargetHost -eq "sparky1") { "clawdbot" } else { "openclaw" }
Write-Host "Deploying poll loop to $TargetHost (CLAW=$claw)..." -ForegroundColor Cyan
scp -q $loopSh "${TargetHost}:/tmp/run_moltworld_poll_and_wake_loop.sh"
scp -q $pullSh "${TargetHost}:/tmp/run_moltworld_pull_and_wake.sh"

$pollEnv = "SCRIPT_DIR=/tmp CLAW=$claw POLL_INTERVAL_SEC=$PollIntervalSec"
if ($Background) {
    $out = ssh $TargetHost "sed -i 's/\r$//' /tmp/run_moltworld_poll_and_wake_loop.sh /tmp/run_moltworld_pull_and_wake.sh 2>/dev/null; chmod +x /tmp/run_moltworld_poll_and_wake_loop.sh /tmp/run_moltworld_pull_and_wake.sh; nohup env $pollEnv bash /tmp/run_moltworld_poll_and_wake_loop.sh >> ~/.moltworld_poll.log 2>&1 & echo started"
    Write-Host $out
    Write-Host "Loop running in background. Log: ssh $TargetHost tail -f ~/.moltworld_poll.log" -ForegroundColor Gray
    exit 0
}

Write-Host "Starting loop (foreground, poll every ${PollIntervalSec}s). Ctrl+C to stop." -ForegroundColor Gray
ssh -t $TargetHost "sed -i 's/\r$//' /tmp/run_moltworld_poll_and_wake_loop.sh /tmp/run_moltworld_pull_and_wake.sh 2>/dev/null; chmod +x /tmp/run_moltworld_poll_and_wake_loop.sh /tmp/run_moltworld_pull_and_wake.sh; env $pollEnv bash /tmp/run_moltworld_poll_and_wake_loop.sh"
