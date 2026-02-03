# Remove Chromium from sparky (snap and/or apt). Use after switching to Google Chrome .deb for Clawd browser tool.
# Usage: .\scripts\clawd\run_remove_chromium_on_sparky.ps1 [-Target sparky2]
param(
    [string]$Target = "sparky2"
)

$ErrorActionPreference = "Continue"
Write-Host "`n=== Removing Chromium on $Target ===" -ForegroundColor Cyan
ssh $Target "sudo snap remove chromium 2>/dev/null; sudo apt-get remove -y chromium-browser 2>/dev/null; echo Done"
Write-Host "`nClawd uses Google Chrome (.deb) for the browser tool; Chromium is no longer needed." -ForegroundColor Green
