# Deploy backend changes to sparky1 and sparky2
param(
    [string]$BackendUrl = "http://sparky1:8000"
)

$ErrorActionPreference = "Stop"

Write-Host "Deploying backend changes to sparky1 and sparky2..." -ForegroundColor Cyan

# Read the main.py file
$mainPyPath = Join-Path $PSScriptRoot "..\backend\app\main.py"
$mainPyContent = Get-Content $mainPyPath -Raw

# Create temporary file
$tempFile = [System.IO.Path]::GetTempFileName()
$mainPyContent | Out-File -FilePath $tempFile -Encoding UTF8

try {
    # Deploy to sparky1
    Write-Host "`nDeploying to sparky1..." -ForegroundColor Yellow
    scp $tempFile sparky1:/tmp/main.py
    ssh sparky1 "mkdir -p /home/malicor/ai2ai/backend/app && mv /tmp/main.py /home/malicor/ai2ai/backend/app/main.py && pkill -f 'uvicorn app.main:app' || true; sleep 2; cd /home/malicor/ai2ai/backend && nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/ai2ai_backend.log 2>&1 &"
    
    # Deploy to sparky2
    Write-Host "`nDeploying to sparky2..." -ForegroundColor Yellow
    scp $tempFile sparky2:/tmp/main.py
    ssh sparky2 "mkdir -p /home/malicor/ai2ai/backend/app && mv /tmp/main.py /home/malicor/ai2ai/backend/app/main.py && pkill -f 'uvicorn app.main:app' || true; sleep 2; cd /home/malicor/ai2ai/backend && nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/ai2ai_backend.log 2>&1 &"
    
    Write-Host "`n[OK] Deployment complete!" -ForegroundColor Green
    Write-Host "Backend restarted on sparky1 and sparky2" -ForegroundColor Green
} finally {
    # Clean up temp file
    if (Test-Path $tempFile) {
        Remove-Item $tempFile -Force
    }
}
