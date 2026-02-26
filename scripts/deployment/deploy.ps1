# Deploy backend changes to sparky1 and sparky2
#
# When backend runs in Docker on sparky1 (default):
#   .\scripts\deployment\deploy.ps1 -Docker
#   Copies backend/app/ to both servers, rebuilds and restarts the backend container on sparky1.
#
#   .\scripts\deployment\deploy.ps1 -Docker -CopyOnly
#   Copies only; you run the Docker rebuild on sparky1 yourself.
#
# When backend runs bare-metal (uvicorn on host):
#   .\scripts\deployment\deploy.ps1 -CopyOnly
#   Copies app/ and restart_after_deploy.sh; you run restart_after_deploy.sh on each server.
#   .\scripts\deployment\deploy.ps1   (no -Docker) tries host restart over ssh (no sudo).
param(
    [string]$BackendUrl = "http://sparky1:8000",
    [switch]$CopyOnly = $false,
    [switch]$Docker = $true,
    [string]$Sparky1Repo = "ai_ai2ai"
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$projectRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$restartScriptPath = Join-Path $scriptDir "restart_after_deploy.sh"
$appDir = Join-Path $projectRoot "backend\app"

Write-Host "Deploying backend (app/, Dockerfile, restart_after_deploy.sh) to sparky1 and sparky2..." -ForegroundColor Cyan

$sparky1Backend = if ($Docker) { "/home/malicor/$Sparky1Repo/backend" } else { "/home/malicor/ai2ai/backend" }
$sparky1Scripts = if ($Docker) { "/home/malicor/$Sparky1Repo/scripts/deployment" } else { "/home/malicor/ai2ai/scripts/deployment" }

foreach ($h in @("sparky1", "sparky2")) {
    Write-Host "  Copying to $h..." -ForegroundColor Yellow
    $backendDir = if ($h -eq "sparky1") { $sparky1Backend } else { "/home/malicor/ai2ai/backend" }
    $scriptsDir = if ($h -eq "sparky1") { $sparky1Scripts } else { "/home/malicor/ai2ai/scripts/deployment" }

    ssh $h "mkdir -p $backendDir/app/routes $backendDir/app/static $scriptsDir"

    # Copy the entire app/ directory (all modules + routes)
    scp -r "$appDir\*" "${h}:$backendDir/app/"
    # Ensure routes/ subdirectory is copied
    if (Test-Path "$appDir\routes") {
        scp -r "$appDir\routes\*" "${h}:$backendDir/app/routes/"
    }
    # Copy Dockerfile
    $dockerfilePath = Join-Path $projectRoot "backend\Dockerfile"
    if (Test-Path $dockerfilePath) {
        scp $dockerfilePath "${h}:$backendDir/Dockerfile"
    }
    # Copy requirements.txt
    $reqPath = Join-Path $projectRoot "backend\requirements.txt"
    if (Test-Path $reqPath) {
        scp $reqPath "${h}:$backendDir/requirements.txt"
    }
    # Copy restart script
    if (Test-Path $restartScriptPath) {
        scp $restartScriptPath "${h}:$scriptsDir/restart_after_deploy.sh"
        ssh $h "dos2unix $scriptsDir/restart_after_deploy.sh 2>/dev/null || sed -i 's/\r$//' $scriptsDir/restart_after_deploy.sh"
    }
    Write-Host "  [OK] app/ copied to $h" -ForegroundColor Green
}

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
        Write-Host "  bash ~/ai2ai/scripts/deployment/restart_after_deploy.sh" -ForegroundColor White
        Write-Host "  exit" -ForegroundColor Gray
    }
    Write-Host ""
    exit 0
}

if ($Docker) {
    Write-Host "`nRebuilding and restarting backend container on sparky1..." -ForegroundColor Cyan
    ssh sparky1 "cd /home/malicor/$Sparky1Repo && docker compose -f deployment/docker-compose.sparky1.yml up -d --build backend"
    Write-Host "  [OK] Backend container restarted on sparky1" -ForegroundColor Green
} else {
    Write-Host "`nRestarting backend on sparky1 and sparky2 (no sudo)..." -ForegroundColor Cyan
    foreach ($h in @("sparky1", "sparky2")) {
        ssh $h "pkill -f 'uvicorn app.main:app' || true; sleep 2; cd /home/malicor/ai2ai/backend && nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> /tmp/ai2ai_backend.log 2>&1 &"
    }
    Write-Host "  [OK] Backend restarted on sparky1 and sparky2" -ForegroundColor Green
}

# Verify
Write-Host "`nVerifying..." -ForegroundColor Cyan
Start-Sleep -Seconds 3
try {
    $resp = Invoke-RestMethod -Uri "$BackendUrl/health" -TimeoutSec 10
    Write-Host "  [OK] Backend healthy: agents=$($resp.agents), world_size=$($resp.world_size)" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] Health check failed: $_" -ForegroundColor Yellow
}
