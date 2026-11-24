# Quantum Rescue — Dependency Audit & Deep Bug Hunt Report (`v32`)

## 1. Dependency Audit Summary

### Backend (`backend/requirements.txt` & `backend/requirements-dev.txt`)
- **Removed unused dependency**: Dropped `networkx>=3.3` (0 imports across `backend/app/` and `backend/tests/`).
- **Fixed Pydantic v1/v2 compatibility pin**: Updated `pydantic>=2.9.0` → `pydantic>=1.10.0,<3.0.0` (matching `app/core/compat.py` and `_PYDANTIC_V2` in `tool_args.py`) and aligned `fastapi>=0.92.0`, `uvicorn[standard]>=0.17.6`, `websockets>=11.0`, `httpx>=0.23.0`.
- **Test dependencies**: Added `jsonschema>=4.17.0` (`requirements.txt` & `requirements-dev.txt`) alongside `pytest`, `pytest-asyncio`, `ruff`.
- **Zero forbidden dependencies**: Confirmed 0 SQL/ORM (`sqlite3`, `sqlalchemy`, `psycopg`, `redis`), 0 `qiskit`, and 0 Docker files.

### Frontend (`frontend/package.json`)
- Verified all 11 bare package imports across 64 `.ts`/`.tsx` files (`react`, `react-dom`, `three`, `@react-three/fiber`, `@react-three/drei`, `@react-three/postprocessing`, `postprocessing`, `framer-motion`, `lucide-react`, `recharts`, `zustand`) match compatible declared versions (React 18 / R3F v8 / Drei v9 / Postprocessing v2 / Three 0.169 / Zustand 5).
- Verified all 3 Vite configs (`vite.scene.config.ts`, `vite.control.config.ts`, `vite.jarvis.config.ts`) and expanded `frontend/src/vite-env.d.ts` `__APP_MODE__` to include `"operations"` and `"jarvis"`.

---

## 2. Bugs Found & Fixed

### Backend Core, Simulation, Navigation, Optimization & Storage
- **`backend/app/main.py`**: Prevented silent death of `simulation_loop()` and `global_simulation_loop()` on transient exceptions; cancelled and awaited `global_tick_task` and closed active WebSockets on lifespan shutdown; moved WebSocket/frontend-counter cleanup into `finally:` blocks; fixed `CORSMiddleware` `allow_credentials=False` with wildcard origins.
- **`backend/app/world/global_engine.py` & `global_models.py`**: Guarded `haversine_km()` against floating-point domain/NaN errors; clamped `local_to_geo()` coordinates; sanitized non-finite `dt_seconds`/disaster inputs; fixed drone battery floor so depleted drones don't recharge; reset ambulance `destination_hospital_id` on return to `AVAILABLE`; fixed shelter over-routing and `FULL` status; bounded `decision_memory` (500), `counterfactual_runs` (100), and `failure_history` (100); fixed zero-ambulance `eff_amb` calculation.
- **`backend/app/navigation/route_explorer.py` & `pathfinder.py`**: Fixed `IndexError` in Yen's K-shortest (`len(p) > i + 1`); bounded `route_logs` (`max_logs=500`); guarded empty/disconnected graphs and `grid_n >= 1`; added A* `closed` set to skip stale heap pops.
- **`backend/app/optimization/*`**: Made CP-SAT deterministic (`num_search_workers=1`, `random_seed=42`); guarded 0-qubit and `math.exp` overflow/NaN in `quantum_solver.py`; clamped normalized objective/score ratios to `[0.0, 1.0]`; deduplicated task IDs in `route_sequencer.py`.
- **`backend/app/database/repository.py` & `exports/global_export.py`**: Blocked path traversal in `save_local_world_snapshot` and `_exp_path`; implemented atomic JSON writes (`fsync` + `os.replace`); handled corrupted JSON files without crashing; fixed `deque` JSON serialization and HTML-escaped report fields in `global_export.py`.
- **`backend/app/events/bus.py` & `auth/rbac.py`**: Evicted oldest `event_id` from `_seen_ids` on deque rollover; fixed `limit <= 0` slicing; capped active auth tokens (`MAX_ACTIVE_TOKENS = 1000`).

### AI Pipeline, Providers, Approvals & API Routes
- **`backend/app/providers/ai_providers.py` & `backend/app/ai/jarvis_agent.py`**: Enabled intra-provider key rotation across all healthy keys in the 6-key pool before provider failover; reset `error_count = 0` in `enable_key`; hardened Gemini/Grok adapters against malformed JSON and empty `candidates`/`choices`; safely serialized non-string `grounded_context`; kept Gemini keys out of URL query strings and redacted provider errors; removed redundant tool declarations from narrative polishing because tools already execute in the grounded orchestrator and Gemini rejects unsupported schema fields.
- **`backend/app/ai/jarvis_agent.py` & `frontend/src/apps/JarvisCommandApp.tsx`**: Added visible pending and error replies, bounded client/provider waits, per-intent exception containment, help responses, and natural numeric ambulance/swarm phrasing so commands no longer fail silently.
- **`backend/app/approvals/engine.py`**: Blocked post-execution/post-rejection `reject()` mutations and duplicate `approve_and_execute` calls; added `EXECUTING` re-entrancy guard and explicit `bump_version=True` on `operation.executed`; validated IDs and enums before mutating world state.
- **`backend/app/ai/jarvis_agent.py`**: Handled empty/whitespace messages cleanly (`IDLE` reply) and clamped oversized messages (`MAX_MESSAGE_LENGTH = 4000`); guarded `use_llm_polish=True` failures; capped active sessions (`MAX_SESSIONS = 500`) and pruned orphaned conversations; sanitized `filename` in `_save_world_local`.
- **`backend/app/api/global_routes.py` & `structured_api.py`**: Converted unhandled `KeyError`/`ValueError` 500s across 15+ endpoints into clean HTTP 400/404/422 responses; emitted `world.mode_changed` so `/api/v2/*` caches invalidate on mode switch; hardened `/api/ai/chat/stream` SSE error frames; fixed `deque` slicing on `/api/routes/logs`; bounded `VersionedResponseCache` (`max_entries=512`) and `/api/v2/search` query length (200 chars).

### Frontend Runtime, Memory Leaks & 3D Stability
- **WebSockets (`client.ts`, `globalApi.ts`)**: Added `closed` mount guard, `clearTimeout` cleanup, `onerror` socket close, and capped exponential reconnect backoff (`1s → 15s`).
- **Voice/Mic & API Error Handling (`JarvisCommandApp.tsx`, `OperationsCommandApp.tsx`, `WorldCommandApp.tsx`, `Unified3DTerrainWorld.tsx`)**: Added `AbortController` cleanup and `res.ok` checks on all `fetch` calls (including HTTP 422 tool errors); fixed late `getUserMedia` `MediaStream`/`AudioContext`/`SpeechRecognition` leaks and stale `voiceMode` closure.
- **3D & GPU Disposal (`DroneFleet.tsx`, `CameraController.tsx`, `JarvisNeuralCore3D.tsx`, `GeospatialGlobe3D.tsx`, `SkyAtmosphere.tsx`, `City.tsx`, `Unified3DTerrainWorld.tsx`)**: Fixed negative heading modulo wrap (`Math.atan2`), added `Number.isFinite` guards on drone/camera/audio math, fixed topdown WASD zero-vector panning, guarded `instanceMatrix` updates, and added `useEffect` disposal for dynamically created textures, geometries, and `ShaderMaterial`s.

---

## 3. Verification Summary
- **`./scripts/verify_all.sh`**: `ALL CHECKS PASSED`
- **Backend tests**: **87/87 passing**, including the original regression suite plus approval concurrency, reset safety, provider secret redaction, invalid-target rejection, routing-bound tests, LLM-polish payload/timeout tests, and visible command-error fallbacks.
- **Frontend static audit**: 67 `.ts`/`.tsx` files — TypeScript and all three production builds pass; 0 known npm audit vulnerabilities; 0 broken relative imports or missing npm packages.
