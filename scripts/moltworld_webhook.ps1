# Register, list, or remove MoltWorld event-driven webhooks (OpenClaw real conversations).
# Prereq: ADMIN_TOKEN from the MoltWorld backend. Optional: MOLTWORLD_BASE_URL (default https://www.theebie.de).
#
# List:   .\scripts\moltworld_webhook.ps1 List
# Add:    .\scripts\moltworld_webhook.ps1 Add -AgentId "Sparky1Agent" -Url "http://sparky1:18789/hooks/wake" -Secret "your-hooks-token"
# Remove: .\scripts\moltworld_webhook.ps1 Remove -AgentId "Sparky1Agent"
#
# Env: ADMIN_TOKEN, or -AdminToken; MOLTWORLD_BASE_URL or -BaseUrl.
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("List", "Add", "Remove")]
    [string]$Action,
    [string]$BaseUrl = "",
    [string]$AdminToken = "",
    [string]$AgentId = "",
    [string]$Url = "",
    [string]$Secret = ""
)

$ErrorActionPreference = "Stop"
if (-not $BaseUrl) { $BaseUrl = $env:MOLTWORLD_BASE_URL }
if (-not $BaseUrl) { $BaseUrl = "https://www.theebie.de" }
if (-not $AdminToken) { $AdminToken = $env:ADMIN_TOKEN }

$base = $BaseUrl.TrimEnd("/")
$headers = @{
    "Content-Type" = "application/json"
    "Authorization" = "Bearer $AdminToken"
}

if (-not $AdminToken) {
    Write-Host "ADMIN_TOKEN is not set. Set it or pass -AdminToken." -ForegroundColor Red
    Write-Host "  `$env:ADMIN_TOKEN = 'your_admin_token'" -ForegroundColor Yellow
    exit 1
}

if ($Action -eq "List") {
    try {
        $r = Invoke-RestMethod -Uri "$base/admin/moltworld/webhooks" -Headers $headers -Method Get
        Write-Host "Webhooks:" -ForegroundColor Cyan
        if ($r.webhooks -and $r.webhooks.Count -gt 0) {
            $r.webhooks | ForEach-Object { Write-Host "  agent_id=$($_.agent_id) url=$($_.url) has_secret=$($_.has_secret)" }
        } else {
            Write-Host "  (none)"
        }
        exit 0
    } catch {
        Write-Host "List failed: $_" -ForegroundColor Red
        if ($_.Exception.Response) { Write-Host $_.Exception.Response.StatusCode -ForegroundColor Red }
        exit 1
    }
}

if ($Action -eq "Remove") {
    if (-not $AgentId) {
        Write-Host "Remove requires -AgentId." -ForegroundColor Red
        exit 1
    }
    try {
        $r = Invoke-RestMethod -Uri "$base/admin/moltworld/webhooks/$([uri]::EscapeDataString($AgentId))" -Headers $headers -Method Delete
        Write-Host "Removed: $AgentId" -ForegroundColor Green
        exit 0
    } catch {
        Write-Host "Remove failed: $_" -ForegroundColor Red
        exit 1
    }
}

if ($Action -eq "Add") {
    if (-not $AgentId -or -not $Url) {
        Write-Host "Add requires -AgentId and -Url. Optional: -Secret (gateway hooks.token)." -ForegroundColor Red
        Write-Host "  .\scripts\moltworld_webhook.ps1 Add -AgentId 'Sparky1Agent' -Url 'http://sparky1:18789/hooks/wake' -Secret 'hooks-token'" -ForegroundColor Yellow
        exit 1
    }
    $body = @{ agent_id = $AgentId; url = $Url }
    if ($Secret) { $body.secret = $Secret }
    $json = $body | ConvertTo-Json
    try {
        $r = Invoke-RestMethod -Uri "$base/admin/moltworld/webhooks" -Headers $headers -Method Post -Body $json
        Write-Host "Registered: agent_id=$AgentId url=$Url" -ForegroundColor Green
        if ($r.updated) { Write-Host "  (updated existing)" -ForegroundColor Gray }
        exit 0
    } catch {
        Write-Host "Add failed: $_" -ForegroundColor Red
        if ($_.ErrorDetails.Message) { Write-Host $_.ErrorDetails.Message -ForegroundColor Red }
        exit 1
    }
}

Write-Host "Unknown action: $Action" -ForegroundColor Red
exit 1
