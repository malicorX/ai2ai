# Sync script: Syncs code between local machine and sparky1/sparky2
# This script handles git operations on the local machine (which has GitHub auth)
# and file syncing to/from sparky1/sparky2
#
# Usage:
#   .\scripts\deployment\sync_to_sparkies.ps1 push      # Push to GitHub, then sync to sparkies
#   .\scripts\deployment\sync_to_sparkies.ps1 pull      # Pull from GitHub, then sync to sparkies
#   .\scripts\deployment\sync_to_sparkies.ps1 both      # Do both (default)
#   .\scripts\deployment\sync_to_sparkies.ps1 synconly # Sync agent/backend files only (no git). Use to deploy local changes.

param(
    [string]$Mode = "both",  # pull | push | both | synconly
    [string]$RemotePath = "~/ai_ai2ai"
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

if ($Mode -eq "synconly") {
    # Sync files only, no git. Deploy current working tree to both sparkies.
    Write-Host "`n[Sync only] Syncing agent + backend files to sparkies (no git)..." -ForegroundColor Cyan
    $filesToSync = @(
        "agents/agent_template/agent.py",
        "agents/agent_template/agent_tools.py",
        "agents/agent_template/do_job.py",
        "agents/agent_template/langgraph_agent.py",
        "agents/agent_template/langgraph_control.py",
        "agents/agent_template/langgraph_runtime.py",
        "agents/agent_template/moltworld_bot.py",
        "agents/agent_template/requirements.txt"
    )
    foreach ($hostName in @("sparky1", "sparky2")) {
        Write-Host "`n  → $hostName ($RemotePath)..." -ForegroundColor Yellow
        $n = 0
        foreach ($file in $filesToSync) {
            $localPath = Join-Path $ProjectRoot $file
            if (Test-Path $localPath) {
                try {
                    $null = scp -o BatchMode=yes -o ConnectTimeout=15 -q $localPath "${hostName}:${RemotePath}/$file" 2>&1
                    if ($LASTEXITCODE -eq 0) { Write-Host "    ok $file" -ForegroundColor Green; $n++ } else { Write-Host "    fail $file" -ForegroundColor Red }
                } catch { Write-Host "    fail $file" -ForegroundColor Red }
            }
        }
        $clr = if ($n -eq $filesToSync.Count) { 'Green' } else { 'Yellow' }
        Write-Host ('  Synced {0} files to {1}' -f $n, $hostName) -ForegroundColor $clr
    }
    Write-Host ""; Write-Host '=== Sync complete ===' -ForegroundColor Cyan
    exit 0
}

if ($Mode -eq "pull" -or $Mode -eq "both") {
    # Step 2: Pull changes from sparky1 and sparky2
    Write-Host "`n[2/4] Pulling changes from sparky1..." -ForegroundColor Yellow
    try {
        $sparky1Changes = ssh -o BatchMode=yes -o ConnectTimeout=15 sparky1 'cd ~/ai_ai2ai; git status --porcelain 2>&1'
        if ($sparky1Changes -and $sparky1Changes -notmatch "fatal|error") {
            Write-Host "  sparky1 has uncommitted changes - consider committing them first" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  Could not check sparky1 status" -ForegroundColor Yellow
    }
    
    Write-Host "`n[2/4] Pulling changes from sparky2..." -ForegroundColor Yellow
    try {
        $sparky2Changes = ssh -o BatchMode=yes -o ConnectTimeout=15 sparky2 'cd ~/ai_ai2ai; git status --porcelain 2>&1'
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
            Write-Host "  git add -A; git commit -m 'Your message'; git push" -ForegroundColor Cyan
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
        "agents/agent_template/agent_tools.py",
        "agents/agent_template/do_job.py",
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
                $null = scp -o BatchMode=yes -o ConnectTimeout=15 -q $localPath "sparky1:${RemotePath}/$file" 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "  ok $file" -ForegroundColor Green
                    $syncedCount++
                } else {
                    Write-Host "  fail $file" -ForegroundColor Red
                }
            } catch {
                Write-Host "  fail $file" -ForegroundColor Red
            }
        }
    }
    $color1 = if ($syncedCount -eq $filesToSync.Count) { 'Green' } else { 'Yellow' }
    Write-Host ('  Synced {0}/{1} files to sparky1' -f $syncedCount, $filesToSync.Count) -ForegroundColor $color1
    
    Write-Host "`n[4/4] Syncing to sparky2..." -ForegroundColor Yellow
    $filesToSync2 = @(
        "agents/agent_template/agent.py",
        "agents/agent_template/agent_tools.py",
        "agents/agent_template/do_job.py",
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
                $null = scp -o BatchMode=yes -o ConnectTimeout=15 -q $localPath "sparky2:${RemotePath}/$file" 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "  ok $file" -ForegroundColor Green
                    $syncedCount2++
                } else {
                    Write-Host "  fail $file" -ForegroundColor Red
                }
            } catch {
                Write-Host "  fail $file" -ForegroundColor Red
            }
        }
    }
    $color2 = if ($syncedCount2 -eq $filesToSync2.Count) { 'Green' } else { 'Yellow' }
    Write-Host ('  Synced {0}/{1} files to sparky2' -f $syncedCount2, $filesToSync2.Count) -ForegroundColor $color2
}

Write-Host ""
Write-Host '=== Sync Complete ===' -ForegroundColor Cyan
Write-Host 'Tip: Use git pull on sparky1/sparky2 to get latest changes from GitHub' -ForegroundColor Yellow
Write-Host '     Or use this script with -Mode push to sync your changes' -ForegroundColor Yellow
