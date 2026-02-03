# Register a Moltbook agent and optionally save credentials on sparky and install skill. Run from dev machine.
# Usage:
#   .\scripts\moltbook\run_moltbook_register.ps1
#   .\scripts\moltbook\run_moltbook_register.ps1 -Name "Sparky2" -Description "Clawd agent on sparky2"
#   .\scripts\moltbook\run_moltbook_register.ps1 -SaveOn sparky2 -InstallSkill
param(
    [string]$Name = "MalicorSparky2",
    [string]$Description = "Clawd agent on sparky2; uses Ollama. Screens tasks, reports, and participates on Moltbook.",
    [string]$SaveOn = "",   # e.g. sparky2 to save credentials on that host after register
    [switch]$InstallSkill
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$payloadPath = Join-Path $scriptDir "moltbook_register_payload.json"

# Build payload
$payload = @{ name = $Name; description = $Description } | ConvertTo-Json -Compress
$payload | Set-Content -Path $payloadPath -Encoding UTF8 -NoNewline

Write-Host "Registering agent '$Name' on Moltbook..." -ForegroundColor Cyan
try {
    $body = Get-Content $payloadPath -Raw
    $resp = Invoke-RestMethod -Uri "https://www.moltbook.com/api/v1/agents/register" -Method POST -ContentType "application/json" -Body $body -TimeoutSec 30
} catch {
    Write-Host "Register failed (try from sparky2: curl -X POST https://www.moltbook.com/api/v1/agents/register -H 'Content-Type: application/json' -d '$payload'): $_" -ForegroundColor Yellow
    exit 1
}

$apiKey = $resp.agent.api_key
$claimUrl = $resp.agent.claim_url
$verificationCode = $resp.agent.verification_code

Write-Host ""
Write-Host "Registered. SAVE YOUR API KEY NOW:" -ForegroundColor Green
Write-Host "  api_key: $apiKey"
Write-Host "  claim_url: $claimUrl"
Write-Host "  verification_code: $verificationCode"
Write-Host ""
Write-Host "Human must open claim_url and post the verification tweet to activate the agent." -ForegroundColor Cyan
Write-Host ""

if ($SaveOn) {
    & (Join-Path $scriptDir "run_moltbook_save_credentials.ps1") -ApiKey $apiKey -AgentName $Name -Target $SaveOn
}
if ($InstallSkill) {
    $t = if ($SaveOn) { $SaveOn } else { "sparky2" }
    & (Join-Path $scriptDir "run_moltbook_install_skill.ps1") -Target $t
}

Write-Host "Claim URL (send to human): $claimUrl" -ForegroundColor Yellow
