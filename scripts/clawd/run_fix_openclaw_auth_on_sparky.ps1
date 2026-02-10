# Deploy and run the auth fix on sparky2: create auth-profiles.json for the main agent so wake can call the model.
# Pass the API key via -AnthropicApiKey or env ANTHROPIC_API_KEY (key is sent via temp file, not command line).
# Usage: .\scripts\clawd\run_fix_openclaw_auth_on_sparky.ps1 -TargetHost sparky2 -AnthropicApiKey $env:ANTHROPIC_API_KEY
#   Or set $env:ANTHROPIC_API_KEY then: .\scripts\clawd\run_fix_openclaw_auth_on_sparky.ps1
param(
    [string]$TargetHost = "sparky2",
    [string]$AnthropicApiKey = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$fixSh = Join-Path $scriptDir "fix_openclaw_auth_on_sparky.sh"
if (-not (Test-Path $fixSh)) {
    Write-Host "ERROR: $fixSh not found." -ForegroundColor Red
    exit 1
}

if (-not $AnthropicApiKey) { $AnthropicApiKey = $env:ANTHROPIC_API_KEY }
if (-not $AnthropicApiKey) {
    Write-Host "ERROR: Set -AnthropicApiKey or env ANTHROPIC_API_KEY (your Anthropic API key, e.g. sk-ant-...)." -ForegroundColor Red
    exit 1
}

$keyFile = [System.IO.Path]::GetTempFileName()
try {
    [System.IO.File]::WriteAllText($keyFile, $AnthropicApiKey.Trim(), [System.Text.Encoding]::UTF8)
    Write-Host "Fixing OpenClaw auth on $TargetHost (creating auth-profiles.json for main agent)..." -ForegroundColor Cyan
    scp -q $keyFile "${TargetHost}:/tmp/moltworld_anthropic_key_secret"
    scp -q $fixSh "${TargetHost}:/tmp/fix_openclaw_auth_on_sparky.sh"
    $out = ssh $TargetHost "sed -i 's/\r$//' /tmp/fix_openclaw_auth_on_sparky.sh 2>/dev/null; chmod +x /tmp/fix_openclaw_auth_on_sparky.sh; ANTHROPIC_KEY_FILE=/tmp/moltworld_anthropic_key_secret bash /tmp/fix_openclaw_auth_on_sparky.sh" 2>&1
    Write-Host $out
    $exitCode = $LASTEXITCODE
    if ($exitCode -eq 0) {
        Write-Host "Auth fixed. Run the math-reply test: .\scripts\testing\test_moltworld_math_reply.ps1 -AdminToken <token>" -ForegroundColor Green
    } else {
        Write-Host "Fix failed (exit $exitCode). Check output above." -ForegroundColor Red
    }
    exit $exitCode
} finally {
    Remove-Item -LiteralPath $keyFile -Force -ErrorAction SilentlyContinue
}
