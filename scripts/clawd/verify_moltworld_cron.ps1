# Quick verify: MoltWorld chat crons, gateway reachability, webhooks (notify on new chat), and world presence.
# Usage: .\scripts\clawd\verify_moltworld_cron.ps1
# Optional: ADMIN_TOKEN env → list webhooks (agents get notified on new chat only if webhooks registered).
param()

$worldUrl = "https://www.theebie.de/world"
$baseUrl = "https://www.theebie.de"
$curlCheck = "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 http://127.0.0.1:18789/ 2>/dev/null"

Write-Host "=== Gateway reachable (port 18789) ===" -ForegroundColor Cyan
$c1 = (ssh sparky1 $curlCheck 2>$null)
$c2 = (ssh sparky2 $curlCheck 2>$null)
if ($c1 -eq "200") { Write-Host "  sparky1: OK" -ForegroundColor Green } else { Write-Host "  sparky1: down (code $c1). Run .\scripts\clawd\run_restart_gateways_on_sparkies.ps1" -ForegroundColor Yellow }
if ($c2 -eq "200") { Write-Host "  sparky2: OK" -ForegroundColor Green } else { Write-Host "  sparky2: down (code $c2). Run .\scripts\clawd\run_restart_gateways_on_sparkies.ps1" -ForegroundColor Yellow }

$adminToken = $env:ADMIN_TOKEN
if ($adminToken) {
    Write-Host "`n=== Notify on new chat (webhooks) ===" -ForegroundColor Cyan
    try {
        $wh = Invoke-RestMethod -Uri "$baseUrl/admin/moltworld/webhooks" -Headers @{ "Authorization" = "Bearer $adminToken" } -Method Get -ErrorAction Stop
        $list = @($wh.webhooks)
        if ($list.Count -eq 0) {
            Write-Host "  No webhooks registered. Agents are NOT notified when someone posts; they only run on cron schedule (every 2 min)." -ForegroundColor Yellow
            Write-Host "  To enable: Phase B in OPENCLAW_BOT_TO_BOT_STATUS_AND_PLAN.md (hooks.enabled + register URL)." -ForegroundColor Gray
        } else {
            Write-Host "  $($list.Count) webhook(s) registered (agents can be notified on new chat):" -ForegroundColor Green
            foreach ($w in $list) { Write-Host "    $($w.agent_id) -> $($w.url)" -ForegroundColor Gray }
        }
    } catch {
        Write-Host "  Could not list webhooks (need ADMIN_TOKEN): $_" -ForegroundColor Gray
    }
} else {
    Write-Host "`n=== Notify on new chat (webhooks) ===" -ForegroundColor Cyan
    Write-Host "  Set ADMIN_TOKEN to list webhooks. Without webhooks, agents are NOT notified on new chat; only cron (every 2 min)." -ForegroundColor Gray
}

Write-Host "`n=== Cron status ===" -ForegroundColor Cyan
Write-Host "sparky1:" -ForegroundColor Gray
ssh sparky1 "source ~/.nvm/nvm.sh 2>/dev/null; source ~/.bashrc 2>/dev/null; clawdbot cron list" 2>$null
Write-Host "sparky2:" -ForegroundColor Gray
ssh sparky2 "source ~/.nvm/nvm.sh 2>/dev/null; source ~/.bashrc 2>/dev/null; openclaw cron list" 2>$null

Write-Host "`n=== World (theebie.de) ===" -ForegroundColor Cyan
try {
    $r = Invoke-RestMethod -Uri $worldUrl -Method Get -ErrorAction Stop
    $agents = $r.agents
    if ($agents) {
        foreach ($a in $agents) {
            $name = if ($a.display_name) { $a.display_name } else { $a.agent_id }
            $seen = if ($a.last_seen_at) { [DateTimeOffset]::FromUnixTimeSeconds([long][double]$a.last_seen_at).LocalDateTime.ToString("yyyy-MM-dd HH:mm:ss") } else { "n/a" }
            Write-Host "  $name at ($($a.x),$($a.y)) last_seen $seen" -ForegroundColor Green
        }
    } else {
        Write-Host "  No agents in world." -ForegroundColor Yellow
    }
} catch {
    Write-Host "  Could not fetch world: $_" -ForegroundColor Yellow
    $r = $null
}

if ($r -and $r.recent_chat) {
    $chat = @($r.recent_chat)
    $lastN = $chat | Select-Object -Last 3
    Write-Host "`n=== Last chat (recent_chat) ===" -ForegroundColor Cyan
    foreach ($m in $lastN) {
        $sender = $m.sender_name -as [string]
        if (-not $sender) { $sender = $m.sender_id -as [string] }
        $text = ($m.text -as [string])
        if (-not $text) { $text = "" }
        if ($text.Length -gt 50) { $text = $text.Substring(0, 47) + "..." }
        $ts = $m.created_at
        $tStr = if ($ts) { [DateTimeOffset]::FromUnixTimeSeconds([long][double]$ts).LocalDateTime.ToString("HH:mm:ss") } else { "n/a" }
        Write-Host "  [$tStr] $sender : $text" -ForegroundColor Gray
    }
}

Write-Host "`nCheck world chat at: https://www.theebie.de/ui/" -ForegroundColor Gray
