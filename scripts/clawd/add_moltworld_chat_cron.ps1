# Add MoltWorld chat cron on sparkies so the OpenClaw bot runs a turn and uses world_state + chat_say.
# - sparky2 (OpenClaw): uses ISOLATED session so the job runs without main-session heartbeat (avoids "empty-heartbeat-file" skip).
# - sparky1 (Clawdbot): uses MAIN session + system event. Isolated fails with EISDIR (Clawdbot #2096). For cron to run, enable heartbeat on sparky1 (e.g. agents.defaults.heartbeat.every in clawdbot.json).
# Usage: .\scripts\clawd\add_moltworld_chat_cron.ps1
param(
    [string[]]$Hosts = @("sparky1", "sparky2")
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$removeSh = Join-Path $scriptDir "run_moltworld_cron_remove.sh"

# Pull model: agent pulls world_state then reacts. CRITICAL: answer questions with the answer only (e.g. number); never "Hi".
$baseEvent = 'You are {0}. Call world_state first. Look at the LAST message in recent_chat. If it is a math question (e.g. "how much is 7+?" or "how much is 3 + 2?"), you MUST call chat_say with ONLY the numeric answer (e.g. "7" or "5")—never "Hi" or any greeting. Example: last message "how much is 3+2?" -> chat_say text "5". If the last message is NOT a question, call chat_say with one short greeting. Use only these tools; no plain-text output.'

# Every 2 minutes each, staggered by 1 min so they can have real back-and-forth (reply within ~1-2 min).
$hostConfig = @{
    "sparky1" = @{ AgentName = "Sparky1Agent"; Cron = "0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36,38,40,42,44,46,48,50,52,54,56,58 * * * *"; Cmd = "clawdbot"; Isolated = $false }
    "sparky2" = @{ AgentName = "MalicorSparky2"; Cron = "1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,39,41,43,45,47,49,51,53,55,57,59 * * * *"; Cmd = "openclaw"; Isolated = $true }
}

foreach ($h in $Hosts) {
    $cfg = $hostConfig[$h]
    if (-not $cfg) {
        Write-Host "Unknown host $h; skipping." -ForegroundColor Yellow
        continue
    }
    $eventText = $baseEvent -f $cfg.AgentName
    $eventEscaped = $eventText -replace "'", "'\''"
    $cli = $cfg.Cmd
    $sessionType = if ($cfg.Isolated) { "isolated" } else { "main" }
    Write-Host "Updating MoltWorld chat cron on $h ($sessionType session, agent: $($cfg.AgentName))..." -ForegroundColor Cyan
    try {
        scp -q $removeSh "${h}:/tmp/run_moltworld_cron_remove.sh"
        ssh $h "CLAW=$cli bash /tmp/run_moltworld_cron_remove.sh" | ForEach-Object { Write-Host "  $_" }
        if ($cfg.Isolated) {
            # Isolated: runs immediately in a dedicated turn; no dependency on heartbeat. --no-deliver = no announce.
            $remoteCmd = "source ~/.nvm/nvm.sh 2>/dev/null; source ~/.bashrc 2>/dev/null; $cli cron add --name 'MoltWorld chat turn' --cron '$($cfg.Cron)' --tz 'UTC' --session isolated --message '$eventEscaped' --wake now --no-deliver"
        } else {
            # Main session: system event triggers next heartbeat (requires heartbeat enabled).
            $remoteCmd = "source ~/.nvm/nvm.sh 2>/dev/null; source ~/.bashrc 2>/dev/null; $cli cron add --name 'MoltWorld chat turn' --cron '$($cfg.Cron)' --tz 'UTC' --session main --system-event '$eventEscaped' --wake now"
        }
        ssh $h $remoteCmd
        Write-Host "  [OK] $h" -ForegroundColor Green
    } catch {
        Write-Host "  [FAIL] $h : $_" -ForegroundColor Red
    }
}
Write-Host "List crons: ssh sparky1 'clawdbot cron list'; ssh sparky2 'openclaw cron list'" -ForegroundColor Gray
Write-Host "Trigger now: .\scripts\clawd\run_moltworld_chat_now.ps1" -ForegroundColor Gray
