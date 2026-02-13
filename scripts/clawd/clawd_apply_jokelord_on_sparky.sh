#!/usr/bin/env bash
# Apply jokelord tool-calling patch to Clawdbot, build, and install on sparky2.
# Run on sparky2: bash ~/ai2ai/scripts/clawd/clawd_apply_jokelord_on_sparky.sh
# After this: add compat.supportedParameters to Ollama models (clawd_add_supported_parameters.py), restart gateway.
# See docs/external-tools/clawd/CLAWD_JOKELORD_STEPS.md for full steps.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${CLAWDBOT_BUILD_DIR:-$HOME/clawdbot-jokelord-build}"
CLAWDBOT_REPO="${CLAWDBOT_REPO:-https://github.com/clawdbot/clawdbot.git}"
CLAWDBOT_TAG="${CLAWDBOT_TAG:-}"
JOKELORD_REPO="https://github.com/jokelord/openclaw-local-model-tool-calling-patch.git"
# jokelord repo uses openclawd-2026.2.3 (was openclawd-2026.1.24)
JOKELORD_PATCHED_SRC="openclawd-2026.2.3/src"

echo "Build dir: $BUILD_DIR"
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

if [[ ! -d clawdbot ]]; then
  echo "Cloning Clawdbot (default branch)..."
  git clone --depth 1 "$CLAWDBOT_REPO" clawdbot
fi
# Re-clone jokelord if patch dir missing or wrong version (e.g. had 2026.1.24, now need 2026.2.3)
if [[ ! -d "jokelord-patch/$JOKELORD_PATCHED_SRC" ]]; then
  rm -rf jokelord-patch
fi
if [[ ! -d jokelord-patch ]]; then
  echo "Cloning jokelord patch..."
  git clone --depth 1 "$JOKELORD_REPO" jokelord-patch
fi

echo "Copying patched files from jokelord into Clawdbot..."
PATCH_SRC="$BUILD_DIR/jokelord-patch/$JOKELORD_PATCHED_SRC"
DEST="$BUILD_DIR/clawdbot/src"
for rel in config/zod-schema.core.ts config/types.models.ts agents/model-compat.ts agents/pi-embedded-runner/run/attempt.ts; do
  if [[ -f "$PATCH_SRC/$rel" ]]; then
    mkdir -p "$(dirname "$DEST/$rel")"
    cp "$PATCH_SRC/$rel" "$DEST/$rel"
    echo "  $rel"
  else
    echo "  WARN: missing $PATCH_SRC/$rel" >&2
  fi
done

echo "Applying compat fixes (OpenClaw naming, types, zod)..."
bash "$SCRIPT_DIR/clawd_jokelord_compat_fixes.sh" "$BUILD_DIR/clawdbot"

echo "Installing deps and building..."
cd "$BUILD_DIR/clawdbot"
# Ensure Node/npm are available (pnpm install relies on npm).
# Non-interactive shells (ssh) may not load PATH (e.g., nvm). Try sourcing common profiles.
if ! command -v node &>/dev/null || ! command -v npm &>/dev/null; then
  for f in "$HOME/.bashrc" "$HOME/.profile" "$HOME/.bash_profile" "$HOME/.zshrc"; do
    if [[ -f "$f" ]]; then
      # shellcheck disable=SC1090
      source "$f"
    fi
  done
  # If nvm is installed, load it explicitly (some profiles return early in non-interactive shells).
  if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
    # shellcheck disable=SC1090
    source "$HOME/.nvm/nvm.sh"
    if command -v nvm &>/dev/null; then
      nvm use --silent default || nvm use --silent 22 || true
    fi
  fi
fi
if ! command -v node &>/dev/null || ! command -v npm &>/dev/null; then
  echo "ERROR: node/npm not found in PATH (non-interactive shell)." >&2
  echo "Open an interactive shell or ensure Node is on PATH, then re-run." >&2
  echo "See docs/external-tools/clawd/CLAWD_JOKELORD_STEPS.md for suggested install methods." >&2
  exit 1
fi
# Use pnpm if available, else npx pnpm (no global install needed)
PNPM="pnpm"
if ! command -v pnpm &>/dev/null; then
  PNPM="npx --yes pnpm"
  echo "Using $PNPM (no global pnpm)"
fi
$PNPM install
$PNPM run build
# Control UI (chat at /chat): gateway serves dist/control-ui/; build so "Control UI assets not found" does not appear
if $PNPM run ui:build 2>/dev/null; then
  echo "Control UI assets built (dist/control-ui/)."
else
  echo "NOTE: ui:build skipped or failed; /chat may show 'Control UI assets not found'. Run: pnpm run ui:build"
fi
echo "Installing globally..."
if npm install -g . 2>/dev/null; then
  echo "Installed to user global (no sudo)."
elif [[ -t 0 ]]; then
  sudo npm install -g .
else
  echo "NOTE: Run manually (with or without sudo):"
  echo "  cd \"$BUILD_DIR/clawdbot\" && npm install -g ."
fi

echo ""
echo "Done. Next steps:"
echo "  1. Add supportedParameters to Ollama models: python3 $SCRIPT_DIR/clawd_add_supported_parameters.py"
echo "  2. Restart gateway: clawdbot gateway stop; sleep 2; nohup clawdbot gateway >> ~/.clawdbot/gateway.log 2>&1 &"
echo "  3. Test: new chat, ask e.g. 'Use the browser to open https://fiverr.com and list 5 logo design gigs'"
