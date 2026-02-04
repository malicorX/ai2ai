# Post to Moltbook now on sparky2 with safe quoting.
# Usage: .\scripts\moltbook\run_moltbook_post_now.ps1 -Title "..." -Content "..." [-Submolt general] [-Target sparky2]
param(
    [string]$Target = "sparky2",
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$Content,
    [string]$Submolt = "general"
)

$ErrorActionPreference = "Stop"

$titleB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Title))
$contentB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Content))

$cmd = "MB_TITLE_B64=$titleB64 MB_CONTENT_B64=$contentB64 MB_SUBMOLT=$Submolt /home/malicor/ai2ai/scripts/moltbook/moltbook_post_on_sparky.sh"
ssh $Target $cmd
