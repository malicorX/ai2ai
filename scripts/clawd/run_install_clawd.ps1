# Run Clawd (Moltbot) install on sparky1 and sparky2 via SSH.
# Prereqs: Node >= 22 on each sparky. First time: run bootstrap interactively on each host (sudo will prompt):
#   ssh sparky1  ->  cd ~/ai_ai2ai && bash scripts/clawd/bootstrap_clawd_on_sparky.sh
#   ssh sparky2  ->  cd ~/ai_ai2ai && bash scripts/clawd/bootstrap_clawd_on_sparky.sh
# Then run this script from your dev machine to install/update Clawd.
# Usage: .\scripts\clawd\run_install_clawd.ps1
# Optional: -CopyOnly to only copy the script; you run it on each host yourself.
param(
    [switch]$CopyOnly = $false
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$installScript = Join-Path $scriptDir "install_clawd_on_sparky.sh"

if (-not (Test-Path $installScript)) {
    Write-Host "Missing $installScript" -ForegroundColor Red
    exit 1
}

$hosts = @("sparky1", "sparky2")
$remoteRepo = "ai_ai2ai"
$remoteScript = "/home/malicor/$remoteRepo/scripts/clawd/install_clawd_on_sparky.sh"

$bootstrapScript = Join-Path $scriptDir "bootstrap_clawd_on_sparky.sh"
foreach ($h in $hosts) {
    Write-Host "`n=== $h ===" -ForegroundColor Cyan
    try {
        # Ensure scripts dir exists and copy both scripts
        ssh $h "mkdir -p /home/malicor/$remoteRepo/scripts/clawd"
        scp $installScript "${h}:$remoteScript"
        if (Test-Path $bootstrapScript) { scp $bootstrapScript "${h}:/home/malicor/$remoteRepo/scripts/clawd/bootstrap_clawd_on_sparky.sh" }
        ssh $h "sed -i 's/\r$//' $remoteScript /home/malicor/$remoteRepo/scripts/clawd/bootstrap_clawd_on_sparky.sh 2>/dev/null; chmod +x $remoteScript /home/malicor/$remoteRepo/scripts/clawd/bootstrap_clawd_on_sparky.sh 2>/dev/null"
        Write-Host "  Copied install + bootstrap scripts to $h" -ForegroundColor Green

        if ($CopyOnly) {
            Write-Host "  (CopyOnly) Run on $h : ssh $h 'bash $remoteScript'" -ForegroundColor Yellow
        } else {
            Write-Host "  Running install on $h..." -ForegroundColor Yellow
            ssh $h "bash $remoteScript"
            Write-Host "  [OK] Install finished on $h" -ForegroundColor Green
        }
    } catch {
        Write-Host "  [FAIL] $h : $_" -ForegroundColor Red
        if (-not $CopyOnly) { exit 1 }
    }
}

if ($CopyOnly) {
    Write-Host "`nCopyOnly: run on each host:" -ForegroundColor Cyan
    Write-Host "  ssh sparky1 'bash $remoteScript'" -ForegroundColor White
    Write-Host "  ssh sparky2 'bash $remoteScript'" -ForegroundColor White
} else {
    Write-Host "`nNext: on each sparky run 'moltbot onboard --install-daemon' (pairing/channels). See docs/external-tools/clawd/CLAWD_SPARKY.md for cron." -ForegroundColor Cyan
}
Write-Host "If Node was missing: run bootstrap once interactively on each host (sudo will prompt):" -ForegroundColor Yellow
Write-Host "  ssh sparky1  ->  cd ~/ai_ai2ai && bash scripts/clawd/bootstrap_clawd_on_sparky.sh" -ForegroundColor Gray
Write-Host "  ssh sparky2  ->  cd ~/ai_ai2ai && bash scripts/clawd/bootstrap_clawd_on_sparky.sh" -ForegroundColor Gray
Write-Host "  Then re-run: .\scripts\clawd\run_install_clawd.ps1" -ForegroundColor Gray
