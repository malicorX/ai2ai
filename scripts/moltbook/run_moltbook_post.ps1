# Copy Moltbook post/queue/maybe-post scripts to sparky2. Run from dev machine.
# Usage: .\scripts\moltbook\run_moltbook_post.ps1 [-Target sparky2]
param(
    [string]$Target = "sparky2",
    [string]$RemoteScriptsPath = "~/ai2ai/scripts/moltbook"
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
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
Write-Host "On sparky2:" -ForegroundColor Green
Write-Host '  Post now:     ./moltbook_post_on_sparky.sh "Title" "Content" general' -ForegroundColor Cyan
Write-Host '  Queue post:   ./moltbook_queue_on_sparky.sh "Title" "Content" general' -ForegroundColor Cyan
Write-Host "  Maybe post:   ./moltbook_maybe_post_on_sparky.sh   # checks daily cap + queue + 30min; posts one from queue" -ForegroundColor Cyan
Write-Host "  Prepare run:  ./moltbook_prepare_from_run_on_sparky.sh   # if today's test log exists, queue one summary" -ForegroundColor Cyan
Write-Host "Cron (hourly: check if there is something to post, then post one from queue):" -ForegroundColor Green
Write-Host "  0 * * * * $RemoteScriptsPath/moltbook_prepare_from_run_on_sparky.sh; $RemoteScriptsPath/moltbook_maybe_post_on_sparky.sh >> /tmp/moltbook_cron.log 2>&1" -ForegroundColor Cyan
