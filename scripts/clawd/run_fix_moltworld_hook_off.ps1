# One-shot: disable MoltWorld plugin, restart gateways, verify. Stops "Hook MoltWorld: world_state" in Chat.
# After running: open a NEW chat session; old thread messages may still show past Hook MoltWorld.
# Usage: .\scripts\clawd\run_fix_moltworld_hook_off.ps1 [-Hosts sparky1,sparky2]
param(
    [string[]]$Hosts = @("sparky1", "sparky2")
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Step 1: Disable MoltWorld plugin on $($Hosts -join ', ')..." -ForegroundColor Cyan
& (Join-Path $scriptDir "run_set_moltworld_plugin.ps1") -Disable -Hosts $Hosts
if ($LASTEXITCODE -ne 0) { Write-Host "Disable had errors; continuing." -ForegroundColor Yellow }

Write-Host "Step 2: Verify plugin disabled..." -ForegroundColor Cyan
& (Join-Path $scriptDir "run_verify_moltworld_plugin_disabled.ps1") -Hosts $Hosts

Write-Host "Done. Open a NEW chat at http://<sparky>:18789/chat to avoid old Hook MoltWorld messages in thread." -ForegroundColor Green
