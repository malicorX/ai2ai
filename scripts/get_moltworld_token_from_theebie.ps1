# Get MoltWorld agent token from the theebie server (reads agent_tokens.json on the host).
# The backend stores tokens in AGENT_TOKENS_PATH; the compose volume puts it at backend_data/agent_tokens.json on the host.
# Usage: .\scripts\get_moltworld_token_from_theebie.ps1 -AgentId MalicorSparky2 [-TheebieHost root@84.38.65.246] [-WriteEnvAndPush]
#   -WriteEnvAndPush: write deployment/sparky2_moltworld.env and scp to sparky2 as ~/.moltworld.env
param(
    [Parameter(Mandatory=$false)]
    [string]$AgentId = "MalicorSparky2",
    [string]$TheebieHost = "root@84.38.65.246",
    [switch]$WriteEnvAndPush = $false
)

$ErrorActionPreference = "Stop"
$projectRoot = (Get-Item $PSScriptRoot).Parent.FullName

# On theebie, compose is at /opt/ai_ai2ai, volume is backend_data -> /app/data
$remotePath = "/opt/ai_ai2ai/backend_data/agent_tokens.json"

Write-Host "Reading $remotePath on $TheebieHost for agent_id=$AgentId..." -ForegroundColor Cyan
$json = ssh $TheebieHost "cat $remotePath 2>/dev/null || echo '{}'"
if (-not $json -or $json -eq "{}") {
    Write-Host "File empty or missing on theebie. No tokens issued yet." -ForegroundColor Red
    Write-Host "  (1) On theebie: add ADMIN_TOKEN to backend env, restart backend." -ForegroundColor Yellow
    Write-Host "  (2) On theebie: run scripts/theebie_issue_tokens.sh (with ADMIN_TOKEN set) to create tokens." -ForegroundColor Yellow
    Write-Host "  (3) Then re-run this script to fetch and push to sparky2." -ForegroundColor Yellow
    Write-Host "See docs/MOLTWORLD_MANUAL_SETUP_SPARKIES.md" -ForegroundColor Cyan
    exit 1
}

$tokenMap = $json | ConvertFrom-Json
# Format is { "token_hex": "agent_id", ... }; we need token where value eq AgentId
$token = $null
foreach ($p in $tokenMap.PSObject.Properties) {
    if ($p.Value -eq $AgentId) {
        $token = $p.Name
        break
    }
}
if (-not $token) {
    Write-Host "No token found for agent_id=$AgentId. Issued tokens: $($tokenMap.PSObject.Properties | ForEach-Object { $_.Value } | Join-Path -Separator ', ')." -ForegroundColor Red
    exit 1
}

Write-Host "Token for $AgentId : $token" -ForegroundColor Green

if ($WriteEnvAndPush) {
    $baseUrl = "https://www.theebie.de"
    $displayName = $AgentId
    $envPath = Join-Path $projectRoot "deployment\${AgentId.ToLower()}_moltworld.env"
    if ($AgentId -eq "MalicorSparky2") { $envPath = Join-Path $projectRoot "deployment\sparky2_moltworld.env" }
    if ($AgentId -eq "Sparky1Agent") { $envPath = Join-Path $projectRoot "deployment\sparky1_moltworld.env" }
    # Use export VAR=value and LF only (no BOM) so bash can source the file
    $content = "export WORLD_API_BASE=$baseUrl`nexport AGENT_ID=$AgentId`nexport DISPLAY_NAME=$displayName`nexport WORLD_AGENT_TOKEN=$token`n"
    [System.IO.File]::WriteAllText($envPath, $content, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Wrote $envPath" -ForegroundColor Cyan
    $remote = if ($AgentId -eq "MalicorSparky2") { "sparky2" } elseif ($AgentId -eq "Sparky1Agent") { "sparky1" } else { $null }
    if ($remote) {
        scp $envPath "${remote}:~/.moltworld.env"
        Write-Host "Copied to ${remote}:~/.moltworld.env" -ForegroundColor Green
        Write-Host "On $remote run: set -a; . ~/.moltworld.env; set +a  (then start the agent)" -ForegroundColor Yellow
    }
}
