#!/usr/bin/env bash
# One-time setup: create a venv and install deps for the MoltWorld Python bot.
# Run from repo root: bash scripts/clawd/setup_moltworld_bot_venv.sh
# Or on sparky: cd ~/ai_ai2ai && bash scripts/clawd/setup_moltworld_bot_venv.sh
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"
VENV_DIR="${REPO_ROOT}/venv"
if [[ -d "$VENV_DIR" ]]; then
  echo "venv already exists at $VENV_DIR"
else
  echo "Creating venv at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi
echo "Installing requirements..."
"$VENV_DIR/bin/pip" install -r agents/agent_template/requirements.txt
echo "Done. Run the bot with: source venv/bin/activate && AGENT_ID=Sparky1Agent bash scripts/clawd/run_moltworld_python_bot.sh"
echo "Or the script will auto-use venv if present."
