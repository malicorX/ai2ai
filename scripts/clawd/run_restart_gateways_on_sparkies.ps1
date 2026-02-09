# Restart OpenClaw/Clawd gateways on both sparkies (e.g. after SOUL or config change).
# Usage: .\scripts\clawd\run_restart_gateways_on_sparkies.ps1
param()

$envCmd = "source ~/.nvm/nvm.sh 2>/dev/null; source ~/.bashrc 2>/dev/null"

Write-Host "Restarting gateway on sparky1 (Clawd)..." -ForegroundColor Cyan
ssh sparky1 "$envCmd; clawdbot gateway stop 2>/dev/null; sleep 2; systemctl --user restart clawdbot-gateway.service 2>/dev/null || (nohup clawdbot gateway >> ~/.clawdbot/gateway.log 2>&1 &); sleep 1; echo Done"
Write-Host "Restarting gateway on sparky2 (OpenClaw)..." -ForegroundColor Cyan
# sparky2: unit is clawdbot-gateway.service but must run openclaw (clawdbot not installed)
$sparky2Fix = "sed -i 's|node_modules/clawdbot/dist|node_modules/openclaw/dist|g' ~/.config/systemd/user/clawdbot-gateway.service 2>/dev/null; systemctl --user daemon-reload 2>/dev/null"
ssh sparky2 "$envCmd; $sparky2Fix; openclaw gateway stop 2>/dev/null; sleep 2; systemctl --user restart clawdbot-gateway.service 2>/dev/null || (nohup openclaw gateway >> ~/.openclaw/gateway.log 2>&1 &); sleep 1; echo Done"
Write-Host "Gateways restarted. SOUL and config will apply on next cron or new session." -ForegroundColor Green
