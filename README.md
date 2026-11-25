# QUANTUM RESCUE V2 — Autonomous Disaster Response Digital Twin

**Zero Database · Zero Docker · Plain JSON Persistence · Genuine Model-Native AI Function Calling**

## Architecture (5 Local Services)

| Service | Address | Responsibility |
| :--- | :--- | :--- |
| **1. Simulation Backend** | `http://127.0.0.1:8000` | Authoritative 4×4 km metropolitan digital twin, disaster lifecycle engine (flood, earthquake, fire, cyclone, collapse, landslide), simulated survivor model, 3D A* pathfinding, Greedy/OR-Tools/QAOA/Hybrid solvers, atomic JSON persistence, WebSocket sync |
| **2. 3D Visual Environment** | `http://localhost:5173` | Real-time Three.js metropolitan rendering, instanced disaster & survivor visuals, 6 camera modes (`orbit`, `topdown`, `follow`, `fpv`, `free`, `disaster_focus`) |
| **3. Mission Control Panel** | `http://localhost:5174` | Disaster Simulation Studio, 4-strategy live benchmark arena, fleet avionics, QAOA charts, JSON experiment archive & replay |
| **4. AI Agent Backend** | `http://127.0.0.1:8001` | Independent AI orchestration service with 3-key Grok + 3-key Gemini round-robin rotation, `AUTO` failover, 112 allowlisted validated tools, `OBSERVE`/`ASSISTED`/`AUTONOMOUS` modes, WebSocket world observer, JSON execution traces |
| **5. AI Rescue Command Console** | `http://localhost:5175` | Emergency operations console with live world telemetry, real-time tool execution cards, operator approval cards, voice command input (Web Speech API), and 6-key provider health monitor |

## Local Persistence (`runtime_data/`)

No SQLite, SQLAlchemy, Redis, or database server is used anywhere. All configuration, world snapshots, experiment history/replays, event journals (`.jsonl`), conversation sessions, and execution traces are stored as atomic local JSON files inside `runtime_data/`.

## Setup & One-Click Launch

1. Configure your API keys in `agent_backend/.env` (copy from `agent_backend/.env.example`):
   - `GROK_API_KEY_1`, `GROK_API_KEY_2`, `GROK_API_KEY_3` (optional)
   - `GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`, `GEMINI_API_KEY_3` (optional)
2. Launch all 5 services locally:
   - **Windows**: Double-click `start.bat` (or run `start.bat` in PowerShell/CMD)
   - **macOS / Linux**: `chmod +x start.sh && ./start.sh`

## Running the Test Suites

```bash
# Backend + JSON Storage + Disaster Simulation + E2E Tests
cd backend && python -m unittest discover -s tests -v

# AI Agent (6-Key Rotation, Grok/Gemini Native Function Calling, Permissions, Interruption, Memory)
cd agent_backend && python -m unittest discover -s tests -v
```
