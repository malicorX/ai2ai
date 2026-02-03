# Run Clawd non-interactive prep on sparky1 and sparky2 (doctor --fix, gateway.mode local).
# Run after run_install_clawd.ps1 so when you onboard, base state is ready.
# Usage: .\scripts\clawd\run_clawd_prepare.ps1
param(
    [string[]]$Hosts = @("sparky1", "sparky2")
)

$ErrorActionPreference = "Continue"
$scriptDir = $PSScriptRoot
$prepareScript = Join-Path $scriptDir "clawd_prepare_on_sparky.sh"
$remoteRepo = "ai_ai2ai"
$remotePath = "/home/malicor/$remoteRepo/scripts/clawd/clawd_prepare_on_sparky.sh"

if (-not (Test-Path $prepareScript)) {
    Write-Host "Missing $prepareScript" -ForegroundColor Red
    exit 1
}

foreach ($h in $Hosts) {
    Write-Host "`n=== $h ===" -ForegroundColor Cyan
    try {
        scp $prepareScript "${h}:$remotePath"
        ssh $h "sed -i 's/\r$//' $remotePath 2>/dev/null; chmod +x $remotePath; bash $remotePath"
        Write-Host "  [OK] Prep done on $h" -ForegroundColor Green
    } catch {
        Write-Host "  [WARN] $h : $_" -ForegroundColor Yellow
    }
}
Write-Host "`nNext: on the host where you want the gateway, run interactively: moltbot onboard --install-daemon" -ForegroundColor Cyan
