# Test that MoltWorld world state (GET /world, recent_chat) is receivable by the agent.
# Phase 1 (API): Inject a token, then GET /world with Sparky2 agent token; assert recent_chat contains it.
#   Proves: backend returns recent_chat to a client using the agent token (same as the plugin uses).
# Phase 2 (echo): Trigger sparky2 turn to call world_state and chat_say RECEIVED iff token seen.
#   Proves: the model calls the tools and conditions on recent_chat (optional; model-dependent).
#
# Usage: .\scripts\testing\test_moltworld_receive.ps1 [-ApiOnly] [-AgentTokenSparky2 <token>]
#   ADMIN_TOKEN: for injecting the message.
#   AGENT_TOKEN_SPARKY2 or -AgentTokenSparky2: for Phase 1 (GET /world). Get from sparky2:
#     ssh sparky2 'jq -r ".plugins.entries[\"openclaw-moltworld\"].config.token" ~/.openclaw/openclaw.json'
#   -ApiOnly: run only Phase 1 (no SSH to sparky2).
param(
    [string]$BaseUrl = "",
    [string]$AdminToken = "",
    [string]$AgentTokenSparky2 = "",
    [string]$SecondAgentHost = "sparky2",
    [switch]$ApiOnly = $false
)

$ErrorActionPreference = "Stop"
if (-not $BaseUrl) { $BaseUrl = $env:MOLTWORLD_BASE_URL }
if (-not $BaseUrl) { $BaseUrl = "https://www.theebie.de" }
if (-not $AdminToken) { $AdminToken = $env:ADMIN_TOKEN }

if (-not $AgentTokenSparky2) { $AgentTokenSparky2 = $env:AGENT_TOKEN_SPARKY2 }
$base = $BaseUrl.TrimEnd("/")
if (-not $AdminToken) {
    Write-Host "ADMIN_TOKEN is not set. Set it or pass -AdminToken." -ForegroundColor Red
    exit 1
}

$echoToken = "MOLTWORLD_ECHO_" + [guid]::NewGuid().ToString("N").Substring(0, 12)

Write-Host "MoltWorld receive test (does agent get world/recent_chat?)" -ForegroundColor Cyan
Write-Host "  Base: $base" -ForegroundColor Gray
Write-Host "  Echo token: $echoToken" -ForegroundColor Gray

$adminHeaders = @{ "Content-Type" = "application/json"; "Authorization" = "Bearer $AdminToken" }

# 1) Inject the token as a message from Sparky1Agent
try {
    $body = @{ sender_id = "Sparky1Agent"; sender_name = "Sparky1Agent"; text = $echoToken } | ConvertTo-Json
    Invoke-RestMethod -Uri "$base/admin/chat/say" -Headers $adminHeaders -Method Post -Body $body | Out-Null
    Write-Host "  Injected: Sparky1Agent said the echo token" -ForegroundColor Green
} catch {
    Write-Host "  admin/chat/say failed: $_" -ForegroundColor Red
    exit 1
}

Start-Sleep -Seconds 3

# Phase 1 (API): GET /world with Sparky2 token — does MoltWorld return recent_chat with our token?
if ($AgentTokenSparky2) {
    Write-Host "  Phase 1 (API): GET /world with Sparky2 agent token..." -ForegroundColor Cyan
    try {
        $world = Invoke-RestMethod -Uri "$base/world" -Method Get -Headers @{ "Authorization" = "Bearer $AgentTokenSparky2" } -TimeoutSec 10
        $recent = @($world.recent_chat)
        $found = $false
        foreach ($m in $recent) {
            if (($m.text -as [string]) -like "*$echoToken*") { $found = $true; break }
        }
        if ($found) {
            Write-Host "  Phase 1 PASS: GET /world returned recent_chat containing the echo token (MoltWorld push/receive path works at API level)." -ForegroundColor Green
        } else {
            Write-Host "  Phase 1 FAIL: GET /world did not return recent_chat containing the token. recent_chat count: $($recent.Count)" -ForegroundColor Red
            exit 1
        }
    } catch {
        Write-Host "  Phase 1 FAIL: GET /world failed: $_" -ForegroundColor Red
        exit 1
    }
    if ($ApiOnly) {
        Write-Host "  (ApiOnly: skipping Phase 2)" -ForegroundColor Gray
        exit 0
    }
} else {
    Write-Host "  Phase 1 skipped (set AgentTokenSparky2 or AGENT_TOKEN_SPARKY2 to test GET /world)." -ForegroundColor Gray
    if ($ApiOnly) {
        Write-Host "  (ApiOnly: no Phase 2.)" -ForegroundColor Gray
        exit 0
    }
}

# Phase 2: Trigger sparky2 with echo script (world_state then chat_say RECEIVED iff token in recent_chat)
$projectRoot = (Get-Item $PSScriptRoot).Parent.Parent.FullName
$shScript = Join-Path $projectRoot "scripts\clawd\run_moltworld_echo_once.sh"
if (-not (Test-Path $shScript)) {
    Write-Host "  Missing $shScript" -ForegroundColor Red
    exit 1
}
Write-Host "  Triggering $SecondAgentHost echo turn..." -ForegroundColor Cyan
scp -q $shScript "${SecondAgentHost}:/tmp/run_moltworld_echo_once.sh"
$runOut = ssh $SecondAgentHost "ECHO_TOKEN=$echoToken bash /tmp/run_moltworld_echo_once.sh" 2>&1
Write-Host "  Turn run: $runOut" -ForegroundColor Gray

# 3) Poll for RECEIVED or NOT_RECEIVED from MalicorSparky2
$maxWaitSec = 100
$pollIntervalSec = 15
$waited = 0
$reply = ""

while ($waited -le $maxWaitSec) {
    try {
        $chat = Invoke-RestMethod -Uri "$base/chat/recent?limit=20" -Method Get -TimeoutSec 10
    } catch {
        if ($waited -ge $maxWaitSec) { break }
        Start-Sleep -Seconds $pollIntervalSec
        $waited += $pollIntervalSec
        continue
    }
    $messages = @($chat.messages)
    foreach ($m in $messages) {
        if (($m.sender_id -as [string]) -ne "MalicorSparky2") { continue }
        $text = ($m.text -as [string]).Trim()
        if ($text -eq "RECEIVED" -or $text -like "*RECEIVED*") { $reply = "RECEIVED"; break }
        if ($text -eq "NOT_RECEIVED" -or $text -like "*NOT_RECEIVED*") { $reply = "NOT_RECEIVED"; break }
    }
    if ($reply) { break }
    if ($waited -ge $maxWaitSec) { break }
    Write-Host "  No RECEIVED/NOT_RECEIVED yet (${waited}s)..." -ForegroundColor Gray
    Start-Sleep -Seconds $pollIntervalSec
    $waited += $pollIntervalSec
}

if ($reply -eq "RECEIVED") {
    Write-Host "" -ForegroundColor Gray
    Write-Host "PASS: MalicorSparky2 received MoltWorld data (saw the token in recent_chat and replied RECEIVED)." -ForegroundColor Green
    exit 0
}

if ($reply -eq "NOT_RECEIVED") {
    Write-Host "" -ForegroundColor Gray
    Write-Host "FAIL: MalicorSparky2 called world_state but did NOT see the token in recent_chat (replied NOT_RECEIVED). Check backend GET /world returns recent_chat and agent token has access." -ForegroundColor Red
    exit 1
}

Write-Host "" -ForegroundColor Gray
Write-Host "FAIL: No RECEIVED or NOT_RECEIVED from MalicorSparky2 within ${maxWaitSec}s. Model may not have called the tools or gateway timed out." -ForegroundColor Red
exit 1
