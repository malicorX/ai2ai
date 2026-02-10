# Solid MoltWorld turn: pull world/recent_chat on each sparky, inject into the turn message, then wake the gateway.
# The agent receives the data in the message and only has to call chat_say (no reliance on world_state being called first).
#
# Usage: .\scripts\clawd\run_moltworld_pull_and_wake_now.ps1
# Requires: Each sparky has ~/.moltworld.env (WORLD_AGENT_TOKEN, AGENT_ID, DISPLAY_NAME) and gateway running.
param(
    [string[]]$Hosts = @("sparky1", "sparky2")
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$shScript = Join-Path $scriptDir "run_moltworld_pull_and_wake.sh"

foreach ($target in $Hosts) {
    $cmd = if ($target -eq "sparky1") { "clawdbot" } else { "openclaw" }
    Write-Host "Pull world + wake on $target (solid flow)..." -ForegroundColor Cyan
    scp -q $shScript "${target}:/tmp/run_moltworld_pull_and_wake.sh" 2>$null
    $out = ssh $target "sed -i 's/\r$//' /tmp/run_moltworld_pull_and_wake.sh 2>/dev/null; chmod +x /tmp/run_moltworld_pull_and_wake.sh; CLAW=$cmd bash /tmp/run_moltworld_pull_and_wake.sh" 2>&1
    Write-Host $out
    if ($out -match '"ok":\s*true') { Write-Host "  $target : OK" -ForegroundColor Green } else { Write-Host "  $target : check output above" -ForegroundColor Yellow }
    if ($target -eq "sparky1") {
        Write-Host "  Waiting 75s for turn to complete..." -ForegroundColor Gray
        Start-Sleep -Seconds 75
    } elseif ($target -eq "sparky2") {
        Write-Host "  Waiting 75s for turn to complete..." -ForegroundColor Gray
        Start-Sleep -Seconds 75
    }
}

Write-Host "`nCheck world chat: https://www.theebie.de/ui/" -ForegroundColor Gray
