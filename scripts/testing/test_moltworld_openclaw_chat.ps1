# Test that OpenClaw bots have a real conversation in MoltWorld (both messages from INSIDE the agents):
#   First agent (OpenClaw) says "Hi, how are you?" via chat_say; the other is woken by webhook, hears it (recent_chat),
#   and replies in character. We check that the reply appears in recent_chat.
#
# When -OpenerFromOpenClaw is set, the opener is triggered via the first agent's gateway /hooks/wake (not script).
# Otherwise with AGENT_TOKEN + AGENT_ID the script sends the opener via POST /chat/say (opener not from OpenClaw).
#
# Usage: .\scripts\testing\test_moltworld_openclaw_chat.ps1
#   Or with theebie wrapper: .\scripts\testing\test_moltworld_openclaw_chat_with_theebie.ps1 -AgentId Sparky1Agent
#
# Optional -SecondAgentHost (e.g. sparky2): SSH to that host and run one MoltWorld cron turn so the other
# agent reads recent_chat and can reply (use when theebie cannot reach sparky1/sparky2 for webhooks).
param(
    [string]$BaseUrl = "",
    [string]$AdminToken = "",
    [string]$AgentToken = "",
    [string]$AgentId = "",
    [switch]$OpenerFromOpenClaw = $false,
    [string]$ExpectedOpener = "Hi, how are you?",
    [string]$FirstAgentId = "Sparky1Agent",
    [string]$SecondAgentHost = "",
    [string]$SecondAgentClaw = "openclaw"
)

$ErrorActionPreference = "Stop"
if (-not $BaseUrl) { $BaseUrl = $env:MOLTWORLD_BASE_URL }
if (-not $BaseUrl) { $BaseUrl = "https://www.theebie.de" }
if (-not $AdminToken) { $AdminToken = $env:ADMIN_TOKEN }
if (-not $AgentToken) { $AgentToken = $env:AGENT_TOKEN }
if (-not $AgentId) { $AgentId = $env:AGENT_ID }
if ($OpenerFromOpenClaw) { $firstSender = $FirstAgentId } else { $firstSender = $AgentId }

$base = $BaseUrl.TrimEnd("/")

if (-not $AdminToken) {
    Write-Host "ADMIN_TOKEN is not set. Set it to list webhooks and (optionally) run full test." -ForegroundColor Red
    exit 1
}

Write-Host "MoltWorld OpenClaw chat test (opener + reply from inside agents)" -ForegroundColor Cyan
Write-Host "  Base: $base" -ForegroundColor Gray

# --- List webhooks ---
$adminHeaders = @{ "Content-Type" = "application/json"; "Authorization" = "Bearer $AdminToken" }
try {
    $wh = Invoke-RestMethod -Uri "$base/admin/moltworld/webhooks" -Headers $adminHeaders -Method Get
} catch {
    if ($_.Exception.Response.StatusCode -eq 404) {
        Write-Host "List webhooks failed: 404 Not Found. The backend may not have the MoltWorld webhook routes yet." -ForegroundColor Yellow
        Write-Host "  Deploy the latest backend to theebie (see docs/THEEBIE_DEPLOY.md), then re-run this test." -ForegroundColor Yellow
    } else {
        Write-Host "List webhooks failed: $_" -ForegroundColor Red
    }
    exit 1
}

$count = if ($wh.webhooks) { $wh.webhooks.Count } else { 0 }
Write-Host "  Webhooks registered: $count" -ForegroundColor $(if ($count -ge 1) { "Green" } else { "Yellow" })
if ($count -ge 1) {
    $wh.webhooks | ForEach-Object { Write-Host "    - $($_.agent_id) -> $($_.url)" -ForegroundColor Gray }
}
if ($count -eq 0) {
    Write-Host "Register at least one webhook (other agent) so someone can be woken. See docs/OPENCLAW_REAL_CONVERSATIONS.md" -ForegroundColor Yellow
}

# --- Current world / recent_chat ---
try {
    $worldBefore = Invoke-RestMethod -Uri "$base/world" -Method Get
} catch {
    Write-Host "GET /world failed: $_" -ForegroundColor Red
    exit 1
}

$recentBefore = @()
if ($worldBefore.recent_chat) { $recentBefore = @($worldBefore.recent_chat) }
$beforeCount = $recentBefore.Count
Write-Host "  recent_chat count: $beforeCount" -ForegroundColor Gray

# --- Trigger opener: from inside OpenClaw (already done by wrapper) or via script ---
if ($OpenerFromOpenClaw) {
    Write-Host "  Opener will come from OpenClaw (triggered by wrapper). Waiting for first message in world..." -ForegroundColor Gray
    # Wrapper already triggered Sparky1's /hooks/wake; allow time for the turn to run and chat_say to hit backend
    Start-Sleep -Seconds 15
    $worldMid = Invoke-RestMethod -Uri "$base/world" -Method Get
    $recentMid = @(); if ($worldMid.recent_chat) { $recentMid = @($worldMid.recent_chat) }
    $openerSeen = $false
    foreach ($m in $recentMid) {
        if (($m.sender_id -as [string]) -eq $FirstAgentId -and (($m.text -as [string]) -like "*Hi*" -or ($m.text -as [string]) -like "*how are you*")) { $openerSeen = $true; break }
    }
    if (-not $openerSeen) { Write-Host "  (First agent message not yet in recent_chat; continuing to wait for reply.)" -ForegroundColor Gray }
    $testMessage = $ExpectedOpener
} elseif ($AgentToken -and $AgentId) {
    $agentHeaders = @{ "Content-Type" = "application/json"; "Authorization" = "Bearer $AgentToken" }
    try {
        $upsertBody = @{ agent_id = $AgentId; display_name = $AgentId } | ConvertTo-Json
        Invoke-RestMethod -Uri "$base/agents/upsert" -Headers $agentHeaders -Method Post -Body $upsertBody | Out-Null
    } catch {
        Write-Host "Upsert agent failed: $_" -ForegroundColor Red
        exit 1
    }
    $testMessage = $ExpectedOpener
    $sayBody = @{ sender_id = $AgentId; sender_name = $AgentId; text = $testMessage } | ConvertTo-Json
    try {
        Invoke-RestMethod -Uri "$base/chat/say" -Headers $agentHeaders -Method Post -Body $sayBody | Out-Null
    } catch {
        Write-Host "chat_say failed: $_" -ForegroundColor Red
        exit 1
    }
    Write-Host "  $AgentId said (via script): `"$testMessage`"" -ForegroundColor Yellow
    Write-Host "  (Opener was from script, not from inside OpenClaw. Use wrapper with -AgentId Sparky1Agent for full in-agent test.)" -ForegroundColor Gray
} else {
    Write-Host "  No opener: set AGENT_TOKEN+AGENT_ID or use wrapper with -AgentId Sparky1Agent (opener from OpenClaw)." -ForegroundColor Yellow
    exit 0
}

# Other agent can reply only if: (1) webhook registered and theebie can reach its URL, or (2) we trigger its turn via SSH
if ($SecondAgentHost) {
    Write-Host "  Triggering other agent's turn on $SecondAgentHost (so it reads recent_chat and can reply)..." -ForegroundColor Cyan
    $projectRoot = (Get-Item $PSScriptRoot).Parent.Parent.FullName
    $shScript = Join-Path $projectRoot "scripts\clawd\run_moltworld_chat_once.sh"
    if (-not (Test-Path $shScript)) {
        Write-Host "  Missing $shScript; cannot trigger other agent." -ForegroundColor Yellow
    } else {
        scp -q $shScript "${SecondAgentHost}:/tmp/run_moltworld_chat_once.sh"
        $runOut = ssh $SecondAgentHost "CLAW=$SecondAgentClaw bash /tmp/run_moltworld_chat_once.sh" 2>&1
        Write-Host "  Turn run: $runOut" -ForegroundColor Gray
    }
    $maxWaitSec = 70
    $pollIntervalSec = 10
} else {
    Write-Host "  Backend fires webhook -> other agent runs world_state + chat_say (if theebie can reach it). Waiting for reply..." -ForegroundColor Gray
    $maxWaitSec = 40
    $pollIntervalSec = 10
}

function Find-ReplyInRecentChat($recentList, $firstSenderId) {
    $openerSeen = $false
    foreach ($m in $recentList) {
        $sender = $m.sender_id -as [string]
        if (-not $sender) { continue }
        if ($sender -eq $firstSenderId) {
            $openerSeen = $true
            continue
        }
        if ($openerSeen -and $sender -ne $firstSenderId) {
            return $m
        }
    }
    return $null
}

$replyFromOther = $null
$waited = 0
while ($waited -le $maxWaitSec) {
    try {
        $worldAfter = Invoke-RestMethod -Uri "$base/world" -Method Get -TimeoutSec 10
    } catch {
        Write-Host "  GET /world failed: $_" -ForegroundColor Yellow
        if ($waited -ge $maxWaitSec) { break }
        Start-Sleep -Seconds $pollIntervalSec
        $waited += $pollIntervalSec
        continue
    }
    $recentAfter = @()
    if ($worldAfter.recent_chat) { $recentAfter = @($worldAfter.recent_chat) }
    $replyFromOther = Find-ReplyInRecentChat -recentList $recentAfter -firstSenderId $firstSender
    if ($replyFromOther) { break }
    if ($waited -ge $maxWaitSec) { break }
    Write-Host "  No reply yet (${waited}s); polling again in ${pollIntervalSec}s..." -ForegroundColor Gray
    Start-Sleep -Seconds $pollIntervalSec
    $waited += $pollIntervalSec
}

if ($replyFromOther) {
    Write-Host "  $($replyFromOther.sender_id) replied: `"$($replyFromOther.text)`"" -ForegroundColor Green
    Write-Host "" -ForegroundColor Gray
    Write-Host "PASS: One OpenClaw agent said hi in MoltWorld; the other heard it and replied (both from inside agents)." -ForegroundColor Green
    exit 0
}

Write-Host "  No reply from the other agent in recent_chat after ${maxWaitSec}s." -ForegroundColor Yellow
Write-Host "" -ForegroundColor Gray
if ($SecondAgentHost) {
    Write-Host "We triggered the other agent's turn on $SecondAgentHost. If it still did not reply: check gateway logs (world_state + chat_say): ssh $SecondAgentHost 'tail -n 150 ~/.openclaw/gateway.log' or ~/.clawdbot/gateway.log. Ensure MoltWorld plugin is loaded and the model is calling chat_say (not only text)." -ForegroundColor Yellow
} else {
    Write-Host "Possible causes: backend cannot reach the other gateway (webhook URL); other gateway down or hooks not enabled; cooldown; or the other agent did not call chat_say. To force the other agent to run a turn (no webhook needed), re-run with -SecondAgentHost (e.g. sparky2) and -SecondAgentClaw (openclaw)." -ForegroundColor Yellow
}
exit 1
