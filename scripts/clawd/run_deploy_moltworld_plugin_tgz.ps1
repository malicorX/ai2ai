# Deploy MoltWorld plugin from a local .tgz (e.g. after changing tool descriptions) to sparkies.
# Keeps existing plugin config and ~/.moltworld.env; only replaces the plugin code.
# Usage: .\scripts\clawd\run_deploy_moltworld_plugin_tgz.ps1 [-TgzPath path] [-Hosts sparky1,sparky2]
param(
    [string]$TgzPath = "",
    [string[]]$Hosts = @("sparky1", "sparky2")
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
if (-not $TgzPath) {
    $TgzPath = Join-Path $repoRoot "extensions\moltworld\moltworld-openclaw-moltworld-0.3.11.tgz"
}
if (-not (Test-Path $TgzPath)) {
    Write-Host "Tgz not found: $TgzPath. Run: cd extensions/moltworld; npm run build; npm pack" -ForegroundColor Red
    exit 1
}
$tgzName = [System.IO.Path]::GetFileName($TgzPath)

Write-Host "Deploying MoltWorld plugin from $tgzName to $($Hosts -join ', ')..." -ForegroundColor Cyan
foreach ($h in $Hosts) {
    Write-Host "  $h..." -ForegroundColor Gray
    scp -q $TgzPath "${h}:/tmp/$tgzName"
    $claw = "openclaw"
    # Extract tgz (npm pack creates root "package/") into extensions/openclaw-moltworld
    $out = ssh $h "set -e; EXT=~/.$claw/extensions/openclaw-moltworld; rm -rf `$EXT; mkdir -p `$EXT; (cd /tmp && tar -xzf $tgzName); cp -a /tmp/package/* `$EXT/; rm -rf /tmp/package; echo 'Plugin files updated in '`$EXT; ls `$EXT"
    Write-Host $out
    if ($LASTEXITCODE -ne 0) { Write-Host "  $h : deploy failed" -ForegroundColor Yellow } else { Write-Host "  $h : plugin updated" -ForegroundColor Green }
}
Write-Host "On sparky2, write plugin token so chat_say can auth: .\scripts\clawd\run_write_plugin_token_on_sparky.ps1" -ForegroundColor Gray
Write-Host "Restart gateways to load new plugin: .\scripts\clawd\run_restart_gateways_on_sparkies.ps1" -ForegroundColor Cyan
