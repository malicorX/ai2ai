# Deploy and start the 5s poll loop on the replier sparky (default: sparky2). Response time: ~5s to detect new chat + ~60-90s for the turn.
# Usage: .\scripts\clawd\run_moltworld_poll_loop_on_sparky.ps1
#   Or:  .\scripts\clawd\run_moltworld_poll_loop_on_sparky.ps1 -Host sparky2 -Background
param(
    [string]$Host = "sparky2",
    [switch]$Background  # if set, start loop in background (nohup) and exit
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$loopSh = Join-Path $scriptDir "run_moltworld_poll_and_wake_loop.sh"
$pullSh = Join-Path $scriptDir "run_moltworld_pull_and_wake.sh"
if (-not (Test-Path $loopSh)) {
    Write-Host "ERROR: $loopSh not found." -ForegroundColor Red
    exit 1
}

$claw = if ($Host -eq "sparky1") { "clawdbot" } else { "openclaw" }
Write-Host "Deploying poll loop to $Host (CLAW=$claw)..." -ForegroundColor Cyan
scp -q $loopSh "${Host}:/tmp/run_moltworld_poll_and_wake_loop.sh"
scp -q $pullSh "${Host}:/tmp/run_moltworld_pull_and_wake.sh"

if ($Background) {
    $out = ssh $Host "sed -i 's/\r$//' /tmp/run_moltworld_poll_and_wake_loop.sh /tmp/run_moltworld_pull_and_wake.sh 2>/dev/null; chmod +x /tmp/run_moltworld_poll_and_wake_loop.sh /tmp/run_moltworld_pull_and_wake.sh; nohup env SCRIPT_DIR=/tmp CLAW=$claw bash /tmp/run_moltworld_poll_and_wake_loop.sh >> ~/.moltworld_poll.log 2>&1 & echo started"
    Write-Host $out
    Write-Host "Loop running in background. Log: ssh $Host tail -f ~/.moltworld_poll.log" -ForegroundColor Gray
    exit 0
}

Write-Host "Starting loop (foreground). Ctrl+C to stop." -ForegroundColor Gray
ssh -t $Host "sed -i 's/\r$//' /tmp/run_moltworld_poll_and_wake_loop.sh /tmp/run_moltworld_pull_and_wake.sh 2>/dev/null; chmod +x /tmp/run_moltworld_poll_and_wake_loop.sh /tmp/run_moltworld_pull_and_wake.sh; env SCRIPT_DIR=/tmp CLAW=$claw bash /tmp/run_moltworld_poll_and_wake_loop.sh"
