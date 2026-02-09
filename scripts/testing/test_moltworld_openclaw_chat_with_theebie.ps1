# Run the OpenClaw chat test: opener from INSIDE Sparky1's OpenClaw, reply from Sparky2's OpenClaw.
# 1) Gets ADMIN_TOKEN from theebie.
# 2) Triggers Sparky1's gateway /hooks/wake so the model says "Hi, how are you?" via chat_say (opener from inside agent).
# 3) Runs the base test (wait for reply from MalicorSparky2 in recent_chat).
#
# Usage: .\scripts\testing\test_moltworld_openclaw_chat_with_theebie.ps1 [-AgentId Sparky1Agent]
#   -AgentId Sparky1Agent: trigger opener from Sparky1's OpenClaw (default). Other agent (MalicorSparky2) is woken by webhook.
param(
    [string]$TheebieHost = "root@84.38.65.246",
    [string]$AgentId = "Sparky1Agent",
    [string]$Sparky1Host = "sparky1"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Get-Item $PSScriptRoot).Parent.Parent.FullName

# 1) Get ADMIN_TOKEN from theebie
$adminLine = ssh $TheebieHost "grep -h '^ADMIN_TOKEN=' /opt/ai_ai2ai/.env /opt/ai_ai2ai/deployment/.env 2>/dev/null | head -1"
if (-not $adminLine -or $adminLine -notmatch 'ADMIN_TOKEN=(.+)') {
    $adminLine = ssh $TheebieHost "cd /opt/ai_ai2ai && docker compose -f deployment/docker-compose.sparky1.yml exec -T backend env 2>/dev/null | grep '^ADMIN_TOKEN='"
}
if ($adminLine -match 'ADMIN_TOKEN=(.+)') {
    $env:ADMIN_TOKEN = $matches[1].Trim().Trim('"').Trim("'")
    Write-Host "Got ADMIN_TOKEN from theebie." -ForegroundColor Green
} else {
    Write-Host "Could not get ADMIN_TOKEN from theebie." -ForegroundColor Red
    exit 1
}

# 2) Trigger opener from INSIDE Sparky1's OpenClaw (so both messages come from inside the agents)
if ($AgentId -eq "Sparky1Agent") {
    Write-Host "Triggering Sparky1 OpenClaw to say 'Hi, how are you?' in MoltWorld (from inside agent)..." -ForegroundColor Cyan
    $configJson = ssh $Sparky1Host "cat ~/.clawdbot/clawdbot.json 2>/dev/null"
    $gatewayToken = $null
    try {
        $config = $configJson | ConvertFrom-Json
        if ($config.gateway.auth.token) { $gatewayToken = $config.gateway.auth.token }
    } catch { }
    if (-not $gatewayToken) {
        Write-Host "Could not read Sparky1 gateway token from ~/.clawdbot/clawdbot.json." -ForegroundColor Yellow
        Write-Host "Falling back to script-sent opener (not from inside OpenClaw)." -ForegroundColor Yellow
        $json = ssh $TheebieHost "cat /opt/ai_ai2ai/backend_data/agent_tokens.json 2>/dev/null || echo '{}'"
        $tokenMap = $json | ConvertFrom-Json
        foreach ($p in $tokenMap.PSObject.Properties) { if ($p.Value -eq "Sparky1Agent") { $env:AGENT_TOKEN = $p.Name; $env:AGENT_ID = "Sparky1Agent"; break } }
        & (Join-Path $projectRoot "scripts\testing\test_moltworld_openclaw_chat.ps1") -BaseUrl "https://www.theebie.de"
        exit $LASTEXITCODE
    }
    $wakePayload = '{"text":"You are Sparky1Agent in MoltWorld. Call world_state to get the world, then call chat_say with exactly this short message: Hi, how are you? Use only the tools; do not reply with only text.","mode":"now"}'
    $b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($wakePayload))
    $wakeOut = ssh $Sparky1Host "echo $b64 | base64 -d | curl -s -X POST http://127.0.0.1:18789/hooks/wake -H 'Content-Type: application/json' -H 'Authorization: Bearer $gatewayToken' --data-binary @-"
    Write-Host "  Sparky1 /hooks/wake sent (opener from inside OpenClaw)." -ForegroundColor Green
}

# 3) Run the base test (wait for opener, then for reply). Trigger Sparky2's turn via SSH so it reads and replies
#    even when theebie cannot reach sparky2 for webhooks.
& (Join-Path $projectRoot "scripts\testing\test_moltworld_openclaw_chat.ps1") -BaseUrl "https://www.theebie.de" -OpenerFromOpenClaw -FirstAgentId "Sparky1Agent" -ExpectedOpener "Hi, how are you?" -SecondAgentHost "sparky2" -SecondAgentClaw "openclaw"
exit $LASTEXITCODE
