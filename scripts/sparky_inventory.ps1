# SSH inventory for sparky1 and sparky2: what's actually running (OpenClaw/Clawd, Python agent, etc.)
# Writes to sparky_inventory/ (gitignored). Optionally creates a zip on each host and scps it back.
# Usage: .\scripts\sparky_inventory.ps1 [-FetchZip]
# Requires: sparky1 and sparky2 in SSH config (e.g. ~/.ssh/config).

param([switch]$FetchZip = $false)

$ErrorActionPreference = "Continue"
$projectRoot = (Get-Item $PSScriptRoot).Parent.FullName
$outDir = Join-Path $projectRoot "sparky_inventory"
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }

# Inline script run on each host. Avoid ( ) in echo so bash -c does not start subshell.
$invScriptOneLine = "echo hostname; hostname; echo uname; uname -a 2>/dev/null; echo which; which clawdbot openclaw moltbot node npm python3 2>/dev/null; echo processes; ps aux 2>/dev/null | grep -E 'clawd|gateway|agent_template|moltworld' | grep -v grep || true; echo clawdbot_dir; ls -la ~/.clawdbot 2>/dev/null || echo none; echo openclaw_dir; ls -la ~/.openclaw 2>/dev/null || echo none; echo moltworld_env; test -f ~/.moltworld.env && echo yes || echo no; echo repo_ai_ai2ai; ls -la ~/ai_ai2ai 2>/dev/null || echo none; echo repo_ai2ai; ls -la ~/ai2ai 2>/dev/null || echo none; echo clawdbot_json; test -f ~/.clawdbot/clawdbot.json && head -c 8000 ~/.clawdbot/clawdbot.json || echo nofile"

foreach ($target in @("sparky1", "sparky2")) {
    Write-Host "`n--- $target ---" -ForegroundColor Cyan
    $outFile = Join-Path $outDir "${target}_inventory.txt"
    try {
        $out = ssh -o BatchMode=yes -o ConnectTimeout=10 $target $invScriptOneLine 2>&1
        $outStr = $out | Out-String
        # Redact token/apiKey/auth/botToken in saved output
        $outStr = $outStr -replace '("(?:token|apiKey|auth|botToken)"\s*:\s*)"[^"]*"', '$1"<redacted>"'
        [System.IO.File]::WriteAllText($outFile, "Collected: $(Get-Date -Format 'o')`n`n$outStr", [System.Text.UTF8Encoding]::new($false))
        Write-Host "  Wrote $outFile" -ForegroundColor Green
    } catch {
        $err = "SSH failed: $_"
        [System.IO.File]::WriteAllText($outFile, "Collected: $(Get-Date -Format 'o')`n`n$err`n", [System.Text.UTF8Encoding]::new($false))
        Write-Host "  $err" -ForegroundColor Red
    }
}

if ($FetchZip) {
    # On each host: create /tmp/sparky_inventory.zip with config (redacted) and key dir listings; scp back
    $zipScript = @'
cd ~ && (test -d .clawdbot && (cat .clawdbot/clawdbot.json 2>/dev/null | sed -E 's/"(token|apiKey|auth)"[[:space:]]*:[[:space:]]*"[^"]*"/"\1": "<redacted>"/g' > /tmp/clawdbot_safe.json; zip -q -j /tmp/sparky_inventory.zip /tmp/clawdbot_safe.json .clawdbot/clawdbot.json 2>/dev/null) || true); (test -d .openclaw && zip -q -r /tmp/sparky_inventory.zip .openclaw 2>/dev/null) || true; ls -laR .clawdbot .openclaw 2>/dev/null | zip -q /tmp/sparky_inventory.zip - 2>/dev/null; echo /tmp/sparky_inventory.zip
'@
    foreach ($target in @("sparky1", "sparky2")) {
        Write-Host "`nFetchZip $target..." -ForegroundColor Cyan
        try {
            $zipPath = ssh -o BatchMode=yes -o ConnectTimeout=10 $target $zipScript 2>&1 | Select-Object -Last 1
            if ($zipPath -match "sparky_inventory.zip") {
                scp -o BatchMode=yes "${target}:/tmp/sparky_inventory.zip" (Join-Path $outDir "${target}_inventory.zip") 2>&1
                if (Test-Path (Join-Path $outDir "${target}_inventory.zip")) { Write-Host "  Saved ${target}_inventory.zip" -ForegroundColor Green }
            }
        } catch { Write-Host "  $_" -ForegroundColor Red }
    }
}

Write-Host "`nDone. See $outDir" -ForegroundColor Cyan
