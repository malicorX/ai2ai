#!/usr/bin/env bash
# Run on sparky1/sparky2 (or any Linux host) to install Clawd (Moltbot) and wire Ollama.
# Usage: bash scripts/clawd/install_clawd_on_sparky.sh
# Or via SSH: ssh sparky1 'bash -s' < scripts/clawd/install_clawd_on_sparky.sh
set -e

echo "=== Clawd (Moltbot) install on $(hostname) ==="

# Node >= 22 required; install via nvm (no sudo) if missing
ensure_node22() {
  if command -v node &>/dev/null; then
    NODE_VER=$(node -v 2>/dev/null | sed 's/^v//' | cut -d. -f1)
    [[ -n "$NODE_VER" && "$NODE_VER" -ge 22 ]] && return 0
  fi
  echo "Node 22 not found; installing via nvm (no sudo)..."
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [[ ! -d "$NVM_DIR" ]]; then
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
  fi
  # shellcheck source=/dev/null
  [[ -s "$NVM_DIR/nvm.sh" ]] && . "$NVM_DIR/nvm.sh"
  nvm install 22
  nvm use 22
}
ensure_node22
echo "Node $(node -v) OK"
# So Moltbot installer and later commands see nvm's node/npm
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
# shellcheck source=/dev/null
[[ -s "$NVM_DIR/nvm.sh" ]] && . "$NVM_DIR/nvm.sh"
nvm use 22 2>/dev/null || true

# Non-interactive install (skip onboarding; run that manually later)
echo "Running Moltbot installer (--no-onboard)..."
curl -fsSL https://molt.bot/install.sh | bash -s -- --no-onboard

# Ensure moltbot is on PATH (installer may add it)
export PATH="$HOME/.local/bin:$(npm prefix -g 2>/dev/null)/bin:$PATH"
if ! command -v moltbot &>/dev/null; then
  echo "moltbot not in PATH. Try: export PATH=\"\$(npm prefix -g)/bin:\$PATH\" and run moltbot onboard --install-daemon"
fi

# Ollama + PATH for moltbot (so gateway/daemon and CLI work after login)
NPM_BIN="$(npm prefix -g 2>/dev/null)/bin"
if [[ -n "$NPM_BIN" && -d "$NPM_BIN" ]]; then
  if ! grep -q "NPM_BIN\|npm prefix -g.*bin" ~/.bashrc 2>/dev/null; then
    echo "" >> ~/.bashrc
    echo "# Clawd (ai_ai2ai) - npm global bin for moltbot" >> ~/.bashrc
    echo "export PATH=\"\$PATH:$NPM_BIN\"" >> ~/.bashrc
    echo "Added npm global bin to ~/.bashrc for moltbot"
  fi
fi
OLLAMA_ENV="export OLLAMA_API_KEY=\"ollama-local\""
if ! grep -q "OLLAMA_API_KEY" ~/.bashrc 2>/dev/null; then
  echo "" >> ~/.bashrc
  echo "# Clawd + Ollama (ai_ai2ai)" >> ~/.bashrc
  echo "$OLLAMA_ENV" >> ~/.bashrc
  echo "Added OLLAMA_API_KEY to ~/.bashrc"
fi
eval "$OLLAMA_ENV"

echo ""
echo "=== Next steps (run on this host) ==="
echo "1. Onboard and install daemon:  moltbot onboard --install-daemon"
echo "2. Optional: add Telegram/WhatsApp channel (see docs/external-tools/clawd/CLAWD_SPARKY.md)"
echo "3. Add Fiverr screening cron (example in docs/external-tools/clawd/CLAWD_SPARKY.md):"
echo "   moltbot cron add --name \"Fiverr screen\" --cron \"0 */6 * * *\" --tz \"America/Los_Angeles\" \\"
echo "     --session isolated --message \"Use web search to find current Fiverr gigs; summarize up to 10: title, price, link.\" \\"
echo "     --deliver --channel telegram --to YOUR_CHAT_ID"
echo ""
