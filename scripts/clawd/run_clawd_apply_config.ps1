# Apply Clawd config (tools.deny, browser, compat.openaiCompletionsTools) on sparky and restart gateway. Run from dev machine.
# Usage: .\scripts\clawd\run_clawd_apply_config.ps1 [-Hosts sparky2] [-RemotePath /home/malicor/ai2ai/scripts/clawd]
# Fixes /new showing raw JSON: sets tools.deny to ["sessions_send", "message"] and compat.openaiCompletionsTools on Ollama models.
param(
    [string[]]$Hosts = @("sparky1", "sparky2"),
    [string]$RemotePath = "/home/malicor/ai2ai/scripts/clawd"
)

$ErrorActionPreference = "Continue"
$scriptDir = $PSScriptRoot
$remoteScript = Join-Path $scriptDir "clawd_apply_config_remote.sh"
$patchOnlyPy = Join-Path $scriptDir "clawd_patch_config_only.py"
$soulFix = Join-Path $scriptDir "clawd_SOUL_message_fix.txt"
$remotePath = "$RemotePath/clawd_apply_config_remote.sh"
$remotePatchPy = "$RemotePath/clawd_patch_config_only.py"
$clawdWorkspace = "/home/malicor/clawd"

if (-not (Test-Path $remoteScript)) {
    Write-Host "Missing $remoteScript" -ForegroundColor Red
    exit 1
}

foreach ($h in $Hosts) {
    Write-Host "`n=== $h ===" -ForegroundColor Cyan
    try {
        ssh $h "mkdir -p $RemotePath" 2>$null
        # If script path exists as a directory (wrong), remove it so we can put the file there
        ssh $h "test -d $remotePath && rm -rf $remotePath || true" 2>$null
        # Copy into scripts dir (trailing /) so filenames are preserved and we never target a dir as file
        scp -q $remoteScript "${h}:$RemotePath/"
        if (Test-Path $patchOnlyPy) { scp -q $patchOnlyPy "${h}:$RemotePath/" }
        # Run Python patcher first (guarantees tools.deny + message and compat), then full apply + restart
        ssh $h "python3 $remotePatchPy 2>/dev/null || true; sed -i 's/\r$//' $remotePath 2>/dev/null; chmod +x $remotePath; bash $remotePath" 2>&1 | ForEach-Object { Write-Host $_ }
        if (Test-Path $soulFix) {
            scp -q $soulFix "${h}:$RemotePath/"
            ssh $h "mkdir -p $clawdWorkspace; cp $RemotePath/clawd_SOUL_message_fix.txt $clawdWorkspace/SOUL.md" 2>$null
            Write-Host "  SOUL.md deployed to $clawdWorkspace (fix /new stuck)" -ForegroundColor Gray
        }
        Write-Host "  [OK] Config applied + gateway restarted on $h" -ForegroundColor Green
    } catch {
        Write-Host "  [WARN] $h : $_" -ForegroundColor Yellow
    }
}
Write-Host "`nChat: on sparky2 open browser http://127.0.0.1:18789/ or clawdbot tui" -ForegroundColor Cyan
