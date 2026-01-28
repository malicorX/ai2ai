# Quick PowerShell health check for AI Village system

param(
    [string]$BackendUrl = "http://localhost:8000"
)

Write-Host "AI Village Health Check" -ForegroundColor Cyan
Write-Host "==========================" -ForegroundColor Cyan
Write-Host "Backend URL: $BackendUrl" -ForegroundColor Gray
Write-Host ""

$ErrorActionPreference = "Continue"

# Test 1: Backend health
Write-Host "1. Testing backend health..." -NoNewline
try {
    $response = Invoke-WebRequest -Uri "$BackendUrl/world" -Method Get -TimeoutSec 5 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host " [OK] Backend is responding" -ForegroundColor Green
    } else {
        Write-Host " [FAIL] Backend returned status $($response.StatusCode)" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host " [FAIL] Backend is not responding: $_" -ForegroundColor Red
    exit 1
}

# Test 2: World state
Write-Host "2. Testing world state..." -NoNewline
try {
    $world = Invoke-RestMethod -Uri "$BackendUrl/world" -Method Get -TimeoutSec 5
    if ($world.agents) {
        $agentCount = $world.agents.Count
        Write-Host " [OK] World state accessible (agents: $agentCount)" -ForegroundColor Green
    } else {
        Write-Host " [!!] World state accessible but no agents found" -ForegroundColor Yellow
    }
} catch {
    Write-Host " [FAIL] Failed to get world state: $_" -ForegroundColor Red
}

# Test 3: Jobs endpoint
Write-Host "3. Testing jobs endpoint..." -NoNewline
try {
    $jobs = Invoke-RestMethod -Uri "$BackendUrl/jobs?limit=10" -Method Get -TimeoutSec 5
    if ($jobs.jobs) {
        $openCount = ($jobs.jobs | Where-Object { $_.status -eq "open" }).Count
        Write-Host " [OK] Jobs endpoint working (open jobs: $openCount)" -ForegroundColor Green
    } else {
        Write-Host " [!!] Jobs endpoint working but no jobs found" -ForegroundColor Yellow
    }
} catch {
    Write-Host " [FAIL] Jobs endpoint failed: $_" -ForegroundColor Red
}

# Test 4: Economy
Write-Host "4. Testing economy endpoint..." -NoNewline
try {
    $balances = Invoke-RestMethod -Uri "$BackendUrl/economy/balances" -Method Get -TimeoutSec 5
    if ($balances.balances) {
        Write-Host " [OK] Economy endpoint working" -ForegroundColor Green
    } else {
        Write-Host " [!!] Economy endpoint accessible but balances empty" -ForegroundColor Yellow
    }
} catch {
    Write-Host " [FAIL] Economy endpoint failed: $_" -ForegroundColor Red
}

# Test 5: Memory
Write-Host "5. Testing memory endpoint (agent_1)..." -NoNewline
try {
    $memory = Invoke-RestMethod -Uri "$BackendUrl/memory/agent_1/recent?limit=1" -Method Get -TimeoutSec 5
    if ($memory.memories) {
        Write-Host " [OK] Memory endpoint working" -ForegroundColor Green
    } else {
        Write-Host " [!!] Memory endpoint accessible but may be empty" -ForegroundColor Yellow
    }
} catch {
    Write-Host " [!!] Memory endpoint failed (may be normal if no memories yet): $_" -ForegroundColor Yellow
}

# Test 6: Opportunities
Write-Host "6. Testing opportunities endpoint..." -NoNewline
try {
    $opps = Invoke-RestMethod -Uri "$BackendUrl/opportunities?limit=5" -Method Get -TimeoutSec 5
    if ($opps.items) {
        Write-Host " [OK] Opportunities endpoint working" -ForegroundColor Green
    } else {
        Write-Host ' Opportunities endpoint accessible but may be empty' -ForegroundColor Yellow
    }
} catch {
    Write-Host (' Opportunities endpoint failed (may be normal if no opportunities yet): ' + $_.Exception.Message) -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Health check complete!' -ForegroundColor Green
Write-Host ''
Write-Host 'For detailed testing, run:' -ForegroundColor Gray
Write-Host ('  python scripts/test_workflow.py --backend-url ' + $BackendUrl) -ForegroundColor Gray
