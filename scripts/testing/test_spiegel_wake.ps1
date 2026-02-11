# Test MoltWorld wake with "what's on www.spiegel.de" on sparky2.
# Option A: If ADMIN_TOKEN set, inject question via theebie then run pull-and-wake.
# Option B: Direct wake with fixed payload (no theebie) to test gateway+agent only.
param(
    [string]$BaseUrl = "https://www.theebie.de",
    [string]$AdminToken = $env:ADMIN_TOKEN,
    [string]$TargetHost = "sparky2",
    [switch]$DirectWake  # Use fixed payload and POST /v1/responses only (no theebie inject)
)

$ErrorActionPreference = "Stop"
$projectRoot = (Get-Item $PSScriptRoot).Parent.Parent.FullName
$clawdDir = Join-Path $projectRoot "scripts\clawd"

Write-Host "Spiegel wake test on $TargetHost" -ForegroundColor Cyan

if (-not $DirectWake -and $AdminToken) {
    Write-Host "  Injecting question via admin/chat/say then pull-and-wake..." -ForegroundColor Gray
    $question = "what's on www.spiegel.de?"
    $body = @{ sender_id = "TestBot"; sender_name = "TestBot"; text = $question } | ConvertTo-Json
    $headers = @{ "Content-Type" = "application/json"; "Authorization" = "Bearer $AdminToken" }
    try {
        Invoke-RestMethod -Uri "$BaseUrl/admin/chat/say" -Headers $headers -Method Post -Body $body -TimeoutSec 15 | Out-Null
        Write-Host "  Injected: TestBot said the question" -ForegroundColor Green
    } catch {
        Write-Host "  admin/chat/say failed: $_" -ForegroundColor Red
        Write-Host "  Falling back to DirectWake (fixed payload, no theebie)" -ForegroundColor Yellow
        $DirectWake = $true
    }
    if (-not $DirectWake) { Start-Sleep -Seconds 3 }
}

if ($DirectWake -or -not $AdminToken) {
    Write-Host "  Using direct wake (fixed payload, POST /v1/responses on $TargetHost)..." -ForegroundColor Gray
    $inputText = @"
You are MalicorSparky2. MoltWorld recent_chat (latest message last):

  TestBot: what's on www.spiegel.de?

You have the tools world_state, web_fetch (or fetch_url), and chat_say. Use them: call world_state first to get recent_chat and minute_of_day (for time questions). For questions about a webpage (e.g. 'what is on the frontpage of X'), call web_fetch or fetch_url with that URL, then call chat_say with a short summary. Do not say 'functions are insufficient'—use the tools.

Read the last message above. If it is a question, answer it: use world_state and fetch_url as needed, then call chat_say with your answer. If you cannot answer, call chat_say with exactly: I don't know how to answer this, sorry. Always reply using chat_say; do not reply with plain text only.
"@
    $v1Payload = @{ model = "openclaw:main"; input = $inputText } | ConvertTo-Json -Depth 5
    $payloadPath = Join-Path $projectRoot "scripts\testing\v1_spiegel_payload.json"
    $v1Payload | Set-Content -Path $payloadPath -Encoding UTF8
    scp -q $payloadPath "${TargetHost}:/tmp/v1_spiegel_payload.json"
}

# Run pull-and-wake (or direct curl if DirectWake)
if ($DirectWake -or -not $AdminToken) {
    $runSh = Join-Path $clawdDir "run_v1_spiegel_test.sh"
    scp -q $runSh "${TargetHost}:/tmp/run_v1_spiegel_test.sh"
    $runOut = ssh $TargetHost "sed -i 's/\r$//' /tmp/run_v1_spiegel_test.sh 2>/dev/null; chmod +x /tmp/run_v1_spiegel_test.sh; bash /tmp/run_v1_spiegel_test.sh" 2>&1
} else {
    scp -q (Join-Path $clawdDir "run_moltworld_pull_and_wake.sh") "${TargetHost}:/tmp/run_moltworld_pull_and_wake.sh"
    $runOut = ssh $TargetHost "sed -i 's/\r$//' /tmp/run_moltworld_pull_and_wake.sh 2>/dev/null; chmod +x /tmp/run_moltworld_pull_and_wake.sh; MOLTWORLD_SKIP_IF_UNCHANGED=0 CLAW=openclaw bash /tmp/run_moltworld_pull_and_wake.sh 2>&1" 2>&1
}

Write-Host "  Wake result: $runOut" -ForegroundColor Gray

# Gateway log (before we wait)
$logBefore = ssh $TargetHost "wc -l ~/.openclaw/gateway.log 2>/dev/null" 2>$null
Write-Host "  Waiting 90s for turn + tool calls + chat_say..." -ForegroundColor Gray
Start-Sleep -Seconds 90

$gwLog = ssh $TargetHost "tail -n 350 ~/.openclaw/gateway.log 2>/dev/null" 2>$null
Write-Host "`n--- Gateway log (last 350 lines) ---" -ForegroundColor Cyan
if ($gwLog) { $gwLog | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray } }
Write-Host "---" -ForegroundColor Cyan

# Check theebie for reply
try {
    $recent = Invoke-RestMethod -Uri "$BaseUrl/chat/recent?limit=15" -Method Get -TimeoutSec 10
    $fromAgent = ($recent.messages | Where-Object { $_.sender_id -eq "MalicorSparky2" } | Select-Object -First 3)
    Write-Host "`nRecent from MalicorSparky2 on theebie:" -ForegroundColor Cyan
    if ($fromAgent) { $fromAgent | ForEach-Object { Write-Host "  $($_.created_at): $($_.text)" } } else { Write-Host "  (none)" }
} catch { Write-Host "  GET chat/recent failed: $_" }
