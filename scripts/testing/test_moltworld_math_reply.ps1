# Test that MalicorSparky2 (OpenClaw) understands a question in MoltWorld and replies with the answer.
# No hardcoded answer: we inject a question (e.g. "how much is 5+4?") and trigger the replier via
# pull-and-wake; the agent sees recent_chat in the message and must call chat_say with the answer.
#
# Usage: .\scripts\testing\test_moltworld_math_reply.ps1 [-AdminToken ...] [-ShowGatewayLog] [-QuestionerFromOpenClaw]
#   Default: pull-and-wake on sparky2; question injected via admin/chat/say.
#   -UseCronTrigger: trigger sparky2 via one-shot cron instead of pull-and-wake.
#   -ShowGatewayLog: print sparky2 gateway log excerpt (wake/chat_say/tools) at end.
#   -TraceTiming: 6 min timeout; timestamp every step + pull-and-wake timestamps + gateway log timeline for debugging.
#   -Log: also write all output to logs/test_moltworld_math_reply_<timestamp>.txt.
#   -Debug: full debug for both agents — observe (input), do (action), think (gateway log); includes wake payload preview.
#   -QuestionerFromOpenClaw: Sparky1 asks via OpenClaw wake (needs -FirstAgentHost sparky1, hooks + plugin).
#   Output: replier input (recent chat), turn result, Actual chat (last 10), agent summary (input/output both agents).
#   Requires: ADMIN_TOKEN. SSH to SecondAgentHost (and FirstAgentHost if QuestionerFromOpenClaw).
param(
    [string]$BaseUrl = "",
    [string]$AdminToken = "",
    [string]$SecondAgentHost = "sparky2",
    [string]$FirstAgentHost = "sparky1",
    [switch]$UsePullAndWake = $true,
    [switch]$UseCronTrigger,
    [switch]$ShowGatewayLog,
    [switch]$TraceTiming,
    [switch]$Log,
    [switch]$Debug,
    [switch]$QuestionerFromOpenClaw
)

$ErrorActionPreference = "Stop"
if (-not $BaseUrl) { $BaseUrl = $env:MOLTWORLD_BASE_URL }
if (-not $BaseUrl) { $BaseUrl = "https://www.theebie.de" }
if (-not $AdminToken) { $AdminToken = $env:ADMIN_TOKEN }

$base = $BaseUrl.TrimEnd("/")
$projectRoot = (Get-Item $PSScriptRoot).Parent.Parent.FullName

if ($Log) {
    $logsDir = Join-Path $projectRoot "logs"
    New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
    $logFilePath = Join-Path $logsDir "test_moltworld_math_reply_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
    Start-Transcript -Path $logFilePath
    Write-Host "Logging to $logFilePath" -ForegroundColor Gray
}

function Get-Ts { return (Get-Date).ToString("HH:mm:ss.fff") }
function Write-Ts { param([string]$Msg) Write-Host "[$(Get-Ts)] $Msg" -ForegroundColor DarkCyan }

if (-not $AdminToken) {
    Write-Host "ADMIN_TOKEN is not set. Set it or pass -AdminToken." -ForegroundColor Red
    if ($Log) { Stop-Transcript }
    exit 1
}

# Random a, b in 1..9 so we get "how much is 3+5?" style questions
$a = Get-Random -Minimum 1 -Maximum 10
$b = Get-Random -Minimum 1 -Maximum 10
$expectedSum = $a + $b
$question = "how much is $a + $b ?"

Write-Host "MoltWorld math-reply test" -ForegroundColor Cyan
if ($TraceTiming) { Write-Ts "test_start"; Write-Host "  TraceTiming: 6 min timeout; timestamps on every step + gateway log timeline" -ForegroundColor DarkCyan }
Write-Host "  Base: $base" -ForegroundColor Gray
Write-Host "  Question: `"$question`" (expected answer: $expectedSum)" -ForegroundColor Gray
if ($QuestionerFromOpenClaw) {
    Write-Host "  Questioner: OpenClaw on $FirstAgentHost (wake with chat_say)" -ForegroundColor Gray
} else {
    Write-Host "  Questioner: injected as Sparky1Agent via admin/chat/say" -ForegroundColor Gray
}
Write-Host "  Replier: $SecondAgentHost (MalicorSparky2)" -ForegroundColor Gray

$adminHeaders = @{ "Content-Type" = "application/json"; "Authorization" = "Bearer $AdminToken" }

# 1) Get question into chat: either inject via admin or have Sparky1 ask via OpenClaw
if ($TraceTiming) { Write-Ts "inject_question_start" }
if ($QuestionerFromOpenClaw) {
    # Wake Sparky1 (clawdbot) via SSH: push payload + helper script, run script on host (no jq, no fragile quoting).
    $wakePayload = @{ text = "You are Sparky1Agent. Call chat_say with exactly this message: $question Use only the chat_say tool; no other output."; mode = "now" } | ConvertTo-Json -Compress
    $payloadPath = [System.IO.Path]::GetTempFileName()
    $wakeScript = Join-Path $projectRoot "scripts\clawd\run_moltworld_wake_once.sh"
    if (-not (Test-Path $wakeScript)) {
        Write-Host "  ERROR: Missing $wakeScript" -ForegroundColor Red
        if ($Log) { Stop-Transcript }
        exit 1
    }
    try {
        [System.IO.File]::WriteAllText($payloadPath, $wakePayload, [System.Text.Encoding]::UTF8)
        scp -q $payloadPath "${FirstAgentHost}:/tmp/moltworld_wake_payload.json"
        scp -q $wakeScript "${FirstAgentHost}:/tmp/run_moltworld_wake_once.sh"
        $wakeResult = ssh $FirstAgentHost "sed -i 's/\r$//' /tmp/run_moltworld_wake_once.sh 2>/dev/null; chmod +x /tmp/run_moltworld_wake_once.sh; CLAW=clawdbot PAYLOAD_FILE=/tmp/moltworld_wake_payload.json bash /tmp/run_moltworld_wake_once.sh" 2>&1
        if ($wakeResult -eq "NO_TOKEN") {
            Write-Host "  ERROR: Could not get hooks token from $FirstAgentHost. Run enable_hooks_on_sparky.sh." -ForegroundColor Red
            if ($Log) { Stop-Transcript }
            exit 1
        }
        if ($wakeResult -eq "NO_PAYLOAD") {
            Write-Host "  ERROR: Payload file not found on $FirstAgentHost." -ForegroundColor Red
            if ($Log) { Stop-Transcript }
            exit 1
        }
        if ($wakeResult -eq "200") {
            Write-Host "  Sparky1 wake sent (questioner turn running)..." -ForegroundColor Green
        } else {
            Write-Host "  WARN: Sparky1 wake returned HTTP $wakeResult" -ForegroundColor Yellow
        }
    } finally {
        Remove-Item -LiteralPath $payloadPath -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 25
} else {
    try {
        $body = @{ sender_id = "Sparky1Agent"; sender_name = "Sparky1Agent"; text = $question } | ConvertTo-Json
        Invoke-RestMethod -Uri "$base/admin/chat/say" -Headers $adminHeaders -Method Post -Body $body | Out-Null
        if ($TraceTiming) { Write-Ts "inject_question_done (admin/chat/say 200)" }
        Write-Host "  Injected: Sparky1Agent said `"$question`"" -ForegroundColor Green
    } catch {
        Write-Host "  admin/chat/say failed: $_" -ForegroundColor Red
        if ($Log) { Stop-Transcript }
        exit 1
    }
    Start-Sleep -Seconds 5
}
if ($TraceTiming) { Write-Ts "verify_recent_chat_start" }

# 2b) Verify backend has the question (data path: agent will see this via world_state → recent_chat)
try {
    $recent = Invoke-RestMethod -Uri "$base/chat/recent?limit=20" -Method Get -TimeoutSec 10
    $hasQuestion = $false
    foreach ($m in @($recent.messages)) {
        if (($m.sender_id -as [string]) -eq "Sparky1Agent" -and (($m.text -as [string]) -replace "\s+", " ") -like "*$question*") {
            $hasQuestion = $true
            break
        }
    }
    if (-not $hasQuestion) {
        Write-Host "  WARN: Backend /chat/recent does not show our question; agent may not see it. Continuing anyway." -ForegroundColor Yellow
    } else {
        Write-Host "  Verified: question visible in recent chat (data path OK)" -ForegroundColor Green
    }
    if ($TraceTiming) { Write-Ts "verify_recent_chat_done" }
} catch {
    Write-Host "  WARN: Could not verify recent chat: $_" -ForegroundColor Yellow
}

# 2c) Show replier input (what MalicorSparky2 gets in the wake message)
try {
    $recentForInput = Invoke-RestMethod -Uri "$base/chat/recent?limit=10" -Method Get -TimeoutSec 10
    $msgs = @($recentForInput.messages)
    $last5 = if ($msgs.Count -gt 5) { $msgs[-5..-1] } else { $msgs }
    Write-Host ""
    Write-Host "--- Replier input (recent chat injected into wake) ---" -ForegroundColor Cyan
    foreach ($m in $last5) {
        $s = $m.sender_id -as [string]
        $t = $m.text -as [string]
        $ts = if ($m.created_at) { [DateTimeOffset]::FromUnixTimeSeconds([long]$m.created_at).ToString("HH:mm:ss") } else { "" }
        Write-Host "  $s ($ts): $t" -ForegroundColor Gray
    }
    Write-Host "---" -ForegroundColor Cyan
    Write-Host ""
} catch {
    Write-Host "  (Could not fetch recent chat for input summary: $_)" -ForegroundColor Gray
}

# 3) Trigger sparky2: pull-and-wake (no hardcoding) or cron one-shot
if ($TraceTiming) { Write-Ts "trigger_start (scp + ssh pull-and-wake)" }
$projectRoot = (Get-Item $PSScriptRoot).Parent.Parent.FullName
if ($UseCronTrigger) {
    $shScript = Join-Path $projectRoot "scripts\clawd\run_moltworld_math_reply_once.sh"
    if (-not (Test-Path $shScript)) {
        Write-Host "  Missing $shScript; cannot trigger sparky2." -ForegroundColor Red
        if ($Log) { Stop-Transcript }
        exit 1
    }
    Write-Host "  Triggering $SecondAgentHost (OpenClaw) via cron one-shot..." -ForegroundColor Cyan
    scp -q $shScript "${SecondAgentHost}:/tmp/run_moltworld_math_reply_once.sh"
    $runOut = ssh $SecondAgentHost "bash /tmp/run_moltworld_math_reply_once.sh" 2>&1
} else {
    # Pull-and-wake: script pulls world/recent_chat, injects into wake message; agent must understand and call chat_say (no hardcoded answer)
    $shScript = Join-Path $projectRoot "scripts\clawd\run_moltworld_pull_and_wake.sh"
    if (-not (Test-Path $shScript)) {
        Write-Host "  Missing $shScript; cannot trigger sparky2." -ForegroundColor Red
        if ($Log) { Stop-Transcript }
        exit 1
    }
    Write-Host "  Triggering $SecondAgentHost (OpenClaw) via pull-and-wake (agent must understand and answer)..." -ForegroundColor Cyan
    scp -q $shScript "${SecondAgentHost}:/tmp/run_moltworld_pull_and_wake.sh"
    $envDebug = if ($Debug) { "MOLTWORLD_DEBUG=1 " } else { "" }
    $envTrace = if ($TraceTiming) { "MOLTWORLD_TRACE_TIMING=1 " } else { "" }
    # Merge remote stderr into stdout so TRACE_ lines don't trigger PowerShell stderr/error
    $runOut = ssh $SecondAgentHost "${envTrace}${envDebug}sed -i 's/\r$//' /tmp/run_moltworld_pull_and_wake.sh 2>/dev/null; chmod +x /tmp/run_moltworld_pull_and_wake.sh; ${envTrace}${envDebug}CLAW=openclaw bash /tmp/run_moltworld_pull_and_wake.sh 2>&1" 2>&1
}
if ($TraceTiming) { Write-Ts "trigger_done (wake request completed from our side)" }
Write-Host "  Turn run: $runOut" -ForegroundColor Gray
# Emit pull-and-wake trace lines if present (from MOLTWORLD_TRACE_TIMING)
if ($TraceTiming -and $runOut) {
    $traceLines = $runOut -split "`n" | Where-Object { $_ -match 'TRACE_' }
    if ($traceLines) {
        Write-Host "  --- Pull-and-wake timeline (on sparky2) ---" -ForegroundColor DarkCyan
        $traceLines | ForEach-Object { Write-Host "    $($_.Trim())" -ForegroundColor DarkGray }
        Write-Host "  ---" -ForegroundColor DarkCyan
    }
    # Show gateway log immediately so we see what OpenClaw did during the run (tools, chat_say, errors)
    Write-Host ""
    $gwLog = ssh $SecondAgentHost "tail -n 400 ~/.openclaw/gateway.log 2>/dev/null" 2>$null
    if ($gwLog) {
        Write-Host "--- OpenClaw agent activity (gateway log, right after wake returned) ---" -ForegroundColor Cyan
        Write-Host "  The time between TRACE_post_v1_responses_start and _done = OpenClaw agent run. Check below for:" -ForegroundColor Gray
        Write-Host "  - when the request was received, tool calls (world_state / chat_say), model completion, any errors." -ForegroundColor Gray
        $gwLog | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
        Write-Host "---" -ForegroundColor Cyan
        Write-Host ""
    }
    # Daily log often has tool execution detail (chat_say result, theebie response)
    $dailyLog = ssh $SecondAgentHost "tail -n 250 /tmp/openclaw/openclaw-`$(date +%Y-%m-%d).log 2>/dev/null" 2>$null
    if ($dailyLog) {
        Write-Host "--- OpenClaw daily log (tool execution; look for chat_say / POST / 200 / 401) ---" -ForegroundColor Cyan
        Write-Host "  Path on sparky2: /tmp/openclaw/openclaw-YYYY-MM-DD.log" -ForegroundColor Gray
        $dailyLog | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
        Write-Host "---" -ForegroundColor Cyan
        Write-Host ""
    }
}
# Parse payload preview for -Debug (script may emit MOLTWORLD_DEBUG_PAYLOAD={...} on stderr, captured in runOut)
$payloadPreview = ""
if ($Debug -and $runOut) {
    $line = $runOut -split "`n" | Where-Object { $_ -match '^MOLTWORLD_DEBUG_PAYLOAD=' } | Select-Object -First 1
    if ($line -match '^MOLTWORLD_DEBUG_PAYLOAD=(.+)$') {
        try {
            $payloadPreview = ($Matches[1].Trim() | ConvertFrom-Json).payload_text_preview
        } catch {}
    }
}

# 4) Poll for a reply from MalicorSparky2 that contains the expected sum
$maxWaitSec = if ($TraceTiming) { 360 } else { 90 }
$pollIntervalSec = 15   # used after first 45s
$waited = 0
if ($TraceTiming) { Write-Ts ("poll_start (waiting up to " + $maxWaitSec + "s for reply)") }
if (-not $UseCronTrigger) {
    Write-Host ("  (Simple question usually 10-30s; polling every 5s then 15s, max " + $maxWaitSec + "s)") -ForegroundColor Gray
}
$replyFound = $false
$replyText = ""
$diagnosticShown = $false

while ($waited -le $maxWaitSec) {
    try {
        $chat = Invoke-RestMethod -Uri "$base/chat/recent?limit=30" -Method Get -TimeoutSec 10
    } catch {
        Write-Host "  GET /chat/recent failed: $_" -ForegroundColor Yellow
        if ($waited -ge $maxWaitSec) { break }
        Start-Sleep -Seconds $pollIntervalSec
        $waited += $pollIntervalSec
        continue
    }

    $messages = @()
    if ($chat.messages) { $messages = @($chat.messages) }

    # Find our question's timestamp (use most recent matching message so we get this test's injection)
    $questionTime = $null
    $questionNorm = ($question -replace "\s+", " ").Trim()
    $matching = @($messages | Where-Object {
        ($_.sender_id -as [string]) -eq "Sparky1Agent" -and
        (($_.text -as [string]) -replace "\s+", " ").Trim() -like "*$questionNorm*"
    })
    if ($matching.Count -gt 0) {
        $questionTime = ($matching | ForEach-Object { [long]$_.created_at } | Measure-Object -Maximum).Maximum
    }
    if ($null -eq $questionTime) { $questionTime = 0 }

    # Number words for 1..18 (so we accept "five" or "5" for 5, etc.)
    $numberWords = @{
        1="one"; 2="two"; 3="three"; 4="four"; 5="five"; 6="six"; 7="seven"; 8="eight"; 9="nine"
        10="ten"; 11="eleven"; 12="twelve"; 13="thirteen"; 14="fourteen"; 15="fifteen"; 16="sixteen"; 17="seventeen"; 18="eighteen"
    }
    $wordForm = $numberWords[$expectedSum]

    # Only accept a reply that is strictly after our question (ignore old replies when question not yet in list)
    if ($questionTime -gt 0) {
        foreach ($m in $messages) {
            $sid = $m.sender_id -as [string]
            if ($sid -ne "MalicorSparky2") { continue }
            $t = $m.created_at
            if ($t -le $questionTime) { continue }
            $text = ($m.text -as [string]) -replace "\s+", " "
            $match = $text -match "\b$expectedSum\b" -or $text.Trim() -eq "$expectedSum"
            if (-not $match -and $wordForm -and $text -match "\b$wordForm\b") { $match = $true }
            if ($match) {
                $replyFound = $true
                $replyText = $text
                break
            }
        }
    }
    if ($replyFound) {
        if ($TraceTiming) { Write-Ts "reply_found (MalicorSparky2 message with $expectedSum seen)" }
        break
    }
    if ($waited -ge $maxWaitSec) {
        if ($TraceTiming) { Write-Ts ("poll_timeout (no reply after " + $maxWaitSec + "s)") }
        break
    }
    # Poll every 5s for first 45s so we see quick replies; then 15s
    $nextInterval = if ($waited -lt 45) { 5 } else { $pollIntervalSec }
    if ($TraceTiming) {
        Write-Ts ("poll_at " + $waited + "s (no correct reply yet); next in " + $nextInterval + "s")
        # Every 60s show latest MalicorSparky2 message time so we see if any new reply arrived (even wrong)
        if ($waited -ge 60 -and $waited % 60 -eq 0) {
            $latestReply = @($messages) | Where-Object { ($_.sender_id -as [string]) -eq "MalicorSparky2" } | Sort-Object { [long]$_.created_at } -Descending | Select-Object -First 1
            if ($latestReply) {
                $ts = [DateTimeOffset]::FromUnixTimeSeconds([long]$latestReply.created_at).ToString("yyyy-MM-dd HH:mm:ss")
                Write-Host "    [debug] Latest MalicorSparky2 message on theebie: $ts - if this never updates, chat_say is not reaching theebie." -ForegroundColor DarkGray
            } else {
                Write-Host "    [debug] No MalicorSparky2 messages on theebie yet." -ForegroundColor DarkGray
            }
        }
    }
    if (-not $diagnosticShown -and $waited -ge 25) {
        Write-Host ("  No reply yet after " + $waited + "s. If still nothing by 30s, on sparky2 check: tail -f ~/.openclaw/gateway.log and ollama ps") -ForegroundColor Yellow
        $diagnosticShown = $true
    }
    Write-Host ("  No correct reply yet (" + $waited + "s); polling again in " + $nextInterval + "s...") -ForegroundColor Gray
    Start-Sleep -Seconds $nextInterval
    $waited += $nextInterval
}

# 5) Fetch final chat for summary and Actual chat dump
if ($TraceTiming) { Write-Ts "fetch_final_chat_start" }
$finalChat = $null
try {
    $finalChat = Invoke-RestMethod -Uri "$base/chat/recent?limit=30" -Method Get -TimeoutSec 10
} catch {}
if ($TraceTiming) { Write-Ts "fetch_final_chat_done" }

function Format-ChatSnippet {
    param([array]$messages, [int]$limit = 10)
    $list = @($messages)
    $take = if ($list.Count -gt $limit) { $list[-$limit..-1] } else { $list }
    foreach ($m in $take) {
        $s = $m.sender_id -as [string]
        $t = ($m.text -as [string]) -replace "\s+", " "
        $ts = if ($m.created_at) { [DateTimeOffset]::FromUnixTimeSeconds([long]$m.created_at).ToString("yyyy-MM-dd HH:mm:ss") } else { "" }
        "  [$ts] $s`: $t"
    }
}

# Actual chat (last 10)
Write-Host ""
Write-Host "--- Actual chat (last 10) ---" -ForegroundColor Cyan
if ($finalChat -and $finalChat.messages) {
    Format-ChatSnippet -messages $finalChat.messages -limit 10 | ForEach-Object { Write-Host $_ -ForegroundColor Gray }
} else {
    Write-Host "  (no messages or fetch failed)" -ForegroundColor Gray
}
Write-Host "---" -ForegroundColor Cyan

# Agent summary: input / output for both
Write-Host ""
Write-Host "--- Agent summary ---" -ForegroundColor Cyan
Write-Host "  Agent 1 (questioner) Sparky1Agent:" -ForegroundColor Gray
Write-Host "    Input:  $question" -ForegroundColor Gray
Write-Host "    Output: (message in Actual chat above)" -ForegroundColor Gray
Write-Host "  Agent 2 (replier) MalicorSparky2:" -ForegroundColor Gray
Write-Host "    Input:  recent_chat (see Replier input above) + instruction to answer if question" -ForegroundColor Gray
if ($replyFound) {
    Write-Host "    Output: chat_say `"$replyText`" (correct)" -ForegroundColor Green
} else {
    $latest = $null
    if ($finalChat -and $finalChat.messages) {
        $latest = @($finalChat.messages) | Where-Object { ($_.sender_id -as [string]) -eq "MalicorSparky2" } | Select-Object -Last 1
    }
    if ($latest) {
        Write-Host "    Output: (latest) chat_say `"$($latest.text)`"" -ForegroundColor Yellow
    } else {
        Write-Host "    Output: (no reply)" -ForegroundColor Red
    }
}
Write-Host "---" -ForegroundColor Cyan
Write-Host ""

# Debug: what each agent observed, did, and (from logs) thought
if ($Debug) {
    Write-Host "--- Debug: Sparky1 (questioner) ---" -ForegroundColor Magenta
    Write-Host "  Observe: Last message in chat (this test) = `"$question`"" -ForegroundColor Gray
    if ($QuestionerFromOpenClaw) {
        Write-Host "  Do: Wake sent with instruction to call chat_say with the question." -ForegroundColor Gray
        $log1 = ssh $FirstAgentHost "tail -n 80 ~/.clawdbot/gateway.log 2>/dev/null | grep -iE 'wake|hooks|chat_say|tool|message|error|completion|request|response' | tail -n 25" 2>$null
        if ($log1) {
            Write-Host "  Think (gateway log):" -ForegroundColor Gray
            $log1 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
        } else {
            Write-Host "  Think (gateway log): (none or unreachable)" -ForegroundColor DarkGray
        }
    } else {
        Write-Host "  Do: No gateway turn; message injected via admin/chat/say." -ForegroundColor Gray
        Write-Host "  Think: N/A (no model turn)" -ForegroundColor DarkGray
    }
    Write-Host "---" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "--- Debug: Sparky2 (replier) ---" -ForegroundColor Magenta
    Write-Host "  Observe: Recent chat (see Replier input above)." -ForegroundColor Gray
    if ($payloadPreview) {
        Write-Host "  Wake payload (preview, first 1200 chars):" -ForegroundColor Gray
        foreach ($chunk in ($payloadPreview -split "`n")) {
            Write-Host "    $chunk" -ForegroundColor DarkGray
        }
    }
    Write-Host "  Do: POST /v1/responses (main agent with MoltWorld) with payload above; response 200 or 201." -ForegroundColor Gray
    # Show last 25 raw lines first (new gateway may log only here), then filtered lines from last 200
    $log2Raw = ssh $SecondAgentHost "tail -n 25 ~/.openclaw/gateway.log 2>/dev/null" 2>$null
    $log2 = ssh $SecondAgentHost "tail -n 200 ~/.openclaw/gateway.log 2>/dev/null | grep -iE 'wake|hooks|chat_say|tool|message|error|completion|content|reasoning|request|response|prompt|API key|anthropic|auth' | tail -n 50" 2>$null
    if (-not $log2) {
        $log2 = ssh $SecondAgentHost "tail -n 60 ~/.openclaw/gateway.log 2>/dev/null" 2>$null
    }
    if ($log2Raw) {
        Write-Host "  Think (gateway log, last 25 lines):" -ForegroundColor Gray
        $log2Raw | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    }
    if ($log2 -and $log2 -ne $log2Raw) {
        Write-Host "  Think (filtered wake/chat_say/error):" -ForegroundColor Gray
        $log2 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    }
    if (-not $log2Raw -and -not $log2) {
        Write-Host "  Think (gateway log): (none or unreachable)" -ForegroundColor DarkGray
    }
    Write-Host "---" -ForegroundColor Magenta
    Write-Host ""
}

if ($replyFound) {
    if ($TraceTiming) { Write-Ts "test_end PASS" }
    Write-Host "PASS: MalicorSparky2 replied with the correct answer ($expectedSum): `"$replyText`"" -ForegroundColor Green
    if ($ShowGatewayLog -or $Debug -or $TraceTiming) {
        Write-Host ""
        $logLines = ssh $SecondAgentHost "tail -n 120 ~/.openclaw/gateway.log 2>/dev/null | grep -iE 'wake|hooks|chat_say|tools|error' | tail -n 35" 2>$null
        if ($TraceTiming) {
            $logLines = ssh $SecondAgentHost "tail -n 500 ~/.openclaw/gateway.log 2>/dev/null" 2>$null
            if ($logLines) {
                Write-Host "--- OpenClaw agent timeline (gateway log, sparky2; last 500 lines) ---" -ForegroundColor Cyan
                Write-Host "  (Shows when gateway received request, tool calls e.g. world_state/chat_say, model, errors.)" -ForegroundColor Gray
                $logLines | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
                Write-Host "---" -ForegroundColor Cyan
            }
        } elseif ($logLines) {
            Write-Host "--- Sparky2 gateway log excerpt ---" -ForegroundColor Cyan
            $logLines | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray }
            Write-Host "---" -ForegroundColor Cyan
        }
    }
    if ($Log) { Stop-Transcript }
    exit 0
}

if ($TraceTiming) { Write-Ts "test_end FAIL (timeout or no correct reply)" }
Write-Host ("FAIL: No reply from MalicorSparky2 containing " + $expectedSum + " within " + $maxWaitSec + "s.") -ForegroundColor Red
if ($UseCronTrigger) {
    Write-Host "  Check: $base/ui/ Actual chat; sparky2 gateway logs (~/.openclaw/gateway.log) for world_state/chat_say." -ForegroundColor Yellow
} else {
    Write-Host "  Check: $base/ui/ Actual chat; sparky2: ~/.moltworld.env, hooks enabled (enable_hooks_on_sparky.sh), MoltWorld plugin so chat_say is available on wake." -ForegroundColor Yellow
}
Write-Host "  A simple math reply should usually appear in under 1 min. If the run is slow (main agent /v1/responses has heavy context), restart the gateway on sparky2 or re-run; reply may still show up on $base/ui/ later." -ForegroundColor Yellow
Write-Host "  We use Ollama locally (no cloud API key). If the log shows 'No API key for provider anthropic', run: .\scripts\clawd\run_fix_openclaw_ollama_on_sparky.ps1 -TargetHost sparky2" -ForegroundColor Yellow
Write-Host "  See docs/OLLAMA_LOCAL.md and docs/AGENT_CHAT_DEBUG.md section 7d." -ForegroundColor Yellow
Write-Host "  If the model logs chat_say but no message appears on theebie: set plugins.entries.openclaw-moltworld.config.token from ~/.moltworld.env WORLD_AGENT_TOKEN on sparky2; 401 = missing/wrong token." -ForegroundColor Yellow
Write-Host "  On sparky2: tail -100 /tmp/openclaw/openclaw-YYYY-MM-DD.log for chat_say execution; on theebie server check backend logs for POST /chat/say and response code." -ForegroundColor Yellow
Write-Host "  Re-run with -Debug for full observe/do/think for both agents, or -ShowGatewayLog for sparky2 log only." -ForegroundColor Yellow
Write-Host "  The agent must understand the question and call chat_say (no hardcoded answer in the script)." -ForegroundColor Yellow

if ($ShowGatewayLog -or $TraceTiming) {
    Write-Host ""
    if ($TraceTiming) {
        $logLines = ssh $SecondAgentHost "tail -n 500 ~/.openclaw/gateway.log 2>/dev/null" 2>$null
        if ($logLines) {
            Write-Host "--- OpenClaw agent timeline (gateway log, sparky2; last 500 lines) ---" -ForegroundColor Cyan
            Write-Host "  (Shows when gateway received request, tool calls e.g. world_state/chat_say, model, errors.)" -ForegroundColor Gray
            $logLines | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
            Write-Host "---" -ForegroundColor Cyan
        }
        $dailyLogEnd = ssh $SecondAgentHost "tail -n 250 /tmp/openclaw/openclaw-`$(date +%Y-%m-%d).log 2>/dev/null" 2>$null
        if ($dailyLogEnd) {
            Write-Host ""
            Write-Host "--- OpenClaw daily log at end of run (tool execution) ---" -ForegroundColor Cyan
            $dailyLogEnd | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
            Write-Host "---" -ForegroundColor Cyan
        }
    } else {
        $logLines = ssh $SecondAgentHost "tail -n 120 ~/.openclaw/gateway.log 2>/dev/null | grep -iE 'wake|hooks|chat_say|tools|error' | tail -n 40" 2>$null
        if (-not $logLines) {
            $logLines = ssh $SecondAgentHost "tail -n 35 ~/.openclaw/gateway.log 2>/dev/null" 2>$null
        }
        if ($logLines) {
            Write-Host "--- Sparky2 gateway log excerpt ---" -ForegroundColor Cyan
            $logLines | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray }
            Write-Host "---" -ForegroundColor Cyan
        }
    }
}
if ($Log) { Stop-Transcript }
exit 1
