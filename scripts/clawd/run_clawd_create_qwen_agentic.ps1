# Create qwen-agentic Ollama model on sparky (Modelfile + ollama create). Run from dev machine.
# Usage: .\scripts\clawd\run_clawd_create_qwen_agentic.ps1 -Target sparky2 [-RemotePath /home/malicor/ai2ai/scripts/clawd]
param(
    [string]$Target = "sparky2",
    [string]$RemotePath = "/home/malicor/ai2ai/scripts/clawd"
)

$scriptDir = $PSScriptRoot
$remoteScript = Join-Path $scriptDir "clawd_create_qwen_agentic_on_sparky.sh"
$remotePathScript = "$RemotePath/clawd_create_qwen_agentic_on_sparky.sh"

if (-not (Test-Path $remoteScript)) {
    Write-Host "Missing $remoteScript" -ForegroundColor Red
    exit 1
}

Write-Host "Copying script to $Target and running (pull + create qwen-agentic)..." -ForegroundColor Cyan
ssh $Target "mkdir -p $RemotePath" 2>$null
scp -q $remoteScript "${Target}:$remotePathScript"
ssh $Target "sed -i 's/\r$//' $remotePathScript 2>/dev/null; chmod +x $remotePathScript; bash $remotePathScript" 2>&1 | ForEach-Object { Write-Host $_ }
Write-Host "Done. On $Target set Clawd primary to ollama/qwen-agentic:latest" -ForegroundColor Green
