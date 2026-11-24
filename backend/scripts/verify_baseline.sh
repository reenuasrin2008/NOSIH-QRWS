#!/bin/sh
set -eu

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
REPORT="${ROOT_DIR}/docs/BASELINE_REPORT.md"
mkdir -p "${ROOT_DIR}/docs"

{
  echo "# Quantum Rescue — Phase 0 Baseline Verification Report"
  echo ""
  echo "## Backend integrity"
  echo '```text'
  (
    cd "${ROOT_DIR}/backend"
    python3 -c "from app.ai.tool_args import TOOL_ARGS_MODELS, TOOL_DESCRIPTIONS; assert len(TOOL_ARGS_MODELS) == len(TOOL_DESCRIPTIONS) == 50, f'expected 50, got {len(TOOL_ARGS_MODELS)} / {len(TOOL_DESCRIPTIONS)}'; print('TOOL_ARGS_MODELS OK:', len(TOOL_ARGS_MODELS))"
    printf "report_tool_count.py: "
    python3 scripts/report_tool_count.py
    python3 -c "from app.main import app; print('FastAPI app import OK, routes:', len(app.routes))"
  )
  echo '```'
  echo ""
  echo "## Frontend wiring"
  echo '```text'
  (
    cd "${ROOT_DIR}/frontend"
    echo "=== Post-processing ==="
    grep -R "EffectComposer\|N8AO\|Bloom\|SMAA\|ACES_FILMIC" src/ || echo "(NONE)"
    echo "=== Adaptive DPR / perf monitor ==="
    grep -R "PerformanceMonitor\|AdaptiveDpr\|r3f-perf\|<Perf" src/ package.json || echo "(NONE)"
    echo "=== Instancing (must be instancedMesh or <Instances>, not N meshes) ==="
    grep -n "instancedMesh\|<Instances" src/simulation/DroneFleet.tsx src/simulation/LivingPopulation3D.tsx src/simulation/City.tsx || echo "(NONE)"
    echo "=== No setState inside useFrame ==="
    grep -n "useFrame" -A8 src/simulation/*.tsx | grep -E "set[A-Z][a-zA-Z]*\(" || echo "CLEAN"
    echo "=== Camera damping ==="
    grep -R "damp3\|maath/easing" src/simulation/CameraController.tsx || echo "(NONE)"
    echo "=== DemoDirector guard ==="
    grep -n "demo\|import.meta.env.DEV" src/apps/DemoDirector.tsx | head -20 || echo "(NONE)"
    echo "=== Disaster / Intro visual files present? ==="
    ls -la src/simulation/DisasterFootprint.tsx src/simulation/IntroCameraRig.tsx || echo "(MISSING)"
  )
  echo '```'
  echo ""
  echo "## Test suite baseline"
  echo '```text'
  (
    cd "${ROOT_DIR}/backend"
    python3 -m unittest discover -s tests -p "test_global_platform.py" -v 2>&1 || true
    python3 -m unittest discover -s tests -p "test_v2_structured_and_tools.py" -v 2>&1 || true
    python3 -m unittest discover -s tests -p "test_tool_schema.py" -v 2>&1 || true
  )
  echo '```'
} > "${REPORT}"

echo "Wrote ${REPORT}"
