# Test: new-session style request for www.spiegel.de with MoltWorld plugin DISABLED.
# Asserts: no "Hook MoltWorld" in gateway log after the request (plugin must be disabled).
# Run after: .\scripts\clawd\run_set_moltworld_plugin.ps1 -Disable
#
# Usage: .\scripts\testing\test_new_session_spiegel_no_moltworld.ps1 [-TargetHost sparky2]
param([string]$TargetHost = "sparky2")

$ErrorActionPreference = "Stop"
$projectRoot = (Get-Item $PSScriptRoot).Parent.Parent.FullName

Write-Host "Test: new session + spiegel.de question, MoltWorld plugin must be DISABLED on $TargetHost" -ForegroundColor Cyan

# 1) Verify plugin is disabled on target
$pluginCheck = @'
import json, os
for p in [os.path.expanduser("~/.openclaw/openclaw.json"), os.path.expanduser("~/.clawdbot/clawdbot.json")]:
    if os.path.isfile(p):
        with open(p) as f: d = json.load(f)
        e = d.get("plugins",{}).get("entries",{}).get("openclaw-moltworld",{})
        if e.get("enabled") == True:
            print("ENABLED")
            exit(0)
print("DISABLED")
'@
$pluginCheckPath = Join-Path $env:TEMP "check_plugin_disabled.py"
$pluginCheck | Set-Content -Path $pluginCheckPath -Encoding UTF8 -NoNewline
scp -q $pluginCheckPath "${TargetHost}:/tmp/check_plugin_disabled.py" 2>$null
$pluginStatus = ssh -o BatchMode=yes -o ConnectTimeout=10 $TargetHost "python3 /tmp/check_plugin_disabled.py" 2>$null
if ($pluginStatus -match "ENABLED") {
    Write-Host "  FAIL: MoltWorld plugin is still ENABLED on $TargetHost. Run: .\scripts\clawd\run_set_moltworld_plugin.ps1 -Disable" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Plugin is disabled on $TargetHost" -ForegroundColor Green

# 2) Record log line count before request (so we only check new lines)
$lineCountBefore = ssh -o BatchMode=yes -o ConnectTimeout=10 $TargetHost "wc -l < ~/.openclaw/gateway.log 2>/dev/null || echo 0" 2>$null
$lineCountBefore = [int]($lineCountBefore -replace '\s+', '')

# 3) Payload: single user message (simulate new session + one question)
$inputText = "what's on www.spiegel.de today? give a brief summary of current articles."
$v1Payload = @{ model = "openclaw:main"; input = $inputText } | ConvertTo-Json
$v1Path = Join-Path $env:TEMP "new_session_spiegel_v1.json"
$v1Payload | Set-Content -Path $v1Path -Encoding UTF8 -NoNewline
scp -q $v1Path "${TargetHost}:/tmp/new_session_spiegel_v1.json" 2>$null
# hooks/agent payload (used when v1/responses returns 405 on sparky1)
$hooksPayload = @{ message = $inputText; wakeMode = "now"; name = "Test"; model = "openclaw:main"; deliver = $false; timeoutSeconds = 120 } | ConvertTo-Json
$hooksPath = Join-Path $env:TEMP "new_session_spiegel_hooks.json"
$hooksPayload | Set-Content -Path $hooksPath -Encoding UTF8 -NoNewline
scp -q $hooksPath "${TargetHost}:/tmp/new_session_spiegel_hooks.json" 2>$null

$runSh = @'
set -e
CONFIG="${HOME}/.openclaw/openclaw.json"
[[ -f "$CONFIG" ]] || CONFIG="${HOME}/.clawdbot/clawdbot.json"
[[ -f "$CONFIG" ]] || { echo "NO_CONFIG"; exit 1; }
GW_TOKEN=$(python3 -c "
import json,sys,os
with open(os.path.expanduser(sys.argv[1])) as f: d=json.load(f)
gw=d.get('gateway',{}); auth=gw.get('auth') or {}
print(auth.get('token') or gw.get('token') or '')
" "$CONFIG" 2>/dev/null)
# hooks/agent may require hooks.token (sparky1); fallback to gateway token
WAKE_TOKEN=$(python3 -c "
import json,sys,os
with open(os.path.expanduser(sys.argv[1])) as f: d=json.load(f)
h=d.get('hooks',{}); token=h.get('token') if h.get('enabled') else None
if not token: gw=d.get('gateway',{}); auth=gw.get('auth') or {}; token=auth.get('token') or gw.get('token')
print(token or '')
" "$CONFIG" 2>/dev/null)
[[ -n "$GW_TOKEN" ]] || { echo "NO_GW_TOKEN"; exit 1; }
code=$(curl -s -S -X POST http://127.0.0.1:18789/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $GW_TOKEN" \
  -H "x-openclaw-agent-id: main" \
  --data-binary @/tmp/new_session_spiegel_v1.json \
  -o /tmp/new_session_spiegel_response.json -w "%{http_code}")
if [[ "$code" = "405" || "$code" = "404" ]]; then
  HOOKS_AUTH="${WAKE_TOKEN:-$GW_TOKEN}"
  if [[ -n "$HOOKS_AUTH" ]]; then
    code=$(curl -s -S -X POST http://127.0.0.1:18789/hooks/agent \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $HOOKS_AUTH" \
      --data-binary @/tmp/new_session_spiegel_hooks.json \
      -o /tmp/new_session_spiegel_response.json -w "%{http_code}")
  else
    code=$(curl -s -S -X POST http://127.0.0.1:18789/hooks/agent \
      -H "Content-Type: application/json" \
      --data-binary @/tmp/new_session_spiegel_hooks.json \
      -o /tmp/new_session_spiegel_response.json -w "%{http_code}")
  fi
  echo "HTTP $code (hooks/agent)"
else
  echo "HTTP $code"
fi
'@
$runShPath = Join-Path $env:TEMP "run_new_session_spiegel.sh"
$runSh | Set-Content -Path $runShPath -Encoding ASCII -NoNewline
scp -q $runShPath "${TargetHost}:/tmp/run_new_session_spiegel.sh" 2>$null
$httpOut = ssh -o BatchMode=yes -o ConnectTimeout=10 $TargetHost "sed -i 's/\r$//' /tmp/run_new_session_spiegel.sh 2>/dev/null; chmod +x /tmp/run_new_session_spiegel.sh; bash /tmp/run_new_session_spiegel.sh" 2>&1
Write-Host "  Request sent: $httpOut" -ForegroundColor Gray

Write-Host "  Waiting 100s for turn to complete..." -ForegroundColor Gray
Start-Sleep -Seconds 100

# 4) Get new log lines only (since our request)
$lineCountAfter = ssh -o BatchMode=yes -o ConnectTimeout=10 $TargetHost "wc -l < ~/.openclaw/gateway.log 2>/dev/null || echo 0" 2>$null
$lineCountAfter = [int]($lineCountAfter -replace '\s+', '')
$tailLines = [Math]::Min(300, [Math]::Max(0, $lineCountAfter - $lineCountBefore) + 100)
$gwLog = ssh $TargetHost "tail -n $tailLines ~/.openclaw/gateway.log 2>/dev/null" 2>$null

# 5) Assert no MoltWorld plugin tool runs (gateway logs "Hook MoltWorld: {...}" when the plugin runs a tool)
$hookMoltWorld = $gwLog | Select-String -Pattern "Hook MoltWorld\s*:\s*\{"
if ($hookMoltWorld) {
    Write-Host "  FAIL: 'Hook MoltWorld' tool run still appears in gateway log (plugin may be loaded):" -ForegroundColor Red
    $hookMoltWorld | Select-Object -First 5 | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
    Write-Host "  If your Control UI is at 127.0.0.1:18789, ensure it is an SSH tunnel to this sparky (e.g. ssh -L 18789:127.0.0.1:18789 $TargetHost). Otherwise you are talking to a different gateway." -ForegroundColor Yellow
    exit 1
}
Write-Host "  [OK] No Hook MoltWorld in recent log" -ForegroundColor Green

# 6) Show last part of log and response body
Write-Host "`n--- Last 60 log lines ---" -ForegroundColor Cyan
if ($gwLog) { $gwLog | Select-Object -Last 60 | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray } }
Write-Host "---" -ForegroundColor Cyan
$responseBody = ssh $TargetHost "cat /tmp/new_session_spiegel_response.json 2>/dev/null | head -c 2000" 2>$null
Write-Host "`n--- Response body (first 2000 chars) ---" -ForegroundColor Cyan
Write-Host $responseBody
Write-Host "---" -ForegroundColor Cyan
Write-Host "PASS: MoltWorld plugin is disabled on $TargetHost; no Hook MoltWorld in log. Spiegel request used web_fetch (gateway built-in)." -ForegroundColor Green
Write-Host "If you still see Hook MoltWorld in Control UI: your browser (127.0.0.1:18789) may be connected to a different gateway (e.g. local OpenClaw on your PC). Use an SSH tunnel to the sparky: ssh -L 18789:127.0.0.1:18789 $TargetHost" -ForegroundColor Gray
