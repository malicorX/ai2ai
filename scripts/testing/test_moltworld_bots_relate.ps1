# Test that the two OpenClaw agents (Sparky1Agent, MalicorSparky2) relate to each other in MoltWorld chat.
# Fetches recent chat from theebie and verifies: (1) at least one bot->bot reply is not a generic opener,
# (2) at least one reply references or substantively answers the previous message (shared word or substantive answer).
# Optionally triggers narrator then replier before checking.
#
# Usage: .\scripts\testing\test_moltworld_bots_relate.ps1
#   -TriggerNarrator / -TriggerReplier: run pull-and-wake on sparky1 / sparky2 (default: both true)
#   -UsePythonBot: use Python MoltWorld bot instead of gateway (run_moltworld_python_bot.ps1)
#   -SkipTrigger: don't run any pull-and-wake; only fetch chat and assert on current state
#   -BaseUrl, -Sparky1Host, -Sparky2Host, -Last, -WaitAfterNarratorSec, -WaitAfterReplierSec
param(
    [string]$BaseUrl = "https://www.theebie.de",
    [string]$Sparky1Host = "sparky1",
    [string]$Sparky2Host = "sparky2",
    [bool]$TriggerNarrator = $true,
    [bool]$TriggerReplier = $true,
    [switch]$SkipTrigger,
    [switch]$UsePythonBot,
    [int]$Last = 25,
    [int]$WaitAfterNarratorSec = 90,
    [int]$WaitAfterReplierSec = 50
)

$ErrorActionPreference = "Stop"
$projectRoot = (Get-Item $PSScriptRoot).Parent.Parent.FullName
$base = $BaseUrl.TrimEnd("/")

if ($SkipTrigger) {
    $TriggerNarrator = $false
    $TriggerReplier = $false
}

# Generic openers that indicate the bot did NOT reply to what the other said (forbidden as reply to the other agent)
$genericOpeners = @(
    "Hello!",
    "Hello there!",
    "Hi!",
    "What would you like to talk about?",
    "How are you?",
    "Greetings!",
    "How can I help you today?",
    "Hello! What would you like to talk about?",
    "Hi there!",
    "Greetings, traveler!",
    "Hey! How's it going?"
)

function Normalize-Text {
    param([string]$t)
    if (-not $t) { return "" }
    ($t -as [string]).Trim().ToLowerInvariant() -replace "\s+", " "
}

function Is-GenericOpener {
    param([string]$text)
    $n = Normalize-Text $text
    if ([string]::IsNullOrWhiteSpace($n)) { return $true }
    foreach ($g in $genericOpeners) {
        $gn = Normalize-Text $g
        if ($n -eq $gn -or $n -like ($gn + "*") -or $n -like ("*" + $gn)) { return $true }
    }
    return $false
}

# Reply "references" the previous message: shares a meaningful word, or prev is a question and reply is substantive (length > 30).
$stopwords = @("the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must", "can", "need", "to", "from", "as", "into", "through", "during", "this", "that", "these", "those", "it", "its", "you", "your", "we", "what", "which", "who", "how", "when", "where", "why", "all", "each", "every", "both", "some", "such", "no", "not", "only", "same", "so", "than", "too", "very", "just", "if", "because", "about", "up", "out", "by", "here", "there")
function Reply-ReferencesPrevious {
    param([string]$prevText, [string]$replyText)
    if ([string]::IsNullOrWhiteSpace($replyText)) { return $false }
    $prevNorm = Normalize-Text $prevText
    $replyNorm = Normalize-Text $replyText
    $prevWords = $prevNorm -split "\s+" | Where-Object { $_.Length -gt 2 -and $stopwords -notcontains $_ }
    $replyWords = $replyNorm -split "\s+" | Where-Object { $_.Length -gt 2 -and $stopwords -notcontains $_ }
    foreach ($w in $prevWords) {
        if ($replyWords -contains $w) { return $true }
    }
    # Prev is a question and reply is substantive (not just "Hi" or "I'm in")
    if ($prevText -match "\?" -and $replyText.Trim().Length -gt 30) { return $true }
    return $false
}

function Get-RecentChat {
    try {
        $r = Invoke-RestMethod -Uri "$base/chat/recent?limit=$Last" -Method Get -TimeoutSec 15
        return @($r.messages)
    } catch {
        Write-Host "GET /chat/recent failed: $_" -ForegroundColor Red
        return @()
    }
}

function Get-BotToBotPairs {
    param([array]$messages)
    $pairs = @()
    for ($i = 1; $i -lt $messages.Count; $i++) {
        $prev = $messages[$i - 1]
        $curr = $messages[$i]
        $prevId = ($prev.sender_id -as [string]).Trim()
        $currId = ($curr.sender_id -as [string]).Trim()
        $isSparky1 = $prevId -eq "Sparky1Agent" -or $currId -eq "Sparky1Agent"
        $isSparky2 = $prevId -eq "MalicorSparky2" -or $currId -eq "MalicorSparky2"
        if ($isSparky1 -and $isSparky2 -and $prevId -ne $currId) {
            $pairs += [PSCustomObject]@{
                PrevSender = $prevId
                PrevText    = ($prev.text -as [string]).Trim()
                CurrSender  = $currId
                CurrText    = ($curr.text -as [string]).Trim()
            }
        }
    }
    return $pairs
}

$waitNarrator = if ($UsePythonBot) { [Math]::Min(60, $WaitAfterNarratorSec) } else { $WaitAfterNarratorSec }
$waitReplier = if ($UsePythonBot) { [Math]::Min(45, $WaitAfterReplierSec) } else { $WaitAfterReplierSec }

Write-Host "MoltWorld bots-relate test" -ForegroundColor Cyan
if ($UsePythonBot) { Write-Host "  Using Python bot (no gateway)." -ForegroundColor Gray }
Write-Host "  Base: $base" -ForegroundColor Gray
Write-Host "  Last $Last messages; generic openers forbidden when replying to the other bot." -ForegroundColor Gray

if ($TriggerNarrator) {
    Write-Host ""
    Write-Host "Triggering narrator ($Sparky1Host)..." -ForegroundColor Cyan
    if ($UsePythonBot) {
        $botScript = Join-Path $projectRoot "scripts\clawd\run_moltworld_python_bot.ps1"
        try {
            & $botScript -AgentId Sparky1Agent -TargetHost $Sparky1Host -WorldApiBase $base 2>&1 | ForEach-Object { Write-Host $_ -ForegroundColor Gray }
        } catch {
            Write-Host "  Narrator trigger failed (e.g. SSH or remote Python deps): $_" -ForegroundColor Yellow
        }
        Write-Host "  Waiting ${waitNarrator}s for narrator turn..." -ForegroundColor Gray
        Start-Sleep -Seconds $waitNarrator
    } else {
        $shScript = Join-Path $projectRoot "scripts\clawd\run_moltworld_pull_and_wake.sh"
        if (-not (Test-Path $shScript)) { Write-Host "  Missing $shScript" -ForegroundColor Red; exit 1 }
        scp -q $shScript "${Sparky1Host}:/tmp/run_moltworld_pull_and_wake.sh" 2>$null
        $out = ssh $Sparky1Host "sed -i 's/\r$//' /tmp/run_moltworld_pull_and_wake.sh 2>/dev/null; chmod +x /tmp/run_moltworld_pull_and_wake.sh; bash /tmp/run_moltworld_pull_and_wake.sh" 2>&1
        Write-Host $out -ForegroundColor Gray
        if ($out -match '"ok":\s*true') { Write-Host "  Narrator turn requested." -ForegroundColor Green } else { Write-Host "  Check output above." -ForegroundColor Yellow }
        Write-Host "  Waiting ${waitNarrator}s for narrator turn..." -ForegroundColor Gray
        Start-Sleep -Seconds $waitNarrator
    }
}

if ($TriggerReplier) {
    Write-Host ""
    Write-Host "Triggering replier ($Sparky2Host)..." -ForegroundColor Cyan
    if ($UsePythonBot) {
        $botScript = Join-Path $projectRoot "scripts\clawd\run_moltworld_python_bot.ps1"
        try {
            & $botScript -AgentId MalicorSparky2 -TargetHost $Sparky2Host -WorldApiBase $base 2>&1 | ForEach-Object { Write-Host $_ -ForegroundColor Gray }
        } catch {
            Write-Host "  Replier trigger failed (e.g. SSH or remote Python deps): $_" -ForegroundColor Yellow
        }
        Write-Host "  Waiting ${waitReplier}s for replier turn..." -ForegroundColor Gray
        Start-Sleep -Seconds $waitReplier
    } else {
        $shScript = Join-Path $projectRoot "scripts\clawd\run_moltworld_pull_and_wake.sh"
        scp -q $shScript "${Sparky2Host}:/tmp/run_moltworld_pull_and_wake.sh" 2>$null
        $out = ssh $Sparky2Host "sed -i 's/\r$//' /tmp/run_moltworld_pull_and_wake.sh 2>/dev/null; chmod +x /tmp/run_moltworld_pull_and_wake.sh; CLAW=openclaw bash /tmp/run_moltworld_pull_and_wake.sh" 2>&1
        Write-Host $out -ForegroundColor Gray
        if ($out -match '"ok":\s*true') { Write-Host "  Replier turn requested." -ForegroundColor Green } else { Write-Host "  Check output above." -ForegroundColor Yellow }
        Write-Host "  Waiting ${waitReplier}s for replier turn..." -ForegroundColor Gray
        Start-Sleep -Seconds $waitReplier
    }
}

Write-Host ""
Write-Host "Fetching recent chat..." -ForegroundColor Cyan
$messages = Get-RecentChat
if ($messages.Count -eq 0) {
    Write-Host "  No messages. Cannot assert bot-to-bot relation." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Last $($messages.Count) messages on theebie:" -ForegroundColor Green
foreach ($m in $messages) {
    $sid = if ($m.sender_id) { $m.sender_id } else { "?" }
    $name = if ($m.sender_name) { $m.sender_name } else { $sid }
    $rawText = if ($m.text) { $m.text.ToString().Trim() } else { "" }
    if ($rawText.Length -gt 70) { $rawText = $rawText.Substring(0, 67) + "..." }
    $ts = $m.created_at
    if ($ts -match "^\d+(\.\d+)?$") {
        $dt = [DateTimeOffset]::FromUnixTimeSeconds([long][double]$ts).LocalDateTime.ToString("yyyy-MM-dd HH:mm:ss")
    } else { $dt = $ts }
    Write-Host "  [$dt] $name ($sid): $rawText" -ForegroundColor Gray
}

$pairs = Get-BotToBotPairs -messages $messages
Write-Host ""
if ($pairs.Count -eq 0) {
    Write-Host "No consecutive bot->bot pair in last $Last messages (need Sparky1Agent then MalicorSparky2 or vice versa)." -ForegroundColor Yellow
    Write-Host "Result: INCONCLUSIVE (run with -TriggerNarrator and -TriggerReplier to generate a pair, or increase -Last)." -ForegroundColor Yellow
    exit 0
}

Write-Host "Bot-to-bot pairs (consecutive): $($pairs.Count)" -ForegroundColor Cyan
$anyGeneric = $false
$anyRelated = $false
$anyRelates = $false
foreach ($p in $pairs) {
    $generic = Is-GenericOpener -text $p.CurrText
    $references = Reply-ReferencesPrevious -prevText $p.PrevText -replyText $p.CurrText
    if ($generic) {
        $anyGeneric = $true
        Write-Host "  [GENERIC] $($p.PrevSender) -> $($p.CurrSender): ``$($p.CurrText)``" -ForegroundColor Red
    } else {
        $anyRelated = $true
        if ($references) {
            $anyRelates = $true
            Write-Host "  [RELATES] $($p.PrevSender) -> $($p.CurrSender): ``$($p.CurrText)``" -ForegroundColor Green
        } else {
            Write-Host "  [RELATED] $($p.PrevSender) -> $($p.CurrSender): ``$($p.CurrText)``" -ForegroundColor DarkGreen
        }
    }
}

Write-Host ""
Write-Host "RELATES = reply is not generic AND references/answers the previous message (shared word or substantive answer)." -ForegroundColor Gray
Write-Host ""
if ($anyRelates) {
    Write-Host "PASS: At least one bot reply relates to what the other said (not generic, references or answers previous message)." -ForegroundColor Green
    exit 0
}
if ($anyRelated) {
    Write-Host "FAIL: No reply in the window both relates and references the previous message. Some replies are not generic but none clearly answer or reference what the other said." -ForegroundColor Red
    exit 1
}
if ($anyGeneric) {
    Write-Host "FAIL: Every bot-to-bot reply in the window is a generic opener; agents are not relating." -ForegroundColor Red
    exit 1
}
Write-Host "INCONCLUSIVE." -ForegroundColor Yellow
exit 0
