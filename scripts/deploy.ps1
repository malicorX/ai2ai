# Deploy backend changes to sparky1 and sparky2
#
# When backend runs in Docker on sparky1 (default):
#   .\deploy.ps1 -Docker
#   Copies main.py to both servers, rebuilds and restarts the backend container on sparky1.
#
#   .\deploy.ps1 -Docker -CopyOnly
#   Copies only; you run the Docker rebuild on sparky1 yourself.
#
# When backend runs bare-metal (uvicorn on host):
#   .\deploy.ps1 -CopyOnly
#   Copies main.py and restart_after_deploy.sh; you run restart_after_deploy.sh on each server.
#   .\deploy.ps1   (no -Docker) tries host restart over ssh (no sudo).
param(
    [string]$BackendUrl = "http://sparky1:8000",
    [switch]$CopyOnly = $false,  # copy only; you run restart yourself
    [switch]$Docker = $true,     # when true, restart via Docker on sparky1 (backend is in Docker there)
    [string]$Sparky1Repo = "ai_ai2ai"  # path on sparky1 for Docker compose (relative to /home/malicor). Use ai2ai for bare-metal.
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$restartScriptPath = Join-Path $scriptDir "restart_after_deploy.sh"
$mainPyPath = Join-Path $scriptDir "..\backend\app\main.py"

Write-Host "Deploying backend (main.py + restart_after_deploy.sh) to sparky1 and sparky2..." -ForegroundColor Cyan

$mainPyContent = Get-Content $mainPyPath -Raw
$tempFile = [System.IO.Path]::GetTempFileName()
$mainPyContent | Out-File -FilePath $tempFile -Encoding UTF8

$sparky1Backend = if ($Docker) { "/home/malicor/$Sparky1Repo/backend/app" } else { "/home/malicor/ai2ai/backend/app" }
$sparky1Scripts = if ($Docker) { "/home/malicor/$Sparky1Repo/scripts" } else { "/home/malicor/ai2ai/scripts" }
try {
    foreach ($h in @("sparky1", "sparky2")) {
        Write-Host "  Copying to $h..." -ForegroundColor Yellow
        scp $tempFile "${h}:/tmp/main.py"
        $backendDir = if ($h -eq "sparky1") { $sparky1Backend } else { "/home/malicor/ai2ai/backend/app" }
        $scriptsDir = if ($h -eq "sparky1") { $sparky1Scripts } else { "/home/malicor/ai2ai/scripts" }
        ssh $h "mkdir -p $backendDir $scriptsDir && mv /tmp/main.py $backendDir/main.py"
        scp $restartScriptPath "${h}:$scriptsDir/restart_after_deploy.sh"
        ssh $h "dos2unix $scriptsDir/restart_after_deploy.sh 2>/dev/null || sed -i 's/\r$//' $scriptsDir/restart_after_deploy.sh"
    }
    Write-Host "  [OK] main.py and restart_after_deploy.sh are on sparky1 and sparky2" -ForegroundColor Green

    if ($CopyOnly) {
        Write-Host ""
        if ($Docker) {
            Write-Host "Rebuild and restart the backend container on sparky1:" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "  ssh sparky1" -ForegroundColor Gray
            Write-Host "  cd ~/$Sparky1Repo && docker compose -f deployment/docker-compose.sparky1.yml up -d --build backend" -ForegroundColor White
            Write-Host "  exit" -ForegroundColor Gray
        } else {
            Write-Host "Restart the backend on each server (sudo will prompt there):" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "  ssh sparky1" -ForegroundColor Gray
            Write-Host "  bash ~/ai2ai/scripts/restart_after_deploy.sh" -ForegroundColor White
            Write-Host "  exit" -ForegroundColor Gray
            Write-Host ""
            Write-Host "  ssh sparky2" -ForegroundColor Gray
            Write-Host "  bash ~/ai2ai/scripts/restart_after_deploy.sh" -ForegroundColor White
            Write-Host "  exit" -ForegroundColor Gray
        }
        Write-Host ""
        exit 0
    }

    if ($Docker) {
        # Backend on sparky1 runs in Docker; rebuild and restart the container.
        Write-Host "`nRebuilding and restarting backend container on sparky1..." -ForegroundColor Cyan
        ssh sparky1 "cd /home/malicor/$Sparky1Repo && docker compose -f deployment/docker-compose.sparky1.yml up -d --build backend"
        Write-Host "  [OK] Backend container restarted on sparky1" -ForegroundColor Green
    } else {
        # Bare-metal: try to restart over ssh (no sudo – works only if backend runs as your user)
        Write-Host "`nRestarting backend on sparky1 and sparky2 (no sudo)..." -ForegroundColor Cyan
        foreach ($h in @("sparky1", "sparky2")) {
            ssh $h "pkill -f 'uvicorn app.main:app' || true; sleep 2; cd /home/malicor/ai2ai/backend && nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> /tmp/ai2ai_backend.log 2>&1 &"
        }
        Write-Host "  [OK] Backend restarted on sparky1 and sparky2" -ForegroundColor Green
    }
} finally {
    if (Test-Path $tempFile) { Remove-Item $tempFile -Force }
}
