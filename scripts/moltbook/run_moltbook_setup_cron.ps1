# Install or update the Moltbook queue cron job on sparky1 or sparky2.
# Ensures one cron line every 2 hours: run prepare_from_run (if test log exists), then maybe_post (post one from queue).
# Best behavior: at most 1 post per 2h per agent; daily cap still applies (MOLTBOOK_MAX_POSTS_PER_DAY).
# Usage: .\scripts\moltbook\run_moltbook_setup_cron.ps1 [-Target sparky2] [-WhatIf]
param(
    [string]$Target = "sparky2",
    [switch]$WhatIf = $false
)

$ErrorActionPreference = "Stop"
$RemoteScriptsPath = if ($Target -eq "sparky1") { "~/moltbook_scripts" } else { "~/ai2ai/scripts/moltbook" }
# Every 2 hours at :00 (0 */2 * * *) — matches 2h min interval in maybe_post
$cronLine = "0 */2 * * * $RemoteScriptsPath/moltbook_prepare_from_run_on_sparky.sh; $RemoteScriptsPath/moltbook_maybe_post_on_sparky.sh >> /tmp/moltbook_cron.log 2>&1"

Write-Host "Target: $Target" -ForegroundColor Cyan
Write-Host "Scripts path: $RemoteScriptsPath" -ForegroundColor Cyan
Write-Host "Cron line to install:" -ForegroundColor Yellow
Write-Host "  $cronLine" -ForegroundColor White

if ($WhatIf) {
    Write-Host "WhatIf: not modifying crontab. Run without -WhatIf to install." -ForegroundColor Gray
    exit 0
}

# Remove any existing moltbook cron line (match by log path), then add our line. Use a single line for SSH.
$cronEscaped = $cronLine -replace "'", "'\\''"
$fullCmd = "( (crontab -l 2>/dev/null || true) | grep -v 'moltbook_cron.log' | grep -v '^ *\$'; echo '$cronEscaped' ) | crontab -"
ssh $Target $fullCmd
Write-Host "Crontab updated. Verify with: ssh $Target crontab -l" -ForegroundColor Green
