# Quick diagnostic: why did TestBot (or another user) get no answer from the OpenClaw/Clawd bots?
# Runs on your machine, SSHs to sparky2 (and optionally sparky1) to check poll loop, logs, and gateway.
#
# Usage: .\scripts\clawd\run_moltworld_why_no_answer.ps1
#   Or:  .\scripts\clawd\run_moltworld_why_no_answer.ps1 -TriggerWake  (also run one manual pull-and-wake to answer the pending question now)
param(
    [string]$TargetHost = "sparky2",   # host that should reply (OpenClaw = sparky2)
    [switch]$TriggerWake               # run one manual pull-and-wake after diagnostics to answer pending question
)

$ErrorActionPreference = "Continue"
$claw = if ($TargetHost -eq "sparky1") { "clawdbot" } else { "openclaw" }
$gwLog = if ($TargetHost -eq "sparky1") { "~/.clawdbot/gateway.log" } else { "~/.openclaw/gateway.log" }

Write-Host "=== Why no answer? Diagnostic for $TargetHost (CLAW=$claw) ===" -ForegroundColor Cyan
Write-Host ""

# 1) Is the poll loop running?
Write-Host "1) Poll loop process on $TargetHost :" -ForegroundColor Yellow
$proc = ssh $TargetHost "pgrep -af 'run_moltworld_poll_and_wake_loop' 2>/dev/null || true" 2>$null
if ($proc) {
    Write-Host "   Running: $proc" -ForegroundColor Green
} else {
    Write-Host "   NOT RUNNING. No reply will happen until something triggers a wake (cron, webhook, or manual)." -ForegroundColor Red
    Write-Host "   Fix: .\scripts\clawd\run_moltworld_poll_loop_on_sparky.ps1 -TargetHost $TargetHost -Background -PollIntervalSec 10" -ForegroundColor Gray
}
Write-Host ""

# 2) Last poll log lines (did it see the new message?)
Write-Host "2) Last 20 lines of ~/.moltworld_poll.log on $TargetHost :" -ForegroundColor Yellow
$pollLog = ssh $TargetHost "tail -n 20 ~/.moltworld_poll.log 2>/dev/null" 2>$null
if ($pollLog) {
    $pollLog -split "`n" | ForEach-Object { Write-Host "   $_" }
} else {
    Write-Host "   (no log or empty)" -ForegroundColor DarkGray
}
Write-Host ""

# 3) Last gateway activity (wake, tools, errors)
Write-Host "3) Last 35 lines of gateway log (wake/tools/errors) on $TargetHost :" -ForegroundColor Yellow
$gw = ssh $TargetHost "tail -n 80 $gwLog 2>/dev/null | grep -iE 'wake|hooks|cron|chat_say|world_state|tool|error|timeout|401|res' | tail -n 35" 2>$null
if (-not $gw) { $gw = ssh $TargetHost "tail -n 35 $gwLog 2>/dev/null" 2>$null }
if ($gw) {
    $gw -split "`n" | ForEach-Object { Write-Host "   $_" }
} else {
    Write-Host "   (no log or unreachable)" -ForegroundColor DarkGray
}
Write-Host ""

# 4) Gateway reachable?
Write-Host "4) Gateway health (localhost:18789 on $TargetHost):" -ForegroundColor Yellow
$code = ssh $TargetHost "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18789/ 2>/dev/null" 2>$null
if ($code -eq "200") { Write-Host "   OK (200)" -ForegroundColor Green } else { Write-Host "   Not OK (code=$code). Gateway may be down." -ForegroundColor Red }
Write-Host ""

# 5) Optional: trigger one wake now
if ($TriggerWake) {
    Write-Host "5) Triggering one manual pull-and-wake on $TargetHost ..." -ForegroundColor Cyan
    $out = ssh $TargetHost "CLAW=$claw bash /tmp/run_moltworld_pull_and_wake.sh 2>&1" 2>$null
    Write-Host $out
    Write-Host "   Done. Check theebie/MoltWorld for a reply in ~1-2 min." -ForegroundColor Gray
} else {
    Write-Host "5) To answer the pending question now, run:" -ForegroundColor Gray
    Write-Host "   .\scripts\clawd\run_moltworld_why_no_answer.ps1 -TriggerWake" -ForegroundColor Gray
    Write-Host "   Or: ssh $TargetHost `"CLAW=$claw bash /tmp/run_moltworld_pull_and_wake.sh`"" -ForegroundColor Gray
}
