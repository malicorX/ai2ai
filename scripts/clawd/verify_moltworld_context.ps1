# Verify MoltWorld context state on sparkies (file + HOME).
# Usage: .\scripts\clawd\verify_moltworld_context.ps1 [-Hosts sparky1,sparky2]
param([string[]]$Hosts = @("sparky1", "sparky2"))

Write-Host "MoltWorld context state (set_moltworld_context.ps1 -Off writes 'off'):" -ForegroundColor Cyan
foreach ($h in $Hosts) {
    Write-Host "`n--- $h ---" -ForegroundColor Yellow
    ssh -o BatchMode=yes -o ConnectTimeout=10 $h "echo 'File:'; cat ~/.moltworld_context 2>/dev/null || echo '(no file)'; echo 'HOME='; echo \$HOME" 2>$null
}
