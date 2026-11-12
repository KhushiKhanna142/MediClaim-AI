#!/usr/bin/env bash
set -e
export HF_HUB_OFFLINE=1
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"
export PYTHONPATH="$DIR:${PYTHONPATH:-}"

echo "Starting MediClaim-AI React + FastAPI Light-Theme UI on http://localhost:8000..."
.venv/bin/uvicorn src.api.main:app --host 0.0.0.0 --port 8000
