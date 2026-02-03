# Copy jokelord apply script to sparky2 and run it (clone, patch, build, install). Run from dev machine.
# Usage: .\scripts\clawd\run_clawd_apply_jokelord.ps1 -Target sparky2 [-RemotePath /home/malicor/ai2ai/scripts/clawd]
param(
    [string]$Target = "sparky2",
    [string]$RemotePath = "/home/malicor/ai2ai/scripts/clawd"
)

$scriptDir = $PSScriptRoot
$applyScript = Join-Path $scriptDir "clawd_apply_jokelord_on_sparky.sh"
$compatScript = Join-Path $scriptDir "clawd_jokelord_compat_fixes.sh"
$addParamsScript = Join-Path $scriptDir "clawd_add_supported_parameters.py"
$remoteApply = "$RemotePath/clawd_apply_jokelord_on_sparky.sh"
$remoteCompat = "$RemotePath/clawd_jokelord_compat_fixes.sh"
$remoteAddParams = "$RemotePath/clawd_add_supported_parameters.py"

if (-not (Test-Path $applyScript)) {
    Write-Host "Missing $applyScript" -ForegroundColor Red
    exit 1
}

Write-Host "Copying scripts to $Target and running jokelord patch (clone, patch, build, install)..." -ForegroundColor Cyan
ssh $Target "mkdir -p $RemotePath" 2>$null
scp -q $applyScript "${Target}:$remoteApply"
if (Test-Path $compatScript) { scp -q $compatScript "${Target}:$remoteCompat" }
if (Test-Path $addParamsScript) { scp -q $addParamsScript "${Target}:$remoteAddParams" }
ssh $Target "sed -i 's/\r$//' $remoteApply $remoteCompat 2>/dev/null; chmod +x $remoteApply $remoteCompat" 2>&1 | ForEach-Object { Write-Host $_ }
ssh $Target "bash -lc '$remoteApply'" 2>&1 | ForEach-Object { Write-Host $_ }
Write-Host "`nNext on sparky2: add supportedParameters, then restart gateway:" -ForegroundColor Green
Write-Host "  python3 $remoteAddParams" -ForegroundColor Cyan
Write-Host "  clawdbot gateway stop; sleep 2; nohup clawdbot gateway >> ~/.clawdbot/gateway.log 2>&1 &" -ForegroundColor Cyan
Write-Host "See docs/external-tools/clawd/CLAWD_JOKELORD_STEPS.md for full steps." -ForegroundColor Gray
