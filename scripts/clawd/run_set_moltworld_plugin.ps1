# Disable or re-enable the MoltWorld plugin on OpenClaw gateways (reversible).
# When disabled: no "Hook MoltWorld", no world_state/chat_say/go_to/fetch_url from MoltWorld; agents have no connection to MoltWorld.
# When enabled: plugin and tools are back (run this to restore).
#
# Usage:
#   .\scripts\clawd\run_set_moltworld_plugin.ps1 -Disable
#   .\scripts\clawd\run_set_moltworld_plugin.ps1 -Enable
#   .\scripts\clawd\run_set_moltworld_plugin.ps1 -Disable -Hosts sparky1
param(
    [switch]$Disable,
    [switch]$Enable,
    [string[]]$Hosts = @("sparky1", "sparky2")
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$shPath = Join-Path $scriptDir "set_moltworld_plugin_on_sparky.sh"

if (-not $Disable -and -not $Enable) {
    Write-Host "Usage: run_set_moltworld_plugin.ps1 -Disable | -Enable [-Hosts sparky1,sparky2]" -ForegroundColor Yellow
    Write-Host "  -Disable  Remove MoltWorld plugin from agents (no Hook MoltWorld, no world_state/chat_say to theebie)." -ForegroundColor Gray
    Write-Host "  -Enable   Restore MoltWorld plugin (run after -Disable to put connection back)." -ForegroundColor Gray
    exit 0
}

$mode = if ($Disable) { "disable" } else { "enable" }
Write-Host "MoltWorld plugin: $mode on $($Hosts -join ', ')..." -ForegroundColor Cyan
foreach ($h in $Hosts) {
    scp -q $shPath "${h}:/tmp/set_moltworld_plugin_on_sparky.sh" 2>$null
    $out = ssh -o BatchMode=yes -o ConnectTimeout=10 $h "sed -i 's/\r$//' /tmp/set_moltworld_plugin_on_sparky.sh 2>/dev/null; chmod +x /tmp/set_moltworld_plugin_on_sparky.sh; bash /tmp/set_moltworld_plugin_on_sparky.sh $mode" 2>&1
    Write-Host "  $h : $out"
}
Write-Host "Restarting gateways so the change takes effect..." -ForegroundColor Gray
& (Join-Path $scriptDir "run_restart_gateways_on_sparkies.ps1")
if ($Disable) {
    Write-Host "MoltWorld plugin disabled. No Hook MoltWorld; agents have no MoltWorld tools. To restore: .\scripts\clawd\run_set_moltworld_plugin.ps1 -Enable" -ForegroundColor Green
    Write-Host "To also stop narrator/poll from sending wake messages: .\scripts\clawd\set_moltworld_context.ps1 -Off" -ForegroundColor Gray
} else {
    Write-Host "MoltWorld plugin enabled. To disable again: .\scripts\clawd\run_set_moltworld_plugin.ps1 -Disable" -ForegroundColor Green
}
