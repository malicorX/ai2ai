#!/bin/bash
# Run this on sparky1 or sparky2 after deploy.ps1 -CopyOnly has copied main.py.
# Usage: bash restart_after_deploy.sh   (or ./restart_after_deploy.sh)

set -e
BACKEND_DIR="${BACKEND_DIR:-/home/malicor/ai2ai/backend}"
LOG="${LOG:-/tmp/ai2ai_backend.log}"
PORT=8000

echo "Stopping any existing backend on port $PORT..."
sudo pkill -f 'uvicorn app.main:app' 2>/dev/null || true
# Ensure nothing is left on the port (e.g. old process started by root or Docker)
if command -v fuser >/dev/null 2>&1; then
  sudo fuser -k ${PORT}/tcp 2>/dev/null || true
elif command -v lsof >/dev/null 2>&1; then
  PIDS=$(lsof -t -i:${PORT} 2>/dev/null || true)
  if [ -n "$PIDS" ]; then sudo kill -9 $PIDS 2>/dev/null || true; fi
fi
sleep 2
# Wait until port is free (avoid bind failure when old process is slow to exit)
for i in 1 2 3 4 5 6 7 8 9 10; do
  if command -v fuser >/dev/null 2>&1; then
    fuser ${PORT}/tcp 2>/dev/null || break
  elif command -v ss >/dev/null 2>&1; then
    ss -tlnp 2>/dev/null | grep -q ":${PORT} " || break
  else
    break
  fi
  echo "  Port $PORT still in use, waiting..."
  sleep 1
done

echo "Starting backend in $BACKEND_DIR..."
cd "$BACKEND_DIR"
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> "$LOG" 2>&1 &
echo "Backend started (PID $!). Log: $LOG"
