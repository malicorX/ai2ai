# Remove tools.allow on sparky2 so MoltWorld wake gets the same full tool set as Dashboard Chat (web_fetch, browser, etc.).
# Usage: .\scripts\clawd\run_moltworld_tools_same_as_chat.ps1
param(
    [string]$TargetHost = "sparky2"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$shScript = Join-Path $scriptDir "patch_tools_same_as_chat.sh"
$cfgArg = if ($TargetHost -eq "sparky1") { "CONFIG=`$HOME/.clawdbot/clawdbot.json" } else { "CONFIG=`$HOME/.openclaw/openclaw.json" }

Write-Host "Making wake use same tools as Chat on $TargetHost (removing tools.allow)..." -ForegroundColor Cyan
scp -q $shScript "${TargetHost}:/tmp/patch_tools_same_as_chat.sh"
$out = ssh $TargetHost "sed -i 's/\r$//' /tmp/patch_tools_same_as_chat.sh 2>/dev/null; chmod +x /tmp/patch_tools_same_as_chat.sh; $cfgArg bash /tmp/patch_tools_same_as_chat.sh" 2>&1
Write-Host $out
if ($out -match "Removed tools.allow") { Write-Host "  $TargetHost OK" -ForegroundColor Green } else { Write-Host "  $TargetHost check above" -ForegroundColor Yellow }
Write-Host "Restart gateway so config applies: .\scripts\clawd\run_restart_gateways_on_sparkies.ps1" -ForegroundColor Gray
