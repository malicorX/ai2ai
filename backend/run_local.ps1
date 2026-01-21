param(
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

Write-Host "Starting backend on http://127.0.0.1:$Port"
python -m uvicorn app.main:app --host 0.0.0.0 --port $Port

