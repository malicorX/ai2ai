# One-shot snapshot of what the bots are doing: theebie chat + gateway logs + world agent (LangGraph) logs.
# Use this to quickly see recent activity without opening tail windows.
#
# Usage:
#   .\scripts\clawd\check_bots_activity.ps1                    # Snapshot (theebie + last N log lines)
#   .\scripts\clawd\check_bots_activity.ps1 -Watch              # Start live tail windows (same as watch_openclaw_bots + world agent logs)
#   .\scripts\clawd\check_bots_activity.ps1 -TheebieOnly        # Only show recent theebie chat
#   .\scripts\clawd\check_bots_activity.ps1 -GatewayLines 50   # More gateway log lines per host
param(
    [string]$Sparky1Host = "sparky1",
    [string]$Sparky2Host = "sparky2",
    [string]$TheebieUrl = "https://www.theebie.de",
    [int]$TheebieLast = 20,
    [int]$GatewayLines = 25,
    [int]$WorldAgentLines = 20,
    [switch]$Watch,           # Start live tail windows instead of snapshot
    [switch]$TheebieOnly,     # Only fetch and show theebie recent chat
    [switch]$NoTheebie        # Skip theebie (only sparky logs)
)

$ErrorActionPreference = "Continue"

# ----- Theebie recent chat -----
function Show-TheebieRecent {
    $url = "$TheebieUrl/chat/recent?limit=$TheebieLast"
    Write-Host "`n--- theebie recent chat ($TheebieLast) ---" -ForegroundColor Cyan
    try {
        $r = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 15
    } catch {
        Write-Host "  Request failed: $_" -ForegroundColor Red
        return
    }
    $msgs = $r.messages
    if (-not $msgs) {
        Write-Host "  No messages." -ForegroundColor Gray
        return
    }
    foreach ($m in $msgs) {
        $sid = if ($m.sender_id) { $m.sender_id } else { "?" }
        $name = if ($m.sender_name) { $m.sender_name } else { $sid }
        $rawText = if ($m.text) { $m.text.ToString().Trim() } else { "" }
        if ($rawText.Length -gt 72) { $rawText = $rawText.Substring(0, 69) + "..." }
        $ts = $m.created_at
        if ($ts -match "^\d+(\.\d+)?$") {
            $dt = [DateTimeOffset]::FromUnixTimeSeconds([long][double]$ts).LocalDateTime.ToString("HH:mm:ss")
        } else { $dt = $ts }
        $color = if ($sid -eq "Sparky1Agent") { "Cyan" } elseif ($sid -eq "MalicorSparky2") { "Green" } else { "Gray" }
        Write-Host "  [$dt] $name : $rawText" -ForegroundColor $color
    }
}

# ----- Snapshot: fetch remote log tail -----
function Get-RemoteLog {
    param([string]$HostName, [string]$Path, [int]$Lines)
    $cmd = "tail -n $Lines $Path 2>/dev/null"
    $out = ssh -o BatchMode=yes -o ConnectTimeout=10 $HostName $cmd 2>$null
    if (-not $out) { return "(unreachable or empty)" }
    $out
}

# ----- Watch mode: open tail windows -----
function Start-WatchWindows {
    $tailCmd = "tail -f ~/.openclaw/gateway.log ~/.world_agent_langgraph.log 2>/dev/null"
    $cmd1 = "`$host.UI.RawUI.WindowTitle = 'sparky1 gateway + world agent'; ssh $Sparky1Host '$tailCmd'"
    $cmd2 = "`$host.UI.RawUI.WindowTitle = 'sparky2 gateway + world agent'; ssh $Sparky2Host '$tailCmd'"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd1
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd2
    Write-Host "Watch windows started (gateway + world agent log per host). Close windows to stop." -ForegroundColor Cyan
}

# ========== Main ==========
if ($Watch) {
    Start-WatchWindows
    return
}

Write-Host "=== Bots activity snapshot ===" -ForegroundColor Cyan

if (-not $TheebieOnly -and -not $NoTheebie) {
    Show-TheebieRecent
}

if ($TheebieOnly) {
    return
}

# Sparky1
Write-Host "`n--- $Sparky1Host gateway (last $GatewayLines) ---" -ForegroundColor Yellow
$g1 = Get-RemoteLog -HostName $Sparky1Host -Path "~/.openclaw/gateway.log" -Lines $GatewayLines
$g1 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
Write-Host "`n--- $Sparky1Host world agent / LangGraph (last $WorldAgentLines) ---" -ForegroundColor Yellow
$w1 = Get-RemoteLog -HostName $Sparky1Host -Path "~/.world_agent_langgraph.log" -Lines $WorldAgentLines
$w1 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }

# Sparky2
Write-Host "`n--- $Sparky2Host gateway (last $GatewayLines) ---" -ForegroundColor Yellow
$g2 = Get-RemoteLog -HostName $Sparky2Host -Path "~/.openclaw/gateway.log" -Lines $GatewayLines
$g2 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
Write-Host "`n--- $Sparky2Host world agent / LangGraph (last $WorldAgentLines) ---" -ForegroundColor Yellow
$w2 = Get-RemoteLog -HostName $Sparky2Host -Path "~/.world_agent_langgraph.log" -Lines $WorldAgentLines
$w2 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }

Write-Host "`nDone. Use -Watch to open live tail windows." -ForegroundColor Gray
