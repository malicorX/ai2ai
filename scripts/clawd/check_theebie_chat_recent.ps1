# Check whether a reply from the OpenClaw bot made it to theebie backend.
# Fetches GET /chat/recent from theebie and lists recent messages; use to see if
# MalicorSparky2's (or Sparky1Agent's) reply is in the backend when the UI doesn't show it.
#
# Usage: .\scripts\clawd\check_theebie_chat_recent.ps1
#   Or:  .\scripts\clawd\check_theebie_chat_recent.ps1 -BaseUrl "https://www.theebie.de" -Last 30
param(
    [string]$BaseUrl = "https://www.theebie.de",
    [int]$Last = 50
)

$ErrorActionPreference = "Continue"
$url = "$BaseUrl/chat/recent?limit=$Last"
Write-Host "Fetching $url ..." -ForegroundColor Cyan
try {
    $r = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 15
} catch {
    Write-Host "Request failed: $_" -ForegroundColor Red
    exit 1
}
$msgs = $r.messages
if (-not $msgs) {
    Write-Host "No messages in response (or key 'messages' missing)." -ForegroundColor Yellow
    exit 0
}
$n = $msgs.Count
Write-Host "Last $n messages on theebie:" -ForegroundColor Green
Write-Host ""
foreach ($m in $msgs) {
    $sid = if ($m.sender_id) { $m.sender_id } else { "?" }
    $name = if ($m.sender_name) { $m.sender_name } else { $sid }
    $rawText = if ($m.text) { $m.text.ToString().Trim() } else { "" }
    if ($rawText.Length -gt 70) { $rawText = $rawText.Substring(0, 67) + "..." }
    $ts = $m.created_at
    if ($ts -match "^\d+(\.\d+)?$") {
        $dt = [DateTimeOffset]::FromUnixTimeSeconds([long][double]$ts).LocalDateTime.ToString("yyyy-MM-dd HH:mm:ss")
    } else { $dt = $ts }
    Write-Host "  [$dt] $name ($sid): $rawText"
}
Write-Host ""
$sparky2 = @($msgs | Where-Object { $_.sender_id -eq "MalicorSparky2" })
$sparky1 = @($msgs | Where-Object { $_.sender_id -eq "Sparky1Agent" })
$lastNum = [int]$Last
if ($sparky2.Count -gt 0) {
    Write-Host "MalicorSparky2 messages in last $lastNum : $($sparky2.Count)" -ForegroundColor Green
} else {
    Write-Host "No MalicorSparky2 message in last $lastNum. If the gateway logged chat_say, the POST may have failed (401 token, or backend error)." -ForegroundColor Yellow
}
if ($sparky1.Count -gt 0) {
    Write-Host "Sparky1Agent messages in last $lastNum : $($sparky1.Count)" -ForegroundColor Green
}
