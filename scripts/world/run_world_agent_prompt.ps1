param(
    [string]$Target = "sparky2",
    [string]$WorkspacePath = "/home/malicor/clawd"
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)

$promptFile = Join-Path $repoRoot "docs\world\MALICORSPARKY2_PROMPT.md"
$apiFile = Join-Path $repoRoot "docs\world\WORLD_AGENT_API.md"
$schemaFile = Join-Path $repoRoot "docs\world\OPENCLAW_TOOL_SCHEMA.json"

if (-not (Test-Path $promptFile)) { Write-Host "Missing $promptFile" -ForegroundColor Red; exit 1 }
if (-not (Test-Path $apiFile)) { Write-Host "Missing $apiFile" -ForegroundColor Red; exit 1 }
if (-not (Test-Path $schemaFile)) { Write-Host "Missing $schemaFile" -ForegroundColor Red; exit 1 }

ssh $Target "mkdir -p '$WorkspacePath/world'" 2>$null
scp -q $promptFile "${Target}:$WorkspacePath/SOUL.md"
scp -q $apiFile "${Target}:$WorkspacePath/world/WORLD_AGENT_API.md"
scp -q $schemaFile "${Target}:$WorkspacePath/world/OPENCLAW_TOOL_SCHEMA.json"

Write-Host ("World prompt + docs copied to {0}:{1}" -f $Target, $WorkspacePath) -ForegroundColor Green
