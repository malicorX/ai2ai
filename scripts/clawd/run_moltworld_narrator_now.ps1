# Trigger one narrator turn on sparky1 now (same as one cycle of the 5‑minute narrator loop). Handy for testing.
# Usage: .\scripts\clawd\run_moltworld_narrator_now.ps1
param(
    [string]$TargetHost = "sparky1",
    [switch]$NoDeploy   # skip scp; use existing /tmp/run_moltworld_pull_and_wake.sh on host
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pullSh = Join-Path $scriptDir "run_moltworld_pull_and_wake.sh"

Write-Host "Narrator turn (sparky1) now..." -ForegroundColor Cyan
if (-not $NoDeploy) {
    scp -q $pullSh "${TargetHost}:/tmp/run_moltworld_pull_and_wake.sh"
}
# Do not set MOLTWORLD_SKIP_IF_UNCHANGED so the script always does full pull + wake (skip block only runs when that var is set).
$out = ssh $TargetHost "sed -i 's/\r$//' /tmp/run_moltworld_pull_and_wake.sh 2>/dev/null; chmod +x /tmp/run_moltworld_pull_and_wake.sh; CLAW=clawdbot bash /tmp/run_moltworld_pull_and_wake.sh" 2>&1
Write-Host $out
if ($out -match '"ok":\s*true') { Write-Host "  Done." -ForegroundColor Green } else { Write-Host "  Check output above." -ForegroundColor Yellow }
Write-Host "Check chat: https://www.theebie.de/ui/" -ForegroundColor Gray
