# Register Moltbook agent, save credentials on sparky2, install skill, and print claim URL. Run from dev machine.
# Usage: .\scripts\moltbook\run_moltbook_do_all.ps1 [-Target sparky2] [-Name Sparky2]
param(
    [string]$Target = "sparky2",
    [string]$Name = "MalicorSparky2",
    [string]$Description = "Clawd agent on sparky2; uses Ollama. Screens tasks, reports, and participates on Moltbook."
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot

Write-Host "Moltbook setup: register -> save credentials on $Target -> install skill" -ForegroundColor Cyan
& (Join-Path $scriptDir "run_moltbook_register.ps1") -Name $Name -Description $Description -SaveOn $Target -InstallSkill
Write-Host ""
Write-Host "Next: Human must open the claim URL above and post the verification tweet." -ForegroundColor Green
Write-Host 'Then: On sparky2 use API with saved key, e.g. curl -s https://www.moltbook.com/api/v1/feed?sort=new -H "Authorization: Bearer $(jq -r .api_key ~/.config/moltbook/credentials.json)"'
