# Live-watch OpenClaw/Clawd gateways (sparky1 + sparky2). Opens one terminal per host
# that tails the gateway log (and optionally the MoltWorld poll log) so you can see:
#   - when a task was received (wake, cron.run, poll "new message")
#   - how they execute (tool calls, chat_say, completion, errors)
#   - why they didn't get it (no wake, cron skipped, gateway error)
#
# If the gateway window shows nothing new: the running gateway is often started by
# systemd, so it logs to the journal, not the file. Use -UseJournal to follow the
# journal instead (clawdbot-gateway.service on both hosts).
#
# Usage: .\scripts\clawd\watch_openclaw_bots.ps1
#   Or:  .\scripts\clawd\watch_openclaw_bots.ps1 -TargetHost sparky2
#   Or:  .\scripts\clawd\watch_openclaw_bots.ps1 -UseJournal   (when gateway is under systemd)
#
# Log paths (file): sparky1 ~/.clawdbot/gateway.log, sparky2 ~/.openclaw/gateway.log.
# Poll log (when run): ~/.moltworld_poll.log on each host.
param(
    [ValidateSet("Both", "sparky1", "sparky2")]
    [string]$TargetHost = "Both",
    [bool]$IncludePollLog = $true,   # also tail ~/.moltworld_poll.log on each host
    [switch]$UseJournal              # tail journal (journalctl) for gateway instead of file; use when gateway is run by systemd
)

$ErrorActionPreference = "Continue"

function Start-WatchWindow {
    param([string]$Title, [string]$SshHost, [string]$LogPath, [bool]$AddPollLog, [bool]$UseJrn)
    if ($UseJrn) {
        # Gateway under systemd logs to journal; this is where wake/chat_say/tools appear (no poll log in same stream)
        $tailCmd = "journalctl --user -u clawdbot-gateway.service -f --no-pager -n 50"
    } else {
        $tailCmd = "tail -f $LogPath"
        if ($AddPollLog) { $tailCmd += " ~/.moltworld_poll.log 2>/dev/null" }
    }
    $cmd = "`$host.UI.RawUI.WindowTitle = '$Title'; ssh $SshHost '$tailCmd'"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd
}

if ($TargetHost -eq "Both" -or $TargetHost -eq "sparky1") {
    Start-WatchWindow -Title "sparky1 (Clawd) gateway" -SshHost "sparky1" -LogPath "~/.clawdbot/gateway.log" -AddPollLog $IncludePollLog -UseJrn $UseJournal
}
if ($TargetHost -eq "Both" -or $TargetHost -eq "sparky2") {
    Start-WatchWindow -Title "sparky2 (OpenClaw) gateway" -SshHost "sparky2" -LogPath "~/.openclaw/gateway.log" -AddPollLog $IncludePollLog -UseJrn $UseJournal
}

Write-Host "Live-watch started. Close the window(s) to stop." -ForegroundColor Cyan
if ($UseJournal) { Write-Host "  Using journal (systemd) for gateway; use this when the file shows only old 'failed to start' lines." -ForegroundColor Gray }
Write-Host "  Look for: wake, cron.run, hooks, chat_say, world_state, tools, error" -ForegroundColor Gray
if ($IncludePollLog) {
    Write-Host "  Poll log: 'new message, running pull-and-wake' = task received from poll loop" -ForegroundColor Gray
}
Write-Host "  Note: sparky1 often shows no new lines when only TestBot talks (sparky2 replies)." -ForegroundColor DarkGray
