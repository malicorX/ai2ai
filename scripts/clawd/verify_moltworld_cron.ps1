# Quick verify: MoltWorld chat crons and world presence.
# Usage: .\scripts\clawd\verify_moltworld_cron.ps1
param()

$worldUrl = "https://www.theebie.de/world"

Write-Host "=== Cron status ===" -ForegroundColor Cyan
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
}
Write-Host "`nCheck world chat at: https://www.theebie.de/ui/" -ForegroundColor Gray
