# Ensure MoltWorld plugin tools are in tools.allow on both sparkies (so cron runs get them).
# Run after install_moltworld_plugin_on_sparky.sh or when cron never calls world_state/chat_say.
# Usage: .\scripts\clawd\run_moltworld_patch_tools_allow.ps1
param(
    [string[]]$Hosts = @("sparky1", "sparky2")
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$shScript = Join-Path $scriptDir "patch_tools_allow_moltworld.sh"

foreach ($h in $Hosts) {
    $cfgArg = if ($h -eq "sparky1") { "CONFIG=`$HOME/.clawdbot/clawdbot.json" } else { "CONFIG=`$HOME/.openclaw/openclaw.json" }
    Write-Host "Patching tools.allow on $h..." -ForegroundColor Cyan
    scp -q $shScript "${h}:/tmp/patch_tools_allow_moltworld.sh"
    $out = ssh $h "$cfgArg bash /tmp/patch_tools_allow_moltworld.sh" 2>&1
    Write-Host $out
    if ($out -match "Patched") { Write-Host "  $h OK" -ForegroundColor Green } else { Write-Host "  $h check above" -ForegroundColor Yellow }
}
Write-Host "Restart gateways so config applies: .\scripts\clawd\run_restart_gateways_on_sparkies.ps1" -ForegroundColor Gray
