@echo off
setlocal EnableDelayedExpansion
echo =====================================================
echo            QUANTUM RESCUE V2
echo       WORLD  ^|  CONTROL PANEL  ^|  JARVIS
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

echo [1] SIMULATION ENGINE (BACKEND)
echo     http://127.0.0.1:8000
start "SIMULATION ENGINE (:8000)" cmd /k "cd backend && .venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000"

timeout /t 2 /nobreak >nul

echo [2] WORLD (3D METROPOLIS)
echo     http://localhost:5173
start "WORLD (:5173)" cmd /k "cd frontend && npm run dev:world"

echo [3] CONTROL PANEL (TERMINAL)
echo     http://localhost:5174
start "CONTROL PANEL (:5174)" cmd /k "cd frontend && npm run dev:control"

echo [4] JARVIS AI ENGINE (BACKEND)
echo     http://127.0.0.1:8001
start "JARVIS AI ENGINE (:8001)" cmd /k "cd agent_backend && ..\backend\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8001"

echo [5] JARVIS (3D HOLOGRAPHIC AI)
echo     http://localhost:5175
start "JARVIS (:5175)" cmd /k "cd frontend && npm run dev:jarvis"

echo.
echo =====================================================
echo ALL SERVERS STARTED
echo =====================================================
echo   WORLD         : http://localhost:5173
echo   CONTROL PANEL : http://localhost:5174
echo   JARVIS        : http://localhost:5175
echo =====================================================
echo.
