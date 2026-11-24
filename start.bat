@echo off
if not exist backend\.venv (
  python -m venv backend\.venv
  backend\.venv\Scripts\pip install -r backend\requirements.txt
)
if not exist frontend\node_modules (
  cd frontend && npm install && cd ..
)
echo Starting Shared Backend (:8000), World Command (:5173), Operations Command (:5174), and JARVIS Intelligence (:5175)...
start "Quantum Rescue Backend (:8000)" cmd /k "cd backend && .venv\Scripts\uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
start "01 World Command (:5173)" cmd /k "cd frontend && npm run dev:world"
start "02 Operations Command (:5174)" cmd /k "cd frontend && npm run dev:operations"
start "03 JARVIS Intelligence (:5175)" cmd /k "cd frontend && npm run dev:jarvis"
