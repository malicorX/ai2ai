# Load posts from posts_seed.json and add each to the Moltbook queue on both sparky1 and sparky2.
# Usage: .\scripts\moltbook\run_moltbook_seed_both_sparkies.ps1 [-SeedFile path] [-WhatIf]
param(
    [string]$SeedFile = "",
    [switch]$WhatIf = $false
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
if (-not $SeedFile) { $SeedFile = Join-Path $ScriptDir "posts_seed.json" }
if (-not (Test-Path $SeedFile)) { Write-Error "Seed file not found: $SeedFile" }

$posts = Get-Content $SeedFile -Raw -Encoding UTF8 | ConvertFrom-Json
$queueAddScript = Join-Path $ScriptDir "queue_add_from_env.py"
if (-not (Test-Path $queueAddScript)) { Write-Error "Missing $queueAddScript" }

Write-Host "Seeding queue on sparky1 and sparky2 from $SeedFile ($($posts.Count) posts). WhatIf=$WhatIf" -ForegroundColor Cyan
scp $queueAddScript sparky1:/tmp/queue_add_from_env.py
scp $queueAddScript sparky2:/tmp/queue_add_from_env.py

$n = 0
foreach ($p in $posts) {
    $title = $p.title
    $content = $p.content
    $submolt = if ($p.submolt) { $p.submolt } else { "general" }
    $n++
    Write-Host "[$n/$($posts.Count)] Queuing: $title" -ForegroundColor Yellow
    if ($WhatIf) { continue }
    $titleB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($title))
    $contentB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($content))
    $envStr = "export MOLTBOOK_TITLE_B64=$titleB64; export MOLTBOOK_BODY_B64=$contentB64; export MOLTBOOK_SUBMOLT=$submolt; python3 /tmp/queue_add_from_env.py"
    $out1 = ssh sparky1 $envStr
    $out2 = ssh sparky2 $envStr
    Write-Host "  sparky1: $out1"
    Write-Host "  sparky2: $out2"
}

if ($WhatIf) {
    Write-Host "WhatIf: no posts were queued. Run without -WhatIf to seed." -ForegroundColor Gray
} else {
    Write-Host "`nDone. $n posts added to both queues. Cron runs every 2h; at most 1 post per 2h per agent (daily cap applies)." -ForegroundColor Green
    Write-Host "List queue: .\scripts\moltbook\run_moltbook_queue_list.ps1 -Target sparky1" -ForegroundColor Cyan
    Write-Host "           .\scripts\moltbook\run_moltbook_queue_list.ps1 -Target sparky2" -ForegroundColor Cyan
}
