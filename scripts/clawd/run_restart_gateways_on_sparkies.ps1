# Restart OpenClaw/Clawd gateways on both sparkies (e.g. after SOUL or config change).
# Verifies each gateway is listening on 18789; if not, starts via nohup and re-checks.
# Usage: .\scripts\clawd\run_restart_gateways_on_sparkies.ps1
param()

$envCmd = "source ~/.nvm/nvm.sh 2>/dev/null; source ~/.bashrc 2>/dev/null; nvm use 22 2>/dev/null || nvm use default 2>/dev/null"
$curlCheck = "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 http://127.0.0.1:18789/ 2>/dev/null"

Write-Host "Restarting gateway on sparky1 (Clawd)..." -ForegroundColor Cyan
ssh sparky1 "$envCmd; clawdbot gateway stop 2>/dev/null; sleep 2; systemctl --user restart clawdbot-gateway.service 2>/dev/null || (nohup clawdbot gateway >> ~/.clawdbot/gateway.log 2>&1 &); sleep 2; echo Done"
$s1 = (ssh sparky1 $curlCheck 2>$null)
if ($s1 -ne "200") {
    Write-Host "  sparky1 not up, starting nohup..." -ForegroundColor Yellow
    ssh sparky1 "$envCmd; nohup clawdbot gateway >> ~/.clawdbot/gateway.log 2>&1 & sleep 4; echo Done" | Out-Null
    $s1 = (ssh sparky1 $curlCheck 2>$null)
}
if ($s1 -eq "200") { Write-Host "  sparky1 gateway OK (18789)" -ForegroundColor Green } else { Write-Host "  sparky1 gateway not responding; check ~/.clawdbot/gateway.log" -ForegroundColor Yellow }

Write-Host "Restarting gateway on sparky2 (OpenClaw)..." -ForegroundColor Cyan
$sparky2Fix = "openclaw config set gateway.mode local 2>/dev/null; sed -i 's|node_modules/clawdbot/dist|node_modules/openclaw/dist|g' ~/.config/systemd/user/clawdbot-gateway.service 2>/dev/null; systemctl --user daemon-reload 2>/dev/null"
ssh sparky2 "$envCmd; $sparky2Fix; openclaw gateway stop 2>/dev/null; sleep 2; systemctl --user restart clawdbot-gateway.service 2>/dev/null || (nohup openclaw gateway >> ~/.openclaw/gateway.log 2>&1 &); sleep 2; echo Done"
$s2 = (ssh sparky2 $curlCheck 2>$null)
if ($s2 -ne "200") {
    Write-Host "  sparky2 not up, starting nohup..." -ForegroundColor Yellow
    ssh sparky2 "$envCmd; nohup openclaw gateway >> ~/.openclaw/gateway.log 2>&1 & sleep 4; echo Done" | Out-Null
    $s2 = (ssh sparky2 $curlCheck 2>$null)
}
if ($s2 -eq "200") { Write-Host "  sparky2 gateway OK (18789)" -ForegroundColor Green } else { Write-Host "  sparky2 gateway not responding; check ~/.openclaw/gateway.log" -ForegroundColor Yellow }

Write-Host "Gateways restarted. SOUL and config will apply on next cron or new session." -ForegroundColor Green
