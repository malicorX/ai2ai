# Copy moltbook_cron_replies_on_sparky.sh to sparky2 and run it. Run from dev machine.
# Usage: .\scripts\moltbook\run_moltbook_cron_replies.ps1 [-Target sparky2]
param(
    [string]$Target = "sparky2"
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot

$scripts = @(
    "moltbook_check_replies_on_sparky.sh",
    "moltbook_reply_queue_process_on_sparky.sh",
    "moltbook_cron_replies_on_sparky.sh"
)

foreach ($s in $scripts) {
    $local = Join-Path $scriptDir $s
    if (-not (Test-Path $local)) {
        Write-Host "Missing $local" -ForegroundColor Red
        exit 1
    }
}

ssh $Target "mkdir -p ~/ai2ai/scripts/moltbook" 2>$null
foreach ($s in $scripts) {
    scp -q (Join-Path $scriptDir $s) "${Target}:~/ai2ai/scripts/moltbook/$s"
}
ssh $Target "sed -i 's/\r$//' ~/ai2ai/scripts/moltbook/*.sh 2>/dev/null; chmod +x ~/ai2ai/scripts/moltbook/*.sh"

ssh $Target "bash ~/ai2ai/scripts/moltbook/moltbook_cron_replies_on_sparky.sh"
