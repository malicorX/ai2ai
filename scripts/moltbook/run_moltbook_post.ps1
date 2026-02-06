# Copy Moltbook post/queue/maybe-post scripts to sparky1 or sparky2. Run from dev machine.
# Usage: .\scripts\moltbook\run_moltbook_post.ps1 [-Target sparky2]  or  -Target sparky1
# sparky1 uses ~/moltbook_scripts (no repo path); sparky2 uses ~/ai2ai/scripts/moltbook.
param(
    [string]$Target = "sparky2",
    [string]$RemoteScriptsPath = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
if (-not $RemoteScriptsPath) {
    $RemoteScriptsPath = if ($Target -eq "sparky1") { "~/moltbook_scripts" } else { "~/ai2ai/scripts/moltbook" }
}
$scripts = @(
    "moltbook_post_on_sparky.sh",
    "moltbook_queue_on_sparky.sh",
    "moltbook_maybe_post_on_sparky.sh",
    "moltbook_prepare_from_run_on_sparky.sh",
    "moltbook_cron_post_on_sparky.sh"
)
foreach ($s in $scripts) {
    if (-not (Test-Path (Join-Path $scriptDir $s))) {
        Write-Host "Missing $s" -ForegroundColor Red
        exit 1
    }
}

Write-Host "Copying Moltbook scripts to ${Target}:$RemoteScriptsPath" -ForegroundColor Cyan
ssh $Target "mkdir -p $RemoteScriptsPath" 2>$null
foreach ($s in $scripts) {
    scp -q (Join-Path $scriptDir $s) "${Target}:$RemoteScriptsPath/$s"
}
ssh $Target "sed -i 's/\r$//' $RemoteScriptsPath/moltbook_post_on_sparky.sh $RemoteScriptsPath/moltbook_queue_on_sparky.sh $RemoteScriptsPath/moltbook_maybe_post_on_sparky.sh $RemoteScriptsPath/moltbook_prepare_from_run_on_sparky.sh $RemoteScriptsPath/moltbook_cron_post_on_sparky.sh 2>/dev/null; chmod +x $RemoteScriptsPath/moltbook_post_on_sparky.sh $RemoteScriptsPath/moltbook_queue_on_sparky.sh $RemoteScriptsPath/moltbook_maybe_post_on_sparky.sh $RemoteScriptsPath/moltbook_prepare_from_run_on_sparky.sh $RemoteScriptsPath/moltbook_cron_post_on_sparky.sh"
Write-Host "On ${Target} (scripts at $RemoteScriptsPath):" -ForegroundColor Green
Write-Host '  Post now:     ./moltbook_post_on_sparky.sh "Title" "Content" general' -ForegroundColor Cyan
Write-Host '  Queue post:   ./moltbook_queue_on_sparky.sh "Title" "Content" general' -ForegroundColor Cyan
Write-Host "  Maybe post:   ./moltbook_maybe_post_on_sparky.sh   # checks daily cap + queue + 30min; posts one from queue" -ForegroundColor Cyan
Write-Host "  Prepare run:  ./moltbook_prepare_from_run_on_sparky.sh   # if today's test log exists, queue one summary" -ForegroundColor Cyan
Write-Host "Cron (hourly: check queue and post one if allowed):" -ForegroundColor Green
Write-Host "  0 * * * * $RemoteScriptsPath/moltbook_prepare_from_run_on_sparky.sh; $RemoteScriptsPath/moltbook_maybe_post_on_sparky.sh >> /tmp/moltbook_cron.log 2>&1" -ForegroundColor Cyan
Write-Host "To install cron on this host: .\scripts\moltbook\run_moltbook_setup_cron.ps1 -Target $Target" -ForegroundColor Yellow
