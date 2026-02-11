# Test POST /chat/say to theebie with an agent token. Use to verify the token works and the
# backend accepts the message (or see 401/error). Run after deploying plugin debug so gateway
# logs show chat_say response; run this from your machine to isolate token/network.
#
# Usage: .\scripts\clawd\test_chat_say_to_theebie.ps1 -Token "your-agent-token" -SenderId "MalicorSparky2"
#   Or set env: $env:WORLD_AGENT_TOKEN = "..." then .\scripts\clawd\test_chat_say_to_theebie.ps1
param(
    [string]$BaseUrl = "https://www.theebie.de",
    [string]$Token = $env:WORLD_AGENT_TOKEN,
    [string]$SenderId = "MalicorSparky2",
    [string]$SenderName = "MalicorSparky2",
    [string]$Text = "Test message from test_chat_say_to_theebie.ps1"
)

$ErrorActionPreference = "Stop"
if (-not $Token) {
    Write-Host "ERROR: Set -Token or env WORLD_AGENT_TOKEN (agent token for $SenderId)" -ForegroundColor Red
    exit 1
}

$url = "$BaseUrl/chat/say"
$body = @{ sender_id = $SenderId; sender_name = $SenderName; text = $Text } | ConvertTo-Json
$headers = @{
    "Content-Type" = "application/json"
    "Authorization" = "Bearer $Token"
}
Write-Host "POST $url" -ForegroundColor Cyan
Write-Host "  sender_id=$SenderId text=$Text" -ForegroundColor Gray
try {
    $r = Invoke-WebRequest -Uri $url -Method Post -Body $body -Headers $headers -TimeoutSec 15 -UseBasicParsing
    Write-Host "Status: $($r.StatusCode)" -ForegroundColor Green
    Write-Host $r.Content
} catch {
    $status = [int]$_.Exception.Response.StatusCode
    Write-Host "Status: $status" -ForegroundColor Red
    if ($_.ErrorDetails.Message) { Write-Host $_.ErrorDetails.Message }
}
