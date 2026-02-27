# Deploy backend (app/ directory) to theebie.de (www.theebie.de).
# Copies the full app/ package and rebuilds the Docker container.
#
#   .\scripts\deployment\deploy_theebie.ps1           # copy + rebuild backend container
#   .\scripts\deployment\deploy_theebie.ps1 -CopyOnly  # copy only; you rebuild on server
param(
    [string]$TheebieHost = "root@84.38.65.246",
    [string]$RemotePath = "/opt/ai_ai2ai",
    [switch]$CopyOnly = $false
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$projectRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$appDir = Join-Path $projectRoot "backend\app"
$requirementsFile = Join-Path $projectRoot "backend\requirements.txt"
$backendDir = "$RemotePath/backend"

Write-Host "Deploying backend (app/, requirements.txt) to theebie.de ($TheebieHost)..." -ForegroundColor Cyan

try {
    Write-Host "  Copying app/ directory..." -ForegroundColor Yellow

    # Copy requirements.txt
    scp $requirementsFile "${TheebieHost}:$backendDir/requirements.txt"

    # Ensure remote directories exist
    ssh $TheebieHost "mkdir -p $backendDir/app/routes $backendDir/app/static"

    # Copy all .py files in app/
    Get-ChildItem -Path $appDir -Filter "*.py" -File | ForEach-Object {
        scp $_.FullName "${TheebieHost}:$backendDir/app/"
    }

    # Copy all .py files in app/routes/
    $routesDir = Join-Path $appDir "routes"
    if (Test-Path $routesDir) {
        Get-ChildItem -Path $routesDir -Filter "*.py" -File | ForEach-Object {
            scp $_.FullName "${TheebieHost}:$backendDir/app/routes/"
        }
    }

    # Copy static files
    $staticDir = Join-Path $appDir "static"
    if (Test-Path $staticDir) {
        Get-ChildItem -Path $staticDir -File | ForEach-Object {
            scp $_.FullName "${TheebieHost}:$backendDir/app/static/"
        }
    }

    Write-Host "  [OK] app/ and requirements.txt copied" -ForegroundColor Green

    if ($CopyOnly) {
        Write-Host ""
        Write-Host "Rebuild and restart on theebie:" -ForegroundColor Cyan
        Write-Host "  ssh $TheebieHost `"cd $RemotePath && docker compose -f deployment/docker-compose.sparky1.yml up -d --build backend`"" -ForegroundColor White
        Write-Host ""
        exit 0
    }

    Write-Host "`nRebuilding and restarting backend container on theebie..." -ForegroundColor Cyan
    ssh $TheebieHost "cd $RemotePath && docker compose -f deployment/docker-compose.sparky1.yml up -d --build backend"
    Write-Host "  [OK] theebie.de backend restarted. Check https://www.theebie.de/ui/ (hard refresh if needed)" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] $_" -ForegroundColor Red
    throw
}
