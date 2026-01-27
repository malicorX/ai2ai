# Script to add SSH keys from sparky1 and sparky2 to GitHub
# Requires: GitHub Personal Access Token with 'admin:public_key' scope
# 
# Usage:
#   $env:GITHUB_TOKEN = "your_token_here"
#   .\scripts\add_ssh_keys_to_github.ps1

param(
    [string]$GitHubToken = $env:GITHUB_TOKEN,
    [string]$GitHubUser = "malicorX"
)

if (-not $GitHubToken) {
    Write-Host "Error: GitHub token required" -ForegroundColor Red
    Write-Host "Set GITHUB_TOKEN environment variable or pass -GitHubToken parameter" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To create a token:" -ForegroundColor Cyan
    Write-Host "  1. Go to https://github.com/settings/tokens" -ForegroundColor Cyan
    Write-Host "  2. Generate new token (classic)" -ForegroundColor Cyan
    Write-Host "  3. Select scope: 'admin:public_key'" -ForegroundColor Cyan
    Write-Host "  4. Copy the token and run:" -ForegroundColor Cyan
    Write-Host "     `$env:GITHUB_TOKEN = 'your_token'" -ForegroundColor Cyan
    Write-Host "     .\scripts\add_ssh_keys_to_github.ps1" -ForegroundColor Cyan
    exit 1
}

Write-Host "=== Adding SSH Keys to GitHub ===" -ForegroundColor Cyan

# Get SSH keys from sparky1 and sparky2
Write-Host "`n[1/3] Fetching SSH keys from sparky1 and sparky2..." -ForegroundColor Yellow

try {
    $sparky1Key = ssh -o BatchMode=yes -o ConnectTimeout=15 sparky1 "cat ~/.ssh/id_ed25519.pub" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ✗ Failed to get key from sparky1" -ForegroundColor Red
        $sparky1Key = $null
    } else {
        Write-Host "  ✓ Got key from sparky1" -ForegroundColor Green
    }
} catch {
    Write-Host "  ✗ Error getting key from sparky1: $_" -ForegroundColor Red
    $sparky1Key = $null
}

try {
    $sparky2Key = ssh -o BatchMode=yes -o ConnectTimeout=15 sparky2 "cat ~/.ssh/id_ed25519.pub" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ✗ Failed to get key from sparky2" -ForegroundColor Red
        $sparky2Key = $null
    } else {
        Write-Host "  ✓ Got key from sparky2" -ForegroundColor Green
    }
} catch {
    Write-Host "  ✗ Error getting key from sparky2: $_" -ForegroundColor Red
    $sparky2Key = $null
}

# Add keys to GitHub via API
Write-Host "`n[2/3] Adding keys to GitHub..." -ForegroundColor Yellow

$headers = @{
    "Authorization" = "token $GitHubToken"
    "Accept" = "application/vnd.github.v3+json"
}

function Add-SSHKey {
    param(
        [string]$Title,
        [string]$Key
    )
    
    if (-not $Key) {
        Write-Host "  ✗ $Title - No key provided" -ForegroundColor Red
        return $false
    }
    
    $body = @{
        title = $Title
        key = $Key.Trim()
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri "https://api.github.com/user/keys" -Method Post -Headers $headers -Body $body -ContentType "application/json"
        Write-Host "  ✓ Added key: $Title (ID: $($response.id))" -ForegroundColor Green
        return $true
    } catch {
        $errorMsg = $_.ErrorDetails.Message
        if ($errorMsg -match "key is already in use") {
            Write-Host "  ⚠ $Title - Key already exists on GitHub" -ForegroundColor Yellow
            return $true
        } else {
            Write-Host "  ✗ $Title - Error: $errorMsg" -ForegroundColor Red
            return $false
        }
    }
}

$sparky1Added = Add-SSHKey -Title "sparky1" -Key $sparky1Key
$sparky2Added = Add-SSHKey -Title "sparky2" -Key $sparky2Key

# Test connections
Write-Host "`n[3/3] Testing SSH connections..." -ForegroundColor Yellow

if ($sparky1Added) {
    try {
        $test1 = ssh -o BatchMode=yes -o ConnectTimeout=15 sparky1 "ssh -T git@github.com 2>&1"
        if ($test1 -match "successfully authenticated" -or $test1 -match "Hi") {
            Write-Host "  ✓ sparky1 can connect to GitHub" -ForegroundColor Green
        } else {
            Write-Host "  ⚠ sparky1 connection test: $test1" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  ⚠ sparky1 connection test failed" -ForegroundColor Yellow
    }
}

if ($sparky2Added) {
    try {
        $test2 = ssh -o BatchMode=yes -o ConnectTimeout=15 sparky2 "ssh -T git@github.com 2>&1"
        if ($test2 -match "successfully authenticated" -or $test2 -match "Hi") {
            Write-Host "  ✓ sparky2 can connect to GitHub" -ForegroundColor Green
        } else {
            Write-Host "  ⚠ sparky2 connection test: $test2" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  ⚠ sparky2 connection test failed" -ForegroundColor Yellow
    }
}

Write-Host "`n=== Complete ===" -ForegroundColor Cyan
if ($sparky1Added -and $sparky2Added) {
    Write-Host "Both SSH keys have been added to GitHub!" -ForegroundColor Green
    Write-Host "Next step: Update git remotes to use SSH" -ForegroundColor Yellow
    Write-Host "  Run: .\scripts\update_git_remotes_to_ssh.ps1" -ForegroundColor Cyan
} else {
    Write-Host "Some keys may not have been added. Check errors above." -ForegroundColor Yellow
}
