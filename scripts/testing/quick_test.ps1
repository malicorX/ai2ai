# Quick PowerShell health check for AI Village system
# Optional -BackendToken (or env BACKEND_TOKEN): use Bearer auth when backend requires it (e.g. sparky1:8000).

param(
    [string]$BackendUrl = "http://localhost:8000",
    [string]$BackendToken = ""
)

if (-not $BackendToken) { $BackendToken = $env:BACKEND_TOKEN }
$headers = @{}
if ($BackendToken) {
    $headers["Authorization"] = "Bearer $BackendToken"
    Write-Host "Using Bearer token for backend requests." -ForegroundColor Gray
}

Write-Host "AI Village Health Check" -ForegroundColor Cyan
Write-Host "==========================" -ForegroundColor Cyan
Write-Host "Backend URL: $BackendUrl" -ForegroundColor Gray
Write-Host ""

$ErrorActionPreference = "Continue"

# Test 1: Backend health
Write-Host "1. Testing backend health..." -NoNewline
try {
    $params = @{ Uri = "$BackendUrl/world"; Method = "Get"; TimeoutSec = 5; UseBasicParsing = $true }
    if ($headers.Count -gt 0) { $params.Headers = $headers }
    $response = Invoke-WebRequest @params
    if ($response.StatusCode -eq 200) {
        Write-Host " [OK] Backend is responding" -ForegroundColor Green
    } else {
        Write-Host " [FAIL] Backend returned status $($response.StatusCode)" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host " [FAIL] Backend is not responding: $_" -ForegroundColor Red
    if ($_.Exception.Response.StatusCode -eq 401 -and -not $BackendToken) {
        Write-Host "  Tip: Backend may require auth. Set BACKEND_TOKEN or pass -BackendToken, or use a public URL (e.g. https://www.theebie.de)." -ForegroundColor Yellow
    }
    exit 1
}

# Test 2: World state
Write-Host "2. Testing world state..." -NoNewline
try {
    $params = @{ Uri = "$BackendUrl/world"; Method = "Get"; TimeoutSec = 5 }
    if ($headers.Count -gt 0) { $params.Headers = $headers }
    $world = Invoke-RestMethod @params
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
    $params = @{ Uri = "$BackendUrl/jobs?limit=10"; Method = "Get"; TimeoutSec = 5 }
    if ($headers.Count -gt 0) { $params.Headers = $headers }
    $jobs = Invoke-RestMethod @params
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
    $params = @{ Uri = "$BackendUrl/economy/balances"; Method = "Get"; TimeoutSec = 5 }
    if ($headers.Count -gt 0) { $params.Headers = $headers }
    $balances = Invoke-RestMethod @params
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
    $params = @{ Uri = "$BackendUrl/memory/agent_1/recent?limit=1"; Method = "Get"; TimeoutSec = 5 }
    if ($headers.Count -gt 0) { $params.Headers = $headers }
    $memory = Invoke-RestMethod @params
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
    $params = @{ Uri = "$BackendUrl/opportunities?limit=5"; Method = "Get"; TimeoutSec = 5 }
    if ($headers.Count -gt 0) { $params.Headers = $headers }
    $opps = Invoke-RestMethod @params
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
Write-Host ('  python scripts/testing/test_workflow.py --backend-url ' + $BackendUrl) -ForegroundColor Gray
