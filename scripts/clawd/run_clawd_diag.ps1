<# 
Collect Clawdbot diagnostic info from a remote host via SSH.
Usage:
  .\scripts\clawd\run_clawd_diag.ps1 -Target sparky2 [-OutFile .\scripts\clawd\clawd_diag.log]
#>
param(
    [string]$Target = "sparky2",
    [string]$OutFile = (Join-Path $PSScriptRoot "clawd_diag.log")
)

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outPath = [System.IO.Path]::GetFullPath($OutFile)
$localTmp = Join-Path $PSScriptRoot "clawd_diag_remote.$timestamp.sh"
$remoteTmp = "/tmp/clawd_diag_remote.$timestamp.sh"

Write-Host "Collecting Clawdbot diagnostics from $Target..." -ForegroundColor Cyan
Write-Host "Output: $outPath" -ForegroundColor Gray

$remoteScript = @"
#!/usr/bin/env bash
set -e

# Ensure nvm node/npm are on PATH
export PATH="\$HOME/.nvm/versions/node/v22.22.0/bin:\$PATH"

echo "== whoami =="
whoami
echo "== which clawdbot =="
command -v clawdbot || true
echo "== clawdbot --version may warn if config invalid =="
clawdbot --version || true
echo "== node/npm locations =="
command -v node || true
command -v npm || true
echo "== global clawdbot dist schema path =="
SCHEMA="/home/malicor/.nvm/versions/node/v22.22.0/lib/node_modules/clawdbot/dist/config/zod-schema.core.js"
echo "schema: \$SCHEMA"
ls -l "\$SCHEMA" || true
echo "supportedParameters lines:"
grep -n "supportedParameters" "\$SCHEMA" || true
echo "ModelCompatSchema snippet:"
grep -n "ModelCompatSchema" "\$SCHEMA" || true
echo "== config compat keys =="
python3 - <<'PY' || true
import json, os
path = os.path.expanduser("~/.clawdbot/clawdbot.json")
data = json.load(open(path))
models = data.get("models", {}).get("providers", {}).get("ollama", {}).get("models", [])
for i, m in enumerate(models):
    compat = m.get("compat", {})
    print(i, "compat keys:", sorted(compat.keys()))
PY
"@

$remoteScript = $remoteScript -replace "`r`n", "`n"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($localTmp, $remoteScript, $utf8NoBom)

ssh $Target "mkdir -p /tmp" 2>$null | Out-Null
scp -q $localTmp "${Target}:$remoteTmp"
$output = & ssh $Target "sed -i 's/\r$//' $remoteTmp 2>/dev/null; chmod +x $remoteTmp; bash $remoteTmp; rm -f $remoteTmp" 2>&1

$output | Out-File -FilePath $outPath -Encoding utf8
Remove-Item -Force $localTmp -ErrorAction SilentlyContinue
Write-Host "Done. Saved to $outPath" -ForegroundColor Green
