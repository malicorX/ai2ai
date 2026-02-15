# OpenClaw tools test suite: for each agent (sparky1, sparky2) and each available tool,
# send a prompt that should trigger that tool, then verify via gateway log.
# Usage: .\scripts\testing\test_openclaw_tools_suite.ps1 [-Hosts sparky1,sparky2] [-Tools web_fetch,browser,...] [-SkipOptionalExec]
param(
    [string[]]$Hosts = @("sparky1", "sparky2"),
    [string[]]$Tools = @(),   # empty = all
    [switch]$SkipOptionalExec = $true,
    [switch]$IncludeOptional  # include exec test when set
)

$ErrorActionPreference = "Stop"
$projectRoot = (Get-Item $PSScriptRoot).Parent.Parent.FullName
$testsPath = Join-Path $PSScriptRoot "openclaw_tool_tests.json"
if (-not (Test-Path $testsPath)) {
    Write-Host "Missing $testsPath" -ForegroundColor Red
    exit 1
}

$testDef = Get-Content $testsPath -Raw | ConvertFrom-Json
$toolList = $testDef.tools
if ($Tools.Count -gt 0) {
    $toolList = $toolList | Where-Object { $Tools -contains $_.id }
}
if (-not $IncludeOptional -and $SkipOptionalExec) {
    $toolList = $toolList | Where-Object { -not $_.optional }
}

# Remote helper: get gateway token (try openclaw then clawdbot)
$getTokenSh = @'
for c in ~/.openclaw/openclaw.json ~/.clawdbot/clawdbot.json; do
  [ -f "$c" ] || continue
  tok=$(python3 -c "
import json,sys
with open(sys.argv[1]) as f: d=json.load(f)
gw=d.get('gateway',{}); auth=gw.get('auth') or {}
print(auth.get('token') or gw.get('token') or '')
" "$c" 2>/dev/null)
  [ -n "$tok" ] && echo "$tok" && exit 0
done
exit 1
'@

# Remote: get token for hooks/agent (hooks.token or gateway token)
$getWakeTokenSh = @'
for c in ~/.openclaw/openclaw.json ~/.clawdbot/clawdbot.json; do
  [ -f "$c" ] || continue
  tok=$(python3 -c "
import json,sys,os
with open(os.path.expanduser(sys.argv[1])) as f: d=json.load(f)
h=d.get('hooks',{}); token=h.get('token') if h.get('enabled') else None
if not token: gw=d.get('gateway',{}); auth=gw.get('auth') or {}; token=gw.get('token') or auth.get('token')
print(token or '')
" "$c" 2>/dev/null)
  [ -n "$tok" ] && echo "$tok" && exit 0
done
exit 1
'@

# Remote: try v1/responses; on 405/404 try hooks/agent with same prompt as message
$runCurlSh = @'
set -e
GW_TOKEN=$(bash /tmp/ot_suite_get_token.sh)
WAKE_TOKEN=$(bash /tmp/ot_suite_get_wake_token.sh 2>/dev/null) || true
[[ -z "$WAKE_TOKEN" ]] && WAKE_TOKEN="$GW_TOKEN"
code=$(curl -s -S -X POST http://127.0.0.1:18789/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $GW_TOKEN" \
  -H "x-openclaw-agent-id: main" \
  --data-binary @/tmp/ot_suite_payload.json \
  -o /tmp/ot_suite_response.json -w "%{http_code}")
if [[ "$code" = "405" || "$code" = "404" ]]; then
  python3 -c "
import json
d=json.load(open('/tmp/ot_suite_payload.json'))
json.dump({'message': d.get('input',''), 'wakeMode': 'now', 'name': 'Test', 'model': 'openclaw:main', 'deliver': False, 'timeoutSeconds': 120}, open('/tmp/ot_suite_hooks.json','w'))
" 2>/dev/null || true
  if [[ -f /tmp/ot_suite_hooks.json ]]; then
    code=$(curl -s -S -X POST http://127.0.0.1:18789/hooks/agent \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $WAKE_TOKEN" \
      --data-binary @/tmp/ot_suite_hooks.json \
      -o /tmp/ot_suite_response.json -w "%{http_code}")
  fi
fi
echo "$code"
'@

$results = @{}
$logLinesToCheck = 1200

foreach ($targetHost in $Hosts) {
    Write-Host "`n========== $targetHost ==========" -ForegroundColor Cyan
    # Resolve token on host
    $token = $null
    $getTokenFile = Join-Path $env:TEMP "openclaw_suite_get_token.sh"
    $getTokenSh | Set-Content -Path $getTokenFile -Encoding ASCII -NoNewline
    scp -q $getTokenFile "${targetHost}:/tmp/ot_suite_get_token.sh" 2>$null
    $getWakeTokenFile = Join-Path $env:TEMP "ot_suite_get_wake_token.sh"
    $getWakeTokenSh | Set-Content -Path $getWakeTokenFile -Encoding ASCII -NoNewline
    scp -q $getWakeTokenFile "${targetHost}:/tmp/ot_suite_get_wake_token.sh" 2>$null
    $runCurlFile = Join-Path $env:TEMP "ot_suite_run_curl.sh"
    $runCurlSh | Set-Content -Path $runCurlFile -Encoding ASCII -NoNewline
    scp -q $runCurlFile "${targetHost}:/tmp/ot_suite_run_curl.sh" 2>$null
    ssh -o BatchMode=yes -o ConnectTimeout=5 $targetHost "sed -i 's/\r$//' /tmp/ot_suite_get_token.sh /tmp/ot_suite_get_wake_token.sh /tmp/ot_suite_run_curl.sh 2>/dev/null; chmod +x /tmp/ot_suite_run_curl.sh /tmp/ot_suite_get_token.sh /tmp/ot_suite_get_wake_token.sh 2>/dev/null"
    $token = ssh -o BatchMode=yes -o ConnectTimeout=10 $targetHost "bash /tmp/ot_suite_get_token.sh" 2>$null
    if (-not $token) {
        Write-Host "  No gateway token on $targetHost; skip host." -ForegroundColor Yellow
        foreach ($t in $toolList) { $results["${targetHost}:$($t.id)"] = "SKIP" }
        continue
    }

    foreach ($t in $toolList) {
        $id = $t.id
        $name = $t.name
        $prompt = $t.prompt
        $waitSec = $t.waitSeconds
        $pattern = $t.logPattern
        Write-Host "  [$id] $name ... " -NoNewline

        # Payload file locally, scp to host; token is resolved on host to avoid escaping.
        $payloadFile = Join-Path $env:TEMP "ot_suite_payload_$id.json"
        @{ model = "openclaw:main"; input = $prompt } | ConvertTo-Json -Compress | Set-Content -Path $payloadFile -Encoding UTF8 -NoNewline
        scp -q $payloadFile "${targetHost}:/tmp/ot_suite_payload.json" 2>$null

        $codeStr = (ssh -o BatchMode=yes -o ConnectTimeout=15 $targetHost "bash /tmp/ot_suite_run_curl.sh" 2>$null) -replace '\s+$',''
        if (-not $codeStr -or $codeStr -notmatch '^(200|201|202)$') {
            Write-Host "HTTP $codeStr" -ForegroundColor Red
            $results["${targetHost}:$id"] = "FAIL"
            continue
        }

        Start-Sleep -Seconds $waitSec

        # Check gateway log for tool usage (openclaw or clawdbot log)
        $logPaths = "~/.openclaw/gateway.log", "~/.clawdbot/gateway.log"
        $found = $false
        foreach ($lp in $logPaths) {
            $tail = ssh -o BatchMode=yes -o ConnectTimeout=10 $targetHost "tail -n $logLinesToCheck $lp 2>/dev/null" 2>$null
            if ($tail -match $pattern) { $found = $true; break }
        }
        if ($found) {
            Write-Host "OK" -ForegroundColor Green
            $results["${targetHost}:$id"] = "OK"
        } else {
            Write-Host "no log match '$pattern'" -ForegroundColor Yellow
            $results["${targetHost}:$id"] = "FAIL"
        }
    }
}

# Summary table
Write-Host "`n========== Summary ==========" -ForegroundColor Cyan
$hostList = $Hosts
$toolIds = $toolList | ForEach-Object { $_.id }
Write-Host ("Host    | " + ($toolIds -join " | "))
Write-Host ("-------+-" + (($toolIds | ForEach-Object { "---" }) -join "-+-"))
foreach ($h in $hostList) {
    $row = $h.PadRight(7) + "|"
    foreach ($id in $toolIds) {
        $v = $results["${h}:$id"]
        if ($null -eq $v) { $v = "skip" }
        if ($v -eq "OK") { $row += " OK  |" }
        elseif ($v -eq "FAIL") { $row += " FAIL|" }
        else { $row += " skip|" }
    }
    Write-Host $row
}
Write-Host "`nDone. Run with -Tools web_fetch to test only one tool; -Hosts sparky2 for one host." -ForegroundColor Gray
