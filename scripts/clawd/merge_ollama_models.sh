#!/bin/bash
# Merge qwen3.5 models from /home/ollama/.ollama/models/ into /usr/share/.ollama/models/
# Run with: sudo bash merge_ollama_models.sh
# Use --symlink to symlink instead of copy (fast, no disk space needed)

set -e
# Sparky1 uses /usr/share/ollama/.ollama/models; sparky2 uses /home/ollama/.ollama/models
for cand in /usr/share/ollama/.ollama/models /home/ollama/.ollama/models; do
  [[ -d "$cand/manifests/registry.ollama.ai/library/qwen3.5" ]] && SRC="$cand" && break
done
SRC="${SRC:-/home/ollama/.ollama/models}"
DST="/usr/share/.ollama/models"
SYMLINK=false
[[ "${1:-}" = "--symlink" ]] && SYMLINK=true

[[ "$(id -u)" = "0" ]] || { echo "Run with sudo"; exit 1; }

echo "Source: $SRC"
echo "Merging qwen3.5 manifests..."
if [[ -d "$SRC/manifests/registry.ollama.ai/library/qwen3.5" ]]; then
  cp -a "$SRC/manifests/registry.ollama.ai/library/qwen3.5" "$DST/manifests/registry.ollama.ai/library/"
  echo "  manifests copied"
else
  echo "  qwen3.5 manifests not found in $SRC"
fi

echo "Merging qwen3.5 blobs..."
for blob in "$SRC/blobs"/sha256-*; do
  [[ -f "$blob" ]] || continue
  name=$(basename "$blob")
  if [[ ! -e "$DST/blobs/$name" ]]; then
    if $SYMLINK; then
      ln -s "$blob" "$DST/blobs/$name"
      echo "  symlinked $name"
    else
      cp -a "$blob" "$DST/blobs/"
      echo "  copied $name"
    fi
  fi
done

echo "Fixing ownership..."
chown -hR ollama:ollama "$DST"

echo "Done. Restart Ollama: sudo systemctl restart ollama"
