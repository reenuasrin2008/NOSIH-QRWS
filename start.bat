@echo off
setlocal EnableDelayedExpansion
echo =====================================================
echo            QUANTUM RESCUE V2
echo       AUTONOMOUS DISASTER RESPONSE SYSTEM
echo =====================================================
echo.
echo [CHECK] Verifying Python and Node.js availability...
where python >nul 2>&1 || (echo [ERROR] Python 3.10+ not found in PATH. & pause & exit /b 1)
where node >nul 2>&1 || (echo [ERROR] Node.js 18+ not found in PATH. & pause & exit /b 1)

if not exist "backend\.venv\Scripts\python.exe" (
  echo [SETUP 1/3] Creating Python virtual environment and installing backend packages...
  python -m venv backend\.venv
  backend\.venv\Scripts\pip.exe install --upgrade pip
  backend\.venv\Scripts\pip.exe install -r backend\requirements.txt
  backend\.venv\Scripts\pip.exe install -r agent_backend\requirements.txt
)

if not exist "agent_backend\.env" (
  echo [INFO] Creating agent_backend\.env from .env.example — add your Grok/Gemini keys to enable live AI calls.
  copy /Y "agent_backend\.env.example" "agent_backend\.env" >nul
)

if not exist "frontend\node_modules" (
  echo [SETUP 2/3] Installing frontend Node packages...
  pushd frontend
  call npm install
  popd
)

echo [1] SIMULATION BACKEND
echo     http://127.0.0.1:8000
start "Quantum Rescue V2 — Simulation Backend (:8000)" cmd /k "cd backend && .venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000"

timeout /t 2 /nobreak >nul

echo [2] 3D VISUAL ENVIRONMENT
echo     http://localhost:5173
start "Quantum Rescue V2 — 3D Visual (:5173)" cmd /k "cd frontend && npm run dev:scene"

echo [3] MISSION CONTROL PANEL
echo     http://localhost:5174
start "Quantum Rescue V2 — Control Panel (:5174)" cmd /k "cd frontend && npm run dev:control"

echo [4] AI AGENT BACKEND
echo     http://127.0.0.1:8001
start "Quantum Rescue V2 — AI Agent Backend (:8001)" cmd /k "cd agent_backend && ..\backend\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8001"

echo [5] AI RESCUE COMMAND CONSOLE
echo     http://localhost:5175
start "Quantum Rescue V2 — AI Console (:5175)" cmd /k "cd frontend && npm run dev:agent"

echo.
echo =====================================================
echo ALL SERVICES STARTED
echo =====================================================
echo   [1] Simulation Backend : http://127.0.0.1:8000
echo   [2] 3D Visual          : http://localhost:5173
echo   [3] Control Panel      : http://localhost:5174
echo   [4] AI Agent Backend   : http://127.0.0.1:8001
echo   [5] AI Rescue Console  : http://localhost:5175
echo =====================================================
echo.
