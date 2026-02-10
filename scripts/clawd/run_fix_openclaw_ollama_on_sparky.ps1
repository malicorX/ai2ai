# Ensure OpenClaw on sparky2 (replier) uses Ollama locally. No API key required. Run this when the test -Debug shows "No API key for provider anthropic" or when wake returns 200 but no reply.
# Usage: .\scripts\clawd\run_fix_openclaw_ollama_on_sparky.ps1 [-TargetHost sparky2]
param(
    [string]$TargetHost = "sparky2"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$fixSh = Join-Path $scriptDir "fix_openclaw_ollama_on_sparky.sh"
if (-not (Test-Path $fixSh)) {
    Write-Host "ERROR: $fixSh not found." -ForegroundColor Red
    exit 1
}

Write-Host "Fixing OpenClaw to use Ollama locally on $TargetHost (no cloud API key)..." -ForegroundColor Cyan
scp -q $fixSh "${TargetHost}:/tmp/fix_openclaw_ollama_on_sparky.sh"
$out = ssh $TargetHost "sed -i 's/\r$//' /tmp/fix_openclaw_ollama_on_sparky.sh 2>/dev/null; chmod +x /tmp/fix_openclaw_ollama_on_sparky.sh; bash /tmp/fix_openclaw_ollama_on_sparky.sh" 2>&1
Write-Host $out
if ($LASTEXITCODE -eq 0) {
    Write-Host "Done. Run the test: .\scripts\testing\test_moltworld_math_reply.ps1 -AdminToken <token> -Debug" -ForegroundColor Green
} else {
    Write-Host "Fix failed. Check output above." -ForegroundColor Red
}
exit $LASTEXITCODE
