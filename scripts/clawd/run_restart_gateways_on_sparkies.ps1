# Restart OpenClaw gateways on both sparkies (e.g. after SOUL or config change).
# Usage: .\scripts\clawd\run_restart_gateways_on_sparkies.ps1
param()

$envCmd = "source ~/.nvm/nvm.sh 2>/dev/null; source ~/.bashrc 2>/dev/null; nvm use 22 2>/dev/null || nvm use default 2>/dev/null"
$curlCheck = "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 http://127.0.0.1:18789/ 2>/dev/null"
# When ~/.moltworld_context is "off", export MOLTWORLD_CONTEXT=off so the plugin returns direct-chat mode (no board/TASK).
$contextEnv = 'ctx=$(cat ~/.moltworld_context 2>/dev/null | tr -d "\r\n" | tr "[:upper:]" "[:lower:]"); if [ "$ctx" = "off" ]; then export MOLTWORLD_CONTEXT=off; fi'
$sparkyStart = "source ~/.moltworld.env 2>/dev/null; export WORLD_AGENT_TOKEN 2>/dev/null; $contextEnv; $envCmd; nohup openclaw gateway >> ~/.openclaw/gateway.log 2>&1 & sleep 2"

Write-Host "Restarting gateway on sparky1 (OpenClaw)..." -ForegroundColor Cyan
ssh sparky1 "$envCmd; openclaw gateway stop 2>/dev/null; systemctl --user stop clawdbot-gateway.service 2>/dev/null; systemctl --user stop openclaw-gateway.service 2>/dev/null; sleep 2; fuser -k 18789/tcp 2>/dev/null; sleep 2; $sparkyStart; sleep 2; echo Done"
$s1 = (ssh sparky1 $curlCheck 2>$null)
if ($s1 -ne "200") {
    Write-Host "  sparky1 not up, starting nohup..." -ForegroundColor Yellow
    ssh sparky1 "source ~/.moltworld.env 2>/dev/null; $envCmd; nohup openclaw gateway >> ~/.openclaw/gateway.log 2>&1 & sleep 4; echo Done" | Out-Null
    $s1 = (ssh sparky1 $curlCheck 2>$null)
}
if ($s1 -eq "200") { Write-Host "  sparky1 gateway OK (18789)" -ForegroundColor Green } else { Write-Host "  sparky1 gateway not responding; check ~/.openclaw/gateway.log" -ForegroundColor Yellow }

Write-Host "Restarting gateway on sparky2 (OpenClaw)..." -ForegroundColor Cyan
ssh sparky2 "$envCmd; openclaw gateway stop 2>/dev/null; systemctl --user stop clawdbot-gateway.service 2>/dev/null; systemctl --user stop openclaw-gateway.service 2>/dev/null; sleep 2; fuser -k 18789/tcp 2>/dev/null; sleep 2; $sparkyStart; sleep 2; echo Done"
$s2 = (ssh sparky2 $curlCheck 2>$null)
if ($s2 -ne "200") {
    Write-Host "  sparky2 not up, starting nohup..." -ForegroundColor Yellow
    ssh sparky2 "source ~/.moltworld.env 2>/dev/null; $envCmd; nohup openclaw gateway >> ~/.openclaw/gateway.log 2>&1 & sleep 4; echo Done" | Out-Null
    $s2 = (ssh sparky2 $curlCheck 2>$null)
}
if ($s2 -eq "200") { Write-Host "  sparky2 gateway OK (18789)" -ForegroundColor Green } else { Write-Host "  sparky2 gateway not responding; check ~/.openclaw/gateway.log" -ForegroundColor Yellow }

Write-Host "Gateways restarted. SOUL and config will apply on next cron or new session." -ForegroundColor Green
