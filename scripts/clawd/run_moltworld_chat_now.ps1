# Trigger one MoltWorld chat turn on both sparkies now (no wait for cron).
# Uses gateway cron job: model is told to "call world_state then chat_say" (pull is up to the model).
# For a solid pull (script fetches world and injects into the message), use run_moltworld_pull_and_wake_now.ps1 instead.
# Usage: .\scripts\clawd\run_moltworld_chat_now.ps1
# Requires: MoltWorld chat cron already added (add_moltworld_chat_cron.ps1); gateways running.
param()

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$shScript = Join-Path $scriptDir "run_moltworld_chat_once.sh"

foreach ($target in @("sparky1", "sparky2")) {
    $cmd = if ($target -eq "sparky1") { "clawdbot" } else { "openclaw" }
    Write-Host "Running MoltWorld chat turn on $target..." -ForegroundColor Cyan
    scp -q $shScript "${target}:/tmp/run_moltworld_chat_once.sh"
    $out = ssh $target "CLAW=$cmd bash /tmp/run_moltworld_chat_once.sh" 2>&1
    Write-Host $out
    if ($out -match '"ok":\s*true' -or $out -match 'cron run') { Write-Host "  $target : OK" -ForegroundColor Green } else { Write-Host "  $target : check output above" -ForegroundColor Yellow }
    # Main-session cron run only enqueues a system event; the LLM turn runs on next heartbeat (async).
    # Gateway logs show turns often take 50-75s. Wait so the turn completes and chat_say hits the backend.
    if ($target -eq "sparky1") {
        Write-Host "  Waiting 75s for sparky1's turn to complete (main-session heartbeat + LLM + chat_say)..." -ForegroundColor Gray
        Start-Sleep -Seconds 75
    } elseif ($target -eq "sparky2") {
        Write-Host "  Waiting 75s for sparky2's turn to complete..." -ForegroundColor Gray
        Start-Sleep -Seconds 75
    }
}

Write-Host "`nCheck world chat: https://www.theebie.de/ui/" -ForegroundColor Gray
