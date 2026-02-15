#!/usr/bin/env bash
# Build OpenClaw from main and install globally. Use Node 22+. Run on sparky.
# After this, run add_openai_completions_tools.py and restart the gateway.
# Usage: bash build_openclaw_from_main_on_sparky.sh
set -e
BUILD_DIR="${OPENCLAW_BUILD_DIR:-$HOME/openclaw-main-build}"
REPO="${OPENCLAW_REPO:-https://github.com/openclaw/openclaw.git}"

source ~/.nvm/nvm.sh 2>/dev/null || true
source ~/.bashrc 2>/dev/null || true
nvm use 22 2>/dev/null || nvm use default 2>/dev/null || true

mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"
if [[ ! -d openclaw ]]; then
  git clone --depth 1 "$REPO" openclaw
fi
cd openclaw
git fetch origin main 2>/dev/null || true
git checkout main
git pull origin main 2>/dev/null || true

PNPM="pnpm"
command -v pnpm >/dev/null 2>&1 || PNPM="npx --yes pnpm"
$PNPM install
$PNPM run build
$PNPM run ui:build

npm install -g .
echo "OpenClaw from main installed. Next: add compat.openaiCompletionsTools (add_openai_completions_tools.py), then restart gateway."
