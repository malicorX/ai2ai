# Deploy plain SOUL (no world_state / MoltWorld) to both sparkies so the model is not instructed to call world_state.
# Usage: .\scripts\clawd\run_deploy_plain_soul_no_moltworld.ps1
param([string[]]$Hosts = @("sparky1", "sparky2"))

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$plainSoul = Join-Path $scriptDir "soul_plain_no_moltworld.md"
$deploySh = Join-Path $scriptDir "deploy_plain_soul_no_moltworld.sh"

foreach ($h in $Hosts) {
    scp -q $plainSoul "${h}:/tmp/soul_plain_no_moltworld.md"
    scp -q $deploySh "${h}:/tmp/deploy_plain_soul_no_moltworld.sh"
    ssh $h "sed -i 's/\r$//' /tmp/deploy_plain_soul_no_moltworld.sh; chmod +x /tmp/deploy_plain_soul_no_moltworld.sh; bash /tmp/deploy_plain_soul_no_moltworld.sh /tmp/soul_plain_no_moltworld.md"
}
Write-Host "Restarting gateways..." -ForegroundColor Cyan
& (Join-Path $scriptDir "run_restart_gateways_on_sparkies.ps1")
Write-Host "Plain SOUL deployed. Open a NEW chat." -ForegroundColor Green
