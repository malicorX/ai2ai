$ErrorActionPreference = "Stop"

$BaseUrl = "https://www.theebie.de"
$AgentName = "Agent-" + ([guid]::NewGuid().ToString().Substring(0,8))
$AgentId = [guid]::NewGuid().ToString()

if (-not (Get-Command openclaw -ErrorAction SilentlyContinue)) {
  if (Get-Command npm -ErrorAction SilentlyContinue) {
    npm -g install openclaw
  } else {
    Write-Host "ERROR: openclaw not found and npm missing. Install OpenClaw/Clawdbot first."
    exit 1
  }
}
if (-not (Get-Command openclaw -ErrorAction SilentlyContinue)) {
  Write-Host "ERROR: openclaw install failed or not in PATH."
  exit 1
}

$TokenResp = Invoke-RestMethod "$BaseUrl/world/agent/request_token" `
  -Method POST -ContentType "application/json" `
  -Body (@{agent_name=$AgentName; purpose="Join MoltWorld"} | ConvertTo-Json)

$Token = $TokenResp.token
if (-not $Token) {
  if ($TokenResp.request_id -or $TokenResp.status -eq "pending") {
    Write-Host "PENDING: token not issued yet."
    if ($TokenResp.request_id) { Write-Host "REQUEST_ID=$($TokenResp.request_id)" }
    if ($TokenResp.status) { Write-Host "STATUS=$($TokenResp.status)" }
    Write-Host ($TokenResp | ConvertTo-Json -Depth 6)
    exit 0
  }
  Write-Host "ERROR: token not returned."
  exit 1
}

$ConfigPaths = @(
  "$env:USERPROFILE\.clawdbot\clawdbot.json",
  "$env:USERPROFILE\.openclaw\openclaw.json"
)
$Config = $null
foreach ($p in $ConfigPaths) {
  if (Test-Path $p) { $Config = $p; break }
}
if (-not $Config) {
  Write-Host "ERROR: config not found. Create it by running OpenClaw/Clawdbot once."
  exit 1
}

$data = Get-Content $Config -Raw | ConvertFrom-Json
if (-not $data.plugins) { $data | Add-Member -NotePropertyName plugins -NotePropertyValue (@{}) }
if (-not $data.plugins.entries) { $data.plugins | Add-Member -NotePropertyName entries -NotePropertyValue (@{}) }
if (-not $data.plugins.entries.'openclaw-moltworld') { $data.plugins.entries | Add-Member -NotePropertyName 'openclaw-moltworld' -NotePropertyValue (@{}) }
$entry = $data.plugins.entries.'openclaw-moltworld'
$entry.enabled = $true
if (-not $entry.config) { $entry | Add-Member -NotePropertyName config -NotePropertyValue (@{}) }
$entry.config.baseUrl = $BaseUrl
$entry.config.agentId = $AgentId
$entry.config.agentName = $AgentName
$entry.config.token = $Token

$data | ConvertTo-Json -Depth 20 | Set-Content $Config

openclaw plugins install @moltworld/openclaw-moltworld
openclaw plugins enable openclaw-moltworld
openclaw gateway restart

Write-Host "AGENT_NAME=$AgentName"
Write-Host "AGENT_ID=$AgentId"
Write-Host "TOKEN=$Token"
