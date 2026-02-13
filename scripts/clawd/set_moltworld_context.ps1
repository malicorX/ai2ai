# Toggle MoltWorld context on or off so you can talk to the OpenClaw agent with or without the MoltWorld project.
#
# When ON (default): narrator/poll loops run pull-and-wake and inject full MoltWorld context (recent_chat, TASK, rules)
#   into each turn. Chat in Control UI shows that context when you're in a MoltWorld session.
# When OFF: pull-and-wake exits without sending; no new MoltWorld context is injected. You can chat in Control UI
#   and your message is not preceded by the big block (start a new chat session to avoid old context in history).
#
# Usage:
#   .\scripts\clawd\set_moltworld_context.ps1 -On
#   .\scripts\clawd\set_moltworld_context.ps1 -Off
#   .\scripts\clawd\set_moltworld_context.ps1 -Status
#   .\scripts\clawd\set_moltworld_context.ps1 -Off -Hosts sparky1
param(
    [switch]$On,
    [switch]$Off,
    [switch]$Status,
    [string[]]$Hosts = @("sparky1", "sparky2")
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$contextFile = "~/.moltworld_context"

if (-not $On -and -not $Off -and -not $Status) {
    Write-Host "Usage: set_moltworld_context.ps1 -On | -Off | -Status [-Hosts sparky1,sparky2]" -ForegroundColor Yellow
    Write-Host "  -On     MoltWorld context ON: pull-and-wake injects recent_chat, TASK, rules (default)." -ForegroundColor Gray
    Write-Host "  -Off    MoltWorld context OFF: pull-and-wake skips inject; chat without MoltWorld block." -ForegroundColor Gray
    Write-Host "  -Status Show current context state per host." -ForegroundColor Gray
    Write-Host "  -Hosts  Hosts to apply to (default: sparky1, sparky2)." -ForegroundColor Gray
    exit 0
}

foreach ($h in $Hosts) {
    if ($Status) {
        $val = ssh -o BatchMode=yes -o ConnectTimeout=10 $h "cat ~/.moltworld_context 2>/dev/null || echo ''" 2>$null
        if (-not $val -or -not $val.Trim()) { $val = "on" } else { $val = $val.Trim().ToLower() }
        if ($val -eq "off") {
            Write-Host "  $h : OFF (no MoltWorld context injection)" -ForegroundColor Yellow
        } else {
            Write-Host "  $h : ON (MoltWorld context injected)" -ForegroundColor Green
        }
        continue
    }
    if ($Off) {
        ssh -o BatchMode=yes -o ConnectTimeout=10 $h "echo -n off > ~/.moltworld_context" 2>$null
        Write-Host "  $h : MoltWorld context set to OFF" -ForegroundColor Yellow
    }
    if ($On) {
        ssh -o BatchMode=yes -o ConnectTimeout=10 $h "rm -f ~/.moltworld_context 2>/dev/null" 2>$null
        Write-Host "  $h : MoltWorld context set to ON (file removed)" -ForegroundColor Green
    }
}

if ($Off) {
    Write-Host ""
    Write-Host "Narrator/poll loops will keep running but pull-and-wake will skip (no inject)." -ForegroundColor Gray
    Write-Host "To avoid old MoltWorld instructions in the thread: start a NEW chat session in Control UI." -ForegroundColor Yellow
    Write-Host "Once context is off, world_state will return 'Direct chat mode' so the bot answers you and uses web_fetch for URL questions." -ForegroundColor Gray
}
if ($On) {
    Write-Host ""
    Write-Host "Pull-and-wake will inject MoltWorld context again on next run." -ForegroundColor Gray
}
