# Deploy and start MoltWorld loops. By default: narrator = OpenClaw (sparky1), replier = OpenClaw (sparky2).
# Run run_setup_openclaw_on_sparky1.ps1 once so sparky1 has ~/.openclaw and the plugin; then this script uses OpenClaw for both.
# Use -UsePythonNarrator to fall back to Python bot on sparky1 (e.g. if OpenClaw is not set up on sparky1).
#
# Usage: .\scripts\clawd\run_moltworld_openclaw_loops.ps1 [-Background] [-UsePythonNarrator] [-NarratorIntervalSec 120]
param(
    [switch]$Background,
    [switch]$UsePythonNarrator,
    [int]$NarratorIntervalSec = 120,
    [int]$PollIntervalSec = 10,
    [string]$Sparky1Host = "sparky1",
    [string]$Sparky2Host = "sparky2",
    [string]$RemoteRepoPath = "~/ai_ai2ai"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Get-Item $scriptDir).Parent.Parent.FullName

$narratorSh = Join-Path $projectRoot "scripts\clawd\run_moltworld_openclaw_narrator_loop.sh"
$pythonNarratorSh = Join-Path $projectRoot "scripts\clawd\run_moltworld_python_bot_loop.sh"
$pythonBotSh = Join-Path $projectRoot "scripts\clawd\run_moltworld_python_bot.sh"
$pollSh = Join-Path $projectRoot "scripts\clawd\run_moltworld_openclaw_poll_loop.sh"
$wakeSh = Join-Path $projectRoot "scripts\clawd\run_moltworld_pull_and_wake.sh"
foreach ($f in @($narratorSh, $pollSh, $wakeSh)) {
    if (-not (Test-Path $f)) { Write-Host "Missing $f" -ForegroundColor Red; exit 1 }
}
if ($UsePythonNarrator) {
    foreach ($f in @($pythonNarratorSh, $pythonBotSh)) {
        if (-not (Test-Path $f)) { Write-Host "Missing $f" -ForegroundColor Red; exit 1 }
    }
}

Write-Host "Deploying loop scripts..." -ForegroundColor Cyan
# Sparky1: OpenClaw narrator and/or Python bot narrator + bot script
scp -q $narratorSh $wakeSh "${Sparky1Host}:${RemoteRepoPath}/scripts/clawd/"
if ($UsePythonNarrator) {
    scp -q $pythonNarratorSh $pythonBotSh "${Sparky1Host}:${RemoteRepoPath}/scripts/clawd/"
    # Copy Python bot module for narrator
    $botPy = Join-Path $projectRoot "agents\agent_template\moltworld_bot.py"
    $runtimePy = Join-Path $projectRoot "agents\agent_template\langgraph_runtime.py"
    scp -q $botPy "${Sparky1Host}:${RemoteRepoPath}/agents/agent_template/"
    scp -q $runtimePy "${Sparky1Host}:${RemoteRepoPath}/agents/agent_template/"
}
$chmodList = "${RemoteRepoPath}/scripts/clawd/run_moltworld_openclaw_narrator_loop.sh ${RemoteRepoPath}/scripts/clawd/run_moltworld_pull_and_wake.sh"
if ($UsePythonNarrator) { $chmodList += " ${RemoteRepoPath}/scripts/clawd/run_moltworld_python_bot_loop.sh ${RemoteRepoPath}/scripts/clawd/run_moltworld_python_bot.sh" }
ssh $Sparky1Host "sed -i 's/\r$//' ${RemoteRepoPath}/scripts/clawd/*.sh 2>/dev/null; chmod +x $chmodList 2>/dev/null; echo ok"
# Sparky2: poll + wake
scp -q $pollSh $wakeSh "${Sparky2Host}:${RemoteRepoPath}/scripts/clawd/"
ssh $Sparky2Host "sed -i 's/\r$//' ${RemoteRepoPath}/scripts/clawd/run_moltworld_openclaw_poll_loop.sh ${RemoteRepoPath}/scripts/clawd/run_moltworld_pull_and_wake.sh 2>/dev/null; chmod +x ${RemoteRepoPath}/scripts/clawd/run_moltworld_openclaw_poll_loop.sh ${RemoteRepoPath}/scripts/clawd/run_moltworld_pull_and_wake.sh"

# Kill existing loops so only one driver per role
ssh $Sparky1Host "pkill -f 'run_moltworld_openclaw_narrator_loop' 2>/dev/null; pkill -f 'run_moltworld_python_bot_loop' 2>/dev/null; sleep 1; echo ok"
ssh $Sparky2Host "pkill -f 'run_moltworld_openclaw_poll_loop' 2>/dev/null; pkill -f 'run_moltworld_python_bot_poll_loop' 2>/dev/null; sleep 1; echo ok"

$redir = [char]0x32 + [char]0x3e + [char]0x26 + [char]0x31
$bg = [char]0x20 + [char]0x26
if ($Background) {
    if (-not $UsePythonNarrator) {
        Write-Host "Starting narrator (OpenClaw) on $Sparky1Host (every ${NarratorIntervalSec}s)..." -ForegroundColor Cyan
        $cmd0 = "cd $RemoteRepoPath; NARRATOR_INTERVAL_SEC=$NarratorIntervalSec nohup bash scripts/clawd/run_moltworld_openclaw_narrator_loop.sh >> `$HOME/.moltworld_openclaw_narrator.log $redir $bg echo started"
        ssh $Sparky1Host $cmd0
    } else {
        Write-Host "Starting narrator (Python bot) on $Sparky1Host (every ${NarratorIntervalSec}s)..." -ForegroundColor Cyan
        $cmd1 = "cd $RemoteRepoPath; AGENT_ID=Sparky1Agent NARRATOR_INTERVAL_SEC=$NarratorIntervalSec nohup bash scripts/clawd/run_moltworld_python_bot_loop.sh >> `$HOME/.moltworld_python_narrator.log $redir $bg echo started"
        ssh $Sparky1Host $cmd1
    }
    Write-Host "Starting poll loop (OpenClaw) on $Sparky2Host (poll ${PollIntervalSec}s)..." -ForegroundColor Cyan
    $cmd2 = "cd $RemoteRepoPath; AGENT_ID=MalicorSparky2 POLL_INTERVAL_SEC=$PollIntervalSec nohup bash scripts/clawd/run_moltworld_openclaw_poll_loop.sh >> `$HOME/.moltworld_openclaw_poll.log $redir $bg echo started"
    ssh $Sparky2Host $cmd2
    $narratorLog = if (-not $UsePythonNarrator) { "~/.moltworld_openclaw_narrator.log" } else { "~/.moltworld_python_narrator.log" }
    Write-Host "Done. Logs: ssh $Sparky1Host tail -f $narratorLog; ssh $Sparky2Host tail -f ~/.moltworld_openclaw_poll.log" -ForegroundColor Green
    return
}

if (-not $UsePythonNarrator) {
    Write-Host "Starting narrator (OpenClaw) on $Sparky1Host..." -ForegroundColor Cyan
    $c1 = "cd $RemoteRepoPath; NARRATOR_INTERVAL_SEC=$NarratorIntervalSec nohup bash scripts/clawd/run_moltworld_openclaw_narrator_loop.sh >> `$HOME/.moltworld_openclaw_narrator.log $redir $bg echo started"
    ssh $Sparky1Host $c1
} else {
    Write-Host "Starting narrator (Python bot) on $Sparky1Host..." -ForegroundColor Cyan
    $c1 = "cd $RemoteRepoPath; AGENT_ID=Sparky1Agent NARRATOR_INTERVAL_SEC=$NarratorIntervalSec nohup bash scripts/clawd/run_moltworld_python_bot_loop.sh >> `$HOME/.moltworld_python_narrator.log $redir $bg echo started"
    ssh $Sparky1Host $c1
}
Write-Host "Starting poll loop (OpenClaw) on $Sparky2Host..." -ForegroundColor Cyan
$c2 = "cd $RemoteRepoPath; AGENT_ID=MalicorSparky2 POLL_INTERVAL_SEC=$PollIntervalSec nohup bash scripts/clawd/run_moltworld_openclaw_poll_loop.sh >> `$HOME/.moltworld_openclaw_poll.log $redir $bg echo started"
ssh $Sparky2Host $c2
Write-Host "Loops started. Narrator = OpenClaw (sparky1). Use -UsePythonNarrator to fall back to Python bot on sparky1." -ForegroundColor Green
