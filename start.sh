#!/usr/bin/env bash
set -euo pipefail

echo "====================================================="
echo "           QUANTUM RESCUE V2"
echo "       WORLD  |  CONTROL PANEL  |  JARVIS"
echo "====================================================="

if [ ! -d "backend/.venv" ]; then
  echo "[SETUP] Creating Python virtualenv and installing backend + agent packages..."
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install --upgrade pip
  backend/.venv/bin/pip install -r backend/requirements.txt
  backend/.venv/bin/pip install -r agent_backend/requirements.txt
fi

if [ ! -f "agent_backend/.env" ]; then
  cp agent_backend/.env.example agent_backend/.env
  echo "[INFO] Created agent_backend/.env from template. Add your Grok/Gemini API keys."
fi

if [ ! -d "frontend/node_modules" ]; then
  echo "[SETUP] Installing frontend Node packages..."
  (cd frontend && npm install)
fi

trap 'echo "Stopping all Quantum Rescue V2 servers..."; kill 0' EXIT INT TERM

echo "[1] SIMULATION ENGINE  http://127.0.0.1:8000"
(cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000) &
sleep 2

echo "[2] WORLD              http://localhost:5173"
(cd frontend && npm run dev:world) &

echo "[3] CONTROL PANEL      http://localhost:5174"
(cd frontend && npm run dev:control) &

echo "[4] JARVIS AI ENGINE   http://127.0.0.1:8001"
(cd agent_backend && ../backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001) &

echo "[5] JARVIS             http://localhost:5175"
(cd frontend && npm run dev:jarvis) &

echo "====================================================="
echo "ALL SERVERS STARTED"
echo "  WORLD         : http://localhost:5173"
echo "  CONTROL PANEL : http://localhost:5174"
echo "  JARVIS        : http://localhost:5175"
echo "====================================================="
wait
