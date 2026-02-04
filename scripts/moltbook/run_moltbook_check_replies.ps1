# Copy moltbook_check_replies_on_sparky.sh to sparky2 and run it. Run from dev machine.
# Usage: .\scripts\moltbook\run_moltbook_check_replies.ps1 [-Target sparky2] [-AutoReply] [-QueueReplies] [-DraftReplies] [-MaxDrafts 5] [-ReplyTemplate "Thanks..."]
param(
    [string]$Target = "sparky2",
    [switch]$AutoReply,
    [switch]$QueueReplies,
    [switch]$DraftReplies,
    [int]$MaxDrafts = 5,
    [string]$ReplyTemplate = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$localScript = Join-Path $scriptDir "moltbook_check_replies_on_sparky.sh"

if (-not (Test-Path $localScript)) {
    Write-Host "Missing $localScript" -ForegroundColor Red
    exit 1
}

ssh $Target "mkdir -p ~/ai2ai/scripts/moltbook" 2>$null
scp -q $localScript "${Target}:~/ai2ai/scripts/moltbook/moltbook_check_replies_on_sparky.sh"
ssh $Target "sed -i 's/\r$//' ~/ai2ai/scripts/moltbook/moltbook_check_replies_on_sparky.sh 2>/dev/null; chmod +x ~/ai2ai/scripts/moltbook/moltbook_check_replies_on_sparky.sh"

$envParts = @()
if ($AutoReply) { $envParts += "MOLTBOOK_AUTO_REPLY=1" }
if ($QueueReplies) { $envParts += "MOLTBOOK_QUEUE_REPLIES=1" }
if ($ReplyTemplate) { $envParts += "MOLTBOOK_REPLY_TEMPLATE=`"$ReplyTemplate`"" }
$envPrefix = if ($envParts.Count -gt 0) { ($envParts -join " ") + " " } else { "" }

ssh $Target "$envPrefix bash ~/ai2ai/scripts/moltbook/moltbook_check_replies_on_sparky.sh"

if ($DraftReplies) {
    $draftScript = Join-Path $scriptDir "run_moltbook_reply_draft.ps1"
    if (-not (Test-Path $draftScript)) {
        Write-Host "Missing $draftScript" -ForegroundColor Red
        exit 1
    }
    & $draftScript -Target $Target -MaxDrafts $MaxDrafts
}
