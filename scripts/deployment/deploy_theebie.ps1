# Deploy backend (main.py + static/) to theebie.de (www.theebie.de).
# See docs/THEEBIE_DEPLOY.md. Run after deploy.ps1 when you want theebie UI/API updated.
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
$mainPyPath = Join-Path $projectRoot "backend\app\main.py"
$staticDir = Join-Path $projectRoot "backend\app\static"
$backendDir = "$RemotePath/backend/app"

Write-Host "Deploying backend (main.py, static/) to theebie.de ($TheebieHost)..." -ForegroundColor Cyan

$mainPyContent = Get-Content $mainPyPath -Raw
$tempFile = [System.IO.Path]::GetTempFileName()
$mainPyContent | Out-File -FilePath $tempFile -Encoding UTF8

try {
    Write-Host "  Copying main.py and static/..." -ForegroundColor Yellow
    scp $tempFile "${TheebieHost}:/tmp/main.py"
    ssh $TheebieHost "mkdir -p $backendDir $backendDir/static && mv /tmp/main.py $backendDir/main.py"
    if (Test-Path $staticDir) {
        Get-ChildItem -Path $staticDir -File | ForEach-Object {
            scp $_.FullName "${TheebieHost}:$backendDir/static/"
        }
        Write-Host "  [OK] main.py and static/ copied" -ForegroundColor Green
    }

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
} finally {
    if (Test-Path $tempFile) { Remove-Item $tempFile -Force }
}
