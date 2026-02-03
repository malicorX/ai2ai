# Restart Clawd gateway on sparky1/sparky2 with OLLAMA_API_KEY so TUI gets tokens from Ollama.
# Run from your dev machine. Gateway must already be installed (run_install_clawd.ps1 + run_clawd_prepare.ps1).
# Usage: .\scripts\clawd\run_start_clawd_gateway.ps1 [-Hosts sparky1,sparky2]
param(
    [string[]]$Hosts = @("sparky1", "sparky2")
)

$ErrorActionPreference = "Continue"
$scriptDir = $PSScriptRoot
$startScript = Join-Path $scriptDir "start_clawd_gateway.sh"
$remoteRepo = "ai_ai2ai"
$remotePath = "/home/malicor/$remoteRepo/scripts/clawd/start_clawd_gateway.sh"

if (-not (Test-Path $startScript)) {
    Write-Host "Missing $startScript" -ForegroundColor Red
    exit 1
}

foreach ($h in $Hosts) {
    Write-Host "`n=== $h ===" -ForegroundColor Cyan
    try {
        scp $startScript "${h}:$remotePath"
        ssh $h "sed -i 's/\r$//' $remotePath 2>/dev/null; chmod +x $remotePath; bash $remotePath"
        Write-Host "  [OK] Gateway restarted on $h (OLLAMA_API_KEY=ollama-local)" -ForegroundColor Green
    } catch {
        Write-Host "  [WARN] $h : $_" -ForegroundColor Yellow
    }
}
Write-Host "`nTry TUI again: ssh sparky1; source ~/.bashrc; clawdbot tui" -ForegroundColor Cyan
