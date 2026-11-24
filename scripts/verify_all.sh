#!/bin/sh
set -eu

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_PYTHON="${ROOT_DIR}/backend/.venv/bin/python"
if [ ! -x "${BACKEND_PYTHON}" ]; then
  BACKEND_PYTHON="python3"
fi

echo "== Backend integrity =="
(
  cd "${ROOT_DIR}/backend"
  "${BACKEND_PYTHON}" -c "from app.ai.tool_args import TOOL_ARGS_MODELS, TOOL_DESCRIPTIONS; assert len(TOOL_ARGS_MODELS) == len(TOOL_DESCRIPTIONS) == 50"
  COUNT="$("${BACKEND_PYTHON}" scripts/report_tool_count.py)"
  [ "${COUNT}" = "50" ] || { echo "Expected 50 tools, got ${COUNT}"; exit 1; }
  "${BACKEND_PYTHON}" -c "from app.main import app; assert len(app.routes) >= 95"
)

echo "== Backend tests =="
(
  cd "${ROOT_DIR}/backend"
  if "${BACKEND_PYTHON}" -c "import pytest" >/dev/null 2>&1; then
    "${BACKEND_PYTHON}" -m pytest tests/ -q
  else
    "${BACKEND_PYTHON}" -m unittest discover -s tests -p "test_*.py" -q
  fi
)

echo "== Backend lint (if ruff installed) =="
if command -v ruff >/dev/null 2>&1; then
  ruff check "${ROOT_DIR}/backend/app"
fi

echo "== Frontend builds (if node_modules installed) =="
if [ -d "${ROOT_DIR}/frontend/node_modules" ]; then
  (
    cd "${ROOT_DIR}/frontend"
    npm run build >/dev/null
    npm run build:operations >/dev/null
    npm run build:jarvis >/dev/null
  )
else
  echo "Skipping npm build (frontend/node_modules not installed in this environment)"
fi

echo "== Frontend useFrame setState check =="
(
  cd "${ROOT_DIR}/frontend"
  if grep -Rn "useFrame" -A8 src/simulation/*.tsx src/components/jarvis/*.tsx | grep -E "set[A-Z][a-zA-Z]*\("; then
    echo "ERROR: Found setState-like call inside useFrame!"
    exit 1
  fi
)

echo "== Dead-code print/console.log check =="
if grep -rn "print(" "${ROOT_DIR}/backend/app/" >/dev/null 2>&1; then
  echo "ERROR: Found print() in backend/app/"
  exit 1
fi

echo "ALL CHECKS PASSED"
