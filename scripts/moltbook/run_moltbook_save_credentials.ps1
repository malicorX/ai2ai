# Save Moltbook API key and agent name to ~/.config/moltbook/credentials.json on sparky. Run from dev machine.
# Usage: .\scripts\moltbook\run_moltbook_save_credentials.ps1 -ApiKey "moltbook_xxx" -AgentName "MalicorSparky2" [-Target sparky2]
param(
    [Parameter(Mandatory = $true)]
    [string]$ApiKey,
    [Parameter(Mandatory = $true)]
    [string]$AgentName,
    [string]$Target = "sparky2"
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$remoteScript = Join-Path $scriptDir "moltbook_save_credentials_on_sparky.sh"
$remotePath = "/home/malicor/ai_ai2ai/scripts/moltbook/moltbook_save_credentials_on_sparky.sh"

if (-not (Test-Path $remoteScript)) {
    Write-Host "Missing $remoteScript" -ForegroundColor Red
    exit 1
}

# Escape for SSH: single-quote the values so shell does not expand them
$safeKey = $ApiKey.Replace("'", "'\"'\"'")
$safeName = $AgentName.Replace("'", "'\"'\"'")
ssh $Target "mkdir -p /home/malicor/ai_ai2ai/scripts/moltbook" 2>$null
scp -q $remoteScript "${Target}:$remotePath"
ssh $Target "sed -i 's/\r$//' $remotePath 2>/dev/null; chmod +x $remotePath; MOLTBOOK_API_KEY='$safeKey' MOLTBOOK_AGENT_NAME='$safeName' bash $remotePath"
Write-Host "Credentials saved on $Target at ~/.config/moltbook/credentials.json" -ForegroundColor Green
