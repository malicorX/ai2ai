param(
  [string]$BaseUrl = "http://sparky1:8000",
  [string]$RunId = "latest",
  [string]$OutPath = "M:\Data\Projects\ai_ai2ai\result_viewer.html"
)

$ErrorActionPreference = "Stop"

function Get-Json($url) {
  return Invoke-RestMethod -Uri $url -Method GET -TimeoutSec 30
}

if ($RunId -eq "latest") {
  $runs = Get-Json "$BaseUrl/runs?limit=1"
  if (-not $runs.runs -or $runs.runs.Count -lt 1) {
    throw "No archived runs found at $BaseUrl/runs"
  }
  $RunId = $runs.runs[0].run_id
}

$viewerUrl = "$BaseUrl/runs/$RunId/viewer"
Write-Host "Downloading viewer for run $RunId ..."
Invoke-WebRequest -Uri $viewerUrl -OutFile $OutPath -TimeoutSec 60
Write-Host "Wrote: $OutPath"

