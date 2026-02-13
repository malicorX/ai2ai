# Live-watch OpenClaw gateways (sparky1 + sparky2). Opens one terminal per host
# that tails the gateway log (and optionally poll log / world agent log) so you can see:
#   - when a task was received (wake, cron.run, poll "new message")
#   - how they execute (tool calls, chat_say, completion, errors)
#   - why they didn't get it (no wake, cron skipped, gateway error)
#
# For a one-shot snapshot (theebie chat + last N log lines) use check_bots_activity.ps1.
# For live watch with world agent (LangGraph) log included, use check_bots_activity.ps1 -Watch.
#
# If the gateway window shows nothing new: the running gateway may log to the journal.
# Use -UseJournal to follow journal (openclaw-gateway or clawdbot-gateway.service).
#
# Usage: .\scripts\clawd\watch_openclaw_bots.ps1
#   Or:  .\scripts\clawd\watch_openclaw_bots.ps1 -TargetHost sparky2
#   Or:  .\scripts\clawd\watch_openclaw_bots.ps1 -IncludeWorldAgent   (also tail ~/.world_agent_langgraph.log)
#   Or:  .\scripts\clawd\check_bots_activity.ps1   (snapshot); .\scripts\clawd\check_bots_activity.ps1 -Watch (live)
#
# Log paths: both sparkies ~/.openclaw/gateway.log; world agent ~/.world_agent_langgraph.log; poll ~/.moltworld_poll.log.
param(
    [ValidateSet("Both", "sparky1", "sparky2")]
    [string]$TargetHost = "Both",
    [bool]$IncludePollLog = $true,   # also tail ~/.moltworld_poll.log on each host
    [bool]$IncludeWorldAgent = $false,  # also tail ~/.world_agent_langgraph.log (Python agent with USE_LANGGRAPH=1)
    [switch]$UseJournal              # tail journal (journalctl) for gateway instead of file
)

$ErrorActionPreference = "Continue"

function Start-WatchWindow {
    param([string]$Title, [string]$SshHost, [string]$LogPath, [bool]$AddPollLog, [bool]$UseJrn, [bool]$AddWorldAgent = $false)
    if ($UseJrn) {
        $tailCmd = "journalctl --user -u openclaw-gateway.service -f --no-pager -n 50 2>/dev/null || journalctl --user -u clawdbot-gateway.service -f --no-pager -n 50"
    } else {
        $tailCmd = "tail -f $LogPath"
        if ($AddPollLog) { $tailCmd += " ~/.moltworld_poll.log 2>/dev/null" }
        if ($AddWorldAgent) { $tailCmd += " ~/.world_agent_langgraph.log 2>/dev/null" }
    }
    $cmd = "`$host.UI.RawUI.WindowTitle = '$Title'; ssh $SshHost '$tailCmd'"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd
}

if ($TargetHost -eq "Both" -or $TargetHost -eq "sparky1") {
    Start-WatchWindow -Title "sparky1 OpenClaw gateway" -SshHost "sparky1" -LogPath "~/.openclaw/gateway.log" -AddPollLog $IncludePollLog -UseJrn $UseJournal -AddWorldAgent $IncludeWorldAgent
}
if ($TargetHost -eq "Both" -or $TargetHost -eq "sparky2") {
    Start-WatchWindow -Title "sparky2 OpenClaw gateway" -SshHost "sparky2" -LogPath "~/.openclaw/gateway.log" -AddPollLog $IncludePollLog -UseJrn $UseJournal -AddWorldAgent $IncludeWorldAgent
}

Write-Host "Live-watch started. Close the window(s) to stop." -ForegroundColor Cyan
if ($UseJournal) { Write-Host "  Using journal (systemd) for gateway; use this when the file shows only old 'failed to start' lines." -ForegroundColor Gray }
Write-Host "  Look for: wake, cron.run, hooks, chat_say, world_state, tools, error" -ForegroundColor Gray
if ($IncludePollLog) {
    Write-Host "  Poll log: 'new message, running pull-and-wake' = task received from poll loop" -ForegroundColor Gray
}
if ($IncludeWorldAgent) {
    Write-Host "  World agent log: Python agent (USE_LANGGRAPH=1) move/chat/jobs/decide" -ForegroundColor Gray
}
Write-Host "  Snapshot instead: .\scripts\clawd\check_bots_activity.ps1" -ForegroundColor DarkGray
