# Copy moltbook_reply_queue_process_on_sparky.sh to sparky2 and run it. Run from dev machine.
# Usage: .\scripts\moltbook\run_moltbook_reply_queue_process.ps1 [-Target sparky2] [-ReplyTemplate "Thanks..."] [-MinIntervalSeconds 120]
param(
    [string]$Target = "sparky2",
    [string]$ReplyTemplate = "",
    [int]$MinIntervalSeconds = 120
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$localScript = Join-Path $scriptDir "moltbook_reply_queue_process_on_sparky.sh"

if (-not (Test-Path $localScript)) {
    Write-Host "Missing $localScript" -ForegroundColor Red
    exit 1
}

ssh $Target "mkdir -p ~/ai2ai/scripts/moltbook" 2>$null
scp -q $localScript "${Target}:~/ai2ai/scripts/moltbook/moltbook_reply_queue_process_on_sparky.sh"
ssh $Target "sed -i 's/\r$//' ~/ai2ai/scripts/moltbook/moltbook_reply_queue_process_on_sparky.sh 2>/dev/null; chmod +x ~/ai2ai/scripts/moltbook/moltbook_reply_queue_process_on_sparky.sh"

$envParts = @()
if ($ReplyTemplate) { $envParts += "MOLTBOOK_REPLY_TEMPLATE=`"$ReplyTemplate`"" }
if ($MinIntervalSeconds -gt 0) { $envParts += "MOLTBOOK_REPLY_MIN_INTERVAL=$MinIntervalSeconds" }
$envPrefix = if ($envParts.Count -gt 0) { ($envParts -join " ") + " " } else { "" }

ssh $Target "$envPrefix bash ~/ai2ai/scripts/moltbook/moltbook_reply_queue_process_on_sparky.sh"
