# QUANTUM RESCUE — Global Autonomous Disaster Intelligence & Command System

**Quantum Rescue** is a zero-database, seven-country disaster-response digital twin operated through **three independent frontend command centres** sharing **one authoritative Python FastAPI simulation backend** and one fast tool-calling AI agent (**JARVIS**).

---

## 1. Architecture at a Glance (For Developers & AI Coding Agents)

| Service | Localhost URL | Entry Point / Command | Role |
| :--- | :--- | :--- | :--- |
| **Shared Backend** | `http://127.0.0.1:8000` (`http://127.0.0.1:8000/docs`) | `cd backend && uvicorn app.main:app --reload --port 8000` | Authoritative 7-country world, continuous flood hydrology & wind-driven fire spread, 98 global drones, Yen's K-shortest route explorer, fast Quantum-Inspired QUBO Demo Optimizer, RBAC, Event Bus + Frontend Command Bus, 50-tool JARVIS orchestrator, Approval Engine, local JSON storage (`backend/local_data/`), and ZIP/GeoJSON exports |
| **01 — World Command** | `http://localhost:5173` | `cd frontend && npm run dev:world` | 10×10 km continuous 7-country GTA-style flat open-world map (plus optional Orbital Globe view) with instanced skyscrapers, highways, 160 vehicles, 240 pedestrians, banking quadcopter drones, hospitals, shelters, disasters, and JARVIS camera sync |
| **02 — Operations Command** | `http://localhost:5174` | `cd frontend && npm run dev:operations` | Aerospace/GIS Global Control Room: 7-country matrix, Country Editor, Disaster & Cascade Control, Ambulance & Supply Calculators, Fleet/Swarm/Routes, Counterfactuals, Mutual Aid, Rescue Equity, Approvals, E-Stop, and 4-Solver Benchmark Arena |
| **03 — JARVIS Intelligence** | `http://localhost:5175` | `cd frontend && npm run dev:jarvis` | Universal Command Console with WebGL 3D Geospatial Globe, 1-click Direct AI Tool Runner (all 50 tools), Voice Push-to-Talk + Barge-In, 6-Key Gemini/Grok Provider Health HUD, inline Route/Disaster/Plan cards, Approval Cards, and Live Execution Trace |

### Key Engineering Invariants (For AI Agents Modifying This Codebase)
1. **Zero External Databases:** Do **not** add SQLite, PostgreSQL, SQLAlchemy, or Redis. All world snapshots and experiment runs are generated at runtime and persisted as plain JSON under `backend/local_data/` via `backend/app/database/repository.py`.
2. **Fast Quantum-Inspired Demo Only:** Do **not** re-add heavy `qiskit` / `qiskit-aer` dependencies. `backend/app/optimization/quantum_solver.py` runs a sub-10 ms Quantum-Inspired QUBO Demo Optimizer with classical constraint validation.
3. **Single Authoritative State:** All three frontends synchronize via `/ws/global` and `/ws/simulation` from `backend/app/main.py`. Never duplicate simulation state inside a frontend.
4. **Approval-Gated State Changes:** Every consequential JARVIS action (`prepare_*` tools) creates a `PENDING` approval in `backend/app/approvals/engine.py` and executes only after explicit operator approval (`POST /api/approvals/{id}/approve`).
5. **Pydantic v1 & v2 Compatibility:** `backend/app/core/compat.py` is imported by `backend/app/core/models.py` so the backend runs cleanly on both Pydantic v1 and v2.

---

## 2. Prerequisites

- **Python** 3.11+
- **Node.js** 18+ and **npm** 9+

---

## 3. How to Run Locally

### Option A — One-Click Launch (All 4 Servers)
- **Linux / macOS:**
  ```bash
  chmod +x start.sh
  ./start.sh
  ```
- **Windows:** Double-click `start.bat` (or run `start.bat` in Command Prompt).

### Option B — Manual Step-by-Step Launch (Recommended for AI Agents & Debugging)

1. **Start the Shared FastAPI Backend (`:8000`):**
   ```bash
   cd backend
   python3 -m venv .venv
   # Linux/macOS:
   source .venv/bin/activate
   # Windows:
   # .venv\Scripts\activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Install Frontend Dependencies (once):**
   ```bash
   cd frontend
   npm install
   ```

3. **Start the Three Independent Frontend Servers (in 3 separate terminals):**
   ```bash
   # Terminal 1 — 01 World Command (http://localhost:5173)
   cd frontend && npm run dev:world

   # Terminal 2 — 02 Operations Command (http://localhost:5174)
   cd frontend && npm run dev:operations

   # Terminal 3 — 03 JARVIS Intelligence (http://localhost:5175)
   cd frontend && npm run dev:jarvis
   ```

### Optional — Configure Gemini & Grok Keys (6-Key Pool)
Copy `backend/.env.example` to `backend/.env` and set `GEMINI_API_KEY_1..3` / `GEMINI_MODEL` and/or `GROK_API_KEY_1..3` / `GROK_MODEL`. Keys stay strictly server-side. Without API keys, JARVIS responds in **<5 ms** using its grounded deterministic tool orchestrator.

---

## 60-Second Demo Script

1. **Open JARVIS Intelligence** at `http://localhost:5175`.
2. **Send a compound Veridia cyclone/swarm/mutual-aid command** (for example: trigger/assess a severe cyclone in Veridia Basin, prepare an autonomous search drone swarm, and propose cross-border mutual aid).
3. **Click `Approve & Execute`** on the generated operator authorization card(s) to commit the planned operations to the authoritative simulation backend.
4. **Switch to World Command** at `http://localhost:5173` to watch the live disaster footprint, deployed swarm, and **recovery arcs** animate across the 3D open world.
5. **Open Operations Command** at `http://localhost:5174` and inspect the **Run comparison** (4-World Counterfactual Digital Twin & 4-Solver Benchmark comparison).

---

## 4. Automated Verification Commands (For CI & AI Agents)

Run the full backend verification suite (20 tests + all 50 JARVIS direct tool calls; verify the live registry count with `python3 backend/scripts/report_tool_count.py`):
```bash
python3 backend/scripts/report_tool_count.py
cd backend
python3 -m unittest discover -s tests -p "test_global_platform.py" -v
pytest tests/test_quantum_rescue.py tests/test_advanced_modules.py -v
```

Verify frontend TypeScript compilation and production bundles:
```bash
cd frontend
npm run build
npm run build:operations
npm run build:jarvis
```

---

## 5. Key API Endpoints Quick Reference

- **World & Live Entities:** `GET /api/world/overview`, `GET /api/world/live-entities/{country_id}`, `POST /api/world/tick`, `POST /api/world/save-local`, `POST /api/world/emergency-stop`
- **Countries & Disasters:** `GET /api/countries`, `GET /api/countries/{id}`, `PATCH /api/countries/{id}`, `POST /api/disasters`, `GET /api/disasters/cascade/{country_id}`
- **Routing & Swarms:** `POST /api/routes/explore`, `POST /api/routes/multistop`, `POST /api/swarms/prepare`, `GET /api/global/drones`
- **JARVIS AI & Tools:** `POST /api/ai/chat`, `POST /api/ai/chat/stream`, `GET /api/ai/tools`, `POST /api/ai/tools/{tool_name}`, `GET /api/ai/providers/status`
- **Approvals & Exports:** `GET /api/approvals`, `POST /api/approvals/{id}/approve`, `POST /api/approvals/{id}/reject`, `GET /api/global/export/geojson`, `GET /api/global/export/zip`
