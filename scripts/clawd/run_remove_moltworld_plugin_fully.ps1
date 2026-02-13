# Fully remove MoltWorld: remove cron, remove plugin from config, hide extension dir, restart gateways.
# Use this when "disable" still leaves the MoltWorld hook active (e.g. gateway loads plugin from extension dir).
# Reversible: run install_moltworld_plugin_on_sparky.sh on each host, then run_set_moltworld_plugin.ps1 -Enable.
# Usage: .\scripts\clawd\run_remove_moltworld_plugin_fully.ps1 [-Hosts sparky1,sparky2]
param(
    [string[]]$Hosts = @("sparky1", "sparky2")
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$removeSh = Join-Path $scriptDir "remove_moltworld_plugin_on_sparky.sh"
$cronRemoveSh = Join-Path $scriptDir "run_moltworld_cron_remove.sh"

Write-Host "Step 1: Remove MoltWorld cron on both hosts..." -ForegroundColor Cyan
foreach ($h in $Hosts) {
    $cli = if ($h -eq "sparky1") { "clawdbot" } else { "openclaw" }
    scp -q $cronRemoveSh "${h}:/tmp/run_moltworld_cron_remove.sh" 2>$null
    $out = ssh -o BatchMode=yes -o ConnectTimeout=10 $h "sed -i 's/\r$//' /tmp/run_moltworld_cron_remove.sh 2>/dev/null; chmod +x /tmp/run_moltworld_cron_remove.sh; CLAW=$cli bash /tmp/run_moltworld_cron_remove.sh" 2>&1
    Write-Host "  $h ($cli): $out"
}

Write-Host "Step 2: Remove plugin from config and hide extension dir on $($Hosts -join ', ')..." -ForegroundColor Cyan
foreach ($h in $Hosts) {
    scp -q $removeSh "${h}:/tmp/remove_moltworld_plugin_on_sparky.sh" 2>$null
    $out = ssh -o BatchMode=yes -o ConnectTimeout=10 $h "sed -i 's/\r$//' /tmp/remove_moltworld_plugin_on_sparky.sh 2>/dev/null; chmod +x /tmp/remove_moltworld_plugin_on_sparky.sh; bash /tmp/remove_moltworld_plugin_on_sparky.sh" 2>&1
    Write-Host "  $h : $out"
}

Write-Host "Step 3: Restart gateways..." -ForegroundColor Cyan
& (Join-Path $scriptDir "run_restart_gateways_on_sparkies.ps1")

Write-Host "Step 4: Verify (no plugin entry)..." -ForegroundColor Cyan
& (Join-Path $scriptDir "run_verify_moltworld_plugin_disabled.ps1") -Hosts $Hosts

Write-Host "Done. MoltWorld fully removed (cron + config + extension hidden). Open a NEW chat at http://<sparky>:18789/chat" -ForegroundColor Green
