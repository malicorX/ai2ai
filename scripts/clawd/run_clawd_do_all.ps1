# Patch Clawd config (tools.profile=full, browser.executablePath, compat.openaiCompletionsTools, optional primary model) on sparky and restart gateway.
# Run from dev machine. Usage: .\scripts\clawd\run_clawd_do_all.ps1 [-Target sparky2] [-PrimaryModel ollama/qwen2.5-coder:32b] [-RemotePath /home/malicor/ai_ai2ai/scripts/clawd]
param(
    [string]$Target = "sparky2",
    [string]$PrimaryModel = "",
    [string]$RemotePath = "/home/malicor/ai_ai2ai/scripts/clawd"
)

$ErrorActionPreference = "Continue"
$scriptDir = $PSScriptRoot
$patchScript = Join-Path $scriptDir "clawd_patch_config_remote.py"
$remotePatch = "$RemotePath/clawd_patch_config_remote.py"

if (-not (Test-Path $patchScript)) {
    Write-Host "Missing $patchScript" -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Clawd do-all on $Target ===" -ForegroundColor Cyan
ssh $Target "mkdir -p $RemotePath" 2>$null
scp -q $patchScript "${Target}:$remotePatch"

$patchCmd = "python3 $remotePatch"
if ($PrimaryModel) {
    $patchCmd = "python3 $remotePatch $PrimaryModel"
    Write-Host "Primary model: $PrimaryModel" -ForegroundColor Gray
}
ssh $Target $patchCmd 2>&1 | ForEach-Object { Write-Host $_ }

Write-Host "Restarting gateway on $Target..." -ForegroundColor Yellow
ssh $Target "bash ~/bin/start_clawd_gateway.sh" 2>&1 | ForEach-Object { Write-Host $_ }

Write-Host "`n[OK] Config patched + gateway restarted on $Target" -ForegroundColor Green
Write-Host "Chat: http://127.0.0.1:18789/ (tunnel to $Target) or clawdbot tui on $Target" -ForegroundColor Cyan
