# Fix Clawdbot main agent Ollama auth on sparky1 so narrator/hook lanes can run (no "No API key for provider ollama").
# Usage: .\scripts\clawd\run_fix_clawdbot_ollama_on_sparky.ps1 [-TargetHost sparky1]
param([string]$TargetHost = "sparky1")

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$sh = Join-Path $scriptDir "fix_clawdbot_ollama_on_sparky.sh"
Write-Host "Fixing Clawdbot Ollama auth on $TargetHost..." -ForegroundColor Cyan
scp -q $sh "${TargetHost}:/tmp/fix_clawdbot_ollama_on_sparky.sh"
$out = ssh $TargetHost "sed -i 's/\r$//' /tmp/fix_clawdbot_ollama_on_sparky.sh; chmod +x /tmp/fix_clawdbot_ollama_on_sparky.sh; bash /tmp/fix_clawdbot_ollama_on_sparky.sh" 2>&1
Write-Host $out
if ($out -match "AUTH_UPDATED") { Write-Host "  $TargetHost OK" -ForegroundColor Green } else { Write-Host "  Check output above." -ForegroundColor Yellow }
Write-Host "Restart gateway: .\scripts\clawd\run_restart_gateways_on_sparkies.ps1" -ForegroundColor Gray
