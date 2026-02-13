# Run migrate_sparky_to_openclaw_only.sh on both sparkies so they use OpenClaw only (no Clawdbot).
# Usage: .\scripts\clawd\run_migrate_sparkies_to_openclaw_only.ps1 [-ArchiveClawdbot]
# -ArchiveClawdbot: rename ~/.clawdbot to ~/.clawdbot.archived.<timestamp> on each host.
param(
    [switch]$ArchiveClawdbot,
    [string[]]$Hosts = @("sparky1", "sparky2"),
    [string]$RemotePath = "/home/malicor/ai_ai2ai/scripts/clawd"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$migrateSh = Join-Path $scriptDir "migrate_sparky_to_openclaw_only.sh"
if (-not (Test-Path $migrateSh)) { Write-Host "Missing $migrateSh" -ForegroundColor Red; exit 1 }

$arg = if ($ArchiveClawdbot) { "--archive-clawdbot" } else { "" }
Write-Host "Migrating to OpenClaw only on $($Hosts -join ', ')..." -ForegroundColor Cyan
foreach ($h in $Hosts) {
    Write-Host "`n=== $h ===" -ForegroundColor Cyan
    scp -q $migrateSh "${h}:${RemotePath}/"
    ssh $h "sed -i 's/\r$//' $RemotePath/migrate_sparky_to_openclaw_only.sh; chmod +x $RemotePath/migrate_sparky_to_openclaw_only.sh; bash $RemotePath/migrate_sparky_to_openclaw_only.sh $arg" 2>&1 | ForEach-Object { Write-Host $_ }
}
Write-Host "`nDone. Both sparkies use OpenClaw only. Restart loops if needed: .\scripts\clawd\run_moltworld_openclaw_loops.ps1 -Background" -ForegroundColor Green
