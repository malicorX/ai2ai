#!/usr/bin/env bash
# Non-interactive prep for Clawd: doctor --fix, gateway.mode local.
# Run after install so when you SSH in to onboard, base state is ready.
# Usage: bash scripts/clawd/clawd_prepare_on_sparky.sh
set -e

export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[[ -s "$NVM_DIR/nvm.sh" ]] && . "$NVM_DIR/nvm.sh"
[[ -f ~/.bashrc ]] && source ~/.bashrc 2>/dev/null || true

CLI=""
for c in moltbot clawdbot; do
  if command -v $c &>/dev/null; then CLI=$c; break; fi
done
if [[ -z "$CLI" ]]; then
  echo "moltbot/clawdbot not in PATH. Run from a shell where install completed (source ~/.bashrc)."
  exit 1
fi

echo "Using $CLI on $(hostname)"
$CLI config set gateway.mode local 2>/dev/null || true
# Persist full Ollama provider in config (baseUrl + apiKey + models required in one block)
CFG="${HOME}/.clawdbot/clawdbot.json"
mkdir -p "$(dirname "$CFG")"
if [[ ! -f "$CFG" ]]; then echo '{}' > "$CFG"; fi
python3 -c "
import json, os, sys
p = sys.argv[1]
d = json.load(open(p)) if os.path.isfile(p) else {}
prov = d.setdefault(\"models\", {}).setdefault(\"providers\", {}).setdefault(\"ollama\", {\"baseUrl\": \"http://127.0.0.1:11434/v1\", \"apiKey\": \"ollama-local\", \"api\": \"openai-completions\", \"models\": []})
prov[\"baseUrl\"] = prov.get(\"baseUrl\", \"http://127.0.0.1:11434/v1\")
prov[\"apiKey\"] = prov.get(\"apiKey\", \"ollama-local\")
prov[\"api\"] = prov.get(\"api\", \"openai-completions\")
defaults = [
  {\"id\": \"llama3.1:70b\", \"name\": \"Llama 3.1 70B\", \"reasoning\": False, \"input\": [\"text\"], \"cost\": {\"input\": 0, \"output\": 0, \"cacheRead\": 0, \"cacheWrite\": 0}, \"contextWindow\": 131072, \"maxTokens\": 8192},
  {\"id\": \"llama3.3:latest\", \"name\": \"Llama 3.3\", \"reasoning\": False, \"input\": [\"text\"], \"cost\": {\"input\": 0, \"output\": 0, \"cacheRead\": 0, \"cacheWrite\": 0}, \"contextWindow\": 131072, \"maxTokens\": 8192}
]
ids = {m[\"id\"] for m in prov.get(\"models\", [])}
for m in defaults:
  if m[\"id\"] not in ids:
    prov.setdefault(\"models\", []).append(m)
    ids.add(m[\"id\"])
json.dump(d, open(p, \"w\"), indent=2)
" "$CFG" 2>/dev/null || true
$CLI doctor --fix 2>/dev/null || true
# Create dirs doctor may not create non-interactively
mkdir -p ~/.clawdbot/agents/main/sessions ~/.clawdbot/credentials
chmod 700 ~/.clawdbot ~/.clawdbot/credentials 2>/dev/null || true
# Copy start_clawd_gateway.sh to ~/bin so you can run it without the repo path
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p ~/bin
if [[ -f "$SCRIPT_DIR/start_clawd_gateway.sh" ]]; then
  cp "$SCRIPT_DIR/start_clawd_gateway.sh" ~/bin/start_clawd_gateway.sh
  sed -i 's/\r$//' ~/bin/start_clawd_gateway.sh 2>/dev/null || true
  chmod +x ~/bin/start_clawd_gateway.sh
  echo "Installed ~/bin/start_clawd_gateway.sh (run: bash ~/bin/start_clawd_gateway.sh)"
fi
echo "Done. Next: run '$CLI onboard --install-daemon' (interactive) for pairing and channels."
exit 0
