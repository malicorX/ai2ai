# Check OpenClaw auth on the replier sparky (default: sparky2). We use Ollama locally; this reports if auth-profiles.json has ollama/anthropic/openai.
# Usage: .\scripts\clawd\run_moltworld_check_auth_on_sparky.ps1
#   Or:  .\scripts\clawd\run_moltworld_check_auth_on_sparky.ps1 -TargetHost sparky2
param(
    [string]$TargetHost = "sparky2"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$checkSh = Join-Path $scriptDir "check_openclaw_auth_on_sparky.sh"
if (-not (Test-Path $checkSh)) {
    Write-Host "ERROR: $checkSh not found." -ForegroundColor Red
    exit 1
}

Write-Host "Checking OpenClaw auth on $TargetHost (agent that serves wake)..." -ForegroundColor Cyan
scp -q $checkSh "${TargetHost}:/tmp/check_openclaw_auth_on_sparky.sh"
$out = ssh $TargetHost "sed -i 's/\r$//' /tmp/check_openclaw_auth_on_sparky.sh 2>/dev/null; chmod +x /tmp/check_openclaw_auth_on_sparky.sh; bash /tmp/check_openclaw_auth_on_sparky.sh" 2>&1
Write-Host $out
if ($LASTEXITCODE -eq 0) {
    Write-Host "Auth OK. Re-run the math-reply test." -ForegroundColor Green
} else {
    Write-Host "Apply the Fix above on $TargetHost, then restart the gateway and re-run the test." -ForegroundColor Yellow
}
exit $LASTEXITCODE
