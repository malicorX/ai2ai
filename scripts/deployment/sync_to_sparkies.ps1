# Sync script: Syncs code between local machine and sparky1/sparky2
# This script handles git operations on the local machine (which has GitHub auth)
# and file syncing to/from sparky1/sparky2
# 
# Usage: 
#   .\scripts\deployment\sync_to_sparkies.ps1 push    # Push local changes to GitHub, then sync to sparkies
#   .\scripts\deployment\sync_to_sparkies.ps1 pull    # Pull changes from GitHub, then sync to sparkies  
#   .\scripts\deployment\sync_to_sparkies.ps1 both    # Do both (default)

param(
    [string]$Mode = "both"  # pull: get changes from GitHub, push: send changes to GitHub+sparkies, both: do both
)

$ErrorActionPreference = "Continue"
$ProjectRoot = $PSScriptRoot + "\..\.."

Write-Host "=== AI2AI Git Sync ===" -ForegroundColor Cyan

# Step 1: Pull from GitHub (on local machine)
Write-Host "`n[1/4] Pulling from GitHub..." -ForegroundColor Yellow
Push-Location $ProjectRoot
try {
    git pull origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Warning: git pull had issues" -ForegroundColor Yellow
    }
} catch {
    Write-Host "Error pulling from GitHub: $_" -ForegroundColor Red
}
Pop-Location

if ($Mode -eq "pull" -or $Mode -eq "both") {
    # Step 2: Pull changes from sparky1 and sparky2
    Write-Host "`n[2/4] Pulling changes from sparky1..." -ForegroundColor Yellow
    try {
        $sparky1Changes = ssh -o BatchMode=yes -o ConnectTimeout=15 sparky1 "cd ~/ai_ai2ai && git status --porcelain 2>&1"
        if ($sparky1Changes -and $sparky1Changes -notmatch "fatal|error") {
            Write-Host "  sparky1 has uncommitted changes - consider committing them first" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  Could not check sparky1 status" -ForegroundColor Yellow
    }
    
    Write-Host "`n[2/4] Pulling changes from sparky2..." -ForegroundColor Yellow
    try {
        $sparky2Changes = ssh -o BatchMode=yes -o ConnectTimeout=15 sparky2 "cd ~/ai_ai2ai && git status --porcelain 2>&1"
        if ($sparky2Changes -and $sparky2Changes -notmatch "fatal|error") {
            Write-Host "  sparky2 has uncommitted changes - consider committing them first" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  Could not check sparky2 status" -ForegroundColor Yellow
    }
}

if ($Mode -eq "push" -or $Mode -eq "both") {
    # Step 3: Push to GitHub (from local)
    Write-Host "`n[3/4] Pushing to GitHub..." -ForegroundColor Yellow
    Push-Location $ProjectRoot
    try {
        $status = git status --porcelain
        if ($status) {
            Write-Host "  You have uncommitted changes. Commit them first:" -ForegroundColor Yellow
            Write-Host "  git add -A && git commit -m 'Your message' && git push" -ForegroundColor Cyan
        } else {
            git push origin main
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  Pushed to GitHub successfully" -ForegroundColor Green
            }
        }
    } catch {
        Write-Host "  Error pushing to GitHub: $_" -ForegroundColor Red
    }
    Pop-Location
    
    # Step 4: Sync files to sparky1 and sparky2
    Write-Host "`n[4/4] Syncing to sparky1..." -ForegroundColor Yellow
    $filesToSync = @(
        "agents/agent_template/agent.py",
        "agents/agent_template/langgraph_agent.py",
        "agents/agent_template/langgraph_control.py",
        "agents/agent_template/langgraph_runtime.py",
        "backend/app/main.py",
        "backend/app/static/index.html",
        "deployment/docker-compose.sparky1.yml"
    )
    
    $syncedCount = 0
    foreach ($file in $filesToSync) {
        $localPath = Join-Path $ProjectRoot $file
        if (Test-Path $localPath) {
            try {
                $null = scp -o BatchMode=yes -o ConnectTimeout=15 -q $localPath "sparky1:~/ai_ai2ai/$file" 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "  ✓ $file" -ForegroundColor Green
                    $syncedCount++
                } else {
                    Write-Host "  ✗ $file" -ForegroundColor Red
                }
            } catch {
                Write-Host "  ✗ $file" -ForegroundColor Red
            }
        }
    }
    Write-Host "  Synced $syncedCount/$($filesToSync.Count) files to sparky1" -ForegroundColor $(if ($syncedCount -eq $filesToSync.Count) { "Green" } else { "Yellow" })
    
    Write-Host "`n[4/4] Syncing to sparky2..." -ForegroundColor Yellow
    $filesToSync2 = @(
        "agents/agent_template/agent.py",
        "agents/agent_template/langgraph_agent.py",
        "agents/agent_template/langgraph_control.py",
        "agents/agent_template/langgraph_runtime.py",
        "backend/app/main.py",
        "backend/app/static/index.html",
        "deployment/docker-compose.sparky2.yml"
    )
    
    $syncedCount2 = 0
    foreach ($file in $filesToSync2) {
        $localPath = Join-Path $ProjectRoot $file
        if (Test-Path $localPath) {
            try {
                $null = scp -o BatchMode=yes -o ConnectTimeout=15 -q $localPath "sparky2:~/ai_ai2ai/$file" 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "  ✓ $file" -ForegroundColor Green
                    $syncedCount2++
                } else {
                    Write-Host "  ✗ $file" -ForegroundColor Red
                }
            } catch {
                Write-Host "  ✗ $file" -ForegroundColor Red
            }
        }
    }
    Write-Host "  Synced $syncedCount2/$($filesToSync2.Count) files to sparky2" -ForegroundColor $(if ($syncedCount2 -eq $filesToSync2.Count) { "Green" } else { "Yellow" })
}

Write-Host "`n=== Sync Complete ===" -ForegroundColor Cyan
Write-Host "Tip: Use 'git pull' on sparky1/sparky2 to get latest changes from GitHub" -ForegroundColor Yellow
Write-Host "     Or use this script with -Mode push to sync your changes" -ForegroundColor Yellow
