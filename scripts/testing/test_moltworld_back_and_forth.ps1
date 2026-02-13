# Trigger a back-and-forth conversation between Sparky1Agent and MalicorSparky2 until each has
# posted at least MinPerBot messages (default 5). Uses the Python MoltWorld bot on each host;
# the LLM decides what to say (no hardcoded lines). Topic is whatever the LLM continues from
# the current chat (or the narrator opener if chat is empty). Run from repo root or scripts/testing.
#
# Usage: .\scripts\testing\test_moltworld_back_and_forth.ps1
#        .\scripts\testing\test_moltworld_back_and_forth.ps1 -MinPerBot 5 -WaitSec 25 -MaxRounds 15
param(
    [string]$BaseUrl = "https://www.theebie.de",
    [string]$Sparky1Host = "sparky1",
    [string]$Sparky2Host = "sparky2",
    [int]$MinPerBot = 5,
    [int]$WaitSec = 22,
    [int]$MaxRounds = 18,
    [int]$ChatWindow = 35,
    [switch]$NoDeploy
)

$ErrorActionPreference = "Stop"
$projectRoot = (Get-Item $PSScriptRoot).Parent.Parent.FullName
$base = $BaseUrl.TrimEnd("/")

function Get-RecentMessages {
    param([int]$Limit = 50)
    try {
        $r = Invoke-RestMethod -Uri "$base/chat/recent?limit=$Limit" -Method Get -TimeoutSec 15
        return @($r.messages)
    } catch {
        Write-Host "  GET /chat/recent failed: $_" -ForegroundColor Red
        return @()
    }
}

function Get-Counts {
    param([array]$messages)
    $s1 = 0
    $s2 = 0
    foreach ($m in $messages) {
        $sid = ($m.sender_id -as [string]).Trim()
        if ($sid -eq "Sparky1Agent") { $s1++ }
        elseif ($sid -eq "MalicorSparky2") { $s2++ }
    }
    return @{ Sparky1 = $s1; Sparky2 = $s2 }
}

function Get-LastSender {
    param([array]$messages)
    if ($messages.Count -eq 0) { return $null }
    return ($messages[-1].sender_id -as [string]).Trim()
}

function Invoke-Bot {
    param([string]$AgentId, [string]$TargetHost)
    $botScript = Join-Path $projectRoot "scripts\clawd\run_moltworld_python_bot.ps1"
    $params = @{
        AgentId     = $AgentId
        TargetHost  = $TargetHost
        WorldApiBase = $base
    }
    if ($NoDeploy) { $params['NoDeploy'] = $true }
    try {
        $out = & $botScript @params 2>&1 | Out-String
        $out = $out.Trim()
        if ($out -match "(?m)^(sent|noop|moved|error)\s*$") { return $matches[1] }
        if ($out -match "\b(sent|noop|moved|error)\b") { return $matches[1] }
        return "error"
    } catch {
        Write-Host "  Bot trigger failed: $_" -ForegroundColor Yellow
        return "error"
    }
}

# Main
Write-Host "MoltWorld back-and-forth test" -ForegroundColor Cyan
Write-Host "  Goal: at least $MinPerBot messages from each bot (LLM-driven, one topic)." -ForegroundColor Gray
Write-Host "  Hosts: $Sparky1Host (Sparky1Agent), $Sparky2Host (MalicorSparky2)" -ForegroundColor Gray
Write-Host "  Wait between turns: ${WaitSec}s  Max rounds: $MaxRounds" -ForegroundColor Gray
Write-Host ""

$messages = Get-RecentMessages -Limit $ChatWindow
$counts = Get-Counts -messages $messages
$lastSender = Get-LastSender -messages $messages
Write-Host "  Current window: Sparky1=$($counts.Sparky1)  Sparky2=$($counts.Sparky2)  last=$lastSender" -ForegroundColor Gray
Write-Host ""

$round = 0
while ($round -lt $MaxRounds) {
    $messages = Get-RecentMessages -Limit $ChatWindow
    $counts = Get-Counts -messages $messages
    $lastSender = Get-LastSender -messages $messages

    if ($counts.Sparky1 -ge $MinPerBot -and $counts.Sparky2 -ge $MinPerBot) {
        Write-Host "  Reached goal: Sparky1=$($counts.Sparky1)  Sparky2=$($counts.Sparky2)" -ForegroundColor Green
        break
    }

    # Whose turn: if last from S2 or empty -> S1; else S2
    $triggerS1 = ($lastSender -eq "MalicorSparky2" -or $lastSender -eq $null -or $lastSender -eq "")
    if ($triggerS1) {
        Write-Host "[Round $($round + 1)] Triggering Sparky1Agent ($Sparky1Host)..." -ForegroundColor Cyan
        $result = Invoke-Bot -AgentId "Sparky1Agent" -TargetHost $Sparky1Host
        Write-Host "  -> $result" -ForegroundColor Gray
    } else {
        Write-Host "[Round $($round + 1)] Triggering MalicorSparky2 ($Sparky2Host)..." -ForegroundColor Cyan
        $result = Invoke-Bot -AgentId "MalicorSparky2" -TargetHost $Sparky2Host
        Write-Host "  -> $result" -ForegroundColor Gray
    }
    Write-Host "  Waiting ${WaitSec}s..." -ForegroundColor Gray
    Start-Sleep -Seconds $WaitSec
    $round++
}

# Final fetch and assert
$messages = Get-RecentMessages -Limit $ChatWindow
$counts = Get-Counts -messages $messages

Write-Host ""
Write-Host "Last $([Math]::Min($messages.Count, 20)) messages (newest last):" -ForegroundColor Green
$show = $messages | Select-Object -Last 20
foreach ($m in $show) {
    $sid = if ($m.sender_id) { $m.sender_id } else { "?" }
    $txt = ($m.text -as [string]).Trim()
    if ($txt.Length -gt 60) { $txt = $txt.Substring(0, 57) + "..." }
    $ts = $m.created_at
    if ($ts -match "^\d+(\.\d+)?$") {
        $dt = [DateTimeOffset]::FromUnixTimeSeconds([long][double]$ts).LocalDateTime.ToString("HH:mm:ss")
    } else { $dt = $ts }
    Write-Host "  [$dt] $sid : $txt" -ForegroundColor Gray
}

Write-Host ""
if ($counts.Sparky1 -ge $MinPerBot -and $counts.Sparky2 -ge $MinPerBot) {
    Write-Host "PASS: Sparky1=$($counts.Sparky1)  Sparky2=$($counts.Sparky2) (min $MinPerBot each)" -ForegroundColor Green
    exit 0
}
Write-Host "FAIL: Sparky1=$($counts.Sparky1)  Sparky2=$($counts.Sparky2) (need at least $MinPerBot each in last $ChatWindow messages)" -ForegroundColor Red
exit 1
