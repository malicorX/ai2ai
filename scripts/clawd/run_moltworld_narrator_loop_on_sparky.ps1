# Deploy and optionally start the narrator loop on sparky1 (sparky1 starts conversations; sparky2 replies via its poll loop).
# Usage: .\scripts\clawd\run_moltworld_narrator_loop_on_sparky.ps1
#   Or:  .\scripts\clawd\run_moltworld_narrator_loop_on_sparky.ps1 -Background   # start loop in background
#   Or:  .\scripts\clawd\run_moltworld_narrator_loop_on_sparky.ps1 -IntervalSec 600   # every 10 min
param(
    [string]$TargetHost = "sparky1",
    [switch]$Background,
    [int]$IntervalSec = 300
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$narratorSh = Join-Path $scriptDir "run_moltworld_narrator_loop.sh"
$pullSh = Join-Path $scriptDir "run_moltworld_pull_and_wake.sh"
if (-not (Test-Path $narratorSh)) {
    Write-Host "ERROR: $narratorSh not found." -ForegroundColor Red
    exit 1
}

Write-Host "Deploying narrator loop to $TargetHost (runs every ${IntervalSec}s)..." -ForegroundColor Cyan
scp -q $narratorSh "${TargetHost}:/tmp/run_moltworld_narrator_loop.sh"
scp -q $pullSh "${TargetHost}:/tmp/run_moltworld_pull_and_wake.sh"

$envStr = "SCRIPT_DIR=/tmp CLAW=clawdbot NARRATOR_INTERVAL_SEC=$IntervalSec"
if ($Background) {
    $out = ssh $TargetHost "sed -i 's/\r$//' /tmp/run_moltworld_narrator_loop.sh /tmp/run_moltworld_pull_and_wake.sh 2>/dev/null; chmod +x /tmp/run_moltworld_narrator_loop.sh /tmp/run_moltworld_pull_and_wake.sh; nohup env $envStr bash /tmp/run_moltworld_narrator_loop.sh >> ~/.moltworld_narrator.log 2>&1 & echo started"
    Write-Host $out
    Write-Host "Narrator loop running in background. Log: ssh $TargetHost tail -f ~/.moltworld_narrator.log" -ForegroundColor Gray
    Write-Host "When sparky1 posts, sparky2's poll loop will wake and reply (ensure poll loop is running on sparky2)." -ForegroundColor Gray
    exit 0
}

Write-Host "Starting narrator loop (foreground, every ${IntervalSec}s). Ctrl+C to stop." -ForegroundColor Gray
ssh -t $TargetHost "sed -i 's/\r$//' /tmp/run_moltworld_narrator_loop.sh /tmp/run_moltworld_pull_and_wake.sh 2>/dev/null; chmod +x /tmp/run_moltworld_narrator_loop.sh /tmp/run_moltworld_pull_and_wake.sh; env $envStr bash /tmp/run_moltworld_narrator_loop.sh"
