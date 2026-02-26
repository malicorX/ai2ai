# Backup backend_data from sparky1 to local and optionally to sparky2
# Usage:
#   .\scripts\ops\backup_data.ps1             # backup sparky1 data locally
#   .\scripts\ops\backup_data.ps1 -ToSparky2  # also rsync to sparky2

param(
    [switch]$ToSparky2 = $false,
    [string]$LocalBackupDir = "backups"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$backupRoot = Join-Path $projectRoot $LocalBackupDir
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $backupRoot "backend_data_$timestamp"

Write-Host "Backing up sparky1 backend_data to $backupDir..." -ForegroundColor Cyan

if (-not (Test-Path $backupRoot)) { New-Item -ItemType Directory -Path $backupRoot | Out-Null }

scp -r "sparky1:/home/malicor/ai_ai2ai/backend_data" $backupDir

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Backup saved to $backupDir" -ForegroundColor Green
    $size = (Get-ChildItem -Recurse $backupDir | Measure-Object -Property Length -Sum).Sum
    Write-Host "     Size: $([math]::Round($size / 1MB, 2)) MB" -ForegroundColor Gray
} else {
    Write-Host "[FAIL] Backup failed" -ForegroundColor Red
    exit 1
}

if ($ToSparky2) {
    Write-Host "Syncing backend_data to sparky2..." -ForegroundColor Cyan
    ssh sparky1 "rsync -avz /home/malicor/ai_ai2ai/backend_data/ sparky2:/home/malicor/ai_ai2ai/backend_data/"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Synced to sparky2" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Sync to sparky2 failed" -ForegroundColor Yellow
    }
}

# Prune old backups (keep last 5)
$oldBackups = Get-ChildItem -Path $backupRoot -Directory | Sort-Object Name -Descending | Select-Object -Skip 5
foreach ($old in $oldBackups) {
    Write-Host "Pruning old backup: $($old.Name)" -ForegroundColor Gray
    Remove-Item -Recurse -Force $old.FullName
}
