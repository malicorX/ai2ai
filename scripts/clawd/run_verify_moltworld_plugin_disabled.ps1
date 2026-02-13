# Verify MoltWorld plugin is disabled on sparkies (run check_tools_config.py on each host).
# Usage: .\scripts\clawd\run_verify_moltworld_plugin_disabled.ps1 [-Hosts sparky1,sparky2]
param(
    [string[]]$Hosts = @("sparky1", "sparky2")
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyPath = Join-Path $scriptDir "check_tools_config.py"

foreach ($h in $Hosts) {
    Write-Host "--- $h ---" -ForegroundColor Cyan
    scp -q $pyPath "${h}:/tmp/check_tools_config.py" 2>$null
    $out = ssh -o BatchMode=yes -o ConnectTimeout=10 $h "python3 /tmp/check_tools_config.py" 2>&1
    Write-Host $out
    if ($out -match "openclaw-moltworld\.enabled:\s*True") {
        Write-Host "  FAIL: Plugin still enabled on $h" -ForegroundColor Red
    } elseif ($out -match "openclaw-moltworld\.enabled:\s*(False|None)") {
        Write-Host "  OK: Plugin disabled or removed on $h" -ForegroundColor Green
    }
    Write-Host ""
}
