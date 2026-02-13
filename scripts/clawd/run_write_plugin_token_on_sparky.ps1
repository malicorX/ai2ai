# Write WORLD_AGENT_TOKEN from ~/.moltworld.env into the plugin extension .token file on sparky2.
# Run after deploying the MoltWorld plugin so chat_say can read the token even when the gateway doesn't pass config.
# Usage: .\scripts\clawd\run_write_plugin_token_on_sparky.ps1 [-TargetHost sparky2]
param([string]$TargetHost = "sparky2")

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$sh = Join-Path $scriptDir "write_plugin_token_on_sparky.sh"
if (-not (Test-Path $sh)) { Write-Host "Missing $sh" -ForegroundColor Red; exit 1 }
Write-Host "Writing plugin token on $TargetHost..." -ForegroundColor Cyan
scp -q $sh "${TargetHost}:/tmp/write_plugin_token_on_sparky.sh"
$out = ssh $TargetHost "sed -i 's/\r$//' /tmp/write_plugin_token_on_sparky.sh 2>/dev/null; chmod +x /tmp/write_plugin_token_on_sparky.sh; bash /tmp/write_plugin_token_on_sparky.sh" 2>&1
Write-Host $out
if ($out -match "OK:") { Write-Host "Done. Restart gateway on $TargetHost to use new plugin + token." -ForegroundColor Green } else { Write-Host "Check ~/.moltworld.env on $TargetHost has WORLD_AGENT_TOKEN" -ForegroundColor Yellow }
