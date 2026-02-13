# Diagnostic: send "what's on www.spiegel.de?" to the gateway, then print:
#   - Plugin/cron/context status, HTTP code, endpoint used
#   - The agent's summary of Spiegel articles (if the gateway logs it as chat_say)
# Use this to see why MoltWorld still appears in the browser and to get a summary of articles.
#
# Usage: .\scripts\testing\run_spiegel_diagnostic.ps1 [-TargetHost sparky1]
# Default target is sparky1. Takes ~2 min (100s wait for the turn).
param([string]$TargetHost = "sparky1")

$ErrorActionPreference = "Stop"
$projectRoot = (Get-Item $PSScriptRoot).Parent.Parent.FullName

Write-Host "`n=== Spiegel diagnostic on $TargetHost ===" -ForegroundColor Cyan

# --- 1) Diagnostics (plugin, context, cron, config) ---
$diagSh = @'
echo "DIAG_START"
CONFIG="$HOME/.openclaw/openclaw.json"
[[ -f "$CONFIG" ]] || CONFIG="$HOME/.clawdbot/clawdbot.json"
echo "CONFIG=$CONFIG"
[[ -f "$CONFIG" ]] && echo "CONFIG_EXISTS=yes" || echo "CONFIG_EXISTS=no"
# Plugin
python3 -c "
import json, os
home = os.path.expanduser('~')
for p in [os.path.join(home, '.openclaw', 'openclaw.json'), os.path.join(home, '.clawdbot', 'clawdbot.json')]:
    if os.path.isfile(p):
        with open(p) as f: d = json.load(f)
        e = d.get('plugins',{}).get('entries',{}).get('openclaw-moltworld',{})
        print('PLUGIN_ENABLED=' + ('yes' if e.get('enabled') is True else 'no'))
        break
else:
    print('PLUGIN_ENABLED=unknown')
" 2>/dev/null || echo "PLUGIN_ENABLED=unknown"
# Context file
if [[ -f "$HOME/.moltworld_context" ]]; then
  echo "CONTEXT_FILE=off"
  cat "$HOME/.moltworld_context" | tr -d '\r\n' | tr '[:upper:]' '[:lower:]' | grep -q '^off$' && echo "CONTEXT_OFF=yes" || echo "CONTEXT_OFF=no"
else
  echo "CONTEXT_FILE=missing"
  echo "CONTEXT_OFF=no"
fi
# MoltWorld cron (gateway)
for cli in clawdbot openclaw; do
  id=$($cli cron list 2>/dev/null | awk '/MoltWorld chat turn/{print $1; exit}' || true)
  if [[ -n "$id" ]]; then
    echo "MOLTWORLD_CRON=yes ($cli id=$id)"
    break
  fi
done
[[ -z "$id" ]] && echo "MOLTWORLD_CRON=no"
echo "DIAG_END"
'@
$diagPath = Join-Path $env:TEMP "spiegel_diag.sh"
$diagSh | Set-Content -Path $diagPath -Encoding ASCII -NoNewline
scp -q $diagPath "${TargetHost}:/tmp/spiegel_diag.sh" 2>$null
$diagOut = ssh -o BatchMode=yes -o ConnectTimeout=10 $TargetHost "bash /tmp/spiegel_diag.sh 2>/dev/null" 2>$null
Write-Host "`n--- Diagnostics ---" -ForegroundColor Yellow
$diagOut | ForEach-Object { Write-Host "  $_" }

# --- 2) Log line count before request ---
$lineCountBefore = ssh -o BatchMode=yes -o ConnectTimeout=10 $TargetHost "wc -l < ~/.openclaw/gateway.log 2>/dev/null || wc -l < ~/.clawdbot/gateway.log 2>/dev/null || echo 0" 2>$null
$lineCountBefore = [int]($lineCountBefore -replace '\s+', '')

# --- 3) Payload and run (same as test_new_session_spiegel_no_moltworld) ---
$inputText = "what's on www.spiegel.de today? give a brief summary of current articles."
$v1Payload = @{ model = "openclaw:main"; input = $inputText } | ConvertTo-Json
$v1Path = Join-Path $env:TEMP "spiegel_diag_v1.json"
$v1Payload | Set-Content -Path $v1Path -Encoding UTF8 -NoNewline
scp -q $v1Path "${TargetHost}:/tmp/spiegel_diag_v1.json" 2>$null
$hooksPayload = @{ message = $inputText; wakeMode = "now"; name = "Test"; model = "openclaw:main"; deliver = $false; timeoutSeconds = 120 } | ConvertTo-Json
$hooksPath = Join-Path $env:TEMP "spiegel_diag_hooks.json"
$hooksPayload | Set-Content -Path $hooksPath -Encoding UTF8 -NoNewline
scp -q $hooksPath "${TargetHost}:/tmp/spiegel_diag_hooks.json" 2>$null

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
  --data-binary @/tmp/spiegel_diag_v1.json \
  -o /tmp/spiegel_diag_response.json -w "%{http_code}")
ENDPOINT="v1/responses"
if [[ "$code" = "405" || "$code" = "404" ]]; then
  HOOKS_AUTH="${WAKE_TOKEN:-$GW_TOKEN}"
  if [[ -n "$HOOKS_AUTH" ]]; then
    code=$(curl -s -S -X POST http://127.0.0.1:18789/hooks/agent \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $HOOKS_AUTH" \
      --data-binary @/tmp/spiegel_diag_hooks.json \
      -o /tmp/spiegel_diag_response.json -w "%{http_code}")
  else
    code=$(curl -s -S -X POST http://127.0.0.1:18789/hooks/agent \
      -H "Content-Type: application/json" \
      --data-binary @/tmp/spiegel_diag_hooks.json \
      -o /tmp/spiegel_diag_response.json -w "%{http_code}")
  fi
  ENDPOINT="hooks/agent"
fi
echo "HTTP_CODE=$code"
echo "ENDPOINT=$ENDPOINT"
'@
$runPath = Join-Path $env:TEMP "spiegel_diag_run.sh"
$runSh | Set-Content -Path $runPath -Encoding ASCII -NoNewline
scp -q $runPath "${TargetHost}:/tmp/spiegel_diag_run.sh" 2>$null
$httpOut = ssh -o BatchMode=yes -o ConnectTimeout=10 $TargetHost "sed -i 's/\r$//' /tmp/spiegel_diag_run.sh 2>/dev/null; chmod +x /tmp/spiegel_diag_run.sh; bash /tmp/spiegel_diag_run.sh" 2>&1
Write-Host "`n--- Request ---" -ForegroundColor Yellow
$httpOut | ForEach-Object { Write-Host "  $_" }

Write-Host "  Waiting 100s for turn (fetch + summary)..." -ForegroundColor Gray
Start-Sleep -Seconds 100

# --- 4) Extract last chat_say text from gateway log (the agent's summary) ---
$extractPy = @'
import sys, re, json
lines = sys.stdin.read()
last_text = None
for line in lines.splitlines():
    if '"chat_say"' not in line or '"arguments"' not in line:
        continue
    m = re.search(r'\{.*\}', line)
    if not m:
        continue
    try:
        d = json.loads(m.group(0))
        if d.get('name') == 'chat_say' and isinstance(d.get('arguments'), dict):
            t = (d.get('arguments') or {}).get('text')
            if isinstance(t, str) and t.strip():
                last_text = t.strip()
    except Exception:
        pass
if last_text:
    print(last_text)
'@
$extractPath = Join-Path $env:TEMP "spiegel_extract_chat_say.py"
$extractPy | Set-Content -Path $extractPath -Encoding UTF8 -NoNewline
scp -q $extractPath "${TargetHost}:/tmp/spiegel_extract_chat_say.py" 2>$null

# Gateway may log to /tmp/openclaw/openclaw-YYYY-MM-DD.log (see gateway startup message); fallback to ~/.openclaw/gateway.log
$getLogAndSummarySh = @'
LOG=$(ls -t /tmp/openclaw/openclaw-*.log 2>/dev/null | head -1)
[ -z "$LOG" ] && LOG=~/.openclaw/gateway.log
[ ! -f "$LOG" ] && LOG=~/.clawdbot/gateway.log
tail -n 500 "$LOG" 2>/dev/null | python3 /tmp/spiegel_extract_chat_say.py 2>/dev/null
'@
$getLogShPath = Join-Path $env:TEMP "spiegel_get_summary.sh"
$getLogAndSummarySh | Set-Content -Path $getLogShPath -Encoding ASCII -NoNewline
scp -q $getLogShPath "${TargetHost}:/tmp/spiegel_get_summary.sh" 2>$null
$summary = ssh -o BatchMode=yes -o ConnectTimeout=15 $TargetHost "bash /tmp/spiegel_get_summary.sh" 2>$null
# Fetch log for Hook MoltWorld check and fallback display (same path logic)
$getLogOnlySh = @'
LOG=$(ls -t /tmp/openclaw/openclaw-*.log 2>/dev/null | head -1)
[ -z "$LOG" ] && LOG=~/.openclaw/gateway.log
[ ! -f "$LOG" ] && LOG=~/.clawdbot/gateway.log
tail -n 500 "$LOG" 2>/dev/null
'@
$getLogOnlyPath = Join-Path $env:TEMP "spiegel_get_log.sh"
$getLogOnlySh | Set-Content -Path $getLogOnlyPath -Encoding ASCII -NoNewline
scp -q $getLogOnlyPath "${TargetHost}:/tmp/spiegel_get_log.sh" 2>$null
$gwLog = ssh -o BatchMode=yes -o ConnectTimeout=15 $TargetHost "bash /tmp/spiegel_get_log.sh" 2>$null

# --- 5) Output ---
Write-Host "`n=== SUMMARY OF ARTICLES (www.spiegel.de) ===" -ForegroundColor Green
# Only treat as summary if it looks like prose (not a log line); gateway may not log chat_say when plugin is disabled
$summaryTrimmed = $summary -replace '\s+', ' ' -replace '^\s+|\s+$', ''
$isLikelySummary = $summaryTrimmed.Length -gt 0 -and $summaryTrimmed.Length -lt 8000 -and $summaryTrimmed -notmatch '^\d{4}-\d{2}-\d{2}T'
if ($isLikelySummary) {
    Write-Host $summaryTrimmed
} else {
    Write-Host "(Could not extract agent summary from gateway log.)" -ForegroundColor Yellow
    Write-Host "When the MoltWorld plugin is disabled, the agent may use built-in web_fetch and reply in the chat; the gateway might not log that as a tool call. Check the Control UI chat for the reply, or enable the plugin and re-run." -ForegroundColor Gray
    Write-Host "`nLast 50 lines of gateway log:" -ForegroundColor Gray
    $tailLog = ssh -o BatchMode=yes -o ConnectTimeout=10 $TargetHost 'LOG=$(ls -t /tmp/openclaw/openclaw-*.log 2>/dev/null | head -1); [ -z "$LOG" ] && LOG=~/.openclaw/gateway.log; [ ! -f "$LOG" ] && LOG=~/.clawdbot/gateway.log; tail -n 50 "$LOG" 2>/dev/null' 2>$null
    if ($tailLog) { $tailLog | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray } }
}

Write-Host "`n--- Response body (first 500 chars) ---" -ForegroundColor Gray
$body = ssh -o BatchMode=yes -o ConnectTimeout=5 $TargetHost "cat /tmp/spiegel_diag_response.json 2>/dev/null" 2>$null
if ($body -and $body.Length -gt 0) { Write-Host $body.Substring(0, [Math]::Min(500, $body.Length)) -ForegroundColor DarkGray } else { Write-Host "(empty)" -ForegroundColor DarkGray }

# Hook MoltWorld in log?
$hookMolt = $gwLog | Select-String -Pattern "Hook MoltWorld\s*:\s*\{"
if ($hookMolt) {
    Write-Host "`n[!] Hook MoltWorld appeared in log (plugin ran tools). To get plain chat without MoltWorld: disable plugin and start a new session." -ForegroundColor Yellow
}
# Embedded run = no Ollama, no tools, no Spiegel summary
$embeddedRun = $gwLog | Select-String -Pattern "embedded run done"
if ($embeddedRun -and -not $isLikelySummary) {
    Write-Host "`n[!] Log shows embedded run done. This host routed the request to the embedded agent (no Ollama, no fetch_url). For a Spiegel summary use sparky2 or configure this gateway so hooks use the main model." -ForegroundColor Yellow
}
Write-Host ""
