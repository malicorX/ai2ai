#!/usr/bin/env bash
# Create qwen-agentic Ollama model for Clawd tool use (Hegghammer Gist style).
# Run on sparky2: bash ~/ai2ai/scripts/clawd/clawd_create_qwen_agentic_on_sparky.sh
# Then set Clawd primary to ollama/qwen-agentic:latest
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODELFILE="$SCRIPT_DIR/clawd_qwen_agentic.Modelfile"
# If repo file missing, write Modelfile inline so we don't depend on sync
if [[ ! -f "$MODELFILE" ]]; then
  cat > "$MODELFILE" << 'MODELFILE_END'
FROM qwen2.5-coder:32b

SYSTEM """You are a helpful assistant with access to tools.

CRITICAL TOOL BEHAVIOR:
- When you have tools available, USE THEM directly without asking for confirmation
- Don't describe what you could do — just do it
- If the user asks about weather, check the weather. If they ask to search something, search it
- Never say "I don't have access to X" when you have a tool that provides X
- Check your available tools and use them immediately
- Execute the task, then report results

Be concise. Act decisively. Don't ask permission for routine tool use."""
MODELFILE_END
  echo "Wrote $MODELFILE"
fi

echo "Pulling base model qwen2.5-coder:32b (skip if already present)..."
ollama pull qwen2.5-coder:32b || true

echo "Creating qwen-agentic from $MODELFILE..."
cd "$SCRIPT_DIR"
ollama create qwen-agentic -f "$(basename "$MODELFILE")"

echo "Done. Set Clawd primary to ollama/qwen-agentic:latest (Control UI or: clawdbot config set agents.defaults.model.primary 'ollama/qwen-agentic:latest')"
