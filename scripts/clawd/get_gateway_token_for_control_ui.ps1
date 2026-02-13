# Get the gateway auth token from sparky1 and/or sparky2 so you can paste it into OpenClaw Control UI.
# The Control UI needs this token to connect to the gateway (otherwise: "unauthorized: gateway token missing").
#
# Usage: .\scripts\clawd\get_gateway_token_for_control_ui.ps1
#        .\scripts\clawd\get_gateway_token_for_control_ui.ps1 -Host sparky1
param(
    [string[]]$Hosts = @("sparky1", "sparky2")
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$getTokenSh = @'
CONFIG="$HOME/.openclaw/openclaw.json"
[[ -f "$CONFIG" ]] || CONFIG="$HOME/.clawdbot/clawdbot.json"
if [[ ! -f "$CONFIG" ]]; then
  echo "NO_CONFIG"
  exit 0
fi
python3 -c "
import json, sys
try:
    with open('$CONFIG') as f:
        d = json.load(f)
    gw = d.get('gateway') or {}
    auth = gw.get('auth') or {}
    tok = auth.get('token') or gw.get('token') or ''
    print(tok)
except Exception as e:
    print('', file=sys.stderr)
    sys.exit(1)
"
'@

Write-Host "=== Gateway token for OpenClaw Control UI ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Control UI shows 'gateway token missing' when it has no token to authenticate to the gateway." -ForegroundColor Gray
Write-Host "Do this:" -ForegroundColor Yellow
Write-Host "  1. Get the token from the host you want to chat with (below)." -ForegroundColor White
Write-Host "  2. In Control UI: Settings (or Config) -> paste the token where it asks for gateway token." -ForegroundColor White
Write-Host "  3. Set the gateway URL to the host you're connecting to (see below)." -ForegroundColor White
Write-Host ""

foreach ($h in $Hosts) {
    Write-Host "--- $h ---" -ForegroundColor Cyan
    $tok = $getTokenSh | ssh -o BatchMode=yes -o ConnectTimeout=10 $h "bash -s" 2>$null
    if ($tok -and $tok -ne "NO_CONFIG") {
        Write-Host "Token (paste into Control UI settings):" -ForegroundColor Yellow
        Write-Host $tok -ForegroundColor White
        Write-Host "Gateway URL: http://${h}:18789" -ForegroundColor Gray
        Write-Host "  (If Control UI runs on your PC, ensure you can reach ${h}:18789, e.g. VPN or SSH port forward: ssh -L 18789:127.0.0.1:18789 $h)" -ForegroundColor Gray
    } else {
        Write-Host "  Could not read token (no config or ssh failed)" -ForegroundColor Yellow
    }
    Write-Host ""
}

Write-Host "To chat with sparky1: use sparky1's token and URL http://sparky1:18789 (or your port-forward)." -ForegroundColor Gray
Write-Host "To chat with sparky2: use sparky2's token and URL http://sparky2:18789." -ForegroundColor Gray
Write-Host "If Control UI runs on the same machine as the gateway (e.g. you SSH to sparky1 and open Control there), use http://127.0.0.1:18789 and the token from that host." -ForegroundColor Gray
