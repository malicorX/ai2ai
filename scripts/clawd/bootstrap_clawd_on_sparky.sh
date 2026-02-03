#!/usr/bin/env bash
# One-time bootstrap: install Node 22 and Clawd (Moltbot) on a sparky.
# Run interactively on each host (sudo will prompt for password):
#   ssh sparky1
#   cd ~/ai_ai2ai && bash scripts/clawd/bootstrap_clawd_on_sparky.sh
#   exit
#   ssh sparky2
#   cd ~/ai_ai2ai && bash scripts/clawd/bootstrap_clawd_on_sparky.sh
#   exit
# Then from your dev machine: .\scripts\clawd\run_install_clawd.ps1 (to re-run Clawd install only, or to sync script changes).
set -e

echo "=== Bootstrap Clawd on $(hostname) ==="

# Install Node 22 if missing (Debian/Ubuntu)
if ! command -v node &>/dev/null || [[ $(node -v 2>/dev/null | sed 's/^v//' | cut -d. -f1) -lt 22 ]]; then
  echo "Installing Node 22 (sudo will prompt)..."
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi
echo "Node $(node -v) OK"

# Run Clawd install (same as install_clawd_on_sparky.sh)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/install_clawd_on_sparky.sh"
