#!/usr/bin/env bash
# Run on sparky (or: ssh sparky2 'bash -s' < scripts/clawd/clawd_ollama_check.sh)
# Checks Ollama, gateway log, and tests the model endpoint.
set -e

echo "=== 1. Ollama /api/tags ==="
curl -s http://127.0.0.1:11434/api/tags || echo "(failed)"
echo ""
echo "=== 2. ollama list ==="
ollama list 2>/dev/null || echo "(ollama not in PATH or failed)"
echo ""
echo "=== 3. Ollama chat completions (llama3.1:70b) ==="
curl -s http://127.0.0.1:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.1:70b","messages":[{"role":"user","content":"hi"}],"max_tokens":20}' | head -c 500
echo ""
echo ""
echo "=== 4. Last 60 lines of gateway.log ==="
tail -60 ~/.clawdbot/gateway.log 2>/dev/null || echo "(no log)"
echo ""
echo "=== done ==="
