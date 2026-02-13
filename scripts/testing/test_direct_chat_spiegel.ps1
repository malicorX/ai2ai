# Test direct chat (context off): minimal payload "what's on www.spiegel.de", expect world_state returns _direct_chat and model uses web_fetch then chat_say.
# Requires: context off on TargetHost (set_moltworld_context.ps1 -Off), gateway restarted so MOLTWORLD_CONTEXT=off is set.
# Usage: .\scripts\testing\test_direct_chat_spiegel.ps1 [-TargetHost sparky2]
param([string]$TargetHost = "sparky2")

$ErrorActionPreference = "Stop"
$projectRoot = (Get-Item $PSScriptRoot).Parent.Parent.FullName
$clawdDir = Join-Path $projectRoot "scripts\clawd"

Write-Host "Direct-chat Spiegel test on $TargetHost (context must be OFF)" -ForegroundColor Cyan
$ctx = ssh -o BatchMode=yes -o ConnectTimeout=10 $TargetHost "cat ~/.moltworld_context 2>/dev/null | tr -d '\r\n'" 2>$null
if ($ctx -ne "off") {
    Write-Host "  WARNING: ~/.moltworld_context is not 'off' on $TargetHost. Run: .\scripts\clawd\set_moltworld_context.ps1 -Off" -ForegroundColor Yellow
}
# Minimal user message only (no MoltWorld block)
$inputText = "what's on www.spiegel.de now? give me some infos about the current articles"
$payload = @{ model = "openclaw:main"; input = $inputText } | ConvertTo-Json
$payloadPath = Join-Path $env:TEMP "direct_chat_spiegel_payload.json"
$payload | Set-Content -Path $payloadPath -Encoding UTF8 -NoNewline
scp -q $payloadPath "${TargetHost}:/tmp/direct_chat_spiegel_payload.json" 2>$null
# Write the runner script locally then scp it (avoids escaping hell)
$runShContent = @'
set -e
CONFIG="${HOME}/.openclaw/openclaw.json"
[[ -f "$CONFIG" ]] || { echo "No $CONFIG"; exit 1; }
GW_TOKEN=$(python3 -c "
import json,sys,os
with open(sys.argv[1]) as f: d=json.load(f)
gw=d.get('gateway',{}); auth=gw.get('auth') or {}
print(auth.get('token') or gw.get('token') or '')
" "$CONFIG" 2>/dev/null)
[[ -n "$GW_TOKEN" ]] || { echo "NO_GW_TOKEN"; exit 1; }
code=$(curl -s -S -X POST http://127.0.0.1:18789/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $GW_TOKEN" \
  -H "x-openclaw-agent-id: main" \
  --data-binary @/tmp/direct_chat_spiegel_payload.json \
  -o /tmp/direct_chat_response.json -w "%{http_code}")
echo "HTTP $code"
'@
$runShPath = Join-Path $env:TEMP "run_direct_chat_spiegel.sh"
$runShContent | Set-Content -Path $runShPath -Encoding ASCII -NoNewline
scp -q $runShPath "${TargetHost}:/tmp/run_direct_chat_spiegel.sh" 2>$null
ssh -o BatchMode=yes -o ConnectTimeout=10 $TargetHost "sed -i 's/\r$//' /tmp/run_direct_chat_spiegel.sh 2>/dev/null; chmod +x /tmp/run_direct_chat_spiegel.sh; bash /tmp/run_direct_chat_spiegel.sh" 2>&1 | ForEach-Object { Write-Host "  $_" }

Write-Host "  Waiting 90s for turn (world_state -> web_fetch -> chat_say)..." -ForegroundColor Gray
Start-Sleep -Seconds 90

$gwLog = ssh $TargetHost "tail -n 400 ~/.openclaw/gateway.log 2>/dev/null" 2>$null
Write-Host "`n--- Gateway log (last 400 lines) ---" -ForegroundColor Cyan
if ($gwLog) {
    $hasContextOff = $gwLog | Select-String -Pattern "context_off=true"
    $hasWebFetch = $gwLog | Select-String -Pattern "web_fetch|fetch_url"
    $hasDirectChat = $gwLog | Select-String -Pattern "_direct_chat|DIRECT CHAT"
    if ($hasContextOff) { Write-Host "  [OK] context_off=true seen in log" -ForegroundColor Green } else { Write-Host "  [??] context_off=true NOT seen - plugin may not have run or file not off" -ForegroundColor Yellow }
    if ($hasWebFetch) { Write-Host "  [OK] web_fetch/fetch_url seen" -ForegroundColor Green } else { Write-Host "  [??] web_fetch/fetch_url NOT seen" -ForegroundColor Yellow }
    $gwLog | Select-Object -Last 80 | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray }
}
Write-Host "---" -ForegroundColor Cyan
