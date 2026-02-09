# Deploy and run MoltWorld webhook receiver on one or both sparkies.
# The receiver listens for POST from theebie (new_chat) and triggers one MoltWorld cron run.
# Usage: .\scripts\clawd\run_moltworld_webhook_receiver.ps1 [-Target sparky1] [-Target sparky2]
# To run in background on a sparky: ssh sparky1 "cd /tmp && nohup python3 moltworld_webhook_receiver.py > moltworld_webhook.log 2>&1 &"
param(
    [string[]]$Targets = @("sparky1", "sparky2"),
    [switch]$DeployOnly,
    [int]$Port = 9999
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$receiver = Join-Path $scriptDir "moltworld_webhook_receiver.py"

foreach ($t in $Targets) {
    $claw = if ($t -eq "sparky1") { "clawdbot" } else { "openclaw" }
    Write-Host "Deploying webhook receiver to $t (CLAW=$claw, PORT=$Port)..." -ForegroundColor Cyan
    scp -q $receiver "${t}:/tmp/moltworld_webhook_receiver.py"
    if (-not $DeployOnly) {
        Write-Host "  To start on $t (foreground): ssh $t 'CLAW=$claw PORT=$Port python3 /tmp/moltworld_webhook_receiver.py'" -ForegroundColor Gray
        Write-Host "  To start on $t (background): ssh $t 'nohup env CLAW=$claw PORT=$Port python3 /tmp/moltworld_webhook_receiver.py >> /tmp/moltworld_webhook.log 2>&1 &'" -ForegroundColor Gray
    }
}
Write-Host "Then register webhooks from theebie: see docs/MOLTWORLD_WEBHOOKS.md" -ForegroundColor Gray
