# Check Clawd (Moltbot) status on sparky1 and sparky2 from your dev machine.
# Prints a short plain-text summary (readable in Windows PowerShell). Full status uses Unicode tables; run on host for that.
# Usage: .\scripts\clawd\clawd_status.ps1
# Optional: .\scripts\clawd\clawd_status.ps1 -Hosts sparky1
param(
    [string[]]$Hosts = @("sparky1", "sparky2")
)

$ErrorActionPreference = "Continue"
$scriptDir = $PSScriptRoot
$remoteScript = Join-Path $scriptDir "clawd_status_remote.sh"
$remotePath = "/home/malicor/ai_ai2ai/scripts/clawd/clawd_status_remote.sh"

foreach ($h in $Hosts) {
    Write-Host "`n=== $h ===" -ForegroundColor Cyan
    try {
        ssh $h "mkdir -p /home/malicor/ai_ai2ai/scripts/clawd" 2>$null
        scp -q $remoteScript "${h}:$remotePath"
        ssh $h "sed -i 's/\r$//' $remotePath 2>/dev/null; chmod +x $remotePath; bash $remotePath" 2>&1 | ForEach-Object { Write-Host $_ }
    } catch {
        Write-Host "  Error: $_" -ForegroundColor Red
    }
}
Write-Host ""
Write-Host "Gateway unreachable = gateway not running yet. No restart needed; start it once:" -ForegroundColor Yellow
Write-Host "  ssh sparky1" -ForegroundColor Gray
Write-Host "  source ~/.bashrc" -ForegroundColor Gray
Write-Host "  clawdbot onboard --install-daemon" -ForegroundColor White
Write-Host "  (pairing + channels; then the daemon runs and Gateway will show 200)" -ForegroundColor Gray
Write-Host ""
Write-Host "Model: both sparkies use ollama/llama3.1:70b (in ~/.clawdbot/clawdbot.json)." -ForegroundColor Cyan
Write-Host "Full status (with tables): ssh sparky1 'source ~/.bashrc; clawdbot status'" -ForegroundColor Gray
Write-Host ""
