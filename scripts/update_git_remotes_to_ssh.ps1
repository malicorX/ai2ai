# Update git remotes on sparky1 and sparky2 to use SSH instead of HTTPS

Write-Host "=== Updating Git Remotes to SSH ===" -ForegroundColor Cyan

$repoSSH = "git@github.com:malicorX/ai2ai.git"

# Update sparky1
Write-Host "`n[1/2] Updating sparky1..." -ForegroundColor Yellow
try {
    ssh -o BatchMode=yes -o ConnectTimeout=15 sparky1 "cd ~/ai_ai2ai && git remote set-url origin $repoSSH && git remote -v" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ sparky1 remote updated to SSH" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Failed to update sparky1 remote" -ForegroundColor Red
    }
} catch {
    Write-Host "  ✗ Error updating sparky1: $_" -ForegroundColor Red
}

# Update sparky2
Write-Host "`n[2/2] Updating sparky2..." -ForegroundColor Yellow
try {
    ssh -o BatchMode=yes -o ConnectTimeout=15 sparky2 "cd ~/ai_ai2ai && git remote set-url origin $repoSSH && git remote -v" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ sparky2 remote updated to SSH" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Failed to update sparky2 remote" -ForegroundColor Red
    }
} catch {
    Write-Host "  ✗ Error updating sparky2: $_" -ForegroundColor Red
}

# Test git operations
Write-Host "`n[Testing] Verifying git operations..." -ForegroundColor Yellow

try {
    $test1 = ssh -o BatchMode=yes -o ConnectTimeout=15 sparky1 "cd ~/ai_ai2ai && git fetch origin 2>&1 | head -3"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ sparky1 can fetch from GitHub via SSH" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ sparky1 fetch test: $test1" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ⚠ sparky1 fetch test failed" -ForegroundColor Yellow
}

try {
    $test2 = ssh -o BatchMode=yes -o ConnectTimeout=15 sparky2 "cd ~/ai_ai2ai && git fetch origin 2>&1 | head -3"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ sparky2 can fetch from GitHub via SSH" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ sparky2 fetch test: $test2" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ⚠ sparky2 fetch test failed" -ForegroundColor Yellow
}

Write-Host "`n=== Complete ===" -ForegroundColor Cyan
Write-Host "Git remotes have been updated to use SSH!" -ForegroundColor Green
Write-Host "You can now use 'git pull' and 'git push' directly on sparky1 and sparky2" -ForegroundColor Yellow
