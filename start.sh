#!/usr/bin/env bash
set -e
if [ ! -d "backend/.venv" ]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -r backend/requirements.txt
fi
if [ ! -d "frontend/node_modules" ]; then
  (cd frontend && npm install)
fi
echo "Starting Shared Backend (:8000), World Command (:5173), Operations Command (:5174), and JARVIS Intelligence (:5175)..."
(cd backend && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000) &
(cd frontend && npm run dev:world) &
(cd frontend && npm run dev:operations) &
(cd frontend && npm run dev:jarvis) &
wait
